from __future__ import annotations

import base64
import inspect
import json
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.pulse_lab.repositories.pulse_admission_repository import PulseAdmissionRepository
from parallax.domains.pulse_lab.repositories.pulse_agent_eval_repository import PulseAgentEvalRepository
from parallax.domains.pulse_lab.repositories.pulse_candidates_repository import PulseCandidatesRepository
from parallax.domains.pulse_lab.repositories.pulse_jobs_repository import PulseJobsRepository
from parallax.domains.pulse_lab.repositories.pulse_playbooks_repository import PulsePlaybooksRepository
from parallax.domains.pulse_lab.repositories.pulse_read_repository import (
    PulseReadRepository,
    _candidate_handle_filter_clause,
)
from parallax.domains.pulse_lab.repositories.pulse_runs_repository import PulseRunsRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def _repo_bundle(conn: Any, *, running_timeout_ms: int = 300_000) -> SimpleNamespace:
    return SimpleNamespace(
        jobs=PulseJobsRepository(conn, running_timeout_ms=running_timeout_ms),
        admission=PulseAdmissionRepository(conn),
        candidates=PulseCandidatesRepository(conn),
        runs=PulseRunsRepository(conn),
        pulse_agent_eval=PulseAgentEvalRepository(conn),
        read=PulseReadRepository(conn),
        playbooks=PulsePlaybooksRepository(conn),
    )


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
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-claim",
            candidate_id="candidate-claim",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-a",
            timeline_signature="timeline-a",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )

        assert repo.jobs.claim_due_job(now_ms=999) is None
        claimed = repo.jobs.claim_due_job(now_ms=1_000)
    finally:
        conn.close()

    assert claimed is not None
    assert claimed["job_id"] == "job-claim"
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert claimed["updated_at_ms"] == 1_000


