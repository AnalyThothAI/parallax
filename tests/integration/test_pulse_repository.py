from __future__ import annotations

import base64
import inspect
import json
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.pulse_lab.repositories import pulse_repository
from gmgn_twitter_intel.domains.pulse_lab.repositories.pulse_repository import PulseRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def _job_payload(candidate_id: str, *, window: str = "1h", scope: str = "all") -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "candidate_type": "token_target",
        "subject_key": "Asset:asset-1",
        "window": window,
        "scope": scope,
        "trigger_signature": "trigger",
        "timeline_signature": "timeline",
        "priority": 10,
        "target_type": "Asset",
        "target_id": "asset-1",
        "context_json": {"candidate_id": candidate_id, "factor_snapshot": {"schema_version": "test"}},
        "max_attempts": 3,
        "next_run_at_ms": 3_600_001,
    }


def _run_budget_count(conn: Any, table: str, where_sql: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(
        f"SELECT COALESCE(SUM(enqueue_count), 0) AS count FROM {table} WHERE {where_sql}",
        params,
    ).fetchone()
    return int(row["count"] if row else 0)


def test_enqueue_job_and_claim_due_job_marks_running(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-claim",
            candidate_id="candidate-claim",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-a",
            timeline_signature="timeline-a",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )

        assert repo.claim_due_job(now_ms=999) is None
        claimed = repo.claim_due_job(now_ms=1_000)
    finally:
        conn.close()

    assert claimed is not None
    assert claimed["job_id"] == "job-claim"
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert claimed["updated_at_ms"] == 1_000


def test_edge_state_budget_and_candidate_last_edge_events_are_persisted(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        current_state = {
            "candidate_id": "candidate-edge",
            "candidate_type": "token_target",
            "pulse_status": "token_watch",
            "score_band": "watch",
            "watched_confirmation": True,
            "hard_risks": [],
        }

        observed = repo.record_edge_observation(
            candidate_id="candidate-edge",
            current_state_json=current_state,
            edge_signature="sha256:first",
            observed_at_ms=1_700_000_000_000,
        )
        first_budget = repo.claim_edge_budget(
            candidate_id="candidate-edge",
            hour_bucket_ms=1_699_999_200_000,
            now_ms=1_700_000_000_000,
            max_enqueues=2,
        )
        second_budget = repo.claim_edge_budget(
            candidate_id="candidate-edge",
            hour_bucket_ms=1_699_999_200_000,
            now_ms=1_700_000_100_000,
            max_enqueues=2,
        )
        third_budget = repo.claim_edge_budget(
            candidate_id="candidate-edge",
            hour_bucket_ms=1_699_999_200_000,
            now_ms=1_700_000_200_000,
            max_enqueues=2,
        )
        repo.mark_edge_job_enqueued(
            candidate_id="candidate-edge",
            processed_state_json=current_state,
            edge_events_json=["pulse_status_changed"],
            job_id="job-edge",
            processed_at_ms=1_700_000_000_123,
            commit=True,
        )
        enqueued_edge = repo.edge_state_by_candidate("candidate-edge")
        repo.mark_edge_run_finished(
            candidate_id="candidate-edge",
            agent_run_id="run-edge",
            processed_state_json=current_state,
            edge_events_json=["pulse_status_changed"],
            finished_at_ms=1_700_000_000_456,
        )
        finished_edge = repo.edge_state_by_candidate("candidate-edge")
    finally:
        conn.close()

    assert observed["last_processed_state_json"] == {}
    assert first_budget is True
    assert second_budget is True
    assert third_budget is False
    assert enqueued_edge is not None
    assert enqueued_edge["latest_observed_state_json"] == current_state
    assert enqueued_edge["last_processed_state_json"] == {}
    assert enqueued_edge["last_edge_events_json"] == ["pulse_status_changed"]
    assert enqueued_edge["last_job_id"] == "job-edge"
    assert finished_edge is not None
    assert finished_edge["last_processed_state_json"] == current_state
    assert finished_edge["last_processed_at_ms"] == 1_700_000_000_456


def test_claim_pulse_admission_rejects_target_without_candidate_budget_consumption(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        first = repo.claim_pulse_admission(
            candidate_id="cand-1",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_001,
            target_limit=0,
            candidate_limit=3,
            job_payload=_job_payload("cand-1"),
            edge_state={"score_band": "70-79"},
            edge_events=["pulse_status_changed"],
        )
        job = repo.job_for_candidate("cand-1")
        candidate_budget_count = _run_budget_count(
            conn,
            "pulse_candidate_run_budget",
            "candidate_id = %s",
            ("cand-1",),
        )
    finally:
        conn.close()

    assert first.accepted is False
    assert first.reason == "target_budget_exhausted"
    assert job is None
    assert candidate_budget_count == 0


def test_claim_pulse_admission_rejects_candidate_without_target_budget_consumption(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        claim = repo.claim_pulse_admission(
            candidate_id="cand-candidate-budget",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_001,
            target_limit=3,
            candidate_limit=0,
            job_payload=_job_payload("cand-candidate-budget"),
            edge_state={"score_band": "70-79"},
            edge_events=["pulse_status_changed"],
        )
        target_budget_count = _run_budget_count(
            conn,
            "pulse_target_run_budget",
            "target_type = %s AND target_id = %s",
            ("Asset", "asset-1"),
        )
        job = repo.job_for_candidate("cand-candidate-budget")
    finally:
        conn.close()

    assert claim.accepted is False
    assert claim.reason == "candidate_budget_exhausted"
    assert target_budget_count == 0
    assert job is None


def test_claim_pulse_admission_caps_same_target_across_candidates_windows_and_scopes(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        first = repo.claim_pulse_admission(
            candidate_id="cand-target-a",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_001,
            target_limit=1,
            candidate_limit=3,
            job_payload=_job_payload("cand-target-a", window="1h", scope="all"),
            edge_state={"score_band": "70-79"},
            edge_events=["pulse_status_changed"],
        )
        second = repo.claim_pulse_admission(
            candidate_id="cand-target-b",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_100,
            target_limit=1,
            candidate_limit=3,
            job_payload=_job_payload("cand-target-b", window="4h", scope="matched"),
            edge_state={"score_band": "80-89"},
            edge_events=["pulse_status_changed"],
        )
        target_budget_count = _run_budget_count(
            conn,
            "pulse_target_run_budget",
            "target_type = %s AND target_id = %s AND hour_bucket_ms = %s",
            ("Asset", "asset-1", 3_600_000),
        )
        second_candidate_budget_count = _run_budget_count(
            conn,
            "pulse_candidate_run_budget",
            "candidate_id = %s",
            ("cand-target-b",),
        )
        first_job = repo.job_for_candidate("cand-target-a")
        second_job = repo.job_for_candidate("cand-target-b")
    finally:
        conn.close()

    assert first.accepted is True
    assert second.accepted is False
    assert second.reason == "target_budget_exhausted"
    assert target_budget_count == 1
    assert second_candidate_budget_count == 0
    assert first_job is not None
    assert second_job is None


def test_claim_pulse_admission_enqueues_without_marking_processed_until_run_finishes(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        edge_state = {"pulse_status": "token_watch", "score_band": "70-79"}

        claim = repo.claim_pulse_admission(
            candidate_id="cand-processed",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_001,
            target_limit=3,
            candidate_limit=3,
            job_payload=_job_payload("cand-processed"),
            edge_state=edge_state,
            edge_events=["pulse_status_changed"],
        )
        enqueued_edge = repo.edge_state_by_candidate("cand-processed")
        repo.mark_edge_run_finished(
            candidate_id="cand-processed",
            agent_run_id="run-processed",
            processed_state_json=edge_state,
            edge_events_json=["pulse_status_changed"],
            finished_at_ms=3_600_500,
        )
        finished_edge = repo.edge_state_by_candidate("cand-processed")
    finally:
        conn.close()

    assert claim.accepted is True
    assert claim.job is not None
    assert enqueued_edge is not None
    assert enqueued_edge["latest_observed_state_json"] == edge_state
    assert enqueued_edge["last_processed_state_json"] == {}
    assert enqueued_edge["last_job_id"] == claim.job["job_id"]
    assert enqueued_edge["last_edge_events_json"] == ["pulse_status_changed"]
    assert finished_edge is not None
    assert finished_edge["last_processed_state_json"] == edge_state
    assert finished_edge["last_processed_at_ms"] == 3_600_500


def test_enqueue_job_preserves_active_retry_state_on_signature_churn(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        first = repo.enqueue_job(
            candidate_id="candidate-1",
            candidate_type="token_target",
            subject_key="asset-1",
            target_type="Asset",
            target_id="asset-1",
            window="1h",
            scope="all",
            trigger_signature="trigger-1",
            timeline_signature="timeline-1",
            priority=80,
            status="failed",
            attempt_count=2,
            max_attempts=3,
            next_run_at_ms=1_800_000,
            now_ms=1_700_000,
        )
        second = repo.enqueue_job(
            candidate_id="candidate-1",
            candidate_type="token_target",
            subject_key="asset-1",
            target_type="Asset",
            target_id="asset-1",
            window="1h",
            scope="all",
            trigger_signature="trigger-2",
            timeline_signature="timeline-2",
            priority=90,
            status="pending",
            attempt_count=0,
            max_attempts=3,
            next_run_at_ms=1_700_100,
            now_ms=1_700_100,
        )
    finally:
        conn.close()

    assert first["job_id"] == second["job_id"]
    assert second["status"] == "failed"
    assert second["attempt_count"] == 2
    assert second["trigger_signature"] == "trigger-1"


def test_mark_job_failed_retries_then_dead_and_succeeded_sets_done(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-fail",
            candidate_id="candidate-fail",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-fail",
            timeline_signature="timeline-fail",
            priority=10,
            max_attempts=2,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        first_claim = repo.claim_due_job(now_ms=1_000)
        first_failure = repo.mark_job_failed(first_claim, "model unavailable", now_ms=2_000)
        second_claim = repo.claim_due_job(now_ms=first_failure["next_run_at_ms"])
        second_failure = repo.mark_job_failed(second_claim, "model unavailable again", now_ms=3_000)

        repo.enqueue_job(
            job_id="job-success",
            candidate_id="candidate-success",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-success",
            timeline_signature="timeline-success",
            priority=5,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        success_claim = repo.claim_due_job(now_ms=1_000)
        success = repo.mark_job_succeeded("job-success", now_ms=4_000)
    finally:
        conn.close()

    assert first_failure is not None
    assert first_failure["status"] == "failed"
    assert first_failure["last_error"] == "model unavailable"
    assert second_failure is not None
    assert second_failure["status"] == "dead"
    assert success_claim is not None
    assert success_claim["attempt_count"] == 1
    assert success is not None
    assert success["status"] == "done"
    assert success["last_error"] is None


def test_reenqueue_dead_job_resets_attempts_and_is_claimable(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-reenqueue",
            candidate_id="candidate-reenqueue",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-old",
            timeline_signature="timeline-old",
            priority=10,
            max_attempts=1,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        first_claim = repo.claim_due_job(now_ms=1_000)
        dead = repo.mark_job_failed(first_claim, "exhausted", now_ms=1_100)

        repo.enqueue_job(
            job_id="job-reenqueue-new",
            candidate_id="candidate-reenqueue",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-new",
            timeline_signature="timeline-new",
            priority=10,
            max_attempts=2,
            next_run_at_ms=1_200,
            now_ms=1_200,
        )
        claimed = repo.claim_due_job(now_ms=1_200)
    finally:
        conn.close()

    assert dead is not None
    assert dead["status"] == "dead"
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert claimed["max_attempts"] == 2
    assert claimed["trigger_signature"] == "trigger-new"
    assert claimed["timeline_signature"] == "timeline-new"


def test_claim_due_job_recovers_stale_running_without_exceeding_max_attempts(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn, running_timeout_ms=100)
        repo.enqueue_job(
            job_id="job-stale",
            candidate_id="candidate-stale",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-stale",
            timeline_signature="timeline-stale",
            priority=10,
            max_attempts=2,
            next_run_at_ms=1_000,
            now_ms=900,
        )

        first_claim = repo.claim_due_job(now_ms=1_000)
        early_reclaim = repo.claim_due_job(now_ms=1_050)
        stale_reclaim = repo.claim_due_job(now_ms=1_201)
    finally:
        conn.close()

    assert first_claim is not None
    assert first_claim["status"] == "running"
    assert first_claim["attempt_count"] == 1
    assert early_reclaim is None
    assert stale_reclaim is not None
    assert stale_reclaim["status"] == "running"
    assert stale_reclaim["attempt_count"] == 2


def test_claim_due_job_marks_exhausted_stale_running_dead(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn, running_timeout_ms=100)
        enqueued = repo.enqueue_job(
            job_id="job-stale-dead",
            candidate_id="candidate-stale-dead",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-stale-dead",
            timeline_signature="timeline-stale-dead",
            priority=10,
            max_attempts=1,
            next_run_at_ms=1_000,
            now_ms=900,
        )

        first_claim = repo.claim_due_job(now_ms=1_000)
        stale_reclaim = repo.claim_due_job(now_ms=1_201)
        stored = conn.execute(
            "SELECT * FROM pulse_agent_jobs WHERE job_id = %s",
            (enqueued["job_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert first_claim is not None
    assert first_claim["attempt_count"] == 1
    assert stale_reclaim is None
    assert stored is not None
    assert stored["status"] == "dead"


def test_insert_agent_run_and_finish_agent_run_store_audit_json(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-run",
            candidate_id="candidate-run",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-run",
            timeline_signature="timeline-run",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        run = repo.insert_agent_run(
            run_id="run-1",
            job_id="job-run",
            candidate_id="candidate-run",
            provider="openai",
            model="gpt-5-mini",
            sdk_trace_id="trace-1",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_agent",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-prompt-v1",
            schema_version="pulse-schema-v1",
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-run",
            input_hash="input-hash",
            trace_metadata_json={"candidate_id": "candidate-run"},
            usage_json={"input_tokens": 10},
            status="running",
            outcome="running",
            decision_route="meme",
            decision_stage_count=0,
            request_json={"messages": [{"role": "user", "content": "inspect"}]},
            started_at_ms=1_100,
        )
        finished = repo.finish_agent_run(
            "run-1",
            "done",
            response_json={"verdict": "token_watch"},
            output_hash="output-hash",
            usage_json={"output_tokens": 20},
            outcome="completed",
            decision_route="meme",
            decision_stage_count=3,
            finished_at_ms=1_350,
        )
    finally:
        conn.close()

    assert run["request_json"] == {"messages": [{"role": "user", "content": "inspect"}]}
    assert run["trace_metadata_json"] == {"candidate_id": "candidate-run"}
    assert finished is not None
    assert finished["status"] == "done"
    assert finished["response_json"] == {"verdict": "token_watch"}
    assert finished["usage_json"] == {"output_tokens": 20}
    assert finished["output_hash"] == "output-hash"
    assert finished["latency_ms"] == 250
    assert finished["outcome"] == "completed"
    assert finished["decision_route"] == "meme"
    assert finished["decision_stage_count"] == 3


def test_agent_run_outcome_has_no_database_default_and_finish_requires_explicit_outcome(tmp_path) -> None:
    signature = inspect.signature(PulseRepository.finish_agent_run)
    assert signature.parameters["outcome"].default is inspect.Parameter.empty
    assert signature.parameters["outcome"].kind is inspect.Parameter.KEYWORD_ONLY

    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        row = conn.execute(
            """
            SELECT column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'pulse_agent_runs'
              AND column_name = 'outcome'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["column_default"] is None
    with pytest.raises(TypeError):
        PulseRepository.finish_agent_run(  # type: ignore[call-arg]
            object(),
            "run-missing-outcome",
            "done",
        )


def test_agent_harness_version_round_trip(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        inserted = repo.upsert_agent_harness_version(
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-1",
            strategy="signal_pulse_decision",
            provider="openai",
            model="gpt-5-mini",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"stages": ["analyst", "critic", "judge"]}},
            created_at_ms=1_000,
        )
        fetched = repo.agent_harness_version("sha256:harness-1")
    finally:
        conn.close()

    assert inserted["harness_hash"] == "sha256:harness-1"
    assert fetched is not None
    assert fetched["harness_version"] == "pulse-decision-harness-v1"
    assert fetched["manifest_json"]["runtime"]["stages"] == ["analyst", "critic", "judge"]


def test_agent_harness_versions_keep_distinct_hashes_for_same_model_identity(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        first = repo.upsert_agent_harness_version(
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-a",
            strategy="signal_pulse_decision",
            provider="openai",
            model="qwen3.6",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"timeout_seconds": 30}},
            created_at_ms=1_000,
        )
        second = repo.upsert_agent_harness_version(
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-b",
            strategy="signal_pulse_decision",
            provider="openai",
            model="qwen3.6",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"timeout_seconds": 120}},
            created_at_ms=2_000,
        )
        fetched_first = repo.agent_harness_version("sha256:harness-a")
        fetched_second = repo.agent_harness_version("sha256:harness-b")
    finally:
        conn.close()

    assert first["harness_hash"] == "sha256:harness-a"
    assert second["harness_hash"] == "sha256:harness-b"
    assert fetched_first is not None
    assert fetched_first["manifest_json"]["runtime"]["timeout_seconds"] == 30
    assert fetched_second is not None
    assert fetched_second["manifest_json"]["runtime"]["timeout_seconds"] == 120


def test_mark_stale_agent_runs_failed_closes_orphaned_running_audit_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-stale-run",
            candidate_id="candidate-stale-run",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-stale",
            timeline_signature="timeline-stale",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.upsert_agent_harness_version(
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-stale",
            strategy="signal_pulse_decision",
            provider="openai",
            model="qwen3.6",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"stages": ["analyst", "critic", "judge"]}},
            created_at_ms=1_000,
        )
        repo.insert_agent_run(
            run_id="run-stale",
            job_id="job-stale-run",
            candidate_id="candidate-stale-run",
            provider="openai",
            model="qwen3.6",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            input_hash="input-hash",
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-stale",
            request_json={},
            trace_metadata_json={},
            usage_json={},
            status="running",
            outcome="running",
            decision_route="meme",
            decision_stage_count=0,
            started_at_ms=1_000,
        )

        updated = repo.mark_stale_agent_runs_failed(
            now_ms=11_000,
            stale_before_ms=5_000,
        )
        row = conn.execute("SELECT * FROM pulse_agent_runs WHERE run_id = 'run-stale'").fetchone()
    finally:
        conn.close()

    assert updated == 1
    assert row is not None
    assert row["status"] == "failed"
    assert row["outcome"] == "failed"
    assert row["error"] == "stale_running_timeout"
    assert row["finished_at_ms"] == 11_000
    assert row["latency_ms"] == 10_000


def test_recent_target_failure_count_reads_normalized_trace_reason(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-target-failure",
            candidate_id="candidate-target-failure",
            candidate_type="token_target",
            subject_key="asset-1",
            target_type="Asset",
            target_id="asset-1",
            window="1h",
            scope="all",
            trigger_signature="trigger-failure",
            timeline_signature="timeline-failure",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.insert_agent_run(
            run_id="run-target-failure",
            job_id="job-target-failure",
            candidate_id="candidate-target-failure",
            provider="openai",
            model="gpt-5-mini",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            input_hash="input-hash",
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-failure",
            status="failed",
            outcome="failed",
            decision_route="meme",
            decision_stage_count=1,
            request_json={"candidate_id": "candidate-target-failure"},
            trace_metadata_json={"failure_reason": "unknown_evidence_id"},
            error="unknown evidence ids: event-x",
            started_at_ms=1_100,
            finished_at_ms=1_300,
        )

        count = repo.recent_target_failure_count(
            target_type="Asset",
            target_id="asset-1",
            since_ms=1_000,
            reasons=("unknown_evidence_id", "schema_validation_failed"),
        )
        ignored_reason_count = repo.recent_target_failure_count(
            target_type="Asset",
            target_id="asset-1",
            since_ms=1_000,
            reasons=("provider_unavailable",),
        )
    finally:
        conn.close()

    assert count == 1
    assert ignored_reason_count == 0


def test_insert_agent_run_stores_harness_identity(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-harness-run",
            candidate_id="candidate-harness-run",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-harness",
            timeline_signature="timeline-harness",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.upsert_agent_harness_version(
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-run",
            strategy="signal_pulse_decision",
            provider="openai",
            model="gpt-5-mini",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"stages": ["analyst", "critic", "judge"]}},
            created_at_ms=1_000,
        )
        run = repo.insert_agent_run(
            run_id="run-harness",
            job_id="job-harness-run",
            candidate_id="candidate-harness-run",
            provider="openai",
            model="gpt-5-mini",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            input_hash="input-hash",
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-run",
            status="running",
            outcome="running",
            decision_route="meme",
            decision_stage_count=0,
            request_json={"candidate_id": "candidate-harness-run"},
            started_at_ms=1_100,
        )
    finally:
        conn.close()

    assert run["harness_version"] == "pulse-decision-harness-v1"
    assert run["harness_hash"] == "sha256:harness-run"


def test_agent_run_steps_round_trip(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-run-step",
            candidate_id="candidate-run-step",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-run-step",
            timeline_signature="timeline-run-step",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.insert_agent_run(
            run_id="run-step",
            job_id="job-run-step",
            candidate_id="candidate-run-step",
            provider="openai",
            model="gpt-5-mini",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-step",
            input_hash="input-hash",
            status="running",
            outcome="running",
            decision_route="meme",
            decision_stage_count=0,
            request_json={"target": "asset:sol"},
            started_at_ms=1_100,
        )
        step = repo.insert_agent_run_step(
            step_id="run-step:investigator:0",
            run_id="run-step",
            stage="investigator",
            route="meme",
            attempt_index=0,
            provider="openai",
            model="gpt-5-mini",
            prompt_version="meme-investigator-v1",
            schema_version="pulse_decision_v1",
            input_json={"factor_snapshot": {"schema_version": "token_factor_snapshot_v3_social_attention"}},
            prompt_text="Investigate meme token facts only.",
            response_json={"recommendation": "watchlist", "confidence": 0.42},
            trace_metadata_json={"trace_id": "trace-step"},
            usage_json={"input_tokens": 123, "output_tokens": 45},
            latency_ms=350,
            status="ok",
            error=None,
            started_at_ms=1_101,
            finished_at_ms=1_451,
            created_at_ms=1_451,
        )
        steps = repo.list_agent_run_steps("run-step")
    finally:
        conn.close()

    assert step["step_id"] == "run-step:investigator:0"
    assert steps == [step]
    assert steps[0]["prompt_text"] == "Investigate meme token facts only."
    assert steps[0]["input_json"]["factor_snapshot"]["schema_version"] == "token_factor_snapshot_v3_social_attention"
    assert steps[0]["response_json"] == {"recommendation": "watchlist", "confidence": 0.42}


def test_agent_eval_case_and_result_round_trip(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.enqueue_job(
            job_id="job-eval",
            candidate_id="candidate-eval",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-eval",
            timeline_signature="timeline-eval",
            priority=10,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.upsert_agent_harness_version(
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-eval",
            strategy="signal_pulse_decision",
            provider="openai",
            model="gpt-5-mini",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"stages": ["analyst", "critic", "judge"]}},
            created_at_ms=1_000,
        )
        repo.insert_agent_run(
            run_id="run-eval",
            job_id="job-eval",
            candidate_id="candidate-eval",
            provider="openai",
            model="gpt-5-mini",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            input_hash="input-hash",
            harness_version="pulse-decision-harness-v1",
            harness_hash="sha256:harness-eval",
            status="done",
            outcome="completed",
            decision_route="meme",
            decision_stage_count=3,
            request_json={"candidate_id": "candidate-eval"},
            response_json={"route": "meme", "recommendation": "watchlist"},
            started_at_ms=1_100,
            finished_at_ms=1_300,
        )
        case = repo.insert_agent_eval_case(
            eval_case_id="eval-case-run-eval",
            source_run_id="run-eval",
            harness_hash="sha256:harness-eval",
            eval_type="deterministic",
            route="meme",
            recommendation="watchlist",
            input_json={"run_id": "run-eval"},
            expected_json={"recommendation": "watchlist"},
            rubric_json={"checks": ["final_recommendation_matches"]},
            status="active",
            created_at_ms=1_400,
        )
        result = repo.upsert_agent_eval_result(
            eval_result_id="eval-result-run-eval",
            eval_case_id=case["eval_case_id"],
            harness_hash="sha256:harness-eval",
            status="pass",
            score=1.0,
            grader_version="pulse-deterministic-harness-v1",
            details_json={"violations": []},
            created_at_ms=1_500,
        )
        cases = repo.list_agent_eval_cases(source_run_id="run-eval")
        results = repo.list_agent_eval_results(eval_case_id=case["eval_case_id"])
    finally:
        conn.close()

    assert cases == [case]
    assert result["status"] == "pass"
    assert results == [result]
    assert results[0]["details_json"]["violations"] == []


def test_upsert_candidate_and_list_candidates_contract_filters_and_cursor(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(**_candidate_payload("candidate-newer", updated_at_ms=3_000))
        repo.upsert_candidate(
            **_candidate_payload("candidate-older", symbol="PEPE", subject_key="pepewhale", updated_at_ms=2_000)
        )
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-blocked",
                pulse_status="blocked_low_information",
                verdict="blocked_low_information",
                score_band="blocked",
                updated_at_ms=1_000,
            )
        )

        first_page = repo.list_candidates(window="1h", scope="global", status="token_watch", limit=1)
        second_page = repo.list_candidates(
            window="1h",
            scope="global",
            status="token_watch",
            limit=1,
            cursor=first_page["next_cursor"],
        )
        blocked = repo.list_candidates(window="1h", scope="global", status="blocked_low_information", limit=10)
        handle_filtered = repo.list_candidates(window="1h", scope="global", handle="@pepewhale", limit=10)
        query_filtered = repo.list_candidates(window="1h", scope="global", q="pep", limit=10)
    finally:
        conn.close()

    assert [item["candidate_id"] for item in first_page["items"]] == ["candidate-newer"]
    assert (
        first_page["items"][0]["factor_snapshot_json"]["schema_version"] == "token_factor_snapshot_v3_social_attention"
    )
    assert first_page["items"][0]["decision_route"] == "meme"
    assert first_page["items"][0]["decision_recommendation"] == "watchlist"
    assert first_page["items"][0]["decision_confidence"] == 0.42
    assert "agent_recommendation_json" not in first_page["items"][0]
    assert first_page["items"][0]["gate_reasons_json"] == ["fresh_attention"]
    assert second_page["items"][0]["candidate_id"] == "candidate-older"
    assert second_page["next_cursor"] is None
    assert [item["candidate_id"] for item in blocked["items"]] == ["candidate-blocked"]
    assert [item["candidate_id"] for item in handle_filtered["items"]] == ["candidate-older"]
    assert [item["candidate_id"] for item in query_filtered["items"]] == ["candidate-older"]


def test_upsert_candidate_signature_uses_factor_snapshot_contract() -> None:
    signature = inspect.signature(PulseRepository.upsert_candidate)

    assert "factor_snapshot_json" in signature.parameters
    assert "decision_json" in signature.parameters
    assert "decision_route" in signature.parameters
    assert "decision_recommendation" in signature.parameters
    assert "decision_confidence" in signature.parameters
    assert "agent_recommendation_json" not in signature.parameters
    assert "gate_json" in signature.parameters
    assert "radar_score_json" not in signature.parameters
    assert "market_context_json" not in signature.parameters
    assert "thesis_json" not in signature.parameters


def test_upsert_candidate_persists_factor_snapshot_gate_and_decision(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        row = PulseRepository(conn).upsert_candidate(
            **_candidate_payload(
                "candidate-factor-snapshot",
                factor_snapshot_json={
                    "schema_version": "token_factor_snapshot_v3_social_attention",
                    "subject": {},
                    "gates": {"eligible_for_high_alert": False, "blocked_reasons": ["identity_unresolved"]},
                    "data_health": {"identity": "unresolved", "market": "no_resolved_target"},
                    "families": {},
                    "composite": {"rank_score": 0},
                },
                gate_json={"pulse_status": "blocked_low_information", "candidate_score": 12},
                decision_route="research_only",
                decision_recommendation="abstain",
                decision_confidence=0.0,
                decision_abstain_reason="identity_unresolved",
                decision_stage_count=1,
                decision_json={
                    "route": "research_only",
                    "recommendation": "abstain",
                    "confidence": 0.0,
                    "abstain_reason": "identity_unresolved",
                },
                updated_at_ms=3_000,
            )
        )
    finally:
        conn.close()

    assert row["factor_snapshot_json"] == {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {},
        "gates": {"eligible_for_high_alert": False, "blocked_reasons": ["identity_unresolved"]},
        "data_health": {"identity": "unresolved", "market": "no_resolved_target"},
        "families": {},
        "composite": {"rank_score": 0},
    }
    assert row["gate_json"] == {"pulse_status": "blocked_low_information", "candidate_score": 12}
    assert row["decision_route"] == "research_only"
    assert row["decision_recommendation"] == "abstain"
    assert row["decision_confidence"] == 0.0
    assert row["decision_abstain_reason"] == "identity_unresolved"
    assert row["decision_stage_count"] == 1
    assert row["decision_json"] == {
        "route": "research_only",
        "recommendation": "abstain",
        "confidence": 0.0,
        "abstain_reason": "identity_unresolved",
    }


def test_candidate_upsert_rejects_missing_decision_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        payload = _candidate_payload("candidate-missing-decision", updated_at_ms=3_000)
        del payload["decision_json"]
        try:
            PulseRepository(conn).upsert_candidate(**payload)
        except TypeError as exc:
            error = str(exc)
        else:
            error = ""
    finally:
        conn.close()

    assert "decision_json" in error


def test_pulse_summary_reads_market_fresh_count_from_factor_snapshot_contract() -> None:
    conn = FakePulseSummaryConn()

    summary = PulseRepository(conn).pulse_summary(window="1h", scope="global")

    assert summary["market_ready_rate"] == 1.0
    assert "factor_snapshot_json #>> '{data_health,market}' = 'ready'" in conn.summary_sql
    assert "families,market_quality" not in conn.summary_sql
    assert "market_context_json" not in conn.summary_sql


def test_pulse_summary_counts_market_freshness_from_factor_snapshot(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-fresh-factor",
                factor_snapshot_json={
                    "data_health": {"market": "ready"},
                },
                updated_at_ms=3_000,
            )
        )
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-stale-factor",
                factor_snapshot_json={
                    "data_health": {"market": "partial"},
                },
                updated_at_ms=2_000,
            )
        )

        summary = repo.pulse_summary(window="1h", scope="global")
    finally:
        conn.close()

    assert summary["market_ready_rate"] == 0.5


def test_handle_filter_matches_candidate_source_event_author(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        EvidenceRepository(conn).insert_event(
            make_event("event-watch", author_handle="traderpow", received_at_ms=1_000),
            is_watched=True,
        )
        EvidenceRepository(conn).insert_event(
            make_event("event-other", author_handle="otheralpha", received_at_ms=1_100),
            is_watched=True,
        )
        repo = PulseRepository(conn)
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-watch-source",
                symbol="PEPE",
                subject_key="PEPE",
                source_event_ids=["event-watch"],
                evidence_event_ids=["event-watch"],
                updated_at_ms=3_000,
            )
        )
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-other-source",
                symbol="BONK",
                subject_key="BONK",
                source_event_ids=["event-other"],
                evidence_event_ids=["event-other"],
                updated_at_ms=2_000,
            )
        )

        filtered = repo.list_candidates(window="1h", scope="global", handle="@traderpow", limit=10)
        summary = repo.pulse_summary(window="1h", scope="global", handle="@traderpow")
    finally:
        conn.close()

    assert [item["candidate_id"] for item in filtered["items"]] == ["candidate-watch-source"]
    assert summary["candidate_count"] == 1
    assert summary["summary"]["token_watch"] == 1


def test_candidate_handle_filter_clause_checks_source_event_authors() -> None:
    clause, params = pulse_repository._candidate_handle_filter_clause("candidate", "@TraderPow")

    assert "candidate.subject_key" in clause
    assert "candidate.source_event_ids_json" in clause
    assert "candidate.evidence_event_ids_json" in clause
    assert "jsonb_array_elements_text" in clause
    assert "events" in clause
    assert "social_event_extractions" in clause
    assert params == ["traderpow", "traderpow"]


def test_list_candidates_ignores_malformed_structured_cursor(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(**_candidate_payload("candidate-cursor", updated_at_ms=3_000))
        cursor = base64.urlsafe_b64encode(
            json.dumps({"updated_at_ms": {}, "candidate_id": "x"}).encode("utf-8")
        ).decode("ascii")

        result = repo.list_candidates(window="1h", scope="global", limit=10, cursor=cursor)
        invalid_base64 = repo.list_candidates(window="1h", scope="global", limit=10, cursor="not-a-valid-cursor")
        non_ascii = repo.list_candidates(window="1h", scope="global", limit=10, cursor="☃")
    finally:
        conn.close()

    assert [item["candidate_id"] for item in result["items"]] == ["candidate-cursor"]
    assert [item["candidate_id"] for item in invalid_base64["items"]] == ["candidate-cursor"]
    assert [item["candidate_id"] for item in non_ascii["items"]] == ["candidate-cursor"]


def test_list_candidates_preserves_token_target_risk_enum_semantics(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-risk-token",
                candidate_type="token_target",
                pulse_status="risk_rejected_high_info",
                verdict="risk_rejected_high_info",
                score_band="speculative",
                social_phase="unknown",
                updated_at_ms=2_000,
            )
        )

        risk = repo.list_candidates(window="1h", scope="global", status="risk_rejected_high_info", limit=10)
    finally:
        conn.close()

    assert risk["next_cursor"] is None
    assert [
        {
            "candidate_id": item["candidate_id"],
            "candidate_type": item["candidate_type"],
            "pulse_status": item["pulse_status"],
            "verdict": item["verdict"],
            "score_band": item["score_band"],
            "social_phase": item["social_phase"],
        }
        for item in risk["items"]
    ] == [
        {
            "candidate_id": "candidate-risk-token",
            "candidate_type": "token_target",
            "pulse_status": "risk_rejected_high_info",
            "verdict": "risk_rejected_high_info",
            "score_band": "speculative",
            "social_phase": "unknown",
        }
    ]


def test_get_health_counts_candidates_blocked_low_information_and_dead_jobs(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-trade",
                pulse_status="trade_candidate",
                score_band="high_conviction",
                updated_at_ms=3_000,
            )
        )
        repo.upsert_candidate(
            **_candidate_payload(
                "candidate-low-info",
                pulse_status="blocked_low_information",
                verdict="blocked_low_information",
                score_band="blocked",
                updated_at_ms=2_000,
            )
        )
        repo.enqueue_job(
            job_id="job-dead",
            candidate_id="candidate-dead-job",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-dead",
            timeline_signature="timeline-dead",
            priority=1,
            max_attempts=1,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        claimed = repo.claim_due_job(now_ms=1_000)
        repo.mark_job_failed(claimed, "exhausted", now_ms=1_500)
        health = repo.get_health(window="1h", scope="global")
    finally:
        conn.close()

    assert health["candidate_count"] == 2
    assert health["blocked_low_information_count"] == 1
    assert health["dead_job_count"] == 1


def test_playbook_snapshot_and_outcome_use_explicit_spec_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseRepository(conn)
        repo.upsert_candidate(**_candidate_payload("candidate-playbook", updated_at_ms=3_000))
        snapshot = repo.upsert_playbook_snapshot(
            playbook_id="playbook-1",
            candidate_id="candidate-playbook",
            target_type="cex_token",
            target_id="binance:SOLUSDT",
            horizon="6h",
            decision_time_ms=3_100,
            playbook_status="pending_confirmation",
            side="long",
            setup={"trigger": "social ignition"},
            confirmation={"price": "breakout"},
            invalidation={"social": "attention fades"},
            risk={"max_loss": 0.05},
            entry_market={"price": 145.2},
            playbook_version="playbook-v1",
            outcome_status="pending",
            created_at_ms=3_100,
        )
        outcome = repo.upsert_playbook_outcome(
            playbook_id="playbook-1",
            settled_at_ms=4_000,
            actual_return=0.12,
            benchmark_return=0.04,
            abnormal_return=0.08,
            max_favorable_excursion=0.15,
            max_adverse_excursion=-0.03,
            confirmation_hit=True,
            invalidation_hit=False,
            outcome={"label": "worked"},
            created_at_ms=4_000,
        )
    finally:
        conn.close()

    assert snapshot["playbook_id"] == "playbook-1"
    assert snapshot["setup_json"] == {"trigger": "social ignition"}
    assert snapshot["confirmation_json"] == {"price": "breakout"}
    assert snapshot["invalidation_json"] == {"social": "attention fades"}
    assert snapshot["risk_json"] == {"max_loss": 0.05}
    assert snapshot["entry_market_json"] == {"price": 145.2}
    assert outcome["playbook_id"] == "playbook-1"
    assert outcome["actual_return"] == 0.12
    assert outcome["confirmation_hit"] is True
    assert outcome["outcome_json"] == {"label": "worked"}


def test_repository_session_exposes_pulse_repository(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = repositories_for_connection(conn)
    finally:
        conn.close()

    assert isinstance(repos.pulse, PulseRepository)


def _candidate_payload(
    candidate_id: str,
    *,
    symbol: str = "SOL",
    subject_key: str = "toly",
    candidate_type: str = "token_target",
    pulse_status: str = "token_watch",
    verdict: str | None = None,
    score_band: str = "watch",
    social_phase: str = "ignition",
    source_event_ids: list[str] | None = None,
    evidence_event_ids: list[str] | None = None,
    factor_snapshot_json: dict[str, Any] | None = None,
    gate_json: dict[str, Any] | None = None,
    decision_route: str = "meme",
    decision_recommendation: str = "watchlist",
    decision_confidence: float = 0.42,
    decision_abstain_reason: str | None = None,
    decision_stage_count: int = 3,
    decision_json: dict[str, Any] | None = None,
    updated_at_ms: int,
) -> dict[str, Any]:
    resolved_verdict = verdict if verdict is not None else pulse_status
    return {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "subject_key": subject_key,
        "target_type": "asset",
        "target_id": f"asset:{symbol.lower()}",
        "symbol": symbol,
        "window": "1h",
        "scope": "global",
        "pulse_status": pulse_status,
        "verdict": resolved_verdict,
        "social_phase": social_phase,
        "candidate_score": 0.82,
        "score_band": score_band,
        "trigger_signature": f"trigger:{candidate_id}",
        "timeline_signature": f"timeline:{candidate_id}",
        "factor_snapshot_json": factor_snapshot_json
        or {
            "schema_version": "token_factor_snapshot_v3_social_attention",
            "subject": {"target_type": "asset", "target_id": f"asset:{symbol.lower()}", "symbol": symbol},
            "gates": {"eligible_for_high_alert": True, "blocked_reasons": []},
            "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
            "families": {},
            "composite": {"rank_score": 82},
        },
        "gate_json": gate_json or {"pulse_status": pulse_status, "candidate_score": 82},
        "decision_route": decision_route,
        "decision_recommendation": decision_recommendation,
        "decision_confidence": decision_confidence,
        "decision_abstain_reason": decision_abstain_reason,
        "decision_stage_count": decision_stage_count,
        "decision_json": decision_json
        or {
            "route": decision_route,
            "recommendation": decision_recommendation,
            "confidence": decision_confidence,
            "abstain_reason": decision_abstain_reason,
            "summary_zh": "社交热度有效，但仍需确认。",
            "invalidation_conditions": ["attention fades"],
            "residual_risks": ["thin liquidity"],
            "evidence_event_ids": evidence_event_ids or ["event-1"],
        },
        "gate_reasons_json": ["fresh_attention"],
        "risk_reasons_json": ["thin_liquidity"],
        "evidence_event_ids_json": evidence_event_ids or ["event-1"],
        "source_event_ids_json": source_event_ids or ["event-1"],
        "pulse_version": "pulse-v1",
        "gate_version": "gate-v1",
        "prompt_version": "prompt-v1",
        "schema_version": "schema-v1",
        "created_at_ms": updated_at_ms - 100,
        "updated_at_ms": updated_at_ms,
    }


class FakePulseSummaryConn:
    summary_sql = ""

    def execute(self, sql, params=None):
        text = str(sql)
        if "FROM pulse_candidates" in text and "GROUP BY reason" in text:
            return FakePulseSummaryResult({})
        if "FROM pulse_candidates" in text:
            self.summary_sql = text
            return FakePulseSummaryResult(
                {
                    "candidate_count": 1,
                    "trade_candidate_count": 0,
                    "token_watch_count": 1,
                    "risk_rejected_high_info_count": 0,
                    "blocked_low_information_status_count": 0,
                    "blocked_low_information_count": 0,
                    "displayable_count": 1,
                    "market_fresh_count": (
                        1 if "factor_snapshot_json #>> '{data_health,market}' = 'ready'" in text else 0
                    ),
                }
            )
        return FakePulseSummaryResult({"dead_job_count": 0})


class FakePulseSummaryResult:
    def __init__(self, row: dict[str, Any]):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []
