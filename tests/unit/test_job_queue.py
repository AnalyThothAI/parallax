from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime import job_queue
from gmgn_twitter_intel.app.runtime.job_queue import (
    ENRICHMENT_JOBS,
    NOTIFICATION_DELIVERIES,
    WATCHLIST_SUMMARY_JOBS,
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
        descriptor=ENRICHMENT_JOBS,
        worker_name="enrichment",
        lease_ms=120_000,
        max_attempts=3,
        now_ms=lambda: 1_000,
    )

    rows = queue.claim_batch(limit=2, conn=conn)

    assert rows == [{"job_id": "job-1"}]
    sql, params = conn.executed[0]
    assert "FROM enrichment_jobs" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "attempt_count = job.attempt_count + 1" in sql
    assert "attempt_count < max_attempts" in sql
    assert params == (1_000, -119_000, 2, 1_000)


def test_watchlist_claim_sets_unique_lease_token_and_expiry(monkeypatch) -> None:
    conn = FakeConn()
    uuids = iter(["aaa111", "bbb222"])
    monkeypatch.setattr(job_queue, "_new_token_suffix", lambda: next(uuids))
    queue = JobQueue(
        descriptor=WATCHLIST_SUMMARY_JOBS,
        worker_name="handle summary",
        lease_ms=60_000,
        max_attempts=3,
        now_ms=lambda: 10_000,
    )

    queue.claim_batch(limit=1, conn=conn)
    queue.claim_batch(limit=1, conn=conn)

    sql, params = conn.executed[0]
    _second_sql, second_params = conn.executed[1]
    assert "FROM watchlist_handle_summary_jobs" in sql
    assert "lease_token = %s" in sql
    assert "lease_expires_at_ms = %s" in sql
    assert "attempt_count < max_attempts" in sql
    assert params == (10_000, 10_000, 1, "worker:handle_summary:aaa111", 70_000, 10_000)
    assert second_params[3] == "worker:handle_summary:bbb222"
    assert params[3] != second_params[3]


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


def test_lease_finalize_requires_token_and_clears_lease_columns() -> None:
    conn = FakeConn(rows=[{"handle": "alice", "status": "done"}], rowcount=1)
    queue = JobQueue(
        descriptor=WATCHLIST_SUMMARY_JOBS,
        worker_name="handle_summary",
        lease_ms=60_000,
        max_attempts=3,
        now_ms=lambda: 30_000,
    )

    with pytest.raises(ValueError, match="lease_token_required"):
        queue.finalize_success("alice", conn=conn)

    row = queue.finalize_success("alice", conn=conn, lease_token="token-1")
    sql, params = conn.executed[0]
    assert row == {"handle": "alice", "status": "done"}
    assert "status = 'running'" in sql
    assert "lease_token = %s" in sql
    assert "lease_token = NULL" in sql
    assert "lease_expires_at_ms = NULL" in sql
    assert params == ("done", 30_000, "alice", "token-1")


def test_lease_finalize_failure_uses_token_and_returns_none_when_lease_lost() -> None:
    conn = FakeConn(rows=[], rowcount=0)
    queue = JobQueue(
        descriptor=WATCHLIST_SUMMARY_JOBS,
        worker_name="handle_summary",
        lease_ms=60_000,
        max_attempts=3,
        now_ms=lambda: 30_000,
    )

    row = queue.finalize_failure("alice", error="lost", conn=conn, lease_token="wrong-token")

    sql, params = conn.executed[0]
    assert row is None
    assert "status = 'running'" in sql
    assert "lease_token = %s" in sql
    assert "lease_token = NULL" in sql
    assert "lease_expires_at_ms = NULL" in sql
    assert params == (30_000, 300_000, 5_000, "lost", 30_000, "alice", "wrong-token")


def test_backoff_policy_defaults_to_linear_five_seconds_capped_at_five_minutes() -> None:
    policy = BackoffPolicy()

    assert policy.delay_ms(1) == 5_000
    assert policy.delay_ms(3) == 15_000
    assert policy.delay_ms(100) == 300_000


def test_reclaim_stale_marks_exhausted_running_jobs_dead() -> None:
    conn = FakeConn()
    queue = JobQueue(
        descriptor=ENRICHMENT_JOBS,
        worker_name="enrichment",
        lease_ms=120_000,
        max_attempts=3,
        now_ms=lambda: 1_000,
    )

    queue.reclaim_stale(conn=conn)

    sql, params = conn.executed[0]
    assert "UPDATE enrichment_jobs" in sql
    assert "CASE WHEN attempt_count >= max_attempts THEN 'dead' ELSE 'failed' END" in sql
    assert "updated_at_ms < %s" in sql
    assert "AND attempt_count >= max_attempts" not in sql
    assert params == (1_000, -119_000)
