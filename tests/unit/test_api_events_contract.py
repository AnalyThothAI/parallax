from __future__ import annotations

from parallax.app.surfaces.api import routes_events


def test_source_event_detail_uses_explicit_configured_watchlist_membership() -> None:
    payload = routes_events._source_event_detail(
        {
            "event_id": "event-1",
            "received_at_ms": 1_700_000_000_000,
            "author_handle": "@Alice",
        },
        {"alice"},
    )

    assert payload["author_handle"] == "alice"
    assert payload["author_watched"] is True


def test_source_event_detail_does_not_infer_watchlist_membership_from_author_fields() -> None:
    payload = routes_events._source_event_detail(
        {
            "event_id": "event-1",
            "received_at_ms": 1_700_000_000_000,
            "author_handle": "alice",
            "is_watched": True,
        },
        set(),
    )

    assert payload["author_watched"] is False
