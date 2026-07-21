from __future__ import annotations

from parallax.app.surfaces.api import routes_events


def test_source_event_detail_uses_explicit_configured_watchlist_membership() -> None:
    payload = routes_events._source_event_detail(
        _event_read(author_handle="@Alice"),
        {"alice"},
    )

    assert payload["author_handle"] == "alice"
    assert payload["author_watched"] is True


def test_source_event_detail_does_not_infer_watchlist_membership_from_author_fields() -> None:
    payload = routes_events._source_event_detail(
        _event_read(author_handle="alice", is_watched=True),
        set(),
    )

    assert payload["author_watched"] is False


def test_source_event_detail_preserves_source_timestamp_without_receipt_fallback() -> None:
    payload = routes_events._source_event_detail(
        _event_read(timestamp_ms=1_600_000_000_000, received_at_ms=1_700_000_000_000),
        set(),
    )

    assert payload["timestamp_ms"] == 1_600_000_000_000


def _event_read(**overrides: object) -> dict[str, object]:
    return {
        "event_id": "event-1",
        "timestamp_ms": 1_600_000_000_000,
        "received_at_ms": 1_700_000_000_000,
        "source_provider": "gmgn",
        "channel": "twitter_monitor_basic",
        "action": "tweet",
        "author_handle": "alice",
        "author_name": "Alice",
        "author_followers": 100,
        "text_clean": "canonical text",
        "canonical_url": "https://x.com/alice/status/event-1",
        "is_watched": False,
        **overrides,
    }
