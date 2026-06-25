from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories.pulse_jobs_repository import PulseJobsRepository

NOW_MS = 1_779_000_000_000
_ROWCOUNT_MISSING = object()


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        (
            "terminalize_exhausted_stale_running_jobs",
            lambda repo: repo.terminalize_exhausted_stale_running_jobs(
                now_ms=NOW_MS,
                stale_after_ms=300_000,
                limit=100,
            ),
        ),
        (
            "mark_job_failed",
            lambda repo: repo.mark_job_failed(
                _job(attempt_count=2, max_attempts=2),
                "provider_error",
                now_ms=NOW_MS,
            ),
        ),
        (
            "mark_job_cancelled_by_worker_timeout",
            lambda repo: repo.mark_job_cancelled_by_worker_timeout(
                _job(attempt_count=2, max_attempts=2),
                now_ms=NOW_MS,
                execution_started=True,
            ),
        ),
        (
            "terminalize_stale_jobs_by_window",
            lambda repo: repo.terminalize_stale_jobs_by_window(
                now_ms=NOW_MS,
                ttl_by_window_seconds={"1h": 3600},
            ),
        ),
    ],
)
def test_pulse_job_terminal_paths_require_connection_transaction_before_job_or_ledger_sql(
    operation: str,
    invoke: Callable[[PulseJobsRepository], object],
) -> None:
    conn = MissingTransactionConnection(operation=operation)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(RuntimeError, match="pulse_jobs_repository_transaction_required"):
        invoke(repo)

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        (
            "enqueue_job",
            lambda repo: repo.enqueue_job(
                candidate_id="candidate-1",
                candidate_type="asset",
                subject_key="solana:abc",
                window="1h",
                scope="default",
                trigger_signature="trigger",
                timeline_signature="timeline",
                priority=10,
                max_attempts=3,
                now_ms=NOW_MS,
            ),
        ),
        (
            "mark_job_succeeded",
            lambda repo: repo.mark_job_succeeded(
                _job(attempt_count=1, max_attempts=3),
                now_ms=NOW_MS,
            ),
        ),
        (
            "release_running_job_for_backpressure",
            lambda repo: repo.release_running_job_for_backpressure(
                _job(attempt_count=1, max_attempts=3),
                reason="agent_no_start",
                now_ms=NOW_MS,
                delay_ms=30_000,
            ),
        ),
        (
            "release_running_job_for_provider_cooldown",
            lambda repo: repo.release_running_job_for_provider_cooldown(
                _job(attempt_count=1, max_attempts=3),
                reason="provider_cooldown",
                now_ms=NOW_MS,
                cooldown_until_ms=NOW_MS + 60_000,
            ),
        ),
        ("mark_stale_agent_runs_failed", lambda repo: repo.mark_stale_agent_runs_failed(now_ms=NOW_MS)),
    ],
)
def test_pulse_job_mutations_require_connection_transaction_before_sql_when_committing(
    operation: str,
    invoke: Callable[[PulseJobsRepository], object],
) -> None:
    conn = MissingTransactionConnection(operation=operation)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(RuntimeError, match="pulse_jobs_repository_transaction_required"):
        invoke(repo)

    assert conn.sql == []
    assert conn.commits == 0


def test_enqueue_job_requires_explicit_max_attempts_before_sql() -> None:
    conn = SqlForbiddenConnection(operation="enqueue_job")
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="max_attempts"):
        repo.enqueue_job(
            candidate_id="candidate-1",
            candidate_type="asset",
            subject_key="solana:abc",
            window="1h",
            scope="default",
            trigger_signature="trigger",
            timeline_signature="timeline",
            priority=10,
            now_ms=NOW_MS,
        )

    assert conn.sql == []


