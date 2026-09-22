"""count_stream() pages ids, stops at the cap, and samples sizes. Fakes the
HTTP layer only."""
import json

import httpx
from fastapi.testclient import TestClient

from sweep.google import Gmail, _spread
from sweep.session import Session

SIZE = 40_000


def _fake_gmail(pages: list[dict]) -> Gmail:
    calls = iter(pages)

    async def fake_request(method, url, **kw):
        if url.endswith("/messages"):
            return httpx.Response(200, json=next(calls))
        return httpx.Response(200, json={  # messages/{id}
            "sizeEstimate": SIZE,
            "internalDate": "1600000000000",
            "payload": {"headers": [
                {"name": "From", "value": "Orvis <news@orvis.com>"},
                {"name": "Subject", "value": "Sale ends soon"},
            ]},
        })

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._request = fake_request  # type: ignore[method-assign]
    return g


def _page(n: int, more: bool) -> dict:
    d: dict = {"messages": [{"id": str(i)} for i in range(n)]}
    if more:
        d["nextPageToken"] = "next"
    return d


async def _collect(g: Gmail, **kw) -> list[dict]:
    return [line async for line in g.count_stream("q", **kw)]


async def test_streams_progress_then_exact_final_with_avg_bytes_and_preview():
    lines = await _collect(_fake_gmail([_page(500, True), _page(120, False)]))
    assert lines[0] == {"count": 500, "capped": False, "done": False}
    final = lines[-1]
    assert (final["count"], final["capped"], final["done"], final["avg_bytes"]) == (620, False, True, SIZE)
    pv = final["preview"]
    assert pv["sampled"] == 100  # SIZE_SAMPLE spread over 620 ids
    assert pv["oldest"] == pv["newest"] == "2020-09-13"
    assert pv["senders"] == [{"address": "news@orvis.com", "name": "Orvis", "sampled": 100}]
    assert pv["subjects"] == ["Sale ends soon"] * 6


async def test_stops_at_max_pages_and_reports_capped():
    lines = await _collect(_fake_gmail([_page(500, True)] * 3), max_pages=3)
    assert len(lines) == 4  # 3 progress lines + final
    assert (lines[-1]["count"], lines[-1]["capped"], lines[-1]["done"]) == (1500, True, True)


async def test_empty_result_has_zero_avg():
    lines = await _collect(_fake_gmail([{}]))
    assert lines == [{"count": 0, "capped": False, "done": True, "avg_bytes": 0, "preview": None}]


async def test_count_returns_final_line():
    g = _fake_gmail([_page(3, False)])
    out = await g.count("q")
    assert (out["count"], out["done"], out["avg_bytes"]) == (3, True, SIZE)


def test_spread_is_even_and_capped():
    xs = [str(i) for i in range(1000)]
    got = _spread(xs, 10)
    assert got == ["0", "100", "200", "300", "400", "500", "600", "700", "800", "900"]
    assert _spread(["a", "b"], 10) == ["a", "b"]


def test_preset_count_endpoint_streams_ndjson(monkeypatch):
    from sweep import main
    from sweep.routers import cleanup

    monkeypatch.setattr(cleanup, "read_session", lambda req: Session("t", None, "x@y"))
    monkeypatch.setattr(cleanup, "Gmail", lambda s: _fake_gmail([_page(500, True), _page(1, False)]))
    with TestClient(main.app) as c:
        r = c.get("/api/presets/before-2020/count")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(x) for x in r.text.strip().split("\n")]
    assert lines[0]["done"] is False and lines[0]["count"] == 500
    assert (lines[-1]["count"], lines[-1]["done"], lines[-1]["avg_bytes"]) == (501, True, SIZE)


async def test_untrash_removes_only_trash_label_in_batches():
    seen: list[dict] = []

    async def fake_request(method, url, **kw):
        seen.append(kw["json"])
        return httpx.Response(200, json={})

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._request = fake_request  # type: ignore[method-assign]
    assert await g.untrash([str(i) for i in range(1500)]) == 1500
    assert [len(b["ids"]) for b in seen] == [1000, 500]
    assert all(b["removeLabelIds"] == ["TRASH"] and "addLabelIds" not in b for b in seen)


async def test_request_retries_on_429_then_succeeds(monkeypatch):
    import sweep.google as g_mod

    monkeypatch.setattr(g_mod.asyncio, "sleep", _no_sleep)
    responses = iter([httpx.Response(429), httpx.Response(503), httpx.Response(200, json={"ok": 1})])

    class FakeClient:
        async def request(self, *a, **k):
            return next(responses)

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._client = FakeClient()  # type: ignore[assignment]
    assert (await g._request("GET", "u")).json() == {"ok": 1}


async def test_request_retries_empty_200_then_gives_too_fast(monkeypatch):
    import sweep.google as g_mod

    monkeypatch.setattr(g_mod.asyncio, "sleep", _no_sleep)
    responses = iter([httpx.Response(200, content=b""), httpx.Response(200, json={"ok": 1})])

    class FakeClient:
        async def request(self, *a, **k):
            return next(responses)

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._client = FakeClient()  # type: ignore[assignment]
    assert (await g._request("GET", "u")).json() == {"ok": 1}

    always_empty = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))

    class EmptyClient:
        async def request(self, *a, **k):
            return httpx.Response(200, content=b"")

    always_empty._client = EmptyClient()  # type: ignore[assignment]
    try:
        await always_empty._request("GET", "u")
        raise AssertionError("expected HTTPException")
    except Exception as e:
        assert getattr(e, "status_code", None) == 429 and "commotion" in str(e.detail)


