from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.token_intel.interfaces import (
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
)
from parallax.domains.token_intel.repositories.projection_repository import ProjectionRepository

_REQUIRED_CONTROL_WRITE_CASE_NAMES = ("advance_offset", "start_run", "finish_run", "enqueue_dirty_range")


def test_projection_repository_diagnostic_reads_require_explicit_limits_without_defaults() -> None:
    repo = ProjectionRepository(object())

    with pytest.raises(TypeError, match="limit"):
        repo.list_runs(projection_name=TOKEN_RADAR_PROJECTION_NAME)
    with pytest.raises(TypeError, match="limit"):
        repo.list_dirty_ranges(projection_name=TOKEN_RADAR_PROJECTION_NAME)


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, limit: repo.list_runs(limit=limit), id="list-runs"),
        pytest.param(
            lambda repo, limit: repo.claim_dirty_ranges(
                projection_name=TOKEN_RADAR_PROJECTION_NAME,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                limit=limit,
                commit=False,
            ),
            id="claim-dirty-ranges",
        ),
        pytest.param(lambda repo, limit: repo.list_dirty_ranges(limit=limit), id="list-dirty-ranges"),
    ],
)
@pytest.mark.parametrize("limit", [-1, True, "10"])
def test_projection_repository_limits_reject_malformed_before_sql(
    operation: Callable[[ProjectionRepository, object], object],
    limit: object,
) -> None:
    conn = FakeProjectionConnection()

    with pytest.raises(ValueError, match="projection_repository_limit_required"):
        operation(ProjectionRepository(conn), limit)

    assert conn.sql == []


def test_projection_repository_mutations_require_connection_transaction_before_sql_when_committing() -> None:
    cases = _repository_cases()
    for case in cases:
        conn = NoTransactionProjectionConnection()

        with pytest.raises(RuntimeError, match="projection_repository_transaction_required"):
            case.write(conn)

        assert conn.sql == []


def test_projection_repository_commit_owned_writes_use_connection_transaction_without_manual_commit() -> None:
    cases = _repository_cases()
    for case in cases:
        conn = FakeProjectionConnection()

        case.write(conn)

        assert conn.transaction_entries == 1, case.name
        assert conn.transaction_exits == ["ok"], case.name
        assert conn.manual_commits == 0, case.name
        assert conn.sql, case.name
        assert set(conn.sql_depths) == {1}, case.name


def test_projection_repository_stale_run_accounting_requires_cursor_rowcount() -> None:
    conn = FakeProjectionConnection(omit_rowcount=True)

    with pytest.raises(TypeError, match="projection_repository_rowcount_required"):
        ProjectionRepository(conn).mark_stale_running_runs(
            projection_name=TOKEN_RADAR_PROJECTION_NAME,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            stale_before_ms=1_777_799_000_000,
            finished_at_ms=1_777_800_000_000,
            commit=False,
        )


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_projection_repository_stale_run_accounting_rejects_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = FakeProjectionConnection(rowcount=rowcount)

    with pytest.raises(TypeError, match="projection_repository_rowcount_invalid"):
        ProjectionRepository(conn).mark_stale_running_runs(
            projection_name=TOKEN_RADAR_PROJECTION_NAME,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            stale_before_ms=1_777_799_000_000,
            finished_at_ms=1_777_800_000_000,
            commit=False,
        )


def test_projection_repository_claim_dirty_ranges_requires_cursor_rowcount() -> None:
    conn = FakeProjectionConnection(claim_omit_rowcount=True)

    with pytest.raises(TypeError, match="projection_repository_rowcount_required"):
        ProjectionRepository(conn).claim_dirty_ranges(
            projection_name=TOKEN_RADAR_PROJECTION_NAME,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            limit=10,
            commit=False,
        )


@pytest.mark.parametrize("rowcount", [True, False, "1", -1, 0, 2])
def test_projection_repository_claim_dirty_ranges_rejects_invalid_or_mismatched_rowcount(rowcount: object) -> None:
    conn = FakeProjectionConnection(claim_rowcount=rowcount)

    with pytest.raises(TypeError, match="projection_repository_rowcount_invalid"):
        ProjectionRepository(conn).claim_dirty_ranges(
            projection_name=TOKEN_RADAR_PROJECTION_NAME,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            limit=10,
            commit=False,
        )


def test_projection_repository_claim_dirty_ranges_accepts_zero_rowcount_with_no_rows() -> None:
    conn = FakeProjectionConnection(claim_rows=[], claim_rowcount=0)

    rows = ProjectionRepository(conn).claim_dirty_ranges(
        projection_name=TOKEN_RADAR_PROJECTION_NAME,
        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        limit=10,
        commit=False,
    )

    assert rows == []


@pytest.mark.parametrize("case_name", _REQUIRED_CONTROL_WRITE_CASE_NAMES)
def test_projection_repository_required_control_writes_require_cursor_rowcount(case_name: str) -> None:
    case = _required_control_write_case(case_name)
    conn = FakeProjectionConnection(omit_rowcount=True)

    with pytest.raises(TypeError, match="projection_repository_rowcount_required"):
        case.write(conn)


@pytest.mark.parametrize("case_name", _REQUIRED_CONTROL_WRITE_CASE_NAMES)
@pytest.mark.parametrize("rowcount", [True, False, "1", -1, 0, 2])
def test_projection_repository_required_control_writes_reject_invalid_or_unexpected_rowcount(
    case_name: str,
    rowcount: object,
) -> None:
    case = _required_control_write_case(case_name)
    conn = FakeProjectionConnection(rowcount=rowcount)

    with pytest.raises(TypeError, match="projection_repository_rowcount_invalid"):
        case.write(conn)


