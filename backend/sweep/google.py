"""Thin async client for Google OAuth + Gmail/Drive REST.

Uses raw REST via httpx rather than google-api-python-client so the
request surface stays small and readable.
"""
import asyncio
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException

from .config import settings
from .session import Session

log = logging.getLogger("sweep")

TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
DRIVE_ABOUT = "https://www.googleapis.com/drive/v3/about"
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

BATCH_MODIFY_MAX = 1000  # Gmail hard limit per batchModify / batchDelete call
COUNT_MAX_PAGES = 100  # 100 pages x 500 ids = 50,000; past that the UI shows "50,000+"
SIZE_SAMPLE = 100  # messages whose size we fetch to estimate the storage a query holds
RETRIES = 4
TOO_FAST = "Too much commotion, too fast. Wait a few seconds and try again."
NEEDS_RECONSENT = (
    "Sweep needs a permission this sign-in did not grant. Sign out, sign back in, and allow "
    "everything on Google's consent screen."
)
RETRY_STATUSES = {429, 500, 502, 503, 504}

# Gmail allows 250 quota units per second per user as a moving average.
# Concurrency alone does not bound the rate: eight fast calls at a time is
# still hundreds per second. Every call takes its units from this bucket
# first, so a 1,000-message header read paces itself instead of getting
# half its calls refused. One process serves one user, so one bucket.
UNITS_PER_SECOND = 200
UNITS_BURST = 250
COST_GET = 5  # messages.get, messages.list
COST_BATCH = 50  # batchModify, batchDelete


class _Pacer:
    """Token bucket. take(cost) waits until cost units are available."""

    def __init__(self, rate: float, burst: float):
        self.rate, self.burst = rate, burst
        self.tokens = burst
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()

    async def take(self, cost: float) -> None:
        async with self.lock:  # waiters queue in order; the lock is held while sleeping
            while True:
                now = time.monotonic()
                self.tokens = min(self.burst, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= cost:
                    self.tokens -= cost
                    return
                await asyncio.sleep((cost - self.tokens) / self.rate)


pacer = _Pacer(UNITS_PER_SECOND, UNITS_BURST)


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

    async def _request(self, method: str, url: str, cost: int = COST_GET, **kw) -> httpx.Response:
        """One Gmail call, paced by quota cost. Refreshes the token once on
        401 and backs off on 429 / 5xx the way Google asks (0.5s, 1s, 2s,
        4s) before giving up."""

        async def call() -> httpx.Response:
            await pacer.take(cost)
            return await self._client.request(method, url, headers=self._headers, **kw)

        r = await call()
        if r.status_code == 401 and self.session.refresh_token and not self.token_refreshed:
            self.session.access_token = await refresh_access_token(self.session.refresh_token)
            self.token_refreshed = True
            r = await call()
        for attempt in range(RETRIES):
            if r.status_code not in RETRY_STATUSES and not _throttled_200(r) and not _quota_403(r):
                break
            await asyncio.sleep(0.5 * 2**attempt)
            r = await call()
        self.last = r  # kept so a failure can be reported with its context
        if r.status_code == 429 or (r.status_code == 403 and "rateLimit" in r.text):
            log.debug("gmail refused %s %s: %s", method, url.rsplit("/", 1)[-1], r.text[:300])
            raise HTTPException(429, TOO_FAST)
        if _throttled_200(r):  # still empty after backoff: it is a rate limit in disguise
            raise HTTPException(429, TOO_FAST)
        if r.status_code == 403 and "insufficientPermissions" in r.text:
            raise HTTPException(403, NEEDS_RECONSENT)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, f"Google API error: {r.text[:300]}")
        return r

    async def _json(self, method: str, url: str, **kw) -> dict[str, Any]:
        """_request + decode. Gmail answers 204 No Content, not {}, when a
        fields mask selects nothing, i.e. a search with zero matches."""
        r = await self._request(method, url, **kw)
        if r.status_code == 204 or not r.content.strip():
            return {}
        return r.json()

    def describe_last(self) -> str:
        """Status, headers, and body head of the most recent response, for logs."""
        r = getattr(self, "last", None)
        if r is None:
            return "no response recorded"
        keep = ("content-type", "content-length", "content-encoding", "transfer-encoding", "server")
        hdrs = {k: v for k, v in r.headers.items() if k.lower() in keep}
        return (
            f"{r.request.method} {r.request.url.path}?{r.request.url.query.decode()[:200]} -> "
            f"{r.status_code} {hdrs} body[:200]={r.content[:200]!r}"
        )

    # ---- reads -------------------------------------------------------------

    async def profile(self) -> dict[str, Any]:
        return (await self._request("GET", f"{GMAIL}/profile", cost=1)).json()

    async def storage_quota(self) -> dict[str, int] | None:
        try:
            r = await self._request("GET", DRIVE_ABOUT, cost=1, params={"fields": "storageQuota"})
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
            data = await self._json("GET", f"{GMAIL}/messages", params=params)
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
            data = await self._json("GET", f"{GMAIL}/messages", params=params)
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
                    return None  # rate-limited past retries, or gone; the sample survives
                try:
                    return r.json()
                except ValueError:
                    return None  # 200 with an empty or non-JSON body: same treatment

        msgs = [m for m in await asyncio.gather(*(one(i) for i in ids)) if m]
        if not msgs:
            return dict(_EMPTY_SUMMARY)

        sizes, dates, senders, subjects = [], [], Counter(), []
        names: dict[str, str] = {}
        skipped = 0
        for m in msgs:
            try:
                size = int(m.get("sizeEstimate") or 0)
                ts = int(m.get("internalDate") or 0) // 1000
                h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
            except (TypeError, ValueError, KeyError):
                skipped += 1  # one odd message must not sink the whole sample
                continue
            sizes.append(size)
            if 0 < ts < 4_102_444_800:  # sane: after 1970, before 2100
                dates.append(ts)
            addr, name = parse_from(str(h.get("from", "")))
            if addr:
                senders[addr] += 1
                names.setdefault(addr, name)
            if len(subjects) < 6 and h.get("subject"):
                subjects.append(str(h["subject"])[:100])
        if skipped:
            log.warning("sample: skipped %d message(s) with unparseable metadata", skipped)
        if not sizes:
            return dict(_EMPTY_SUMMARY)

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
        self, ids: list[str], headers: list[str], concurrency: int = 8
    ) -> list[dict[str, Any]]:
        """Headers for many messages. Each get is 5 quota units against
        250/sec per user, so eight in flight is the most Gmail sustains
        without 429s. A message that still fails after the retries is
        dropped rather than sinking the whole scan; the count is logged."""
        sem = asyncio.Semaphore(concurrency)

        async def one(i: str) -> dict[str, Any] | None:
            async with sem:
                try:
                    return await self.message_metadata(i, headers)
                except (HTTPException, ValueError):
                    return None

        results = await asyncio.gather(*(one(i) for i in ids))
        msgs = [m for m in results if m]
        if len(msgs) < len(ids):
            log.warning(
                "metadata: %d of %d messages skipped; last refusal: %s",
                len(ids) - len(msgs), len(ids), self.describe_last(),
            )
        return msgs

    # ---- writes ------------------------------------------------------------

    # Each batchModify / batchDelete costs 50 quota units against 250/sec per
    # user, so three in flight is the most Gmail will sustain without 429s.
    BATCH_CONCURRENCY = 3
    TRASH_BODY = {"addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX", "UNREAD"]}
    UNTRASH_BODY = {"removeLabelIds": ["TRASH"]}

    async def _batch_stream(
        self, ids: list[str], endpoint: str, body: dict[str, Any]
    ) -> AsyncIterator[int]:
        """Apply one batch endpoint to ids, 1,000 per call, a few calls at a
        time. Yields the running total after each window completes."""
        chunks = list(_chunks(ids, BATCH_MODIFY_MAX))
        done = 0
        for i in range(0, len(chunks), self.BATCH_CONCURRENCY):
            window = chunks[i : i + self.BATCH_CONCURRENCY]
            await asyncio.gather(
                *(self._request(
                    "POST", f"{GMAIL}/messages/{endpoint}", cost=COST_BATCH, json={"ids": c, **body},
                ) for c in window)
            )
            done += sum(len(c) for c in window)
            yield done

    async def trash_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """List every id for query, then trash them. Progress lines for both
        phases, then a final line carrying the ids so the browser can undo."""
        ids: list[str] = []
        token: str | None = None
        while True:
            params: dict[str, Any] = {"q": query, "maxResults": 500, "fields": "nextPageToken,messages/id"}
            if token:
                params["pageToken"] = token
            data = await self._json("GET", f"{GMAIL}/messages", params=params)
            ids.extend(m["id"] for m in data.get("messages", []))
            token = data.get("nextPageToken")
            yield {"phase": "listing", "found": len(ids), "done": False}
            if not token:
                break
        async for n in self._batch_stream(ids, "batchModify", self.TRASH_BODY):
            yield {"phase": "trashing", "trashed": n, "total": len(ids), "done": False}
        yield {"phase": "done", "trashed": len(ids), "total": len(ids), "ids": ids, "done": True}

    async def untrash_stream(self, ids: list[str]) -> AsyncIterator[dict[str, Any]]:
        """Undo trash(): drop the TRASH label so messages return to All Mail.
        INBOX is not re-added; mail that was archived before stays archived."""
        async for n in self._batch_stream(ids, "batchModify", self.UNTRASH_BODY):
            yield {"restored": n, "total": len(ids), "done": False}
        yield {"restored": len(ids), "total": len(ids), "done": True}

    async def delete_stream(self, ids: list[str]) -> AsyncIterator[dict[str, Any]]:
        """Permanently delete. Irreversible. Caller must hard-confirm."""
        async for n in self._batch_stream(ids, "batchDelete", {}):
            yield {"deleted": n, "total": len(ids), "done": False}
        yield {"deleted": len(ids), "total": len(ids), "done": True}

    async def trash(self, ids: list[str]) -> int:
        """Move messages to Trash, 1,000 per API call."""
        async for _ in self._batch_stream(ids, "batchModify", self.TRASH_BODY):
            pass
        return len(ids)

    async def untrash(self, ids: list[str]) -> int:
        async for _ in self._batch_stream(ids, "batchModify", self.UNTRASH_BODY):
            pass
        return len(ids)

    async def delete_forever(self, ids: list[str]) -> int:
        """Permanently delete everything in ids. Irreversible."""
        async for _ in self._batch_stream(ids, "batchDelete", {}):
            pass
        return len(ids)


def _quota_403(r: httpx.Response) -> bool:
    """Gmail reports the per-minute project quota ('Units per minute per
    user', 15,000 by default) as a 403 with reason rateLimitExceeded, not
    a 429. It clears within the minute, so it is worth the same backoff."""
    return r.status_code == 403 and "rateLimit" in r.text


def _throttled_200(r: httpx.Response) -> bool:
    """Under load Gmail sometimes answers 200 with no body at all. Every call
    we make expects JSON, so an empty 200 is a throttle, not a success.
    (204 is different: it is Gmail's legitimate 'nothing matched'.)"""
    return r.status_code == 200 and not r.content.strip()


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
