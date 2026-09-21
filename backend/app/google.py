"""Thin async client for Google OAuth + Gmail/Drive REST.

Uses raw REST via httpx rather than google-api-python-client so the
request surface stays small and readable.
"""
import asyncio
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


async def exchange_code(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
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

    async def estimate_count(self, query: str) -> dict[str, Any]:
        """Cheap count: Gmail's resultSizeEstimate is rough but instant."""
        data = (
            await self._request("GET", f"{GMAIL}/messages", params={"q": query, "maxResults": 1})
        ).json()
        return {"estimate": data.get("resultSizeEstimate", 0)}

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

    async def delete_forever(self, ids: list[str]) -> int:
        """Permanently delete. Irreversible. Frontend must hard-confirm."""
        for chunk in _chunks(ids, BATCH_MODIFY_MAX):
            await self._request("POST", f"{GMAIL}/messages/batchDelete", json={"ids": chunk})
        return len(ids)


def _chunks(xs: list[str], n: int):
    for i in range(0, len(xs), n):
        yield xs[i : i + n]
