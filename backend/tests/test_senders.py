from sweep.routers.senders import parse_from, parse_unsubscribe


def test_parse_from_with_display_name():
    assert parse_from('Orvis <News@Orvis.com>') == ("news@orvis.com", "Orvis")


def test_parse_from_bare_address():
    assert parse_from("noreply@example.com") == ("noreply@example.com", "")


def test_unsubscribe_prefers_https_over_mailto():
    raw = "<mailto:unsub@x.com>, <https://x.com/unsub?u=1>"
    assert parse_unsubscribe(raw) == "https://x.com/unsub?u=1"


def test_unsubscribe_none_when_only_mailto():
    assert parse_unsubscribe("<mailto:unsub@x.com>") is None