def test_projection_repository_start_run_requires_returned_row_when_rowcount_is_one() -> None:
    conn = FakeProjectionConnection(start_run_row=None)

    with pytest.raises(TypeError, match="projection_repository_rowcount_invalid"):
        ProjectionRepository(conn).start_run(
            projection_name=TOKEN_RADAR_PROJECTION_NAME,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            mode="rebuild",
            source_start_ms=0,
            source_end_ms=1_777_800_000_000,
            run_id="run-1",
            commit=False,
        )


def _repository_cases() -> list[RepositoryCase]:
    return [
        RepositoryCase(
            name="advance_offset",
            write=lambda conn: ProjectionRepository(conn).advance_offset(
                projection_name=TOKEN_RADAR_PROJECTION_NAME,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                source_table=TOKEN_RADAR_SOURCE_TABLE,
                source_max_received_at_ms=1_777_800_000_000,
                source_max_id="row-1",
                last_run_id="run-1",
                lag_ms=100,
            ),
        ),
        RepositoryCase(
            name="start_run",
            write=lambda conn: ProjectionRepository(conn).start_run(
                projection_name=TOKEN_RADAR_PROJECTION_NAME,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                mode="rebuild",
                source_start_ms=0,
                source_end_ms=1_777_800_000_000,
                run_id="run-1",
            ),
        ),
        RepositoryCase(
            name="mark_stale_running_runs",
            write=lambda conn: ProjectionRepository(conn).mark_stale_running_runs(
                projection_name=TOKEN_RADAR_PROJECTION_NAME,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                stale_before_ms=1_777_799_000_000,
                finished_at_ms=1_777_800_000_000,
            ),
        ),
        RepositoryCase(
            name="finish_run",
            write=lambda conn: ProjectionRepository(conn).finish_run(
                run_id="run-1",
                status="ready",
                rows_read=10,
                rows_written=2,
                dirty_ranges_written=0,
            ),
        ),
        RepositoryCase(
            name="enqueue_dirty_range",
            write=lambda conn: ProjectionRepository(conn).enqueue_dirty_range(
                projection_name=TOKEN_RADAR_PROJECTION_NAME,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                entity_type="token",
                entity_key="asset-1",
                window="1h",
                scope="all",
                start_ms=1_777_799_000_000,
                end_ms=1_777_800_000_000,
                reason="test",
            ),
        ),
        RepositoryCase(
            name="claim_dirty_ranges",
            write=lambda conn: ProjectionRepository(conn).claim_dirty_ranges(
                projection_name=TOKEN_RADAR_PROJECTION_NAME,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                limit=10,
            ),
        ),
    ]


def _required_control_write_case(case_name: str) -> RepositoryCase:
    for case in _repository_cases():
        if case.name == case_name:
            return case
    raise AssertionError(case_name)


class RepositoryCase:
    def __init__(self, *, name: str, write: Callable[[Any], Any]) -> None:
        self.name = name
        self.write = write


_CLAIM_ROWCOUNT_FROM_ROWS = object()
_START_RUN_ROW_FROM_PARAMS = object()


class FakeProjectionConnection:
    def __init__(
        self,
        *,
        rowcount: object = 1,
        omit_rowcount: bool = False,
        start_run_row: dict[str, Any] | None | object = _START_RUN_ROW_FROM_PARAMS,
        claim_rows: list[dict[str, Any]] | None = None,
        claim_rowcount: object = _CLAIM_ROWCOUNT_FROM_ROWS,
        claim_omit_rowcount: bool = False,
    ) -> None:
        self.sql: list[str] = []
        self.sql_depths: list[int] = []
        self.transaction_entries = 0
        self.transaction_depth = 0
        self.transaction_exits: list[str] = []
        self.manual_commits = 0
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.start_run_row = start_run_row
        self.claim_rows = [{"dirty_id": "dirty-1"}] if claim_rows is None else claim_rows
        self.claim_rowcount = claim_rowcount
        self.claim_omit_rowcount = claim_omit_rowcount

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def execute(self, sql: str, params: Any = None) -> FakeResult:
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.sql_depths.append(self.transaction_depth)
        if "SELECT * FROM projection_runs WHERE run_id = %s" in text:
            return FakeResult(row={"run_id": str(params[0])})
        if "INSERT INTO projection_runs(" in text and "RETURNING *" in text:
            row = {"run_id": str(params[0])} if self.start_run_row is _START_RUN_ROW_FROM_PARAMS else self.start_run_row
            return FakeResult(row=row, rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)
        if "RETURNING ranges.*" in text:
            rowcount = len(self.claim_rows) if self.claim_rowcount is _CLAIM_ROWCOUNT_FROM_ROWS else self.claim_rowcount
            return FakeResult(rows=self.claim_rows, rowcount=rowcount, omit_rowcount=self.claim_omit_rowcount)
        return FakeResult(rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)

    def commit(self) -> None:
        self.manual_commits += 1
        raise AssertionError("repository-owned writes must use conn.transaction(), not conn.commit()")


class NoTransactionProjectionConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> FakeResult:
        self.sql.append(" ".join(str(sql).split()))
        return FakeResult(rowcount=1)

    def commit(self) -> None:
        raise AssertionError("repository-owned writes must use conn.transaction(), not conn.commit()")


class FakeTransaction:
    def __init__(self, conn: FakeProjectionConnection) -> None:
        self.conn = conn

    def __enter__(self) -> None:
        self.conn.transaction_entries += 1
        self.conn.transaction_depth += 1

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any) -> bool:
        self.conn.transaction_depth -= 1
        self.conn.transaction_exits.append(exc_type.__name__ if exc_type else "ok")
        return False


class FakeResult:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
        rowcount: object = 0,
        omit_rowcount: bool = False,
    ) -> None:
        self.row = row
        self.rows = rows or ([] if row is None else [row])
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows
