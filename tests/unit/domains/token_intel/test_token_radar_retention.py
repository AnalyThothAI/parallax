from __future__ import annotations

from typing import Any

import pytest

from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository
from gmgn_twitter_intel.domains.token_intel.services.token_radar_retention import (
    DAY_MS,
    TokenRadarRetentionService,
)


def test_plan_prunable_rows_protects_coverage_and_actual_latest_batches() -> None:
    conn = RetentionSqlConn(rows=[{"row_id": "old-row", "computed_at_ms": 100}])

    rows = TokenRadarRepository(conn).plan_prunable_rows(cutoff_ms=1_000, limit=25)

    assert rows == [{"row_id": "old-row", "computed_at_ms": 100}]
    assert "coverage_batches AS" in conn.last_sql
    assert "actual_latest_batches AS" in conn.last_sql
    assert "protected_batches AS" in conn.last_sql
    assert "MAX(computed_at_ms) AS computed_at_ms" in conn.last_sql
    assert "NOT EXISTS" in conn.last_sql
    assert conn.last_params == (1_000, 25)


def test_delete_prunable_rows_batch_uses_same_protection_and_commits() -> None:
    conn = RetentionSqlConn(rows=[{"row_id": "old-row-1"}, {"row_id": "old-row-2"}])

    deleted = TokenRadarRepository(conn).delete_prunable_rows_batch(cutoff_ms=1_000, batch_size=2)

    assert deleted == 2
    assert "coverage_batches AS" in conn.last_sql
    assert "actual_latest_batches AS" in conn.last_sql
    assert "protected_batches AS" in conn.last_sql
    assert "DELETE FROM token_radar_rows" in conn.last_sql
    assert "RETURNING rows.row_id" in conn.last_sql
    assert conn.last_params == (1_000, 2)
    assert conn.commit_count == 1


def test_protected_batch_counts_reports_coverage_and_actual_latest() -> None:
    conn = RetentionSqlConn(
        one_row={"protected_coverage_batches": 3, "protected_actual_latest_batches": 8},
    )

    counts = TokenRadarRepository(conn).protected_batch_counts()

    assert counts == {"protected_coverage_batches": 3, "protected_actual_latest_batches": 8}
    assert "coverage_batches AS" in conn.last_sql
    assert "actual_latest_batches AS" in conn.last_sql


def test_retention_dry_run_writes_audit_and_deletes_nothing() -> None:
    repo = FakeRetentionRepository(planned_rows=[{"row_id": "old-row"}])

    result = TokenRadarRetentionService(token_radar=repo).prune(
        now_ms=10 * DAY_MS,
        retention_days=7,
        settlement_grace_days=2,
        batch_size=10,
        max_batches=1,
        dry_run=True,
    )

    assert result["mode"] == "dry_run"
    assert result["cutoff_ms"] == 3 * DAY_MS
    assert result["rows_planned"] == 1
    assert result["rows_deleted"] == 0
    assert result["protected_coverage_batches"] == 2
    assert result["protected_actual_latest_batches"] == 4
    assert repo.delete_calls == []
    assert repo.inserted_runs[0]["status"] == "dry_run"
    assert repo.inserted_runs[0]["rows_planned"] == 1


def test_retention_execute_deletes_in_bounded_batches_and_finishes_audit() -> None:
    repo = FakeRetentionRepository(
        planned_rows=[{"row_id": "old-row-1"}, {"row_id": "old-row-2"}, {"row_id": "old-row-3"}],
        delete_results=[2, 1, 99],
    )

    result = TokenRadarRetentionService(token_radar=repo).prune(
        now_ms=10 * DAY_MS,
        retention_days=7,
        settlement_grace_days=2,
        batch_size=2,
        max_batches=2,
        dry_run=False,
        execute=True,
    )

    assert result["mode"] == "execute"
    assert result["rows_planned"] == 3
    assert result["rows_deleted"] == 3
    assert repo.plan_calls == [{"cutoff_ms": 3 * DAY_MS, "limit": 4}]
    assert repo.delete_calls == [
        {"cutoff_ms": 3 * DAY_MS, "batch_size": 2},
        {"cutoff_ms": 3 * DAY_MS, "batch_size": 2},
    ]
    assert repo.inserted_runs[0]["status"] == "running"
    assert repo.finished_runs[-1]["status"] == "done"
    assert repo.finished_runs[-1]["rows_deleted"] == 3