def test_terminalize_exhausted_stale_running_jobs_requires_explicit_limit_before_sql() -> None:
    conn = SqlForbiddenConnection(operation="terminalize_exhausted_stale_running_jobs")
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="limit"):
        repo.terminalize_exhausted_stale_running_jobs(
            now_ms=NOW_MS,
            stale_after_ms=300_000,
        )

    assert conn.sql == []


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("stale_after_ms", 0, "pulse_jobs_stale_after_ms_required"),
        ("stale_after_ms", -1, "pulse_jobs_stale_after_ms_required"),
        ("stale_after_ms", True, "pulse_jobs_stale_after_ms_required"),
        ("stale_after_ms", "300000", "pulse_jobs_stale_after_ms_required"),
        ("limit", 0, "pulse_jobs_terminalize_limit_required"),
        ("limit", -1, "pulse_jobs_terminalize_limit_required"),
        ("limit", True, "pulse_jobs_terminalize_limit_required"),
        ("limit", "100", "pulse_jobs_terminalize_limit_required"),
    ],
)
def test_terminalize_exhausted_stale_running_jobs_rejects_malformed_limits_before_sql(
    field: str,
    value: object,
    error: str,
) -> None:
    conn = MissingTransactionConnection(operation="terminalize_exhausted_stale_running_jobs")
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)
    kwargs: dict[str, object] = {
        "now_ms": NOW_MS,
        "stale_after_ms": 300_000,
        "limit": 100,
    }
    kwargs[field] = value

    with pytest.raises(RuntimeError, match=error):
        repo.terminalize_exhausted_stale_running_jobs(**kwargs)  # type: ignore[arg-type]

    assert conn.sql == []


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        (
            "mark_job_succeeded",
            lambda repo, job: repo.mark_job_succeeded(
                job,
                now_ms=NOW_MS,
            ),
        ),
        (
            "mark_job_failed",
            lambda repo, job: repo.mark_job_failed(
                job,
                "provider_error",
                now_ms=NOW_MS,
            ),
        ),
        (
            "mark_job_cancelled_by_worker_timeout",
            lambda repo, job: repo.mark_job_cancelled_by_worker_timeout(
                job,
                now_ms=NOW_MS,
                execution_started=True,
            ),
        ),
        (
            "release_running_job_for_backpressure",
            lambda repo, job: repo.release_running_job_for_backpressure(
                job,
                reason="agent_no_start",
                now_ms=NOW_MS,
                delay_ms=30_000,
            ),
        ),
        (
            "release_running_job_for_provider_cooldown",
            lambda repo, job: repo.release_running_job_for_provider_cooldown(
                job,
                reason="provider_cooldown",
                now_ms=NOW_MS,
                cooldown_until_ms=NOW_MS + 60_000,
            ),
        ),
    ],
)
def test_pulse_job_claim_mutations_require_attempt_count_from_claim_before_sql(
    operation: str,
    invoke: Callable[[PulseJobsRepository, dict[str, Any]], object],
) -> None:
    conn = MissingTransactionConnection(operation=operation)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)
    job = _job(attempt_count=1, max_attempts=3)
    job.pop("attempt_count")

    with pytest.raises(ValueError, match="pulse_agent_job_claim_attempt_count_required"):
        invoke(repo, job)

    assert conn.sql == []
    assert conn.commits == 0


def test_pulse_job_failure_requires_max_attempts_from_claim_before_sql() -> None:
    conn = MissingTransactionConnection(operation="mark_job_failed")
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)
    job = _job(attempt_count=1, max_attempts=3)
    job.pop("max_attempts")

    with pytest.raises(ValueError, match="pulse_agent_job_claim_max_attempts_required"):
        repo.mark_job_failed(job, "provider_error", now_ms=NOW_MS)

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        (
            "mark_job_succeeded",
            lambda repo, job: repo.mark_job_succeeded(
                job,
                now_ms=NOW_MS,
            ),
        ),
        (
            "mark_job_failed",
            lambda repo, job: repo.mark_job_failed(
                job,
                "provider_error",
                now_ms=NOW_MS,
            ),
        ),
        (
            "mark_job_cancelled_by_worker_timeout",
            lambda repo, job: repo.mark_job_cancelled_by_worker_timeout(
                job,
                now_ms=NOW_MS,
                execution_started=True,
            ),
        ),
        (
            "release_running_job_for_backpressure",
            lambda repo, job: repo.release_running_job_for_backpressure(
                job,
                reason="agent_no_start",
                now_ms=NOW_MS,
                delay_ms=30_000,
            ),
        ),
        (
            "release_running_job_for_provider_cooldown",
            lambda repo, job: repo.release_running_job_for_provider_cooldown(
                job,
                reason="provider_cooldown",
                now_ms=NOW_MS,
                cooldown_until_ms=NOW_MS + 60_000,
            ),
        ),
    ],
)
def test_pulse_job_claim_mutations_require_updated_at_from_claim_before_sql(
    operation: str,
    invoke: Callable[[PulseJobsRepository, dict[str, Any]], object],
) -> None:
    conn = MissingTransactionConnection(operation=operation)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)
    job = _job(attempt_count=1, max_attempts=3)
    job.pop("updated_at_ms")

    with pytest.raises(ValueError, match="pulse_agent_job_claim_updated_at_ms_required"):
        invoke(repo, job)

    assert conn.sql == []
    assert conn.commits == 0


