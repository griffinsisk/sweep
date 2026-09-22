"""Group a sample of the mailbox by sender so the user can see who is
actually filling it, then unsubscribe where the sender promised a way.
Only metadata headers are fetched — never bodies."""
import asyncio
import logging
import re
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..deps import gmail_client
from ..google import Gmail, parse_from  # noqa: F401  (re-exported for tests)
from .cleanup import stream_ndjson

log = logging.getLogger("sweep")

router = APIRouter(prefix="/api/senders", tags=["senders"])

_HTTP_RE = re.compile(r"<(https?://[^>]+)>")
_MAILTO_RE = re.compile(r"<(mailto:[^>]+)>", re.IGNORECASE)
TOTAL_PAGES = 20  # 20 pages x 500 = 10,000 per sender; past that the UI shows "10,000+"
TOTAL_CONCURRENCY = 5  # messages.list is 5 units against 250/sec; five in flight is gentle
UNSUB_TIMEOUT = 15
Method = Literal["one_click", "mailto", "manual"]
_RANK = {"one_click": 3, "mailto": 2, "manual": 1}


class Unsubscribe(BaseModel):
    """How this sender said to leave. one_click: RFC 8058, Sweep POSTs to
    url. mailto: Sweep sends one empty message, if the user opted in.
    manual: url is a page to open yourself."""

    method: Method
    url: str | None = None
    mailto: str | None = None


class Sender(BaseModel):
    address: str
    domain: str
    name: str
    sampled: int  # messages from this sender inside the sample
    total: int  # messages from this sender inside the scan scope (from:addr + query)
    capped: bool  # total stopped at TOTAL_PAGES pages
    estimated_bytes: int  # mean sampled size x total
    unsubscribe: Unsubscribe | None
    subjects: list[str]


def parse_unsubscribe(raw: str | None) -> str | None:
    """The https link from List-Unsubscribe, if any."""
    if not raw:
        return None
    m = _HTTP_RE.search(raw)
    return m.group(1) if m else None


def classify_unsubscribe(list_unsub: str | None, list_unsub_post: str | None) -> Unsubscribe | None:
    """Read the two RFC headers into one of three paths. One-click needs
    both the Post header (RFC 8058) and an https URL; a bare POST does it.
    Otherwise a mailto entry wins over a plain link, because Sweep can send
    a message but cannot fill in a web form."""
    if not list_unsub:
        return None
    url = parse_unsubscribe(list_unsub)
    m = _MAILTO_RE.search(list_unsub)
    mailto = m.group(1) if m else None
    one_click = bool(list_unsub_post) and "list-unsubscribe=one-click" in list_unsub_post.lower()
    if one_click and url and url.lower().startswith("https://"):
        return Unsubscribe(method="one_click", url=url, mailto=mailto)
    if mailto:
        return Unsubscribe(method="mailto", url=url, mailto=mailto)
    if url:
        return Unsubscribe(method="manual", url=url)
    return None


def _better(a: Unsubscribe | None, b: Unsubscribe | None) -> Unsubscribe | None:
    """Across a sender's messages, keep the path Sweep can do the most with."""
    if a is None or b is None:
        return a or b
    return a if _RANK[a.method] >= _RANK[b.method] else b


def scope_query(address: str, query: str) -> str:
    """The Gmail search that means 'this sender, inside the scan'. The table's
    total, Trash all, and the row all use this one string."""
    return f"from:{address} {query}".strip()


