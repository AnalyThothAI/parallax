from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.asset_market.repositories.discovery_repository import DiscoveryRepository

NOW_MS = 1_779_000_000_000
CLAIM = {
    "provider": "okx_dex_search",
    "lookup_key": "symbol:ABC",
    "payload_hash": "hash-abc",
    "lease_owner": "resolution_refresh",
    "attempt_count": 1,
}
RESULT_ROW = {
    "provider": "okx_dex_search",
    "lookup_key": "symbol:ABC",
    "lookup_type": "dex_symbol_lookup",
    "status": "running",
    "candidate_count": 0,
    "candidate_ids_json": [],
    "result_hash": "hash-old",
    "last_lookup_at_ms": NOW_MS - 1,
    "next_refresh_at_ms": NOW_MS,
    "last_error": None,
    "error_count": 0,
    "created_at_ms": NOW_MS - 1,
    "updated_at_ms": NOW_MS - 1,
}


@pytest.mark.parametrize(
    ("intent_count", "error"),
    [
        pytest.param(0, "discovery_lookup_intent_count_required", id="zero"),
        pytest.param(True, "discovery_lookup_intent_count_required", id="bool"),
        pytest.param("1", "discovery_lookup_intent_count_required", id="string"),
    ],
)
def test_enqueue_lookup_keys_rejects_malformed_intent_count_before_transaction(
    intent_count: object,
    error: str,
) -> None:
    conn = NoTransactionDiscoveryConnection()

    with pytest.raises(ValueError, match=error):
        DiscoveryRepository(conn).enqueue_lookup_keys(
            ["symbol:ABC"],
            reason="token_resolution_refresh",
            intent_count=intent_count,  # type: ignore[arg-type]
            now_ms=NOW_MS,
        )

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"limit": -1}, "discovery_lookup_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "discovery_lookup_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "1"}, "discovery_lookup_claim_limit_required", id="string-limit"),
        pytest.param({"lease_ms": 0}, "discovery_lookup_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"lease_ms": True}, "discovery_lookup_claim_lease_ms_required", id="bool-lease"),
        pytest.param({"lease_ms": "60000"}, "discovery_lookup_claim_lease_ms_required", id="string-lease"),
        pytest.param({"running_timeout_ms": 0}, "discovery_lookup_running_timeout_ms_required", id="zero-timeout"),
        pytest.param({"running_timeout_ms": True}, "discovery_lookup_running_timeout_ms_required", id="bool-timeout"),
        pytest.param(
            {"running_timeout_ms": "60000"},
            "discovery_lookup_running_timeout_ms_required",
            id="string-timeout",
        ),
        pytest.param({"hot_since_ms": True}, "discovery_lookup_hot_since_ms_required", id="bool-hot-since"),
        pytest.param({"hot_since_ms": "1"}, "discovery_lookup_hot_since_ms_required", id="string-hot-since"),
        pytest.param(
            {"hot_not_found_retry_ms": 0},
            "discovery_lookup_hot_not_found_retry_ms_required",
            id="zero-hot-retry",
        ),
        pytest.param(
            {"hot_not_found_retry_ms": True},
            "discovery_lookup_hot_not_found_retry_ms_required",
            id="bool-hot-retry",
        ),
        pytest.param(
            {"hot_not_found_retry_ms": "60000"},
            "discovery_lookup_hot_not_found_retry_ms_required",
            id="string-hot-retry",
        ),
    ],
)
def test_claim_due_lookup_keys_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = NoTransactionDiscoveryConnection()
    params: dict[str, object] = {
        "now_ms": NOW_MS,
        "limit": 1,
        "lease_ms": 60_000,
        "running_timeout_ms": 60_000,
        "lease_owner": "resolution_refresh",
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        DiscoveryRepository(conn).claim_due_lookup_keys(**params)

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    "running_timeout_ms",
    [0, True, "60000"],
)
def test_start_lookup_rejects_malformed_running_timeout_before_transaction(running_timeout_ms: object) -> None:
    conn = NoTransactionDiscoveryConnection()

    with pytest.raises(ValueError, match="discovery_lookup_running_timeout_ms_required"):
        DiscoveryRepository(conn).start_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:ABC",
            lookup_type="dex_symbol_lookup",
            now_ms=NOW_MS,
            running_timeout_ms=running_timeout_ms,  # type: ignore[arg-type]
        )

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repository, claim: repository.mark_lookup_done(
                [claim],
                now_ms=NOW_MS,
            ),
            id="done",
        ),
        pytest.param(
            lambda repository, claim: repository.reschedule_lookup_claims(
                [claim],
                due_at_ms=NOW_MS + 60_000,
                now_ms=NOW_MS,
                last_error="provider retry",
            ),
            id="reschedule",
        ),
        pytest.param(
            lambda repository, claim: repository.terminalize_lookup_claims(
                [claim],
                worker_name="resolution_refresh",
                final_status="error",
                final_reason="provider_error_retry_budget_exhausted",
                now_ms=NOW_MS,
            ),
            id="terminalize",
        ),
    ],
)
def test_lookup_claim_completion_requires_claim_attempt_field_without_default(
    operation: Callable[[DiscoveryRepository, dict[str, Any]], object],
) -> None:
    conn = NoTransactionDiscoveryConnection()
    claim = dict(CLAIM)
    claim.pop("attempt_count")

    with pytest.raises(
        ValueError,
        match="token discovery lookup claim completion requires attempt_count",
    ) as exc_info:
        operation(DiscoveryRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == []


@pytest.mark.parametrize("attempt_count", [0, True, "1"])
def test_lookup_claim_completion_rejects_malformed_attempt_count(attempt_count: object) -> None:
    conn = NoTransactionDiscoveryConnection()
    claim = dict(CLAIM)
    claim["attempt_count"] = attempt_count

    with pytest.raises(
        ValueError,
        match="token discovery lookup claim completion requires attempt_count",
    ):
        DiscoveryRepository(conn).mark_lookup_done([claim], now_ms=NOW_MS)

    assert conn.sql == []


def test_terminalize_lookup_claims_requires_deleted_source_payload_hash_before_ledger_write() -> None:
    conn = TerminalizeMissingPayloadHashConnection()
    repository = DiscoveryRepository(conn)

    with pytest.raises(
        ValueError,
        match="token discovery lookup terminalization requires source payload_hash",
    ):
        repository.terminalize_lookup_claims(
            [CLAIM],
            worker_name="resolution_refresh",
            final_status="error",
            final_reason="provider_error_retry_budget_exhausted",
            now_ms=NOW_MS,
        )

    assert not any("INSERT INTO worker_queue_terminal_events" in sql for sql in conn.sql)


def test_terminalize_lookup_claims_returning_counts_require_cursor_rowcount_before_ledger_write() -> None:
    conn = TerminalizeRowcountConnection(omit_rowcount=True)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        repository.terminalize_lookup_claims(
            [CLAIM],
            worker_name="resolution_refresh",
            final_status="error",
            final_reason="provider_error_retry_budget_exhausted",
            now_ms=NOW_MS,
        )

    assert not any("INSERT INTO worker_queue_terminal_events" in sql for sql in conn.sql)


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_terminalize_lookup_claims_returning_counts_reject_invalid_or_mismatched_rowcount(
    rowcount: Any,
) -> None:
    conn = TerminalizeRowcountConnection(rowcount=rowcount)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        repository.terminalize_lookup_claims(
            [CLAIM],
            worker_name="resolution_refresh",
            final_status="error",
            final_reason="provider_error_retry_budget_exhausted",
            now_ms=NOW_MS,
        )

    assert not any("INSERT INTO worker_queue_terminal_events" in sql for sql in conn.sql)


def test_claim_due_lookup_keys_returning_rows_require_cursor_rowcount() -> None:
    conn = ClaimDueRowcountConnection(rowcount=None, rows=[CLAIM])
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        repository.claim_due_lookup_keys(
            now_ms=NOW_MS,
            limit=1,
            lease_ms=60_000,
            running_timeout_ms=60_000,
            lease_owner="resolution_refresh",
        )


@pytest.mark.parametrize("rowcount", [True, False, "1", -1, 0, 2])
def test_claim_due_lookup_keys_returning_rows_reject_invalid_or_mismatched_rowcount(rowcount: Any) -> None:
    conn = ClaimDueRowcountConnection(rowcount=rowcount, rows=[CLAIM])
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        repository.claim_due_lookup_keys(
            now_ms=NOW_MS,
            limit=1,
            lease_ms=60_000,
            running_timeout_ms=60_000,
            lease_owner="resolution_refresh",
        )


def test_claim_due_lookup_keys_accepts_zero_row_noop_with_matching_rowcount() -> None:
    conn = ClaimDueRowcountConnection(rowcount=0, rows=[])
    repository = DiscoveryRepository(conn)

    assert (
        repository.claim_due_lookup_keys(
            now_ms=NOW_MS,
            limit=1,
            lease_ms=60_000,
            running_timeout_ms=60_000,
            lease_owner="resolution_refresh",
        )
        == []
    )


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repository: repository.start_lookup(
                provider="okx_dex_search",
                lookup_key="symbol:ABC",
                lookup_type="dex_symbol_lookup",
                now_ms=NOW_MS,
                running_timeout_ms=60_000,
            ),
            id="start",
        ),
        pytest.param(
            lambda repository: repository.fail_lookup(
                provider="okx_dex_search",
                lookup_key="symbol:ABC",
                lookup_type="dex_symbol_lookup",
                last_error="provider unavailable",
                next_refresh_at_ms=NOW_MS + 600_000,
                now_ms=NOW_MS,
            ),
            id="fail",
        ),
    ],
)
def test_lookup_result_returning_writes_require_cursor_rowcount(
    operation: Callable[[DiscoveryRepository], object],
) -> None:
    conn = LookupResultWriteConnection(rowcount=None, row=RESULT_ROW)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        operation(repository)


