"""Thin async client for Google OAuth + Gmail/Drive REST.

Uses raw REST via httpx rather than google-api-python-client so the
request surface stays small and readable.
"""
import asyncio
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException

from .config import settings
from .session import Session

TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
DRIVE_ABOUT = "https://www.googleapis.com/drive/v3/about"
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

BATCH_MODIFY_MAX = 1000  # Gmail hard limit per batchModify / batchDelete call
COUNT_MAX_PAGES = 100  # 100 pages x 500 ids = 50,000; past that the UI shows "50,000+"
SIZE_SAMPLE = 100  # messages whose size we fetch to estimate the storage a query holds


async def exchange_code(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if r.status_code != 200:
        raise HTTPException(400, f"Token exchange failed: {r.text}")
    return r.json()


async def refresh_access_token(refresh_token: str) -> str:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token",
            },
        )
    if r.status_code != 200:
        raise HTTPException(401, "Session expired — sign in again")
    return r.json()["access_token"]


async def get_email(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(USERINFO, headers={"Authorization": f"Bearer {access_token}"})
    r.raise_for_status()
    return r.json().get("email", "")


class Gmail:
    """One instance per request. Refreshes the token on 401 and flags it
    so the router can rewrite the cookie."""

    def __init__(self, session: Session):
        self.session = session
        self.token_refreshed = False
        self._client = httpx.AsyncClient(timeout=30)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.session.access_token}"}

    async def _request(self, method: str, url: str, **kw) -> httpx.Response:
        r = await self._client.request(method, url, headers=self._headers, **kw)
        if r.status_code == 401 and self.session.refresh_token and not self.token_refreshed:
            self.session.access_token = await refresh_access_token(self.session.refresh_token)
            self.token_refreshed = True
            r = await self._client.request(method, url, headers=self._headers, **kw)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, f"Google API error: {r.text[:300]}")
        return r

    # ---- reads -------------------------------------------------------------

    async def profile(self) -> dict[str, Any]:
        return (await self._request("GET", f"{GMAIL}/profile")).json()

    async def storage_quota(self) -> dict[str, int] | None:
        try:
            r = await self._request("GET", DRIVE_ABOUT, params={"fields": "storageQuota"})
        except HTTPException:
            return None  # scope not granted — gauge falls back to counts
        q = r.json().get("storageQuota", {})
        return {k: int(v) for k, v in q.items() if v is not None}

    async def list_message_ids(self, query: str, limit: int | None = None) -> list[str]:
        """All message ids matching a Gmail search query (paginated, 500/page)."""
        ids: list[str] = []
        token: str | None = None
        while True:
            params: dict[str, Any] = {"q": query, "maxResults": 500}
            if token:
                params["pageToken"] = token
            data = (await self._request("GET", f"{GMAIL}/messages", params=params)).json()
            ids.extend(m["id"] for m in data.get("messages", []))
            token = data.get("nextPageToken")
            if not token or (limit and len(ids) >= limit):
                break
        return ids[:limit] if limit else ids

    async def count(self, query: str, max_pages: int = COUNT_MAX_PAGES) -> dict[str, Any]:
        """Final result of count_stream(); kept for callers that do not stream."""
        last: dict[str, Any] = {"count": 0, "capped": False, "done": True}
        async for last in self.count_stream(query, max_pages):
            pass
        return last

    async def count_stream(
        self, query: str, max_pages: int = COUNT_MAX_PAGES, sample: int = SIZE_SAMPLE
    ) -> AsyncIterator[dict[str, Any]]:
        """Exact count by paging ids, 500 per call, the same walk trash() does.
        Gmail's resultSizeEstimate saturates around 200, so it is useless for
        a big mailbox. Yields a progress line per page, then a final line with
        done=True, capped, and avg_bytes from a sample of evenly spaced
        messages (Gmail only reports size per message, so exact is 50k calls)."""
        ids: list[str] = []
        token: str | None = None
        capped = True
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "q": query, "maxResults": 500, "fields": "nextPageToken,messages/id",
            }
            if token:
                params["pageToken"] = token
            data = (await self._request("GET", f"{GMAIL}/messages", params=params)).json()
            ids.extend(m["id"] for m in data.get("messages", []))
            token = data.get("nextPageToken")
            if not token:
                capped = False
                break
            yield {"count": len(ids), "capped": False, "done": False}

        summary = await self.sample_summary(_spread(ids, sample)) if ids else _EMPTY_SUMMARY
        yield {"count": len(ids), "capped": capped, "done": True, **summary}

    async def sample_summary(self, ids: list[str], concurrency: int = 8) -> dict[str, Any]:
        """One metadata get per sampled id (5 quota units each against a
        250/sec per-user limit, so ~10 in flight). Returns avg_bytes plus a
        preview: who sent the sample, its date range, a few subjects."""
        if not ids:
            return dict(_EMPTY_SUMMARY)
        sem = asyncio.Semaphore(concurrency)

        async def one(i: str) -> dict[str, Any] | None:
            async with sem:
                try:
                    r = await self._request(
                        "GET", f"{GMAIL}/messages/{i}",
                        params=[
                            ("format", "metadata"),
                            ("metadataHeaders", "From"),
                            ("metadataHeaders", "Subject"),
                            ("fields", "sizeEstimate,internalDate,payload/headers"),
                        ],
                    )
                except HTTPException:
                    return None  # rate-limited or gone; the sample survives without it
                return r.json()

        msgs = [m for m in await asyncio.gather(*(one(i) for i in ids)) if m]
        if not msgs:
            return dict(_EMPTY_SUMMARY)

        sizes, dates, senders, subjects = [], [], Counter(), []
        names: dict[str, str] = {}
        for m in msgs:
            sizes.append(int(m.get("sizeEstimate", 0)))
            if m.get("internalDate"):
                dates.append(int(m["internalDate"]) // 1000)
            h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
            addr, name = parse_from(h.get("from", ""))
            if addr:
                senders[addr] += 1
                names.setdefault(addr, name)
            if len(subjects) < 6 and h.get("subject"):
                subjects.append(h["subject"][:100])

        def iso(ts: int) -> str:
            return datetime.fromtimestamp(ts, UTC).date().isoformat()

        return {
            "avg_bytes": sum(sizes) // len(sizes),
            "preview": {
                "sampled": len(msgs),
                "oldest": iso(min(dates)) if dates else None,
                "newest": iso(max(dates)) if dates else None,
                "senders": [
                    {"address": a, "name": names.get(a, ""), "sampled": n}
                    for a, n in senders.most_common(8)
                ],
                "subjects": subjects,
            },
        }

    async def message_metadata(self, msg_id: str, headers: list[str]) -> dict[str, Any]:
        params = [("format", "metadata")] + [("metadataHeaders", h) for h in headers]
        return (await self._request("GET", f"{GMAIL}/messages/{msg_id}", params=params)).json()

    async def metadata_many(
        self, ids: list[str], headers: list[str], concurrency: int = 20
    ) -> list[dict[str, Any]]:
        sem = asyncio.Semaphore(concurrency)

        async def one(i: str):
            async with sem:
                return await self.message_metadata(i, headers)

        return await asyncio.gather(*(one(i) for i in ids))

    # ---- writes ------------------------------------------------------------

    async def trash(self, ids: list[str]) -> int:
        """Move messages to Trash, 1,000 per API call."""
        for chunk in _chunks(ids, BATCH_MODIFY_MAX):
            await self._request(
                "POST",
                f"{GMAIL}/messages/batchModify",
                json={"ids": chunk, "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX", "UNREAD"]},
            )
        return len(ids)

    async def untrash(self, ids: list[str]) -> int:
        """Undo trash(): drop the TRASH label so messages return to All Mail.
        INBOX is not re-added; mail that was archived before stays archived."""
        for chunk in _chunks(ids, BATCH_MODIFY_MAX):
            await self._request(
                "POST",
                f"{GMAIL}/messages/batchModify",
                json={"ids": chunk, "removeLabelIds": ["TRASH"]},
            )
        return len(ids)

    async def delete_forever(self, ids: list[str]) -> int:
        """Permanently delete. Irreversible. Frontend must hard-confirm."""
        for chunk in _chunks(ids, BATCH_MODIFY_MAX):
            await self._request("POST", f"{GMAIL}/messages/batchDelete", json={"ids": chunk})
        return len(ids)


_EMPTY_SUMMARY: dict[str, Any] = {"avg_bytes": 0, "preview": None}


def parse_from(raw: str) -> tuple[str, str]:
    """'Orvis <News@Orvis.com>' -> ('news@orvis.com', 'Orvis')"""
    if "<" in raw and ">" in raw:
        addr = raw[raw.index("<") + 1 : raw.index(">")].strip().lower()
        return addr, raw[: raw.index("<")].strip().strip('"')
    return raw.strip().lower(), ""


def _spread(xs: list[str], n: int) -> list[str]:
    """Up to n items evenly spaced across xs, so a sample covers old and new alike."""
    if len(xs) <= n:
        return list(xs)
    step = len(xs) / n
    return [xs[int(i * step)] for i in range(n)]


def _chunks(xs: list[str], n: int):
    for i in range(0, len(xs), n):
        yield xs[i : i + n]
