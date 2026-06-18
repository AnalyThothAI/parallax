from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _calls(path: str) -> list[str]:
    tree = ast.parse(_read(path))
    return [
        node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]


def test_token_rank_source_population_is_event_id_bounded() -> None:
    text = _read("src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py")

    assert "populate_edges_for_event_ids" in text
    assert "populate_edges_for_requests" not in text
    assert "_POPULATE_RANK_SOURCE_EDGES_SQL" not in text
    assert "requested_event_ids" in text
    assert "jsonb_to_recordset" in text
    assert re.search(
        r"JOIN\s+events\s+ON\s+events\.event_id\s*=\s*requested_event(?:s|_ids)\.source_event_id",
        text,
    )
    assert not re.search(
        r"JOIN\s+token_intent_resolutions\s+ON\s+token_intent_resolutions\.target_type\s*=\s*requested\.target_type_key",
        text,
    )


def test_token_projection_requires_source_event_ids_for_source_dirty_runtime() -> None:
    text = _read("src/parallax/domains/token_intel/services/token_radar_projection.py")

    assert "source_event_ids_json" in text
    assert "populate_edges_for_event_ids" in text
    assert "populate_edges_for_requests" not in text


def test_pulse_worker_uses_bounded_evidence_loader() -> None:
    worker_path = "src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py"
    text = _read(worker_path)
    calls = _calls(worker_path)

    assert "timeline_rows_for_event_ids" in calls
    assert "timeline_rows" not in calls
    assert "_source_event_ids(row)" in text
    assert "PULSE_SCOPE_WATCHED_ONLY" in text
    assert '"matched": True' in text
    assert "watched_only=_watched_only_for_scope(scope" in text


def test_token_target_repository_exposes_event_id_timeline_loader() -> None:
    text = _read("src/parallax/domains/token_intel/repositories/token_target_repository.py")

    assert "def timeline_rows_for_event_ids" in text
    assert "WITH ORDINALITY" in text
    assert "events.event_id = requested_events.event_id" in text
