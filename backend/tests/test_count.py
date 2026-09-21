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
        return httpx.Response(200, json={"sizeEstimate": SIZE})  # messages/{id}

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


async def test_streams_progress_then_exact_final_with_avg_bytes():
    lines = await _collect(_fake_gmail([_page(500, True), _page(120, False)]))
    assert lines[0] == {"count": 500, "capped": False, "done": False}
    assert lines[-1] == {"count": 620, "capped": False, "done": True, "avg_bytes": SIZE}


async def test_stops_at_max_pages_and_reports_capped():
    lines = await _collect(_fake_gmail([_page(500, True)] * 3), max_pages=3)
    assert len(lines) == 4  # 3 progress lines + final
    assert lines[-1] == {"count": 1500, "capped": True, "done": True, "avg_bytes": SIZE}


async def test_empty_result_has_zero_avg():
    lines = await _collect(_fake_gmail([{}]))
    assert lines == [{"count": 0, "capped": False, "done": True, "avg_bytes": 0}]


async def test_count_returns_final_line():
    g = _fake_gmail([_page(3, False)])
    assert await g.count("q") == {"count": 3, "capped": False, "done": True, "avg_bytes": SIZE}


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
    assert lines[-1] == {"count": 501, "capped": False, "done": True, "avg_bytes": SIZE}
