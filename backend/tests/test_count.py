"""count() pages ids and stops at the cap. Fakes the HTTP layer only."""
import httpx

from sweep.google import Gmail
from sweep.session import Session


def _gmail_with_pages(pages: list[dict]) -> Gmail:
    calls = iter(pages)

    async def fake_request(method, url, **kw):
        return httpx.Response(200, json=next(calls))

    g = Gmail(Session(access_token="t", refresh_token=None, email="x@y"))
    g._request = fake_request  # type: ignore[method-assign]
    return g


async def test_count_sums_pages_and_is_exact_when_pages_run_out():
    g = _gmail_with_pages(
        [
            {"messages": [{"id": str(i)} for i in range(500)], "nextPageToken": "p2"},
            {"messages": [{"id": str(i)} for i in range(120)]},
        ]
    )
    assert await g.count("older_than:1y") == {"count": 620, "capped": False}


async def test_count_stops_at_max_pages_and_reports_capped():
    g = _gmail_with_pages(
        [{"messages": [{"id": str(i)} for i in range(500)], "nextPageToken": "more"}] * 3
    )
    assert await g.count("in:anywhere", max_pages=3) == {"count": 1500, "capped": True}


async def test_count_empty_result():
    g = _gmail_with_pages([{}])
    assert await g.count("from:nobody") == {"count": 0, "capped": False}