def test_retention_execute_stops_when_batch_deletes_zero_rows() -> None:
    repo = FakeRetentionRepository(planned_rows=[{"row_id": "old-row"}], delete_results=[0, 1])

    result = TokenRadarRetentionService(token_radar=repo).prune(
        now_ms=10 * DAY_MS,
        retention_days=7,
        settlement_grace_days=2,
        batch_size=10,
        max_batches=2,
        dry_run=False,
        execute=True,
    )

    assert result["rows_deleted"] == 0
    assert len(repo.delete_calls) == 1


def test_retention_refuses_unsafe_retention_windows() -> None:
    service = TokenRadarRetentionService(token_radar=FakeRetentionRepository())

    with pytest.raises(ValueError, match="retention_days must be >= 2"):
        service.prune(now_ms=10 * DAY_MS, retention_days=1, settlement_grace_days=0)

    with pytest.raises(ValueError, match="settlement_grace_days"):
        service.prune(now_ms=10 * DAY_MS, retention_days=2, settlement_grace_days=2)

    with pytest.raises(ValueError, match="mutually exclusive"):
        service.prune(now_ms=10 * DAY_MS, dry_run=True, execute=True)


def test_retention_marks_audit_failed_when_delete_raises() -> None:
    repo = FakeRetentionRepository(planned_rows=[{"row_id": "old-row"}], delete_error=RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        TokenRadarRetentionService(token_radar=repo).prune(
            now_ms=10 * DAY_MS,
            retention_days=7,
            settlement_grace_days=2,
            batch_size=10,
            max_batches=1,
            dry_run=False,
            execute=True,
        )

    assert repo.finished_runs[-1]["status"] == "failed"
    assert repo.finished_runs[-1]["rows_deleted"] == 0
    assert repo.finished_runs[-1]["error"] == "boom"


class RetentionSqlConn:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        one_row: dict[str, Any] | None = None,
    ) -> None:
        self.rows = rows or []
        self.one_row = one_row
        self.last_sql = ""
        self.last_params: tuple[Any, ...] = ()
        self.commit_count = 0

    def execute(self, sql: str, params: Any = None) -> RetentionSqlConn:
        self.last_sql = str(sql)
        self.last_params = tuple(params or ())
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.one_row

    def commit(self) -> None:
        self.commit_count += 1


class FakeRetentionRepository:
    def __init__(
        self,
        *,
        planned_rows: list[dict[str, Any]] | None = None,
        delete_results: list[int] | None = None,
        delete_error: Exception | None = None,
    ) -> None:
        self.planned_rows = planned_rows or []
        self.delete_results = list(delete_results or [])
        self.delete_error = delete_error
        self.plan_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.inserted_runs: list[dict[str, Any]] = []
        self.finished_runs: list[dict[str, Any]] = []

    def plan_prunable_rows(self, *, cutoff_ms: int, limit: int) -> list[dict[str, Any]]:
        self.plan_calls.append({"cutoff_ms": int(cutoff_ms), "limit": int(limit)})
        return self.planned_rows[: max(0, int(limit))]

    def protected_batch_counts(self) -> dict[str, int]:
        return {"protected_coverage_batches": 2, "protected_actual_latest_batches": 4}

    def insert_retention_run(self, payload: dict[str, Any], *, commit: bool = True) -> dict[str, Any]:
        del commit
        self.inserted_runs.append(dict(payload))
        return dict(payload)

    def delete_prunable_rows_batch(self, *, cutoff_ms: int, batch_size: int) -> int:
        self.delete_calls.append({"cutoff_ms": int(cutoff_ms), "batch_size": int(batch_size)})
        if self.delete_error is not None:
            raise self.delete_error
        if self.delete_results:
            return self.delete_results.pop(0)
        return 0

    def finish_retention_run(
        self,
        run_id: str,
        *,
        status: str,
        rows_deleted: int,
        error: str | None = None,
    ) -> None:
        self.finished_runs.append(
            {
                "run_id": run_id,
                "status": status,
                "rows_deleted": int(rows_deleted),
                "error": error,
            }
        )