@pytest.mark.parametrize("rowcount", [True, False, "1", -1, 0, 2])
def test_lookup_result_returning_writes_reject_invalid_or_non_single_rowcount(rowcount: Any) -> None:
    conn = LookupResultWriteConnection(rowcount=rowcount, row=RESULT_ROW)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        repository.start_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:ABC",
            lookup_type="dex_symbol_lookup",
            now_ms=NOW_MS,
            running_timeout_ms=60_000,
        )


def test_lookup_result_returning_writes_reject_rowcount_one_without_row() -> None:
    conn = LookupResultWriteConnection(rowcount=1, row=None)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        repository.start_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:ABC",
            lookup_type="dex_symbol_lookup",
            now_ms=NOW_MS,
            running_timeout_ms=60_000,
        )


def test_finish_lookup_requires_single_cursor_rowcount() -> None:
    conn = LookupResultWriteConnection(rowcount=None, row=RESULT_ROW)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        repository.finish_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:ABC",
            lookup_type="dex_symbol_lookup",
            status="found",
            candidate_ids=["chain:token"],
            result_hash="hash-new",
            next_refresh_at_ms=NOW_MS + 600_000,
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize("rowcount", [True, False, "1", -1, 0, 2])
def test_finish_lookup_rejects_invalid_or_non_single_rowcount(rowcount: Any) -> None:
    conn = LookupResultWriteConnection(rowcount=rowcount, row=RESULT_ROW)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        repository.finish_lookup(
            provider="okx_dex_search",
            lookup_key="symbol:ABC",
            lookup_type="dex_symbol_lookup",
            status="found",
            candidate_ids=["chain:token"],
            result_hash="hash-new",
            next_refresh_at_ms=NOW_MS + 600_000,
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repository: repository.enqueue_lookup_keys(
                ["symbol:ABC"],
                reason="token_resolution_refresh",
                now_ms=NOW_MS,
            ),
            id="enqueue",
        ),
        pytest.param(lambda repository: repository.mark_lookup_done([CLAIM], now_ms=NOW_MS), id="done"),
        pytest.param(
            lambda repository: repository.reschedule_lookup_claims(
                [CLAIM],
                due_at_ms=NOW_MS + 60_000,
                now_ms=NOW_MS,
                last_error="provider retry",
            ),
            id="reschedule",
        ),
    ],
)
def test_discovery_lookup_write_counts_require_cursor_rowcount(
    operation: Callable[[DiscoveryRepository], object],
) -> None:
    conn = RowcountDiscoveryConnection(rowcount=None)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        operation(repository)


@pytest.mark.parametrize("rowcount", [True, False, "1", -1])
@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repository: repository.enqueue_lookup_keys(
                ["symbol:ABC"],
                reason="token_resolution_refresh",
                now_ms=NOW_MS,
            ),
            id="enqueue",
        ),
        pytest.param(lambda repository: repository.mark_lookup_done([CLAIM], now_ms=NOW_MS), id="done"),
        pytest.param(
            lambda repository: repository.reschedule_lookup_claims(
                [CLAIM],
                due_at_ms=NOW_MS + 60_000,
                now_ms=NOW_MS,
                last_error="provider retry",
            ),
            id="reschedule",
        ),
    ],
)
def test_discovery_lookup_write_counts_reject_invalid_cursor_rowcount(
    operation: Callable[[DiscoveryRepository], object],
    rowcount: Any,
) -> None:
    conn = RowcountDiscoveryConnection(rowcount=rowcount)
    repository = DiscoveryRepository(conn)

    with pytest.raises(TypeError, match="discovery_repository_rowcount_invalid"):
        operation(repository)


class _Cursor:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        rowcount: Any = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self._rows = rows or []
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class FakeDiscoveryConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.sql_depths: list[int] = []
        self.commits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)

        if "UPDATE token_discovery_dirty_lookup_keys queue" in text and "RETURNING" in text:
            row = CLAIM | {
                "status": None,
                "result_hash": None,
                "next_refresh_at_ms": None,
                "error_count": 0,
            }
            return _Cursor([row], rowcount=1)
        if "INSERT INTO token_discovery_dirty_lookup_keys" in text:
            return _Cursor(rowcount=1)
        if "DELETE FROM token_discovery_dirty_lookup_keys queue" in text:
            return _Cursor(rowcount=1)
        if "UPDATE token_discovery_dirty_lookup_keys queue" in text:
            return _Cursor(rowcount=1)
        if "SELECT * FROM token_discovery_results" in text:
            return _Cursor([dict(RESULT_ROW)], rowcount=1)
        if "INSERT INTO token_discovery_results" in text and "RETURNING *" in text:
            return _Cursor([dict(RESULT_ROW)], rowcount=1)
        if "INSERT INTO token_discovery_results" in text:
            return _Cursor(rowcount=1)
        raise AssertionError(f"unexpected discovery repository SQL: {text}")

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def commit(self) -> None:
        self.commits += 1


