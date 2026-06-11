from __future__ import annotations

import pytest

from parallax.domains.token_intel.services.token_radar_payload_hash import stable_token_radar_payload_hash


def test_hash_ignores_exact_factor_snapshot_json_computed_at_path() -> None:
    payload = {
        "factor_snapshot_json": {
            "schema_version": "token_factor_snapshot_v3_social_attention",
            "subject": {"symbol": "BOV"},
            "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_778_000_000_000},
        }
    }
    later_payload = {
        "factor_snapshot_json": {
            **payload["factor_snapshot_json"],
            "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_778_000_060_000},
        }
    }

    assert stable_token_radar_payload_hash(later_payload) == stable_token_radar_payload_hash(payload)


def test_hash_ignores_top_level_token_factor_snapshot_computed_at() -> None:
    snapshot = {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {"symbol": "BOV"},
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_778_000_000_000},
    }
    later_snapshot = {
        **snapshot,
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_778_000_060_000},
    }

    assert stable_token_radar_payload_hash(later_snapshot) == stable_token_radar_payload_hash(snapshot)


def test_hash_keeps_nested_non_factor_provenance_computed_at_significant() -> None:
    payload = {
        "analysis": {
            "subject": {"kind": "non-factor"},
            "provenance": {"computed_at_ms": 1_778_000_000_000, "source": "audit"},
        }
    }
    later_payload = {
        "analysis": {
            "subject": {"kind": "non-factor"},
            "provenance": {"computed_at_ms": 1_778_000_060_000, "source": "audit"},
        }
    }

    assert stable_token_radar_payload_hash(later_payload) != stable_token_radar_payload_hash(payload)


def test_hash_rejects_legacy_non_string_payload_keys() -> None:
    payload = {
        "factor_snapshot_json": {
            "schema_version": "token_factor_snapshot_v3_social_attention",
            "subject": {123: "legacy-key"},
        }
    }

    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        stable_token_radar_payload_hash(payload)


def test_hash_rejects_unordered_payload_containers() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has unsupported containers"):
        stable_token_radar_payload_hash({"source_event_ids": {"event-1", "event-2"}})
