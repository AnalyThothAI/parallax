from __future__ import annotations

import inspect

import pytest

from parallax.domains.narrative_intel.repositories.narrative_repository import (
    NarrativeRepository,
    admission_payload_hash,
)


def test_load_radar_admission_target_reads_ready_publication_state_without_generation_gate() -> None:
    source = inspect.getsource(NarrativeRepository.load_radar_admission_target)

    assert "token_radar_publication_state" in source
    assert "token_radar_projection_coverage" not in source
    assert "latest_attempt_status = 'ready'" in source
    assert "token_radar_current_rows.generation_id = latest.current_generation_id" not in source
    assert "latest.current_published_at_ms AS computed_at_ms" in source


def test_admission_payload_hash_rejects_legacy_payload_keys() -> None:
    with pytest.raises(ValueError, match="current payload hash payload has non-string keys"):
        admission_payload_hash(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "schema_version": "narrative_admission_v1",
                "status": "admitted",
                "source_event_ids_json": ["event-1"],
                123: "legacy",
            }
        )


def test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values() -> None:
    class LegacyJsonbLikeAdapter:
        def __init__(self) -> None:
            self.obj = {"source_event_ids": ["event-1"]}

    with pytest.raises(ValueError, match="current payload hash payload has unsupported values"):
        admission_payload_hash(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "schema_version": "narrative_admission_v1",
                "status": "admitted",
                "source_event_ids_json": LegacyJsonbLikeAdapter(),
            }
        )
