import pytest

from parallax.domains.evidence.types.watchlist import (
    WatchlistTimelineCursorError,
    decode_watchlist_timeline_cursor,
    encode_watchlist_timeline_cursor,
    normalize_watchlist_handle,
)


def test_timeline_cursor_round_trips_without_padding():
    cursor = encode_watchlist_timeline_cursor(received_at_ms=1_700_000_000_123, event_id="event-42")

    assert "=" not in cursor
    assert decode_watchlist_timeline_cursor(cursor) == (1_700_000_000_123, "event-42")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-base64",
        "e30",
        encode_watchlist_timeline_cursor(received_at_ms=0, event_id="event-1"),
        encode_watchlist_timeline_cursor(received_at_ms=1, event_id=""),
    ],
)
def test_timeline_cursor_rejects_invalid_payloads(raw):
    with pytest.raises(WatchlistTimelineCursorError):
        decode_watchlist_timeline_cursor(raw)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("@Toly", "toly"),
        (" trader.pow ", "trader.pow"),
        ("crypto-devin_1", "crypto-devin_1"),
    ],
)
def test_normalize_watchlist_handle_accepts_configured_shape(raw, normalized):
    assert normalize_watchlist_handle(raw) == normalized


@pytest.mark.parametrize("raw", ["", "@", "bad handle", "x" * 65, "slash/name"])
def test_normalize_watchlist_handle_rejects_non_route_handles(raw):
    with pytest.raises(ValueError):
        normalize_watchlist_handle(raw)
