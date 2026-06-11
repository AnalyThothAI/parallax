from __future__ import annotations

from parallax.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    dirty_kind_flags,
    dirty_payload_hash,
)
from parallax.platform.current_read_model_payload_hash import PAYLOAD_HASH_HEX_LENGTH, PAYLOAD_HASH_PREFIX


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

    payload_hash = dirty_payload_hash(first)
    assert payload_hash == dirty_payload_hash(second)
    assert payload_hash.startswith(PAYLOAD_HASH_PREFIX)
    assert len(payload_hash.removeprefix(PAYLOAD_HASH_PREFIX)) == PAYLOAD_HASH_HEX_LENGTH
