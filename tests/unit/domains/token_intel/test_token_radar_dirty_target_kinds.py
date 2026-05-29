from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    dirty_kind_flags,
    dirty_payload_hash,
)


def test_dirty_kind_flags_classify_target_queue_reasons() -> None:
    assert dirty_kind_flags("intent_written") == {
        "market_dirty": False,
        "repair_dirty": False,
    }
    assert dirty_kind_flags("market_tick_current_changed") == {
        "market_dirty": True,
        "repair_dirty": False,
    }
    assert dirty_kind_flags("ops_market_current_repair") == {
        "market_dirty": True,
        "repair_dirty": True,
    }


def test_dirty_kind_flags_classify_repair_without_source_dirty() -> None:
    assert dirty_kind_flags("projection_catch_up") == {
        "market_dirty": False,
        "repair_dirty": True,
    }


def test_dirty_payload_hash_excludes_queue_lifecycle_fields() -> None:
    first = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "source_event_ids": ["event-1"],
        "dirty_at_ms": 111,
        "due_at_ms": 222,
        "leased_until_ms": 333,
        "lease_owner": "worker-a",
        "attempt_count": 1,
        "updated_at_ms": 444,
        "first_dirty_at_ms": 555,
        "last_error": "boom",
    }
    second = {
        **first,
        "dirty_at_ms": 999,
        "due_at_ms": 888,
        "leased_until_ms": 777,
        "lease_owner": "worker-b",
        "attempt_count": 2,
        "updated_at_ms": 666,
        "first_dirty_at_ms": 555,
        "last_error": "different",
    }

    assert dirty_payload_hash(first) == dirty_payload_hash(second)
    assert len(dirty_payload_hash(first)) == 64