async def test_sample_skips_empty_body_instead_of_failing():
    calls = {"n": 0}

    async def fake_request(method, url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, content=b"")  # what a throttled 200 looks like
        return httpx.Response(200, json={"sizeEstimate": SIZE, "payload": {"headers": []}})

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._request = fake_request  # type: ignore[method-assign]
    out = await g.sample_summary(["a", "b", "c"])
    assert out["avg_bytes"] == SIZE
    assert out["preview"]["sampled"] == 2


async def _no_sleep(_):
    return None


def test_delete_endpoint_requires_exact_confirmation(monkeypatch):
    from sweep import main
    from sweep.routers import cleanup

    calls: list[list[str]] = []

    async def fake_request(self, method, url, **kw):
        calls.append(kw["json"]["ids"])
        return httpx.Response(200, json={})

    monkeypatch.setattr(cleanup, "read_session", lambda req: Session("t", None, "x@y"))
    monkeypatch.setattr(Gmail, "_request", fake_request)
    with TestClient(main.app) as c:
        bad = c.post("/api/delete", json={"ids": ["1"], "confirm": "delete forever"})
        good = c.post("/api/delete", json={"ids": ["1", "2"], "confirm": "DELETE FOREVER"})
    assert bad.status_code == 400 and calls == [["1", "2"]]
    lines = [json.loads(x) for x in good.text.strip().split("\n")]
    assert lines[-1] == {"deleted": 2, "total": 2, "done": True}


async def test_trash_stream_reports_both_phases_then_ids():
    pages = iter([_page(500, True), _page(700, False)])
    batches: list[int] = []

    async def fake_request(method, url, **kw):
        if url.endswith("/messages"):
            return httpx.Response(200, json=next(pages))
        batches.append(len(kw["json"]["ids"]))
        return httpx.Response(200, json={})

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._request = fake_request  # type: ignore[method-assign]
    lines = [x async for x in g.trash_stream("q")]
    assert [x["phase"] for x in lines] == ["listing", "listing", "trashing", "done"]
    assert lines[1]["found"] == 1200
    assert lines[2] == {"phase": "trashing", "trashed": 1200, "total": 1200, "done": False}
    assert lines[3]["trashed"] == 1200 and len(lines[3]["ids"]) == 1200
    assert sorted(batches) == [200, 1000]


async def test_sample_survives_a_message_with_bad_metadata():
    bodies = iter(
        [
            {"sizeEstimate": "not-a-number", "internalDate": "x", "payload": {"headers": []}},
            {"sizeEstimate": SIZE, "internalDate": "99999999999999999", "payload": {"headers": []}},
            {"sizeEstimate": SIZE, "internalDate": "1600000000000", "payload": {"headers": [
                {"name": "From", "value": "a@b.c"}, {"name": "Subject", "value": "hi"}]}},
        ]
    )

    async def fake_request(method, url, **kw):
        return httpx.Response(200, json=next(bodies))

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._request = fake_request  # type: ignore[method-assign]
    out = await g.sample_summary(["1", "2", "3"], concurrency=1)
    assert out["avg_bytes"] == SIZE
    assert out["preview"]["sampled"] == 3  # 3 fetched; 1 skipped in parsing
    assert out["preview"]["oldest"] == out["preview"]["newest"] == "2020-09-13"  # absurd date ignored


async def test_204_from_list_means_zero_matches():
    async def fake_request(method, url, **kw):
        return httpx.Response(204)  # Gmail: fields mask selected nothing

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._request = fake_request  # type: ignore[method-assign]
    lines = [x async for x in g.count_stream("category:promotions older_than:1y")]
    assert lines == [{"count": 0, "capped": False, "done": True, "avg_bytes": 0, "preview": None}]
    trash = [x async for x in g.trash_stream("category:promotions older_than:1y")]
    assert trash[-1]["trashed"] == 0 and trash[-1]["ids"] == []
    assert await g.list_message_ids("q") == []


async def test_pacer_spaces_calls_by_quota_cost():
    import time

    from sweep.google import _Pacer

    p = _Pacer(rate=1000, burst=100)  # 100 units ready, then 1,000 per second
    t = time.monotonic()
    for _ in range(3):
        await p.take(100)  # first is free, the next two wait ~0.1s each
    assert 0.18 <= time.monotonic() - t < 0.6


async def test_quota_403_is_retried_then_succeeds(monkeypatch):
    """The per-minute quota comes back as 403 rateLimitExceeded; back off like a 429."""
    from sweep.google import Gmail as G
    from sweep.session import Session as S

    monkeypatch.setattr("sweep.google.asyncio.sleep", lambda s: _noop())
    answers = iter([
        httpx.Response(403, json={"error": {"errors": [{"reason": "rateLimitExceeded"}]}}),
        httpx.Response(200, json={"messagesTotal": 5}),
    ])

    class FakeClient:
        async def request(self, method, url, **kw):
            return next(answers)

    g = G(S(access_token="t", refresh_token=None, email="x@y"))
    g._client = FakeClient()  # type: ignore[assignment]
    assert (await g.profile()) == {"messagesTotal": 5}


async def _noop():
    return None
