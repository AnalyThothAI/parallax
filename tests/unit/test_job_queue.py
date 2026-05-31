from __future__ import annotations

from typing import Any

import pytest

from parallax.app.runtime.job_queue import (
    NOTIFICATION_DELIVERIES,
    PULSE_AGENT_JOBS,
    BackoffPolicy,
    JobQueue,
)


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(self, rows: list[dict[str, Any]] | None = None, rowcount: int = 0) -> None:
        self.rows = rows or []
        self.rowcount = rowcount
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
        self.executed.append((sql, params))
        return FakeCursor(self.rows, self.rowcount)


def test_job_queue_rejects_non_allowlisted_descriptor() -> None:
    with pytest.raises(ValueError, match="job_queue_not_allowlisted"):
        JobQueue(table="events", worker_name="worker", lease_ms=120_000, max_attempts=3)


def test_claim_batch_uses_allowlisted_table_and_skip_locked() -> None:
    conn = FakeConn(rows=[{"job_id": "job-1"}])
    queue = JobQueue(
        descriptor=PULSE_AGENT_JOBS,
        worker_name="pulse_candidate",
        lease_ms=120_000,
        max_attempts=3,
        now_ms=lambda: 1_000,
    )

    rows = queue.claim_batch(limit=2, conn=conn)

    assert rows == [{"job_id": "job-1"}]
    sql, params = conn.executed[0]
    assert "FROM pulse_agent_jobs" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "attempt_count = job.attempt_count + 1" in sql
    assert "attempt_count < max_attempts" in sql
    assert params == (1_000, -119_000, 2, 1_000)


def test_finalize_success_and_failure_are_descriptor_specific() -> None:
    conn = FakeConn()
    queue = JobQueue(
        descriptor=NOTIFICATION_DELIVERIES,
        worker_name="notification_delivery",
        lease_ms=120_000,
        max_attempts=5,
        now_ms=lambda: 20_000,
    )

    queue.finalize_success("delivery-1", conn=conn)
    queue.finalize_failure("delivery-2", error="boom", conn=conn)

    success_sql, success_params = conn.executed[0]
    failure_sql, failure_params = conn.executed[1]
    assert "UPDATE notification_deliveries" in success_sql
    assert "status = %s" in success_sql
    assert "delivered_at_ms = %s" in success_sql
    assert success_params == ("delivered", 20_000, 20_000, "delivery-1")
    assert "last_error = %s" in failure_sql
    assert "next_run_at_ms = CASE" in failure_sql
    assert "attempt_count >= max_attempts" in failure_sql
    assert "LEAST(%s, %s * GREATEST(1, attempt_count))" in failure_sql
    assert failure_params == (20_000, 300_000, 5_000, "boom", 20_000, "delivery-2")


def test_notification_claim_records_last_attempt_time() -> None:
    conn = FakeConn()
    queue = JobQueue(
        descriptor=NOTIFICATION_DELIVERIES,
        worker_name="notification_delivery",
        lease_ms=120_000,
        max_attempts=5,
        now_ms=lambda: 20_000,
    )

    queue.claim_batch(limit=1, conn=conn)

    sql, params = conn.executed[0]
    assert "last_attempt_at_ms = %s" in sql
    assert params == (20_000, -100_000, 1, 20_000, 20_000)


def test_backoff_policy_defaults_to_linear_five_seconds_capped_at_five_minutes() -> None:
    policy = BackoffPolicy()

    assert policy.delay_ms(1) == 5_000
    assert policy.delay_ms(3) == 15_000
    assert policy.delay_ms(100) == 300_000


def test_reclaim_stale_marks_exhausted_running_jobs_dead() -> None:
    conn = FakeConn()
    queue = JobQueue(
        descriptor=PULSE_AGENT_JOBS,
        worker_name="pulse_candidate",
        lease_ms=120_000,
        max_attempts=3,
        now_ms=lambda: 1_000,
    )

    queue.reclaim_stale(conn=conn)

    sql, params = conn.executed[0]
    assert "UPDATE pulse_agent_jobs" in sql
    assert "CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END" in sql
    assert "updated_at_ms < %s" in sql
    assert "AND attempt_count >= max_attempts" not in sql
    assert params == (1_000, -119_000)
