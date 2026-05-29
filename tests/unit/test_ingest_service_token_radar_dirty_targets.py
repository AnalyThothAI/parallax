from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.domains.evidence.services.ingest_service import _source_dirty_events_for_resolutions


def test_source_dirty_events_for_resolutions_uses_event_target_edge() -> None:
    rows = _source_dirty_events_for_resolutions(
        [
            SimpleNamespace(
                event_id="event-1",
                intent_id="intent-1",
                target_type="Asset",
                target_id="asset-1",
            )
        ]
    )

    assert rows == [
        {
            "source_event_id": "event-1",
            "target_type_key": "Asset",
            "identity_id": "asset-1",
        }
    ]


def test_source_dirty_events_for_resolutions_skips_unresolved_intent_identity() -> None:
    rows = _source_dirty_events_for_resolutions(
        [
            {
                "event_id": "event-1",
                "intent_id": "intent-unresolved",
                "target_type": None,
                "target_id": None,
            }
        ]
    )

    assert rows == []
