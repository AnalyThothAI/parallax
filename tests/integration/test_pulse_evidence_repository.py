from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.types import PulseEvidencePacket
from tests.postgres_test_utils import (
    connect_postgres_test,
    repository_session_for_connection,
)
from tests.postgres_test_utils import (
    reset_postgres_schema as migrate,
)


def test_pulse_evidence_repository_upserts_and_reconstructs_packet(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_run(conn, run_id="run-1", candidate_id="candidate-1")
        packet = _packet(run_id="run-1", candidate_id="candidate-1", packet_id="packet-1").sealed_copy()

        with repository_session_for_connection(conn) as repos:
            repos.pulse_evidence.upsert_packet(packet)
            by_hash = repos.pulse_evidence.get_packet_by_hash(packet.evidence_packet_hash)
            by_run = repos.pulse_evidence.get_packet_for_run("run-1")
            latest = repos.pulse_evidence.latest_packet_for_candidate("candidate-1")
    finally:
        conn.close()

    assert by_hash == packet
    assert by_run == packet
    assert latest == packet


def test_pulse_evidence_repository_upsert_replaces_summary_without_losing_packet(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_run(conn, run_id="run-1", candidate_id="candidate-1")
        packet = _packet(run_id="run-1", candidate_id="candidate-1", packet_id="packet-1").sealed_copy()
        replacement = packet.model_copy(update={"summary_json": {"status": "replayed"}})

        with repository_session_for_connection(conn) as repos:
            repos.pulse_evidence.upsert_packet(packet)
            repos.pulse_evidence.upsert_packet(replacement)
            stored = repos.pulse_evidence.get_packet_by_hash(packet.evidence_packet_hash)
    finally:
        conn.close()

    assert stored == replacement
    assert stored.summary_json == {"status": "replayed"}


def test_repository_session_exposes_pulse_evidence_repositories(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        with repository_session_for_connection(conn) as repos:
            assert repos.pulse_evidence.get_packet_by_hash("missing") is None
            assert repos.pulse_evidence_sources.list_source_events(["missing"]) == []
    finally:
        conn.close()


def _insert_run(conn: Any, *, run_id: str, candidate_id: str) -> None:
    conn.execute(
        """
        INSERT INTO pulse_agent_jobs(
          job_id, candidate_id, candidate_type, subject_key, target_type, target_id,
          "window", scope, trigger_signature, timeline_signature, context_json,
          priority, status, attempt_count, max_attempts, next_run_at_ms,
          last_error, created_at_ms, updated_at_ms
        )
        VALUES (
          'job-1', %s, 'token_target', 'Asset:asset-1', 'cex_symbol', 'BNB',
          '1h', 'all', 'trigger', 'timeline', '{}'::jsonb,
          10, 'running', 1, 3, 1, NULL, 1, 1
        )
        """,
        (candidate_id,),
    )
    conn.execute(
        """
        INSERT INTO pulse_agent_runs(
          run_id, job_id, candidate_id, provider, model, backend, sdk_trace_id,
          workflow_name, agent_name, artifact_version_hash, prompt_version,
          schema_version, runtime_version, runtime_hash, input_hash, output_hash,
          trace_metadata_json, usage_json, latency_ms, status, outcome,
          decision_route, decision_stage_count, request_json, response_json, error,
          started_at_ms, finished_at_ms
        )
        VALUES (
          %s, 'job-1', %s, 'test', 'test-model', 'unit', NULL,
          'pulse_evidence_first', 'decision_maker', 'artifact', 'prompt',
          'schema', 'runtime', 'runtime-hash', 'input-hash', NULL,
          '{}'::jsonb, '{}'::jsonb, 0, 'running', 'running',
          'cex', 0, '{}'::jsonb, NULL, NULL, 1, 1
        )
        """,
        (run_id, candidate_id),
    )
    conn.commit()


def _packet(*, run_id: str, candidate_id: str, packet_id: str) -> PulseEvidencePacket:
    return PulseEvidencePacket(
        evidence_packet_id=packet_id,
        run_id=run_id,
        evidence_packet_hash="",
        schema_version="pulse_evidence_packet_v1",
        candidate_id=candidate_id,
        target_type="cex_symbol",
        target_id="BNB",
        symbol="BNB",
        window="1h",
        scope="all",
        snapshot_at_ms=1_800_000_000_000,
        source_event_ids=("event-1",),
        allowed_evidence_refs=(
            {
                "ref_id": "event:event-1",
                "ref_type": "event",
                "source_table": "events",
                "source_id": "event-1",
                "observed_at_ms": 1_800_000_000_000,
                "summary_zh": "官方账号提及 BNB。",
                "quality": "high",
            },
            {
                "ref_id": "metric:market:price_usd",
                "ref_type": "metric",
                "source_table": "market_ticks",
                "source_id": "tick-1",
                "observed_at_ms": 1_800_000_000_000,
                "summary_zh": "价格可用。",
                "quality": "high",
            },
        ),
        social_evidence={"status": "complete", "event_refs": ("event:event-1",), "summary_zh": "社交证据可用"},
        market_evidence={
            "status": "partial",
            "route": "cex",
            "target_market_type": "cex",
            "price_usd": 600.0,
            "venue_ref": "okx",
            "instrument_ref": "pf-1",
            "observed_at_ms": 1_800_000_000_000,
            "freshness_status": "fresh",
            "source_provider": "okx_cex_rest",
            "pricefeed_id": "pf-1",
        },
        identity_evidence={
            "status": "complete",
            "identity_refs": (),
            "profile_refs": (),
            "summary_zh": "身份证据可用",
        },
        quality_metrics={"ref_count": 2, "high_quality_ref_count": 2, "fresh_ref_count": 2},
        data_gaps=(),
        risk_flags=(),
        source_fingerprints={"factor_snapshot": {"candidate_score": 0.82}},
        admission_context={"candidate_score": 0.82},
        summary_json={"status": "built"},
    )
