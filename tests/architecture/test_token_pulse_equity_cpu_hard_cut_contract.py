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
    assert 'watched_only=scope == "matched"' not in text
    assert "PULSE_SCOPE_WATCHED_ONLY[scope]" in text
    assert "_watched_only_for_scope(scope" in text


def test_token_target_repository_exposes_event_id_timeline_loader() -> None:
    text = _read("src/parallax/domains/token_intel/repositories/token_target_repository.py")

    assert "def timeline_rows_for_event_ids" in text
    assert "WITH ORDINALITY" in text
    assert "events.event_id = requested_events.event_id" in text


def test_token_target_and_signal_read_limits_reject_runtime_int_repairs() -> None:
    token_target_source = _read("src/parallax/domains/token_intel/repositories/token_target_repository.py")
    signal_source = _read("src/parallax/domains/token_intel/repositories/signal_repository.py")
    combined = token_target_source + signal_source

    assert "max(0, int(limit))" not in combined
    assert "token_target_repository_limit_required" in token_target_source
    assert "signal_repository_alert_limit_required" in signal_source


def test_token_rebuild_rank_source_and_account_quality_limits_reject_runtime_int_repairs() -> None:
    account_quality_source = _read("src/parallax/domains/account_quality/repositories/account_quality_repository.py")
    event_rebuild_source = _read("src/parallax/domains/token_intel/queries/event_rebuild_query.py")
    rank_source = _read("src/parallax/domains/token_intel/queries/token_radar_rank_source_query.py")
    combined = account_quality_source + event_rebuild_source + rank_source

    assert "max(0, int(limit))" not in combined
    assert "max(1, int(limit))" not in combined
    assert "max(1, int(chunk_size))" not in rank_source
    assert "account_quality_token_rows_limit_required" in account_quality_source
    assert "event_rebuild_recent_events_limit_required" in event_rebuild_source
    assert "token_radar_rank_source_prune_limit_required" in rank_source
    assert "token_radar_rank_source_chunk_size_required" in rank_source
