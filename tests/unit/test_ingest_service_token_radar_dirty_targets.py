from __future__ import annotations

from types import SimpleNamespace

from gmgn_twitter_intel.domains.evidence.services.ingest_service import _dirty_targets_for_resolutions


def test_dirty_targets_for_resolutions_uses_resolved_target_identity() -> None:
    rows = _dirty_targets_for_resolutions(
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
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "source_event_ids": ["event-1"],
        }
    ]


def test_dirty_targets_for_resolutions_skips_unresolved_intent_identity() -> None:
    rows = _dirty_targets_for_resolutions(
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