class NoTransactionDiscoveryConnection(FakeDiscoveryConnection):
    transaction = None


class TerminalizeMissingPayloadHashConnection(FakeDiscoveryConnection):
    def execute(self, sql: str, params: Any = None) -> _Cursor:
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)

        if "DELETE FROM token_discovery_dirty_lookup_keys queue" in text and "RETURNING queue.*" in text:
            row = dict(CLAIM)
            row.pop("payload_hash")
            row["first_dirty_at_ms"] = NOW_MS - 60_000
            return _Cursor([row], rowcount=1)
        if "FROM worker_queue_terminal_events" in text and "operator_action IS NULL" in text:
            return _Cursor([], rowcount=0)
        if "SELECT COALESCE(MAX(terminal_generation), 0) + 1 AS terminal_generation" in text:
            return _Cursor([{"terminal_generation": 1}], rowcount=1)
        if "INSERT INTO worker_queue_terminal_events" in text:
            return _Cursor([{"terminal_id": params["terminal_id"]}], rowcount=1)
        return super().execute(sql, params)


class TerminalizeRowcountConnection(FakeDiscoveryConnection):
    def __init__(self, *, rowcount: Any = 1, omit_rowcount: bool = False) -> None:
        super().__init__()
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)

        if "DELETE FROM token_discovery_dirty_lookup_keys queue" in text and "RETURNING queue.*" in text:
            row = dict(CLAIM)
            row["first_dirty_at_ms"] = NOW_MS - 60_000
            return _Cursor([row], rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)
        if "FROM worker_queue_terminal_events" in text and "operator_action IS NULL" in text:
            return _Cursor([], rowcount=0)
        if "SELECT COALESCE(MAX(terminal_generation), 0) + 1 AS terminal_generation" in text:
            return _Cursor([{"terminal_generation": 1}], rowcount=1)
        if "INSERT INTO worker_queue_terminal_events" in text:
            return _Cursor([{"terminal_id": params["terminal_id"]}], rowcount=1)
        return super().execute(sql, params)


class ClaimDueRowcountConnection(FakeDiscoveryConnection):
    def __init__(self, *, rowcount: Any, rows: list[dict[str, Any]]) -> None:
        super().__init__()
        self.rowcount = rowcount
        self.rows = rows

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)

        if "UPDATE token_discovery_dirty_lookup_keys queue" in text and "RETURNING" in text:
            return _Cursor(self.rows, rowcount=self.rowcount, omit_rowcount=self.rowcount is None)
        return super().execute(sql, params)


class LookupResultWriteConnection(FakeDiscoveryConnection):
    def __init__(self, *, rowcount: Any, row: dict[str, Any] | None) -> None:
        super().__init__()
        self.rowcount = rowcount
        self.row = row

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)

        if "SELECT * FROM token_discovery_results" in text:
            return _Cursor([dict(RESULT_ROW)], rowcount=1)
        if "INSERT INTO token_discovery_results" in text:
            rows = [self.row] if self.row is not None and "RETURNING *" in text else []
            return _Cursor(rows, rowcount=self.rowcount, omit_rowcount=self.rowcount is None)
        return super().execute(sql, params)


class RowcountDiscoveryConnection(FakeDiscoveryConnection):
    def __init__(self, *, rowcount: Any) -> None:
        super().__init__()
        self.rowcount = rowcount

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)
        return _RowcountCursor(self.rowcount)


class _RowcountCursor:
    def __init__(self, rowcount: Any) -> None:
        if rowcount is not None:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        return []


class _Transaction:
    def __init__(self, conn: FakeDiscoveryConnection) -> None:
        self.conn = conn

    def __enter__(self) -> None:
        self.conn.transaction_depth += 1

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