def test_pulse_job_repository_requires_positive_running_timeout() -> None:
    with pytest.raises(RuntimeError, match="pulse_job_running_timeout_ms_required"):
        PulseJobsRepository(SqlForbiddenConnection(operation="init"), running_timeout_ms=0)


def test_pulse_job_enqueue_requires_positive_max_attempts_before_sql() -> None:
    conn = SqlForbiddenConnection(operation="enqueue_job")
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(RuntimeError, match="pulse_agent_job_max_attempts_required"):
        repo.enqueue_job(
            candidate_id="candidate-1",
            candidate_type="asset",
            subject_key="solana:abc",
            window="1h",
            scope="default",
            trigger_signature="trigger",
            timeline_signature="timeline",
            priority=10,
            max_attempts=0,
            now_ms=NOW_MS,
        )

    assert conn.sql == []


def test_mark_stale_agent_runs_failed_requires_cursor_rowcount() -> None:
    conn = RowcountConnection(rowcount=_ROWCOUNT_MISSING)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_required"):
        repo.mark_stale_agent_runs_failed(now_ms=NOW_MS, commit=False)

    assert len(conn.sql) == 1


@pytest.mark.parametrize("rowcount", (True, False, "1", None, -1))
def test_mark_stale_agent_runs_failed_rejects_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = RowcountConnection(rowcount=rowcount)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_invalid"):
        repo.mark_stale_agent_runs_failed(now_ms=NOW_MS, commit=False)

    assert len(conn.sql) == 1


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        (
            "terminalize_exhausted_stale_running_jobs",
            lambda repo: repo.terminalize_exhausted_stale_running_jobs(
                now_ms=NOW_MS,
                stale_after_ms=300_000,
                limit=100,
            ),
        ),
        (
            "terminalize_stale_jobs_by_window",
            lambda repo: repo.terminalize_stale_jobs_by_window(
                now_ms=NOW_MS,
                ttl_by_window_seconds={"1h": 3600},
            ),
        ),
    ],
)
def test_pulse_job_terminal_returning_counts_require_cursor_rowcount(
    operation: str,
    invoke: Callable[[PulseJobsRepository], object],
) -> None:
    conn = ReturningRowsConnection(rowcount=_ROWCOUNT_MISSING, rows=[_job(attempt_count=2, max_attempts=2)])
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_required"):
        invoke(repo)

    assert conn.operation_sql_count(operation) == 1
    assert conn.terminal_ledger_calls == 0


@pytest.mark.parametrize("rowcount", (True, False, "1", None, -1, 0, 2))
def test_pulse_job_terminal_returning_counts_reject_invalid_or_mismatched_rowcount(rowcount: object) -> None:
    conn = ReturningRowsConnection(rowcount=rowcount, rows=[_job(attempt_count=2, max_attempts=2)])
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_invalid"):
        repo.terminalize_exhausted_stale_running_jobs(
            now_ms=NOW_MS,
            stale_after_ms=300_000,
            limit=100,
        )

    assert conn.operation_sql_count("terminalize_exhausted_stale_running_jobs") == 1
    assert conn.terminal_ledger_calls == 0


def test_pulse_job_required_single_returning_writes_require_cursor_rowcount() -> None:
    conn = SingleReturningConnection(
        rowcount=_ROWCOUNT_MISSING,
        row=_job(attempt_count=0, max_attempts=3, status="pending"),
    )
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_required"):
        repo.enqueue_job(
            candidate_id="candidate-1",
            candidate_type="asset",
            subject_key="solana:abc",
            window="1h",
            scope="default",
            trigger_signature="trigger",
            timeline_signature="timeline",
            priority=10,
            max_attempts=3,
            now_ms=NOW_MS,
        )

    assert conn.returning_sql_count == 1


@pytest.mark.parametrize("rowcount", (True, False, "1", None, -1, 0, 2))
def test_pulse_job_required_single_returning_writes_reject_invalid_or_non_single_rowcount(
    rowcount: object,
) -> None:
    conn = SingleReturningConnection(
        rowcount=rowcount,
        row=_job(attempt_count=0, max_attempts=3, status="pending"),
    )
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_invalid"):
        repo.enqueue_job(
            candidate_id="candidate-1",
            candidate_type="asset",
            subject_key="solana:abc",
            window="1h",
            scope="default",
            trigger_signature="trigger",
            timeline_signature="timeline",
            priority=10,
            max_attempts=3,
            now_ms=NOW_MS,
        )

    assert conn.returning_sql_count == 1


