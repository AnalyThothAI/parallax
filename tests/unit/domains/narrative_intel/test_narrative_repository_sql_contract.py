from __future__ import annotations

import inspect

from parallax.domains.narrative_intel.repositories.narrative_repository import NarrativeRepository


def test_load_radar_admission_target_reads_ready_publication_state_without_generation_gate() -> None:
    source = inspect.getsource(NarrativeRepository.load_radar_admission_target)

    assert "token_radar_publication_state" in source
    assert "token_radar_projection_coverage" not in source
    assert "latest_attempt_status = 'ready'" in source
    assert "token_radar_current_rows.generation_id = latest.current_generation_id" not in source
    assert "latest.current_published_at_ms AS computed_at_ms" in source