@router.get("", response_model=list[Sender])
async def top_senders(
    sample: int = Query(1000, ge=100, le=5000),
    query: str = Query("", description="Gmail query to scan inside; empty means all mail"),
    limit: int = Query(50, ge=5, le=200),
    gmail: Gmail = Depends(gmail_client),
):
    log.info("senders: scan scope=%r sample=%d", query or "all mail", sample)
    ids = await gmail.list_message_ids(query, limit=sample)
    log.info("senders: %d ids listed, reading headers", len(ids))
    msgs = await gmail.metadata_many(
        ids, ["From", "Subject", "List-Unsubscribe", "List-Unsubscribe-Post"]
    )

    buckets: dict[str, dict] = defaultdict(
        lambda: {"name": "", "count": 0, "bytes": 0, "unsub": None, "subjects": []}
    )
    for m in msgs:
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        address, name = parse_from(headers.get("from", ""))
        if not address:
            continue
        b = buckets[address]
        b["count"] += 1
        b["bytes"] += int(m.get("sizeEstimate", 0))
        b["name"] = b["name"] or name
        b["unsub"] = _better(
            b["unsub"],
            classify_unsubscribe(headers.get("list-unsubscribe"), headers.get("list-unsubscribe-post")),
        )
        if len(b["subjects"]) < 3 and headers.get("subject"):
            b["subjects"].append(headers["subject"][:120])

    top = sorted(buckets.items(), key=lambda kv: kv[1]["count"], reverse=True)[:limit]
    log.info("senders: %d distinct senders, counting totals for top %d", len(buckets), len(top))

    # The sample says who shows up; the real count says how much of them there is.
    sem = asyncio.Semaphore(TOTAL_CONCURRENCY)

    async def total(addr: str) -> tuple[int, bool]:
        async with sem:
            return await gmail.count_ids(scope_query(addr, query), max_pages=TOTAL_PAGES)

    totals = await asyncio.gather(*(total(addr) for addr, _ in top))
    log.info("senders: done, %d senders", len(top))

    out = [
        Sender(
            address=addr,
            domain=addr.split("@")[-1],
            name=b["name"],
            sampled=b["count"],
            total=n,
            capped=capped,
            estimated_bytes=(b["bytes"] // b["count"]) * n if b["count"] else 0,
            unsubscribe=b["unsub"],
            subjects=b["subjects"],
        )
        for (addr, b), (n, capped) in zip(top, totals)
    ]
    out.sort(key=lambda s: s.total, reverse=True)
    return out


# ---- unsubscribe -----------------------------------------------------------


class UnsubItem(BaseModel):
    address: str
    method: Literal["one_click", "mailto"]
    url: str | None = None
    mailto: str | None = None


class UnsubBody(BaseModel):
    items: list[UnsubItem]
    allow_mailto: bool = False  # the user ticked "send unsubscribe emails from my account"


def parse_mailto(uri: str) -> tuple[str, str, str]:
    """'mailto:leave@x.com?subject=unsubscribe' -> (to, subject, body).
    Subject and body default to 'Unsubscribe', which is what list managers
    expect from an empty request."""
    parts = urlsplit(uri)
    if parts.scheme.lower() != "mailto" or not parts.path:
        raise ValueError(f"not a mailto address: {uri[:80]}")
    to = unquote(parts.path).split(",")[0].strip()
    q = parse_qs(parts.query)
    subject = q.get("subject", ["Unsubscribe"])[0]
    body = q.get("body", ["Unsubscribe"])[0]
    return to, subject, body


async def unsubscribe_one(gmail: Gmail, http: httpx.AsyncClient, item: UnsubItem) -> None:
    """Do what the sender's headers said. Raises on anything short of a
    clear acceptance; the caller turns that into a 'failed' line."""
    if item.method == "one_click":
        if not item.url or not item.url.lower().startswith("https://"):
            raise ValueError("one-click unsubscribe needs an https address")
        # RFC 8058 section 3.2: POST this exact form body, nothing else, no cookies, no auth.
        r = await http.post(item.url, data={"List-Unsubscribe": "One-Click"})
        if not 200 <= r.status_code < 300:
            raise ValueError(f"the sender answered HTTP {r.status_code}")
        return
    if not item.mailto:
        raise ValueError("no mailto address for this sender")
    to, subject, body = parse_mailto(item.mailto)
    await gmail.send_message(to, subject, body)


async def unsubscribe_stream(gmail: Gmail, items: list[UnsubItem]) -> AsyncIterator[dict[str, Any]]:
    """One line per sender as it finishes, then a final tally. 'requested'
    means the sender accepted the request; it does not mean mail stops."""
    requested = failed = 0
    async with httpx.AsyncClient(timeout=UNSUB_TIMEOUT, follow_redirects=False) as http:
        for item in items:
            try:
                await unsubscribe_one(gmail, http, item)
                requested += 1
                yield {"address": item.address, "status": "requested", "done": False}
            except (ValueError, httpx.HTTPError, HTTPException) as e:
                failed += 1
                detail = getattr(e, "detail", None) or str(e) or type(e).__name__
                log.warning("unsubscribe %s failed: %s", item.address, detail)
                yield {"address": item.address, "status": "failed", "detail": detail, "done": False}
    yield {"requested": requested, "failed": failed, "done": True}


@router.post("/unsubscribe")
async def unsubscribe(body: UnsubBody, request: Request):
    """NDJSON. Refuses mailto items unless the user opted in, because that
    path sends email from their account."""
    if len(body.items) > 200:
        raise HTTPException(400, "Unsubscribe from at most 200 senders per request")
    if not body.allow_mailto and any(i.method == "mailto" for i in body.items):
        raise HTTPException(400, "Sending unsubscribe emails is off. Turn it on first.")
    return stream_ndjson(request, "unsubscribe", lambda g: unsubscribe_stream(g, body.items))
