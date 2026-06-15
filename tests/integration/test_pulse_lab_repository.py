from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.repositories.pulse_jobs_repository import PulseJobsRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_terminalize_exhausted_stale_running_jobs_marks_dead_and_writes_bucket(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _apply_terminal_bucket_column(conn)
        repo = PulseJobsRepository(conn, running_timeout_ms=100)
        _enqueue_claimed_job(
            repo,
            job_id="job-exhausted-stale",
            candidate_id="candidate-exhausted-stale",
            max_attempts=1,
            claim_ms=1_000,
        )
        _enqueue_claimed_job(
            repo,
            job_id="job-retryable-stale",
            candidate_id="candidate-retryable-stale",
            max_attempts=2,
            claim_ms=1_000,
        )
        _enqueue_claimed_job(
            repo,
            job_id="job-exhausted-fresh",
            candidate_id="candidate-exhausted-fresh",
            max_attempts=1,
            claim_ms=1_200,
            priority=100,
        )

        terminalized = repo.terminalize_exhausted_stale_running_jobs(
            now_ms=1_201,
            stale_after_ms=100,
            limit=100,
        )
        rows = conn.execute(
            """
            SELECT job_id, status, attempt_count, last_error
            FROM pulse_agent_jobs
            WHERE job_id IN ('job-exhausted-stale', 'job-retryable-stale', 'job-exhausted-fresh')
            ORDER BY job_id
            """
        ).fetchall()
        terminal_event = conn.execute(
            """
            SELECT worker_name, source_table, target_key, final_status, final_reason, final_reason_bucket
            FROM worker_queue_terminal_events
            WHERE target_key = 'job-exhausted-stale'
            """
        ).fetchone()
    finally:
        conn.close()

    by_job_id = {row["job_id"]: row for row in rows}
    assert terminalized == 1
    assert by_job_id["job-exhausted-stale"]["status"] == "dead"
    assert by_job_id["job-exhausted-stale"]["attempt_count"] == 1
    assert by_job_id["job-exhausted-stale"]["last_error"] == "stale_running_timeout"
    assert by_job_id["job-retryable-stale"]["status"] == "running"
    assert by_job_id["job-exhausted-fresh"]["status"] == "running"
    assert terminal_event is not None
    assert terminal_event["worker_name"] == "pulse_candidate"
    assert terminal_event["source_table"] == "pulse_agent_jobs"
    assert terminal_event["final_status"] == "dead"
    assert terminal_event["final_reason"] == "stale_running_timeout"
    assert terminal_event["final_reason_bucket"] == "stale_window_ttl"


def _enqueue_claimed_job(
    repo: PulseJobsRepository,
    *,
    job_id: str,
    candidate_id: str,
    max_attempts: int,
    claim_ms: int,
    priority: int = 10,
) -> dict[str, Any]:
    repo.enqueue_job(
        job_id=job_id,
        candidate_id=candidate_id,
        candidate_type="token_target",
        subject_key=f"Asset:{candidate_id}",
        window="1h",
        scope="all",
        trigger_signature=f"trigger:{candidate_id}",
        timeline_signature=f"timeline:{candidate_id}",
        priority=priority,
        max_attempts=max_attempts,
        next_run_at_ms=claim_ms,
        now_ms=claim_ms - 100,
    )
    row = repo.conn.execute(
        """
        UPDATE pulse_agent_jobs
        SET status = 'running',
            attempt_count = 1,
            last_error = NULL,
            updated_at_ms = %s
        WHERE job_id = %s
        RETURNING *
        """,
        (claim_ms, job_id),
    ).fetchone()
    repo.conn.commit()
    assert row is not None
    return dict(row)


def _apply_terminal_bucket_column(conn: Any) -> None:
    conn.execute(
        """
        ALTER TABLE worker_queue_terminal_events
        ADD COLUMN IF NOT EXISTS final_reason_bucket TEXT NOT NULL DEFAULT 'other'
        """
    )
    conn.commit()