def test_pulse_job_required_single_returning_writes_reject_rowcount_one_without_row() -> None:
    conn = SingleReturningConnection(rowcount=1, row=None)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_invalid"):
        repo.enqueue_job(
            candidate_id="candidate-1",
            candidate_type="asset",
            subject_key="solana:abc",
            window="1h",
            scope="default",
            trigger_signature="trigger",
            timeline_signature="timeline",
            priority=10,
            max_attempts=3,
            now_ms=NOW_MS,
        )

    assert conn.returning_sql_count == 1


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        ("claim_due_job", lambda repo: repo.claim_due_job(now_ms=NOW_MS)),
        (
            "mark_job_succeeded",
            lambda repo: repo.mark_job_succeeded(
                _job(attempt_count=1, max_attempts=3),
                now_ms=NOW_MS,
            ),
        ),
        (
            "mark_job_failed",
            lambda repo: repo.mark_job_failed(
                _job(attempt_count=1, max_attempts=3),
                "provider_error",
                now_ms=NOW_MS,
            ),
        ),
        (
            "retry_terminal_job_from_snapshot",
            lambda repo: repo.retry_terminal_job_from_snapshot(
                {"job_id": "pulse-job-1"},
                now_ms=NOW_MS,
                reason="operator_retry",
            ),
        ),
        (
            "mark_job_cancelled_by_worker_timeout",
            lambda repo: repo.mark_job_cancelled_by_worker_timeout(
                _job(attempt_count=1, max_attempts=3),
                now_ms=NOW_MS,
                execution_started=True,
            ),
        ),
        (
            "release_running_job_for_backpressure",
            lambda repo: repo.release_running_job_for_backpressure(
                _job(attempt_count=1, max_attempts=3),
                reason="agent_no_start",
                now_ms=NOW_MS,
                delay_ms=30_000,
            ),
        ),
        (
            "release_running_job_for_provider_cooldown",
            lambda repo: repo.release_running_job_for_provider_cooldown(
                _job(attempt_count=1, max_attempts=3),
                reason="provider_cooldown",
                now_ms=NOW_MS,
                cooldown_until_ms=NOW_MS + 60_000,
            ),
        ),
    ],
)
def test_pulse_job_optional_single_returning_writes_require_cursor_rowcount(
    operation: str,
    invoke: Callable[[PulseJobsRepository], object],
) -> None:
    conn = SingleReturningConnection(
        rowcount=_ROWCOUNT_MISSING,
        row=_job(attempt_count=1, max_attempts=3, status="failed"),
    )
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_required"):
        invoke(repo)

    assert conn.operation_sql_count(operation) == 1
    assert conn.terminal_ledger_calls == 0


@pytest.mark.parametrize("rowcount", (True, False, "1", None, -1, 2, 0))
def test_pulse_job_optional_single_returning_writes_reject_invalid_or_mismatched_rowcount(
    rowcount: object,
) -> None:
    conn = SingleReturningConnection(
        rowcount=rowcount,
        row=_job(attempt_count=1, max_attempts=3, status="failed"),
    )
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_invalid"):
        repo.claim_due_job(now_ms=NOW_MS)

    assert conn.operation_sql_count("claim_due_job") == 1


def test_pulse_job_optional_single_returning_writes_reject_rowcount_one_without_row() -> None:
    conn = SingleReturningConnection(rowcount=1, row=None)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    with pytest.raises(TypeError, match="pulse_jobs_repository_rowcount_invalid"):
        repo.claim_due_job(now_ms=NOW_MS)

    assert conn.operation_sql_count("claim_due_job") == 1


def test_pulse_job_optional_single_returning_writes_accept_zero_without_row() -> None:
    conn = SingleReturningConnection(rowcount=0, row=None)
    repo = PulseJobsRepository(conn, running_timeout_ms=300_000)

    assert repo.claim_due_job(now_ms=NOW_MS) is None
    assert conn.operation_sql_count("claim_due_job") == 1


def _job(*, attempt_count: int, max_attempts: int, status: str = "running") -> dict[str, Any]:
    return {
        "job_id": "pulse-job-1",
        "candidate_id": "candidate-1",
        "candidate_type": "asset",
        "subject_key": "solana:abc",
        "window": "1h",
        "scope": "default",
        "status": status,
        "attempt_count": attempt_count,
        "max_attempts": max_attempts,
        "created_at_ms": NOW_MS - 600_000,
        "updated_at_ms": NOW_MS - 600_000,
    }


class MissingTransactionConnection:
    transaction = None

    def __init__(self, *, operation: str) -> None:
        self.operation = operation
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> object:
        self.sql.append(sql)
        raise AssertionError(f"{self.operation} must require transaction before SQL")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError(f"{self.operation} must not manually commit without transaction")


class SqlForbiddenConnection:
    def __init__(self, *, operation: str) -> None:
        self.operation = operation
        self.sql: list[str] = []

    def transaction(self) -> _NoopTransaction:
        return _NoopTransaction()

    def execute(self, sql: str, params: Any = None) -> object:
        self.sql.append(sql)
        raise AssertionError(f"{self.operation} must validate required policy before SQL")


class RowcountConnection:
    def __init__(self, *, rowcount: object) -> None:
        self.rowcount = rowcount
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> object:
        self.sql.append(sql)
        return RowcountCursor(rowcount=self.rowcount)


class RowcountCursor:
    def __init__(self, *, rowcount: object) -> None:
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount


class ReturningRowsConnection:
    def __init__(self, *, rowcount: object, rows: list[dict[str, Any]]) -> None:
        self.rowcount = rowcount
        self.rows = rows
        self.sql: list[str] = []
        self.terminal_ledger_calls = 0

    def transaction(self) -> _NoopTransaction:
        return _NoopTransaction()

    def execute(self, sql: str, params: Any = None) -> object:
        text = str(sql)
        self.sql.append(text)
        if "UPDATE pulse_agent_jobs" in text and ("RETURNING *" in text or "RETURNING job.*" in text):
            return ReturningRowsCursor(rowcount=self.rowcount, rows=self.rows)
        if "worker_queue_terminal_events" in text:
            self.terminal_ledger_calls += 1
        raise AssertionError("terminal ledger SQL must not run before returning rowcount validation")

    def operation_sql_count(self, operation: str) -> int:
        if operation == "terminalize_exhausted_stale_running_jobs":
            needle = "AND attempt_count >= max_attempts"
        else:
            needle = "last_error = 'stale_window_ttl'"
        return sum(1 for text in self.sql if needle in text)


class ReturningRowsCursor:
    def __init__(self, *, rowcount: object, rows: list[dict[str, Any]]) -> None:
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class SingleReturningConnection:
    def __init__(self, *, rowcount: object, row: dict[str, Any] | None) -> None:
        self.rowcount = rowcount
        self.row = row
        self.sql: list[str] = []
        self.terminal_ledger_calls = 0

    def transaction(self) -> _NoopTransaction:
        return _NoopTransaction()

    def execute(self, sql: str, params: Any = None) -> object:
        text = str(sql)
        self.sql.append(text)
        if "pulse_agent_jobs" in text and "RETURNING" in text:
            return SingleReturningCursor(rowcount=self.rowcount, row=self.row)
        if "worker_queue_terminal_events" in text:
            self.terminal_ledger_calls += 1
        raise AssertionError("terminal ledger SQL must not run before returning rowcount validation")

    @property
    def returning_sql_count(self) -> int:
        return sum(1 for text in self.sql if "pulse_agent_jobs" in text and "RETURNING" in text)

    def operation_sql_count(self, operation: str) -> int:
        needles = {
            "claim_due_job": "WITH picked AS",
            "mark_job_succeeded": "SET status = 'done'",
            "mark_job_failed": "next_run_at_ms = %s",
            "retry_terminal_job_from_snapshot": "AND status = 'dead'",
            "mark_job_cancelled_by_worker_timeout": "worker_timeout_after_execution",
            "release_running_job_for_backpressure": "GREATEST(0, attempt_count - 1)",
            "release_running_job_for_provider_cooldown": "ELSE attempt_count",
        }
        needle = needles[operation]
        return sum(1 for text in self.sql if needle in text)


class SingleReturningCursor:
    def __init__(self, *, rowcount: object, row: dict[str, Any] | None) -> None:
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount
        self.row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _NoopTransaction:
    def __enter__(self) -> _NoopTransaction:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None
