"""Senders: header classification, real totals, and the unsubscribe stream.
Fakes the HTTP layer only."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from sweep.google import Gmail
from sweep.main import app
from sweep.routers.senders import (
    UnsubItem,
    classify_unsubscribe,
    parse_from,
    parse_mailto,
    parse_unsubscribe,
    scope_query,
    unsubscribe_stream,
)
from sweep.session import Session, read_session

ONE_CLICK_POST = "List-Unsubscribe=One-Click"


def test_parse_from_with_display_name():
    assert parse_from('Orvis <News@Orvis.com>') == ("news@orvis.com", "Orvis")


def test_parse_from_bare_address():
    assert parse_from("noreply@example.com") == ("noreply@example.com", "")


def test_unsubscribe_prefers_https_over_mailto():
    raw = "<mailto:unsub@x.com>, <https://x.com/unsub?u=1>"
    assert parse_unsubscribe(raw) == "https://x.com/unsub?u=1"


def test_unsubscribe_none_when_only_mailto():
    assert parse_unsubscribe("<mailto:unsub@x.com>") is None


# ---- classification ---------------------------------------------------------


def test_one_click_needs_post_header_and_https():
    u = classify_unsubscribe("<https://x.com/u?id=1>, <mailto:leave@x.com>", ONE_CLICK_POST)
    assert (u.method, u.url, u.mailto) == ("one_click", "https://x.com/u?id=1", "mailto:leave@x.com")


def test_post_header_without_https_is_not_one_click():
    u = classify_unsubscribe("<http://x.com/u>, <mailto:leave@x.com>", ONE_CLICK_POST)
    assert u.method == "mailto"


def test_mailto_beats_plain_link():
    u = classify_unsubscribe("<https://x.com/u>, <mailto:leave@x.com>", None)
    assert (u.method, u.mailto, u.url) == ("mailto", "mailto:leave@x.com", "https://x.com/u")


def test_link_only_is_manual():
    u = classify_unsubscribe("<https://x.com/u>", None)
    assert (u.method, u.url, u.mailto) == ("manual", "https://x.com/u", None)


def test_no_header_is_none():
    assert classify_unsubscribe(None, ONE_CLICK_POST) is None
    assert classify_unsubscribe("garbage", None) is None


def test_parse_mailto_defaults_and_params():
    assert parse_mailto("mailto:leave@x.com") == ("leave@x.com", "Unsubscribe", "Unsubscribe")
    to, subject, body = parse_mailto("mailto:leave@x.com?subject=unsub%20me&body=bye")
    assert (to, subject, body) == ("leave@x.com", "unsub me", "bye")
    with pytest.raises(ValueError):
        parse_mailto("https://x.com")


def test_scope_query_joins_sender_and_scan():
    assert scope_query("a@x.com", "older_than:6m") == "from:a@x.com older_than:6m"
    assert scope_query("a@x.com", "") == "from:a@x.com"


# ---- endpoint: totals ---------------------------------------------------------


def _msg(addr: str, unsub: str | None = None, post: str | None = None, size: int = 1000) -> dict:
    headers = [{"name": "From", "value": f"Name <{addr}>"}, {"name": "Subject", "value": "hi"}]
    if unsub:
        headers.append({"name": "List-Unsubscribe", "value": unsub})
    if post:
        headers.append({"name": "List-Unsubscribe-Post", "value": post})
    return {"sizeEstimate": size, "payload": {"headers": headers}}


class FakeGmail:
    """Sample: 3 messages from a, 1 from b. Totals: a has 700 in scope, b has 2."""

    token_refreshed = False

    def __init__(self):
        self.count_queries: list[str] = []

    async def list_message_ids(self, query, limit=None):
        return ["a1", "a2", "a3", "b1"]

    async def metadata_many(self, ids, headers, concurrency=20):
        return [
            _msg("a@x.com", "<https://x.com/u>", ONE_CLICK_POST, size=2000),
            _msg("a@x.com", "<https://x.com/u>", None, size=1000),
            _msg("a@x.com", size=3000),
            _msg("b@y.com", "<mailto:leave@y.com>"),
        ]

    async def count_ids(self, query, max_pages):
        self.count_queries.append(query)
        return (700, False) if query.startswith("from:a@x.com") else (2, True)

    async def close(self):
        pass


def _client(fake) -> TestClient:
    async def gmail_override():
        yield fake

    from sweep.deps import gmail_client

    app.dependency_overrides[gmail_client] = gmail_override
    app.dependency_overrides[read_session] = lambda: Session(access_token="t", refresh_token=None, email="me@x")
    return TestClient(app)


def test_senders_report_real_totals_inside_scope():
    fake = FakeGmail()
    try:
        r = _client(fake).get("/api/senders", params={"query": "older_than:1y"})
        assert r.status_code == 200, r.text
        a, b = r.json()
        assert (a["address"], a["sampled"], a["total"], a["capped"]) == ("a@x.com", 3, 700, False)
        assert a["estimated_bytes"] == 2000 * 700  # mean sampled size x total
        assert a["unsubscribe"]["method"] == "one_click"  # best path across a's messages
        assert (b["sampled"], b["total"], b["capped"]) == (1, 2, True)
        assert b["unsubscribe"]["method"] == "mailto"
        assert sorted(fake.count_queries) == ["from:a@x.com older_than:1y", "from:b@y.com older_than:1y"]
    finally:
        app.dependency_overrides.clear()


# ---- unsubscribe stream -------------------------------------------------------


def _gmail_with(fake_request) -> Gmail:
    g = Gmail(Session(access_token="t", refresh_token=None, email="me@x.com"))
    g._request = fake_request  # type: ignore[method-assign]
    return g


async def test_one_click_posts_rfc8058_form_and_reports_requested(monkeypatch):
    posts = []

    async def fake_post(self, url, **kw):
        posts.append((url, kw.get("data")))
        return httpx.Response(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    g = _gmail_with(None)
    lines = [
        line async for line in unsubscribe_stream(
            g, [UnsubItem(address="a@x.com", method="one_click", url="https://x.com/u")]
        )
    ]
    assert posts == [("https://x.com/u", {"List-Unsubscribe": "One-Click"})]
    assert lines[0] == {"address": "a@x.com", "status": "requested", "done": False}
    assert lines[-1] == {"requested": 1, "failed": 0, "done": True}


async def test_one_click_non_2xx_is_failed_not_requested(monkeypatch):
    async def fake_post(self, url, **kw):
        return httpx.Response(404)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    lines = [
        line async for line in unsubscribe_stream(
            _gmail_with(None), [UnsubItem(address="a@x.com", method="one_click", url="https://x.com/u")]
        )
    ]
    assert lines[0]["status"] == "failed" and "404" in lines[0]["detail"]
    assert lines[-1] == {"requested": 0, "failed": 1, "done": True}


async def test_mailto_sends_one_message_from_the_user():
    sent = []

    async def fake_request(method, url, **kw):
        sent.append((method, url, kw["json"]["raw"]))
        return httpx.Response(200, json={"id": "m1"})

    g = _gmail_with(fake_request)
    lines = [
        line async for line in unsubscribe_stream(
            g, [UnsubItem(address="b@y.com", method="mailto", mailto="mailto:leave@y.com?subject=stop")]
        )
    ]
    assert lines[0]["status"] == "requested"
    method, url, raw = sent[0]
    assert (method, url.endswith("/messages/send")) == ("POST", True)
    import base64

    msg = base64.urlsafe_b64decode(raw).decode()
    assert "From: me@x.com" in msg and "To: leave@y.com" in msg and "Subject: stop" in msg


def test_endpoint_refuses_mailto_without_opt_in():
    c = _client(FakeGmail())
    try:
        body = {"items": [{"address": "b@y.com", "method": "mailto", "mailto": "mailto:leave@y.com"}]}
        r = c.post("/api/senders/unsubscribe", json=body)
        assert r.status_code == 400 and "off" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_endpoint_streams_ndjson(monkeypatch):
    async def fake_post(self, url, **kw):
        return httpx.Response(202)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    # The stream opens its own Gmail client from the cookie, outside Depends.
    monkeypatch.setattr(
        "sweep.routers.cleanup.read_session",
        lambda request: Session(access_token="t", refresh_token=None, email="me@x"),
    )
    c = _client(FakeGmail())
    try:
        body = {"items": [{"address": "a@x.com", "method": "one_click", "url": "https://x.com/u"}]}
        r = c.post("/api/senders/unsubscribe", json=body)
        assert r.status_code == 200, r.text
        lines = [json.loads(line) for line in r.text.strip().splitlines()]
        assert lines[-1] == {"requested": 1, "failed": 0, "done": True}
    finally:
        app.dependency_overrides.clear()
