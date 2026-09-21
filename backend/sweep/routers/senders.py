"""Group a sample of the mailbox by sender so the user can see who is
actually filling it. Only metadata headers are fetched — never bodies."""
import re
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..deps import gmail_client
from ..google import Gmail

router = APIRouter(prefix="/api/senders", tags=["senders"])

_EMAIL_RE = re.compile(r"<([^>]+)>")
_HTTP_RE = re.compile(r"<(https?://[^>]+)>")


class Sender(BaseModel):
    address: str
    domain: str
    name: str
    count: int
    estimated_bytes: int
    unsubscribe_url: str | None
    subjects: list[str]


def parse_from(raw: str) -> tuple[str, str]:
    """'Orvis <news@orvis.com>' -> ('news@orvis.com', 'Orvis')"""
    m = _EMAIL_RE.search(raw)
    if m:
        return m.group(1).lower(), raw[: m.start()].strip().strip('"')
    return raw.strip().lower(), ""


def parse_unsubscribe(raw: str | None) -> str | None:
    """Prefer an https link from List-Unsubscribe; ignore mailto: entries."""
    if not raw:
        return None
    m = _HTTP_RE.search(raw)
    return m.group(1) if m else None


@router.get("", response_model=list[Sender])
async def top_senders(
    sample: int = Query(1000, ge=100, le=5000),
    query: str = Query("older_than:6m", description="Gmail query to sample from"),
    limit: int = Query(50, ge=5, le=200),
    gmail: Gmail = Depends(gmail_client),
):
    ids = await gmail.list_message_ids(query, limit=sample)
    msgs = await gmail.metadata_many(ids, ["From", "Subject", "List-Unsubscribe"])

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
        b["unsub"] = b["unsub"] or parse_unsubscribe(headers.get("list-unsubscribe"))
        if len(b["subjects"]) < 3 and headers.get("subject"):
            b["subjects"].append(headers["subject"][:120])

    ranked = sorted(buckets.items(), key=lambda kv: kv[1]["count"], reverse=True)[:limit]
    return [
        Sender(
            address=addr,
            domain=addr.split("@")[-1],
            name=b["name"],
            count=b["count"],
            estimated_bytes=b["bytes"],
            unsubscribe_url=b["unsub"],
            subjects=b["subjects"],
        )
        for addr, b in ranked
    ]