def test_release_running_job_for_provider_cooldown_delays_without_burning_attempt(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-provider-cooldown",
            candidate_id="candidate-provider-cooldown",
            candidate_type="token_target",
            subject_key="asset-1",
            window="1h",
            scope="all",
            trigger_signature="trigger",
            timeline_signature="timeline",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        claimed = repo.jobs.claim_due_job(now_ms=1_000)
        assert claimed is not None

        released = repo.jobs.release_running_job_for_provider_cooldown(
            claimed,
            reason="provider_cooldown:circuit_open",
            now_ms=1_000,
            cooldown_until_ms=301_000,
        )
    finally:
        conn.close()

    assert released is not None
    assert released["status"] == "pending"
    assert released["next_run_at_ms"] == 301_000
    assert released["attempt_count"] == 0
    assert "provider_cooldown" in released["last_error"]


def test_edge_state_budget_and_candidate_last_edge_events_are_persisted(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        current_state = {
            "candidate_id": "candidate-edge",
            "candidate_type": "token_target",
            "pulse_status": "token_watch",
            "score_band": "watch",
            "watched_confirmation": True,
            "hard_risks": [],
        }

        observed = repo.admission.record_edge_observation(
            candidate_id="candidate-edge",
            current_state_json=current_state,
            edge_signature="sha256:first",
            observed_at_ms=1_700_000_000_000,
        )
        first_budget = repo.admission.claim_edge_budget(
            candidate_id="candidate-edge",
            hour_bucket_ms=1_699_999_200_000,
            now_ms=1_700_000_000_000,
            max_enqueues=2,
        )
        second_budget = repo.admission.claim_edge_budget(
            candidate_id="candidate-edge",
            hour_bucket_ms=1_699_999_200_000,
            now_ms=1_700_000_100_000,
            max_enqueues=2,
        )
        third_budget = repo.admission.claim_edge_budget(
            candidate_id="candidate-edge",
            hour_bucket_ms=1_699_999_200_000,
            now_ms=1_700_000_200_000,
            max_enqueues=2,
        )
        repo.admission.mark_edge_job_enqueued(
            candidate_id="candidate-edge",
            processed_state_json=current_state,
            edge_events_json=["pulse_status_changed"],
            job_id="job-edge",
            processed_at_ms=1_700_000_000_123,
            commit=True,
        )
        enqueued_edge = repo.admission.edge_state_by_candidate("candidate-edge")
        repo.admission.mark_edge_run_finished(
            candidate_id="candidate-edge",
            agent_run_id="run-edge",
            processed_state_json=current_state,
            edge_events_json=["pulse_status_changed"],
            finished_at_ms=1_700_000_000_456,
        )
        finished_edge = repo.admission.edge_state_by_candidate("candidate-edge")
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
        repo = _repo_bundle(conn)
        first = repo.admission.claim_pulse_admission(
            candidate_id="cand-1",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_001,
            target_limit=0,
            candidate_limit=3,
            edge_state={"score_band": "70-79"},
            edge_events=["pulse_status_changed"],
        )
        job = repo.jobs.job_for_candidate("cand-1")
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
        repo = _repo_bundle(conn)
        claim = repo.admission.claim_pulse_admission(
            candidate_id="cand-candidate-budget",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_001,
            target_limit=3,
            candidate_limit=0,
            edge_state={"score_band": "70-79"},
            edge_events=["pulse_status_changed"],
        )
        target_budget_count = _run_budget_count(
            conn,
            "pulse_target_run_budget",
            "target_type = %s AND target_id = %s",
            ("Asset", "asset-1"),
        )
        job = repo.jobs.job_for_candidate("cand-candidate-budget")
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
        repo = _repo_bundle(conn)
        first = repo.admission.claim_pulse_admission(
            candidate_id="cand-target-a",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_001,
            target_limit=1,
            candidate_limit=3,
            edge_state={"score_band": "70-79"},
            edge_events=["pulse_status_changed"],
        )
        second = repo.admission.claim_pulse_admission(
            candidate_id="cand-target-b",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_100,
            target_limit=1,
            candidate_limit=3,
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
        second_job = repo.jobs.job_for_candidate("cand-target-b")
    finally:
        conn.close()

    assert first.accepted is True
    assert second.accepted is False
    assert second.reason == "target_budget_exhausted"
    assert target_budget_count == 1
    assert second_candidate_budget_count == 0
    assert second_job is None


def test_claim_pulse_admission_enqueues_without_marking_processed_until_run_finishes(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        edge_state = {"pulse_status": "token_watch", "score_band": "70-79"}

        claim = repo.admission.claim_pulse_admission(
            candidate_id="cand-processed",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=3_600_000,
            now_ms=3_600_001,
            target_limit=3,
            candidate_limit=3,
            edge_state=edge_state,
            edge_events=["pulse_status_changed"],
        )
        job = repo.jobs.enqueue_job(**_job_payload("cand-processed"))
        repo.admission.mark_edge_job_enqueued(
            candidate_id="cand-processed",
            processed_state_json=edge_state,
            edge_events_json=["pulse_status_changed"],
            job_id=str(job["job_id"]),
            processed_at_ms=3_600_001,
        )
        enqueued_edge = repo.admission.edge_state_by_candidate("cand-processed")
        repo.admission.mark_edge_run_finished(
            candidate_id="cand-processed",
            agent_run_id="run-processed",
            processed_state_json=edge_state,
            edge_events_json=["pulse_status_changed"],
            finished_at_ms=3_600_500,
        )
        finished_edge = repo.admission.edge_state_by_candidate("cand-processed")
    finally:
        conn.close()

    assert claim.accepted is True
    assert enqueued_edge is not None
    assert enqueued_edge["latest_observed_state_json"] == edge_state
    assert enqueued_edge["last_processed_state_json"] == {}
    assert enqueued_edge["last_job_id"] == job["job_id"]
    assert enqueued_edge["last_edge_events_json"] == ["pulse_status_changed"]
    assert finished_edge is not None
    assert finished_edge["last_processed_state_json"] == edge_state
    assert finished_edge["last_processed_at_ms"] == 3_600_500


def test_enqueue_job_preserves_active_retry_state_on_signature_churn(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        first = repo.jobs.enqueue_job(
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
        second = repo.jobs.enqueue_job(
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
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
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
        first_claim = repo.jobs.claim_due_job(now_ms=1_000)
        first_failure = repo.jobs.mark_job_failed(first_claim, "model unavailable", now_ms=2_000)
        second_claim = repo.jobs.claim_due_job(now_ms=first_failure["next_run_at_ms"])
        second_failure = repo.jobs.mark_job_failed(second_claim, "model unavailable again", now_ms=3_000)

        repo.jobs.enqueue_job(
            job_id="job-success",
            candidate_id="candidate-success",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-success",
            timeline_signature="timeline-success",
            priority=5,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        success_claim = repo.jobs.claim_due_job(now_ms=1_000)
        success = repo.jobs.mark_job_succeeded("job-success", now_ms=4_000)
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
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
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
        first_claim = repo.jobs.claim_due_job(now_ms=1_000)
        dead = repo.jobs.mark_job_failed(first_claim, "exhausted", now_ms=1_100)

        repo.jobs.enqueue_job(
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
        claimed = repo.jobs.claim_due_job(now_ms=1_200)
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
        repo = _repo_bundle(conn, running_timeout_ms=100)
        repo.jobs.enqueue_job(
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

        first_claim = repo.jobs.claim_due_job(now_ms=1_000)
        early_reclaim = repo.jobs.claim_due_job(now_ms=1_050)
        stale_reclaim = repo.jobs.claim_due_job(now_ms=1_201)
    finally:
        conn.close()

    assert first_claim is not None
    assert first_claim["status"] == "running"
    assert first_claim["attempt_count"] == 1
    assert early_reclaim is None
    assert stale_reclaim is not None
    assert stale_reclaim["status"] == "running"
    assert stale_reclaim["attempt_count"] == 2


def test_claim_due_job_does_not_globally_release_unclaimed_stale_running_jobs(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn, running_timeout_ms=100)
        for job_id, priority in (("job-stale-a", 20), ("job-stale-b", 10)):
            repo.jobs.enqueue_job(
                job_id=job_id,
                candidate_id=f"candidate-{job_id}",
                candidate_type="token_target",
                subject_key="toly",
                window="1h",
                scope="global",
                trigger_signature=f"trigger-{job_id}",
                timeline_signature=f"timeline-{job_id}",
                priority=priority,
                max_attempts=3,
                next_run_at_ms=1_000,
                now_ms=900,
            )

        first_claim = repo.jobs.claim_due_job(now_ms=1_000)
        second_claim = repo.jobs.claim_due_job(now_ms=1_001)
        reclaimed = repo.jobs.claim_due_job(now_ms=1_202)
        rows = conn.execute(
            """
            SELECT job_id, status, attempt_count, last_error, next_run_at_ms
            FROM pulse_agent_jobs
            WHERE job_id IN ('job-stale-a', 'job-stale-b')
            ORDER BY job_id
            """
        ).fetchall()
    finally:
        conn.close()

    assert first_claim is not None
    assert second_claim is not None
    assert reclaimed is not None
    by_job_id = {row["job_id"]: row for row in rows}
    assert by_job_id["job-stale-a"]["status"] == "running"
    assert by_job_id["job-stale-a"]["attempt_count"] == 2
    assert by_job_id["job-stale-b"]["status"] == "running"
    assert by_job_id["job-stale-b"]["attempt_count"] == 1
    assert by_job_id["job-stale-b"]["last_error"] is None
    assert by_job_id["job-stale-b"]["next_run_at_ms"] == 1_000


def test_claim_due_job_marks_exhausted_stale_running_dead(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn, running_timeout_ms=100)
        enqueued = repo.jobs.enqueue_job(
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

        first_claim = repo.jobs.claim_due_job(now_ms=1_000)
        stale_reclaim = repo.jobs.claim_due_job(now_ms=1_201)
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
    assert stored["status"] == "running"
    assert stored["last_error"] is None


def test_pending_job_counts_and_stale_window_ttl_terminalize_short_window_jobs(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-stale-5m",
            candidate_id="candidate-stale-5m",
            candidate_type="token_target",
            subject_key="toly",
            window="5m",
            scope="all",
            trigger_signature="trigger-5m",
            timeline_signature="timeline-5m",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=1_000,
        )
        repo.jobs.enqueue_job(
            job_id="job-warm-1h",
            candidate_id="candidate-warm-1h",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="all",
            trigger_signature="trigger-1h",
            timeline_signature="timeline-1h",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=1_000,
        )

        before_global = repo.jobs.pending_agent_job_count()
        before_5m = repo.jobs.pending_agent_job_count_for_window_scope(window="5m", scope="all")
        terminalized = repo.jobs.terminalize_stale_jobs_by_window(
            now_ms=302_000,
            ttl_by_window_seconds={"5m": 300},
        )
        after_global = repo.jobs.pending_agent_job_count()
        stale_5m = conn.execute("SELECT * FROM pulse_agent_jobs WHERE job_id = 'job-stale-5m'").fetchone()
        warm_1h = conn.execute("SELECT * FROM pulse_agent_jobs WHERE job_id = 'job-warm-1h'").fetchone()
    finally:
        conn.close()

    assert before_global == 2
    assert before_5m == 1
    assert terminalized == 1
    assert after_global == 1
    assert stale_5m["status"] == "dead"
    assert stale_5m["last_error"] == "stale_window_ttl"
    assert warm_1h["status"] == "pending"


def test_claim_due_job_keeps_priority_before_schedule_age_and_job_id(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-older-low",
            candidate_id="candidate-older-low",
            candidate_type="token_target",
            subject_key="low",
            window="1h",
            scope="all",
            trigger_signature="trigger-low",
            timeline_signature="timeline-low",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=1_000,
        )
        repo.jobs.enqueue_job(
            job_id="job-newer-high",
            candidate_id="candidate-newer-high",
            candidate_type="token_target",
            subject_key="high",
            window="1h",
            scope="all",
            trigger_signature="trigger-high",
            timeline_signature="timeline-high",
            priority=90,
            max_attempts=3,
            next_run_at_ms=2_000,
            now_ms=2_000,
        )

        claimed = repo.jobs.claim_due_job(now_ms=2_000)
    finally:
        conn.close()

    assert claimed is not None
    assert claimed["job_id"] == "job-newer-high"
    assert claimed["priority"] == 90


def test_insert_agent_run_and_finish_agent_run_store_audit_json(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-run",
            candidate_id="candidate-run",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-run",
            timeline_signature="timeline-run",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        run = repo.runs.insert_agent_run(
            run_id="run-1",
            job_id="job-run",
            candidate_id="candidate-run",
            provider="litellm",
            model="gpt-5-mini",
            execution_trace_id="trace-1",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_agent",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-prompt-v1",
            schema_version="pulse-schema-v1",
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-run",
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
        finished = repo.runs.finish_agent_run(
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
    signature = inspect.signature(PulseRunsRepository.finish_agent_run)
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
        PulseRunsRepository.finish_agent_run(  # type: ignore[call-arg]
            object(),
            "run-missing-outcome",
            "done",
        )


def test_agent_runtime_version_round_trip(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        inserted = repo.pulse_agent_eval.upsert_agent_runtime_version(
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-1",
            strategy="signal_pulse_decision",
            provider="litellm",
            model="gpt-5-mini",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"stages": ["analyst", "critic", "judge"]}},
            created_at_ms=1_000,
        )
        fetched = repo.pulse_agent_eval.agent_runtime_version("sha256:runtime-1")
    finally:
        conn.close()

    assert inserted["runtime_hash"] == "sha256:runtime-1"
    assert fetched is not None
    assert fetched["runtime_version"] == "pulse-decision-runtime-v1"
    assert fetched["manifest_json"]["runtime"]["stages"] == ["analyst", "critic", "judge"]


def test_agent_runtime_versions_keep_distinct_hashes_for_same_model_identity(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        first = repo.pulse_agent_eval.upsert_agent_runtime_version(
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-a",
            strategy="signal_pulse_decision",
            provider="litellm",
            model="qwen3.6",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"timeout_seconds": 30}},
            created_at_ms=1_000,
        )
        second = repo.pulse_agent_eval.upsert_agent_runtime_version(
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-b",
            strategy="signal_pulse_decision",
            provider="litellm",
            model="qwen3.6",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"timeout_seconds": 120}},
            created_at_ms=2_000,
        )
        fetched_first = repo.pulse_agent_eval.agent_runtime_version("sha256:runtime-a")
        fetched_second = repo.pulse_agent_eval.agent_runtime_version("sha256:runtime-b")
    finally:
        conn.close()

    assert first["runtime_hash"] == "sha256:runtime-a"
    assert second["runtime_hash"] == "sha256:runtime-b"
    assert fetched_first is not None
    assert fetched_first["manifest_json"]["runtime"]["timeout_seconds"] == 30
    assert fetched_second is not None
    assert fetched_second["manifest_json"]["runtime"]["timeout_seconds"] == 120


def test_mark_stale_agent_runs_failed_closes_orphaned_running_audit_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-stale-run",
            candidate_id="candidate-stale-run",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-stale",
            timeline_signature="timeline-stale",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.pulse_agent_eval.upsert_agent_runtime_version(
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-stale",
            strategy="signal_pulse_decision",
            provider="litellm",
            model="qwen3.6",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"stages": ["analyst", "critic", "judge"]}},
            created_at_ms=1_000,
        )
        repo.runs.insert_agent_run(
            run_id="run-stale",
            job_id="job-stale-run",
            candidate_id="candidate-stale-run",
            provider="litellm",
            model="qwen3.6",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            input_hash="input-hash",
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-stale",
            request_json={},
            trace_metadata_json={},
            usage_json={},
            status="running",
            outcome="running",
            decision_route="meme",
            decision_stage_count=0,
            started_at_ms=1_000,
        )

        updated = repo.jobs.mark_stale_agent_runs_failed(
            now_ms=11_000,
            stale_before_ms=5_000,
        )
        row = conn.execute("SELECT * FROM pulse_agent_runs WHERE run_id = 'run-stale'").fetchone()
    finally:
        conn.close()

    assert updated == 1
    assert row is not None
    assert row["status"] == "failed"
    assert row["outcome"] == "timeout"
    assert row["error"] == "stale_running_timeout"
    assert row["finished_at_ms"] == 11_000
    assert row["latency_ms"] == 10_000


def test_recent_target_failure_count_reads_normalized_trace_reason(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
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
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.runs.insert_agent_run(
            run_id="run-target-failure",
            job_id="job-target-failure",
            candidate_id="candidate-target-failure",
            provider="litellm",
            model="gpt-5-mini",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            input_hash="input-hash",
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-failure",
            status="failed",
            outcome="invalid_unknown_evidence_ref",
            decision_route="meme",
            decision_stage_count=1,
            request_json={"candidate_id": "candidate-target-failure"},
            trace_metadata_json={"failure_reason": "invalid_unknown_evidence_ref"},
            error="unknown evidence ids: event-x",
            started_at_ms=1_100,
            finished_at_ms=1_300,
        )

        count = repo.admission.recent_target_failure_count(
            target_type="Asset",
            target_id="asset-1",
            since_ms=1_000,
            reasons=("invalid_unknown_evidence_ref", "invalid_schema"),
        )
        ignored_reason_count = repo.admission.recent_target_failure_count(
            target_type="Asset",
            target_id="asset-1",
            since_ms=1_000,
            reasons=("provider_unavailable",),
        )
    finally:
        conn.close()

    assert count == 1
    assert ignored_reason_count == 0


def test_insert_agent_run_stores_runtime_identity(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-runtime-run",
            candidate_id="candidate-runtime-run",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-runtime",
            timeline_signature="timeline-runtime",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.pulse_agent_eval.upsert_agent_runtime_version(
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-run",
            strategy="signal_pulse_decision",
            provider="litellm",
            model="gpt-5-mini",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"stages": ["analyst", "critic", "judge"]}},
            created_at_ms=1_000,
        )
        run = repo.runs.insert_agent_run(
            run_id="run-runtime",
            job_id="job-runtime-run",
            candidate_id="candidate-runtime-run",
            provider="litellm",
            model="gpt-5-mini",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            input_hash="input-hash",
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-run",
            status="running",
            outcome="running",
            decision_route="meme",
            decision_stage_count=0,
            request_json={"candidate_id": "candidate-runtime-run"},
            started_at_ms=1_100,
        )
    finally:
        conn.close()

    assert run["runtime_version"] == "pulse-decision-runtime-v1"
    assert run["runtime_hash"] == "sha256:runtime-run"


def test_agent_run_steps_round_trip(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-run-step",
            candidate_id="candidate-run-step",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-run-step",
            timeline_signature="timeline-run-step",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.runs.insert_agent_run(
            run_id="run-step",
            job_id="job-run-step",
            candidate_id="candidate-run-step",
            provider="litellm",
            model="gpt-5-mini",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-step",
            input_hash="input-hash",
            status="running",
            outcome="running",
            decision_route="meme",
            decision_stage_count=0,
            request_json={"target": "asset:sol"},
            started_at_ms=1_100,
        )
        step = repo.runs.insert_agent_run_step(
            step_id="run-step:pulse_decision:0",
            run_id="run-step",
            stage="pulse_decision",
            route="meme",
            attempt_index=0,
            provider="litellm",
            model="gpt-5-mini",
            prompt_version="pulse-decision-v1",
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
        steps = repo.runs.list_agent_run_steps("run-step")
    finally:
        conn.close()

    assert step["step_id"] == "run-step:pulse_decision:0"
    assert steps == [step]
    assert steps[0]["prompt_text"] == "Investigate meme token facts only."
    assert steps[0]["input_json"]["factor_snapshot"]["schema_version"] == "token_factor_snapshot_v3_social_attention"
    assert steps[0]["response_json"] == {"recommendation": "watchlist", "confidence": 0.42}


def test_agent_eval_case_and_result_round_trip(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.jobs.enqueue_job(
            job_id="job-eval",
            candidate_id="candidate-eval",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger-eval",
            timeline_signature="timeline-eval",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        repo.pulse_agent_eval.upsert_agent_runtime_version(
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-eval",
            strategy="signal_pulse_decision",
            provider="litellm",
            model="gpt-5-mini",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            manifest_json={"runtime": {"stages": ["analyst", "critic", "judge"]}},
            created_at_ms=1_000,
        )
        repo.runs.insert_agent_run(
            run_id="run-eval",
            job_id="job-eval",
            candidate_id="candidate-eval",
            provider="litellm",
            model="gpt-5-mini",
            workflow_name="signal_lab_pulse",
            agent_name="pulse_decision_pipeline",
            artifact_version_hash="artifact-hash",
            prompt_version="pulse-decision-v1",
            schema_version="pulse_decision_v1",
            input_hash="input-hash",
            runtime_version="pulse-decision-runtime-v1",
            runtime_hash="sha256:runtime-eval",
            status="done",
            outcome="completed",
            decision_route="meme",
            decision_stage_count=3,
            request_json={"candidate_id": "candidate-eval"},
            response_json={"route": "meme", "recommendation": "watchlist"},
            started_at_ms=1_100,
            finished_at_ms=1_300,
        )
        case = repo.pulse_agent_eval.insert_agent_eval_case(
            eval_case_id="eval-case-run-eval",
            source_run_id="run-eval",
            runtime_hash="sha256:runtime-eval",
            eval_type="deterministic",
            route="meme",
            recommendation="watchlist",
            input_json={"run_id": "run-eval"},
            expected_json={"recommendation": "watchlist"},
            rubric_json={"checks": ["final_recommendation_matches"]},
            status="active",
            created_at_ms=1_400,
        )
        result = repo.pulse_agent_eval.upsert_agent_eval_result(
            eval_result_id="eval-result-run-eval",
            eval_case_id=case["eval_case_id"],
            runtime_hash="sha256:runtime-eval",
            status="pass",
            score=1.0,
            grader_version="pulse-deterministic-eval-v1",
            details_json={"violations": []},
            created_at_ms=1_500,
        )
        cases = repo.pulse_agent_eval.list_agent_eval_cases(source_run_id="run-eval")
        results = repo.pulse_agent_eval.list_agent_eval_results(eval_case_id=case["eval_case_id"])
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
        repo = _repo_bundle(conn)
        repo.candidates.upsert_candidate(**_candidate_payload("candidate-newer", updated_at_ms=3_000))
        repo.candidates.upsert_candidate(
            **_candidate_payload("candidate-older", symbol="PEPE", subject_key="pepewhale", updated_at_ms=2_000)
        )
        repo.candidates.upsert_candidate(
            **_candidate_payload(
                "candidate-blocked",
                symbol="BONK",
                pulse_status="blocked_low_information",
                verdict="blocked_low_information",
                score_band="blocked",
                updated_at_ms=1_000,
            )
        )

        first_page = repo.read.list_candidates(window="1h", scope="global", status="token_watch", limit=1)
        second_page = repo.read.list_candidates(
            window="1h",
            scope="global",
            status="token_watch",
            limit=1,
            cursor=first_page["next_cursor"],
        )
        try:
            repo.read.list_candidates(window="1h", scope="global", status="blocked_low_information", limit=10)
        except ValueError as exc:
            blocked_status_error = str(exc)
        else:
            blocked_status_error = ""
        handle_filtered = repo.read.list_candidates(window="1h", scope="global", handle="@pepewhale", limit=10)
        query_filtered = repo.read.list_candidates(window="1h", scope="global", q="pep", limit=10)
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
    assert "invalid public Signal Pulse status" in blocked_status_error
    assert [item["candidate_id"] for item in handle_filtered["items"]] == ["candidate-older"]
    assert [item["candidate_id"] for item in query_filtered["items"]] == ["candidate-older"]


def test_upsert_candidate_signature_uses_factor_snapshot_contract() -> None:
    signature = inspect.signature(PulseCandidatesRepository.upsert_candidate)

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
        row = _repo_bundle(conn).candidates.upsert_candidate(
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


def test_upsert_candidate_skips_serving_update_when_only_runtime_metadata_changes(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = _repo_bundle(conn)
        repo = repos.candidates
        repos.jobs.enqueue_job(
            job_id="job-stable-projection",
            candidate_id="candidate-stable-projection",
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="global",
            trigger_signature="trigger:candidate-stable-projection",
            timeline_signature="timeline:candidate-stable-projection",
            priority=10,
            max_attempts=3,
            next_run_at_ms=1_000,
            now_ms=900,
        )
        for run_id in ("run-original", "run-retry"):
            repos.runs.insert_agent_run(
                run_id=run_id,
                job_id="job-stable-projection",
                candidate_id="candidate-stable-projection",
                provider="litellm",
                model="gpt-5-mini",
                workflow_name="signal_lab_pulse",
                agent_name="pulse_agent",
                artifact_version_hash="artifact-hash",
                prompt_version="pulse-prompt-v1",
                schema_version="pulse-schema-v1",
                runtime_version="pulse-decision-runtime-v1",
                runtime_hash="sha256:runtime-run",
                input_hash=f"input-{run_id}",
                status="done",
                outcome="completed",
                response_json={"status": "completed"},
                started_at_ms=1_000,
                finished_at_ms=1_100,
            )
        first_payload = _candidate_payload("candidate-stable-projection", updated_at_ms=3_000)
        second_payload = {
            **_candidate_payload("candidate-stable-projection", updated_at_ms=9_000),
            "decision_stage_count": 1,
        }

        first = repo.upsert_candidate(**first_payload)
        second = repo.upsert_candidate(**second_payload)
        stored = conn.execute(
            """
            SELECT decision_stage_count, updated_at_ms
              FROM pulse_candidates
             WHERE candidate_id = %s
            """,
            ("candidate-stable-projection",),
        ).fetchone()
        agent_run_column = conn.execute(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'pulse_candidates'
               AND column_name = 'agent_run_id'
            """
        ).fetchone()
        latest_run = repos.runs.latest_agent_run_for_candidate("candidate-stable-projection")
    finally:
        conn.close()

    assert "agent_run_id" not in first
    assert second is None
    assert dict(stored) == {"decision_stage_count": 3, "updated_at_ms": 3_000}
    assert agent_run_column is None
    assert latest_run is not None
    assert latest_run["run_id"] == "run-retry"


def test_upsert_candidate_uses_product_window_key_across_pulse_versions(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn).candidates
        first = repo.upsert_candidate(**_candidate_payload("candidate-product-v1", updated_at_ms=3_000))
        second_payload = {
            **_candidate_payload("candidate-product-v2", updated_at_ms=9_000),
            "pulse_version": "pulse-v2",
        }
        second = repo.upsert_candidate(**second_payload)
        rows = conn.execute(
            """
            SELECT candidate_id, pulse_version, updated_at_ms
              FROM pulse_candidates
             WHERE candidate_type = 'token_target'
               AND "window" = '1h'
               AND scope = 'global'
               AND target_type = 'asset'
               AND target_id = 'asset:sol'
            """
        ).fetchall()
    finally:
        conn.close()

    assert first["candidate_id"] == "candidate-product-v1"
    assert second["candidate_id"] == "candidate-product-v2"
    assert [dict(row) for row in rows] == [
        {"candidate_id": "candidate-product-v2", "pulse_version": "pulse-v2", "updated_at_ms": 9_000}
    ]


def test_candidate_upsert_rejects_missing_decision_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        payload = _candidate_payload("candidate-missing-decision", updated_at_ms=3_000)
        del payload["decision_json"]
        try:
            _repo_bundle(conn).candidates.upsert_candidate(**payload)
        except TypeError as exc:
            error = str(exc)
        else:
            error = ""
    finally:
        conn.close()

    assert "decision_json" in error


def test_pulse_summary_reads_market_fresh_count_from_factor_snapshot_contract() -> None:
    conn = FakePulseSummaryConn()

    summary = _repo_bundle(conn).read.pulse_summary(window="1h", scope="global")

    assert summary["market_ready_rate"] == 1.0
    assert "evidence_status IN ('complete', 'partial')" in conn.summary_sql
    assert "factor_snapshot_json #>> '{data_health,market}'" not in conn.summary_sql
    assert "market_context_json" not in conn.summary_sql


def test_pulse_summary_counts_market_freshness_from_evidence_packet_status(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.candidates.upsert_candidate(
            **_candidate_payload(
                "candidate-fresh-factor",
                factor_snapshot_json={
                    "data_health": {"market": "ready"},
                },
                updated_at_ms=3_000,
            )
        )
        repo.candidates.upsert_candidate(
            **_candidate_payload(
                "candidate-stale-factor",
                symbol="BONK",
                subject_key="BONK",
                factor_snapshot_json={
                    "data_health": {"market": "ready"},
                },
                evidence_status="insufficient",
                updated_at_ms=2_000,
            )
        )

        summary = repo.read.pulse_summary(window="1h", scope="global")
    finally:
        conn.close()

    assert summary["market_ready_rate"] == 0.5


def test_handle_filter_matches_candidate_subject_key_without_event_author_expansion(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.candidates.upsert_candidate(
            **_candidate_payload(
                "candidate-watch-source",
                symbol="PEPE",
                subject_key="traderpow",
                source_event_ids=["event-watch"],
                evidence_event_ids=["event-watch"],
                updated_at_ms=3_000,
            )
        )
        repo.candidates.upsert_candidate(
            **_candidate_payload(
                "candidate-other-source",
                symbol="BONK",
                subject_key="BONK",
                source_event_ids=["event-other"],
                evidence_event_ids=["event-other"],
                updated_at_ms=2_000,
            )
        )

        filtered = repo.read.list_candidates(window="1h", scope="global", handle="@traderpow", limit=10)
        summary = repo.read.pulse_summary(window="1h", scope="global", handle="@traderpow")
    finally:
        conn.close()

    assert [item["candidate_id"] for item in filtered["items"]] == ["candidate-watch-source"]
    assert summary["candidate_count"] == 1
    assert summary["summary"]["token_watch"] == 1


def test_pulse_handle_filter_does_not_expand_jsonb_event_arrays() -> None:
    clause, params = _candidate_handle_filter_clause("candidate", "@TraderPow")

    assert "candidate.subject_key" in clause
    assert "candidate.source_event_ids_json" not in clause
    assert "candidate.evidence_event_ids_json" not in clause
    assert "jsonb_array_elements_text" not in clause
    assert "events" not in clause
    assert params == ["traderpow"]


def test_list_candidates_ignores_malformed_structured_cursor(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.candidates.upsert_candidate(**_candidate_payload("candidate-cursor", updated_at_ms=3_000))
        cursor = base64.urlsafe_b64encode(
            json.dumps({"updated_at_ms": {}, "candidate_id": "x"}).encode("utf-8")
        ).decode("ascii")

        result = repo.read.list_candidates(window="1h", scope="global", limit=10, cursor=cursor)
        invalid_base64 = repo.read.list_candidates(window="1h", scope="global", limit=10, cursor="not-a-valid-cursor")
        non_ascii = repo.read.list_candidates(window="1h", scope="global", limit=10, cursor="☃")
    finally:
        conn.close()

    assert [item["candidate_id"] for item in result["items"]] == ["candidate-cursor"]
    assert [item["candidate_id"] for item in invalid_base64["items"]] == ["candidate-cursor"]
    assert [item["candidate_id"] for item in non_ascii["items"]] == ["candidate-cursor"]


def test_list_candidates_preserves_token_target_risk_enum_semantics(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.candidates.upsert_candidate(
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

        risk = repo.read.list_candidates(window="1h", scope="global", status="risk_rejected_high_info", limit=10)
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
        repo = _repo_bundle(conn)
        repo.candidates.upsert_candidate(
            **_candidate_payload(
                "candidate-trade",
                pulse_status="trade_candidate",
                score_band="high_conviction",
                updated_at_ms=3_000,
            )
        )
        repo.candidates.upsert_candidate(
            **_candidate_payload(
                "candidate-low-info",
                symbol="BONK",
                subject_key="BONK",
                pulse_status="blocked_low_information",
                verdict="blocked_low_information",
                score_band="blocked",
                updated_at_ms=2_000,
            )
        )
        repo.jobs.enqueue_job(
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
        claimed = repo.jobs.claim_due_job(now_ms=1_000)
        repo.jobs.mark_job_failed(claimed, "exhausted", now_ms=1_500)
        health = repo.read.get_health(window="1h", scope="global")
    finally:
        conn.close()

    assert health["candidate_count"] == 2
    assert health["blocked_low_information_count"] == 1
    assert health["dead_job_count"] == 1


def test_playbook_snapshot_and_outcome_use_explicit_spec_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.candidates.upsert_candidate(**_candidate_payload("candidate-playbook", updated_at_ms=3_000))
        snapshot = repo.playbooks.upsert_playbook_snapshot(
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
        outcome = repo.playbooks.upsert_playbook_outcome(
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


def test_playbook_snapshot_skips_update_when_only_runtime_timestamps_change(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = _repo_bundle(conn)
        repo.candidates.upsert_candidate(**_candidate_payload("candidate-playbook-stable", updated_at_ms=3_000))
        first = repo.playbooks.upsert_playbook_snapshot(
            playbook_id="playbook-stable",
            candidate_id="candidate-playbook-stable",
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
        second = repo.playbooks.upsert_playbook_snapshot(
            playbook_id="playbook-stable",
            candidate_id="candidate-playbook-stable",
            target_type="cex_token",
            target_id="binance:SOLUSDT",
            horizon="6h",
            decision_time_ms=9_100,
            playbook_status="pending_confirmation",
            side="long",
            setup={"trigger": "social ignition"},
            confirmation={"price": "breakout"},
            invalidation={"social": "attention fades"},
            risk={"max_loss": 0.05},
            entry_market={"price": 145.2},
            playbook_version="playbook-v1",
            outcome_status="pending",
            created_at_ms=9_100,
        )
        stored = conn.execute(
            """
            SELECT decision_time_ms, created_at_ms
            FROM pulse_playbook_snapshots
            WHERE playbook_id = 'playbook-stable'
            """
        ).fetchone()
    finally:
        conn.close()

    assert first["decision_time_ms"] == 3_100
    assert second is None
    assert stored["decision_time_ms"] == 3_100
    assert stored["created_at_ms"] == 3_100


def test_repository_session_exposes_focused_pulse_repositories(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = repositories_for_connection(
            conn,
            pulse_job_running_timeout_ms=300_000,
            notification_delivery_running_timeout_ms=300_000,
            notification_delivery_stale_running_terminalization_batch_size=100,
        )
    finally:
        conn.close()

    assert isinstance(repos.pulse_jobs, PulseJobsRepository)
    assert isinstance(repos.pulse_admission, PulseAdmissionRepository)
    assert isinstance(repos.pulse_candidates, PulseCandidatesRepository)
    assert isinstance(repos.pulse_runs, PulseRunsRepository)
    assert isinstance(repos.pulse_agent_eval, PulseAgentEvalRepository)
    assert isinstance(repos.pulse_read, PulseReadRepository)
    assert isinstance(repos.pulse_playbooks, PulsePlaybooksRepository)


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
    evidence_packet_hash: str | None = None,
    evidence_status: str = "complete",
    decision_status: str | None = None,
    display_status: str | None = None,
    updated_at_ms: int,
) -> dict[str, Any]:
    resolved_verdict = verdict if verdict is not None else pulse_status
    resolved_display_status = display_status or _display_status_for_pulse(pulse_status)
    resolved_decision_status = decision_status or _decision_status_for_recommendation(decision_recommendation)
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
        "evidence_packet_hash": evidence_packet_hash if evidence_packet_hash is not None else f"sha256:{candidate_id}",
        "evidence_status": evidence_status,
        "decision_status": resolved_decision_status,
        "display_status": resolved_display_status,
        "created_at_ms": updated_at_ms - 100,
        "updated_at_ms": updated_at_ms,
    }


def _display_status_for_pulse(pulse_status: str) -> str:
    return {
        "trade_candidate": "display_trade_candidate",
        "token_watch": "display_token_watch",
        "risk_rejected_high_info": "display_risk_rejected_high_info",
        "blocked_low_information": "hidden_blocked_low_information",
    }.get(pulse_status, "hidden_insufficient_evidence")


def _decision_status_for_recommendation(recommendation: str) -> str:
    return {
        "high_conviction": "trade_candidate",
        "trade_candidate": "trade_candidate",
        "watchlist": "token_watch",
        "token_watch": "token_watch",
        "ignore": "risk_rejected_high_info",
        "abstain": "abstain",
    }.get(recommendation, "invalid")


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
                    "market_fresh_count": 1 if "evidence_status IN ('complete', 'partial')" in text else 0,
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
