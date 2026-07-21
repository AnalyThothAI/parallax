from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.asset_market.repositories.market_tick_current_dirty_target_repository import (
    MarketTickCurrentDirtyTargetRepository,
)
from parallax.domains.asset_market.repositories.market_tick_current_repository import (
    MarketTickCurrentRepository,
)


def test_enqueue_targets_coalesces_by_target() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 2

    count = MarketTickCurrentDirtyTargetRepository(conn).enqueue_targets(
        [
            ("chain_token", "solana:abc"),
            {"target_type": "chain_token", "target_id": "solana:abc"},
            {"target_type": "cex_symbol", "target_id": "binance:BTCUSDT"},
        ],
        reason="market_tick_written",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    assert count == 2
    assert "INSERT INTO market_tick_current_dirty_targets" in conn.sql[-1]
    assert "ON CONFLICT(target_type, target_id) DO UPDATE SET" in conn.sql[-1]
    assert conn.params[-1]["target_types"] == ["chain_token", "cex_symbol"]
    assert conn.params[-1]["target_ids"] == ["solana:abc", "binance:BTCUSDT"]


def test_claim_due_uses_lease_token_and_skip_locked() -> None:
    conn = _ScriptedConnection(
        [
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:abc",
                    "payload_hash": "hash-1",
                    "lease_owner": "worker-a",
                    "attempt_count": 1,
                }
            ]
        ]
    )

    rows = MarketTickCurrentDirtyTargetRepository(conn).claim_due(
        limit=25,
        now_ms=1_700_000_000_000,
        lease_ms=60_000,
        lease_owner="worker-a",
        commit=False,
    )

    sql = conn.sql[-1]
    assert rows[0]["payload_hash"] == "hash-1"
    assert rows[0]["lease_owner"] == "worker-a"
    assert rows[0]["attempt_count"] == 1
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "attempt_count = market_tick_current_dirty_targets.attempt_count + 1" in sql
    assert "last_error = NULL" in sql
    assert conn.params[-1]["leased_until_ms"] == 1_700_000_060_000


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"limit": -1}, "market_tick_current_dirty_target_claim_limit_required", id="negative-limit"),
        pytest.param({"limit": True}, "market_tick_current_dirty_target_claim_limit_required", id="bool-limit"),
        pytest.param({"limit": "25"}, "market_tick_current_dirty_target_claim_limit_required", id="string-limit"),
        pytest.param({"lease_ms": 0}, "market_tick_current_dirty_target_claim_lease_ms_required", id="zero-lease"),
        pytest.param({"lease_ms": True}, "market_tick_current_dirty_target_claim_lease_ms_required", id="bool-lease"),
        pytest.param(
            {"lease_ms": "60000"},
            "market_tick_current_dirty_target_claim_lease_ms_required",
            id="string-lease",
        ),
    ],
)
def test_market_tick_current_dirty_claim_due_rejects_malformed_parameters_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = _MissingTransactionConnection()
    params: dict[str, object] = {
        "limit": 25,
        "now_ms": 1_700_000_000_000,
        "lease_ms": 60_000,
        "lease_owner": "market_tick_current_projection",
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        MarketTickCurrentDirtyTargetRepository(conn).claim_due(**params)

    assert conn.sql == []
    assert conn.commits == 0


def test_mark_done_cannot_delete_newer_dirty_work() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 0

    deleted = MarketTickCurrentDirtyTargetRepository(conn).mark_done(
        [
            {
                "target_type": "chain_token",
                "target_id": "solana:abc",
                "payload_hash": "old-claim-hash",
                "lease_owner": "worker-a",
                "attempt_count": 1,
            }
        ],
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert deleted == 0
    assert "DELETE FROM market_tick_current_dirty_targets queue" in sql
    assert "queue.payload_hash = done.payload_hash" in sql
    assert "queue.lease_owner = done.lease_owner" in sql
    assert "queue.attempt_count = done.attempt_count" in sql
    assert conn.params[-1]["payload_hashes"] == ["old-claim-hash"]
    assert conn.params[-1]["lease_owners"] == ["worker-a"]
    assert conn.params[-1]["attempt_counts"] == [1]


def test_mark_error_reschedules_only_matching_claim() -> None:
    conn = _ScriptedConnection([])
    conn.rowcount = 1

    updated = MarketTickCurrentDirtyTargetRepository(conn).mark_error(
        [
            {
                "target_type": "cex_symbol",
                "target_id": "binance:BTCUSDT",
                "payload_hash": "claim-hash",
                "lease_owner": "worker-a",
                "attempt_count": 2,
            }
        ],
        error="projection failed",
        retry_ms=30_000,
        max_attempts=3,
        worker_name="market_tick_current_projection",
        now_ms=1_700_000_010_000,
        commit=False,
    )

    sql = conn.sql[-1]
    assert updated == 1
    assert "leased_until_ms = NULL" in sql
    assert "lease_owner = NULL" in sql
    assert "queue.payload_hash = failed.payload_hash" in sql
    assert "queue.lease_owner = failed.lease_owner" in sql
    assert "queue.attempt_count = failed.attempt_count" in sql
    assert conn.params[-1]["due_at_ms"] == 1_700_000_040_000
    assert conn.params[-1]["last_error"] == "projection failed"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        pytest.param({"retry_ms": 0}, "market_tick_current_dirty_target_retry_ms_required", id="zero-retry"),
        pytest.param({"retry_ms": True}, "market_tick_current_dirty_target_retry_ms_required", id="bool-retry"),
        pytest.param({"retry_ms": "30000"}, "market_tick_current_dirty_target_retry_ms_required", id="string-retry"),
        pytest.param(
            {"max_attempts": 0},
            "market_tick_current_dirty_target_max_attempts_required",
            id="zero-attempts",
        ),
        pytest.param(
            {"max_attempts": True},
            "market_tick_current_dirty_target_max_attempts_required",
            id="bool-attempts",
        ),
        pytest.param(
            {"max_attempts": "3"},
            "market_tick_current_dirty_target_max_attempts_required",
            id="string-attempts",
        ),
    ],
)
def test_market_tick_current_dirty_mark_error_rejects_malformed_retry_policy_before_transaction(
    overrides: dict[str, object],
    error: str,
) -> None:
    conn = _MissingTransactionConnection()
    params: dict[str, object] = {
        "error": "projection failed",
        "retry_ms": 30_000,
        "max_attempts": 3,
        "worker_name": "market_tick_current_projection",
        "now_ms": 1_700_000_010_000,
    }
    params.update(overrides)

    with pytest.raises(ValueError, match=error):
        MarketTickCurrentDirtyTargetRepository(conn).mark_error([_dirty_claim()], **params)

    assert conn.sql == []
    assert conn.commits == 0


def test_mark_error_terminalizes_exhausted_claims_into_queue_terminal() -> None:
    claim = {
        **_dirty_claim(),
        "attempt_count": 3,
        "dirty_reason": "market_tick_written",
        "source_watermark_ms": 1_700_000_000_000,
        "first_dirty_at_ms": 1_700_000_000_000,
        "updated_at_ms": 1_700_000_005_000,
    }
    conn = _ScriptedConnection(
        [
            [claim],
            [],
            [{"terminal_generation": 1}],
            [{"terminal_id": "terminal-1", "source_row_json": {}}],
        ],
        rowcount=1,
    )

    changed = MarketTickCurrentDirtyTargetRepository(conn).mark_error(
        [claim],
        error="projection failed",
        retry_ms=30_000,
        max_attempts=3,
        worker_name="market_tick_current_projection",
        now_ms=1_700_000_010_000,
        commit=False,
    )

    assert changed == 1
    assert any(
        "DELETE FROM market_tick_current_dirty_targets queue" in sql and "RETURNING queue.*" in sql for sql in conn.sql
    )
    assert any("INSERT INTO worker_queue_terminal_events" in sql for sql in conn.sql)
    terminal_params = conn.params[-1]
    assert terminal_params["worker_name"] == "market_tick_current_projection"
    assert terminal_params["source_table"] == "market_tick_current_dirty_targets"
    assert terminal_params["final_status"] == "terminal"
    assert terminal_params["final_reason"] == "market_tick_current_dirty_retry_budget_exhausted: projection failed"
    assert terminal_params["attempt_count"] == 3


@pytest.mark.parametrize(
    "operation",
    [
        lambda repo: repo.enqueue_targets(
            [("chain_token", "solana:abc")],
            reason="market_tick_written",
            now_ms=1_700_000_000_000,
        ),
        lambda repo: repo.claim_due(
            limit=25,
            now_ms=1_700_000_000_000,
            lease_ms=60_000,
            lease_owner="market_tick_current_projection",
        ),
        lambda repo: repo.mark_done([_dirty_claim()], now_ms=1_700_000_010_000),
        lambda repo: repo.mark_error(
            [_dirty_claim()],
            error="projection failed",
            retry_ms=30_000,
            max_attempts=3,
            worker_name="market_tick_current_projection",
            now_ms=1_700_000_010_000,
        ),
    ],
)
def test_market_tick_current_dirty_mutations_require_connection_transaction_before_sql_when_committing(
    operation: Callable[[MarketTickCurrentDirtyTargetRepository], object],
) -> None:
    conn = _MissingTransactionConnection()

    with pytest.raises(RuntimeError, match="market_tick_current_dirty_target_transaction_required"):
        operation(MarketTickCurrentDirtyTargetRepository(conn))

    assert conn.sql == []
    assert conn.commits == 0


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda repo, claim: repo.mark_done([claim], now_ms=1_700_000_010_000, commit=False), id="done"),
        pytest.param(
            lambda repo, claim: repo.mark_error(
                [claim],
                error="projection failed",
                retry_ms=30_000,
                max_attempts=3,
                worker_name="market_tick_current_projection",
                now_ms=1_700_000_010_000,
                commit=False,
            ),
            id="error",
        ),
    ],
)
def test_market_tick_current_dirty_completion_requires_claim_attempt_field_without_default(
    operation: Callable[[MarketTickCurrentDirtyTargetRepository, dict[str, Any]], object],
) -> None:
    conn = _ScriptedConnection([])
    claim = _dirty_claim()
    claim.pop("attempt_count")

    with pytest.raises(
        ValueError,
        match="market tick current dirty target completion requires attempt_count",
    ) as exc_info:
        operation(MarketTickCurrentDirtyTargetRepository(conn), claim)

    assert isinstance(exc_info.value.__cause__, KeyError)
    assert conn.sql == []


@pytest.mark.parametrize("attempt_count", [0, True, "1"])
def test_market_tick_current_dirty_completion_rejects_malformed_attempt_count(
    attempt_count: object,
) -> None:
    conn = _ScriptedConnection([])
    claim = {**_dirty_claim(), "attempt_count": attempt_count}

    with pytest.raises(
        ValueError,
        match="market tick current dirty target completion requires attempt_count",
    ):
        MarketTickCurrentDirtyTargetRepository(conn).mark_done(
            [claim],
            now_ms=1_700_000_010_000,
            commit=False,
        )

    assert conn.sql == []


def test_market_tick_current_dirty_completion_counts_require_cursor_rowcount() -> None:
    conn = _RowcountConnection(omit_rowcount=True)
    repo = MarketTickCurrentDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="market_tick_current_dirty_target_rowcount_required"):
        repo.mark_done([_dirty_claim()], now_ms=1_700_000_010_000, commit=False)


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_market_tick_current_dirty_completion_counts_reject_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = _RowcountConnection(rowcount=rowcount)
    repo = MarketTickCurrentDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="market_tick_current_dirty_target_rowcount_invalid"):
        repo.mark_error(
            [_dirty_claim()],
            error="projection failed",
            retry_ms=30_000,
            max_attempts=3,
            worker_name="market_tick_current_projection",
            now_ms=1_700_000_010_000,
            commit=False,
        )


def test_market_tick_current_dirty_enqueue_counts_require_cursor_rowcount() -> None:
    conn = _RowcountConnection(omit_rowcount=True)
    repo = MarketTickCurrentDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="market_tick_current_dirty_target_rowcount_required"):
        repo.enqueue_targets(
            [("chain_token", "solana:abc")],
            reason="market_tick_written",
            now_ms=1_700_000_000_000,
            commit=False,
        )


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_market_tick_current_dirty_enqueue_counts_reject_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = _RowcountConnection(rowcount=rowcount)
    repo = MarketTickCurrentDirtyTargetRepository(conn)

    with pytest.raises(TypeError, match="market_tick_current_dirty_target_rowcount_invalid"):
        repo.enqueue_targets(
            [("chain_token", "solana:abc")],
            reason="market_tick_written",
            now_ms=1_700_000_000_000,
            commit=False,
        )


def test_market_tick_current_dirty_enqueue_count_uses_postgres_rowcount_not_candidate_count() -> None:
    conn = _RowcountConnection(rowcount=0)
    repo = MarketTickCurrentDirtyTargetRepository(conn)

    changed = repo.enqueue_targets(
        [
            ("chain_token", "solana:abc"),
            ("cex_symbol", "binance:BTCUSDT"),
        ],
        reason="market_tick_written",
        now_ms=1_700_000_000_000,
        commit=False,
    )

    assert changed == 0


def test_queue_depth_counts_due_unleased_rows() -> None:
    conn = _ScriptedConnection([[{"count": 7}]])

    depth = MarketTickCurrentDirtyTargetRepository(conn).queue_depth(now_ms=1_700_000_010_000)

    assert depth == 7
    assert "count(*) AS count" in conn.sql[-1]
    assert "due_at_ms <= %(now_ms)s" in conn.sql[-1]
    assert "leased_until_ms IS NULL OR leased_until_ms <= %(now_ms)s" in conn.sql[-1]


def test_latest_tick_for_target_uses_current_projection_ordering() -> None:
    conn = _ScriptedConnection([[{"tick_id": "tick-3"}]])

    row = MarketTickCurrentRepository(conn).latest_tick_for_target(
        target_type="chain_token",
        target_id="solana:abc",
    )

    assert row == {"tick_id": "tick-3"}
    assert "FROM market_ticks" in conn.sql[-1]
    assert "ORDER BY observed_at_ms DESC, received_at_ms DESC, tick_id DESC" in conn.sql[-1]
    assert conn.params[-1] == {"target_type": "chain_token", "target_id": "solana:abc"}


def test_upsert_current_from_tick_returns_true_only_when_visible_row_changes() -> None:
    conn = _ScriptedConnection([[{"changed": True}], []])
    repo = MarketTickCurrentRepository(conn)
    tick = _tick_row(tick_id="tick-1")

    assert repo.upsert_current_from_tick(tick, now_ms=1_700_000_010_000) is True
    assert repo.upsert_current_from_tick(tick, now_ms=1_700_000_020_000) is False

    sql = conn.sql[0]
    assert "INSERT INTO market_tick_current" in sql
    assert "ON CONFLICT(target_type, target_id) DO UPDATE SET" in sql
    assert "WHERE market_tick_current.tick_id IS DISTINCT FROM EXCLUDED.tick_id" in sql
    assert "RETURNING true AS changed" in sql


def test_upsert_current_from_tick_returning_changed_requires_cursor_rowcount() -> None:
    conn = _CurrentRowcountConnection(row={"changed": True}, omit_rowcount=True)
    repo = MarketTickCurrentRepository(conn)

    with pytest.raises(TypeError, match="market_tick_current_repository_rowcount_required"):
        repo.upsert_current_from_tick(_tick_row(tick_id="tick-rowcount-missing"), now_ms=1_700_000_010_000)


@pytest.mark.parametrize("rowcount", ["bad", True, -1])
def test_upsert_current_from_tick_returning_changed_rejects_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = _CurrentRowcountConnection(row={"changed": True}, rowcount=rowcount)
    repo = MarketTickCurrentRepository(conn)

    with pytest.raises(TypeError, match="market_tick_current_repository_rowcount_invalid"):
        repo.upsert_current_from_tick(_tick_row(tick_id="tick-rowcount-invalid"), now_ms=1_700_000_010_000)


@pytest.mark.parametrize(
    ("rowcount", "row"),
    [
        (0, {"changed": True}),
        (1, None),
        (2, {"changed": True}),
    ],
)
def test_upsert_current_from_tick_returning_changed_rejects_rowcount_returning_mismatch(
    rowcount: object,
    row: dict[str, Any] | None,
) -> None:
    conn = _CurrentRowcountConnection(row=row, rowcount=rowcount)
    repo = MarketTickCurrentRepository(conn)

    with pytest.raises(TypeError, match="market_tick_current_repository_rowcount_invalid"):
        repo.upsert_current_from_tick(_tick_row(tick_id="tick-rowcount-mismatch"), now_ms=1_700_000_010_000)


def test_upsert_current_from_tick_preserves_tick_received_and_created_times() -> None:
    conn = _ScriptedConnection([[{"changed": True}]])
    tick = _tick_row(tick_id="tick-delayed")
    tick["received_at_ms"] = 1001
    tick["created_at_ms"] = 1002

    changed = MarketTickCurrentRepository(conn).upsert_current_from_tick(tick, now_ms=9999)

    assert changed is True
    assert conn.params[-1]["updated_at_ms"] == 1001
    assert conn.params[-1]["created_at_ms"] == 1002
    assert conn.params[-1]["now_ms"] == 9999


def test_upsert_current_from_tick_repairs_created_at_once_then_becomes_unchanged() -> None:
    tick = _tick_row(tick_id="tick-created-repair")
    conn = _StatefulCurrentConnection(existing_created_at_ms=int(tick["created_at_ms"]) - 1)
    repo = MarketTickCurrentRepository(conn)

    assert repo.upsert_current_from_tick(tick, now_ms=9999) is True
    assert repo.upsert_current_from_tick(tick, now_ms=10000) is False
    assert conn.current_created_at_ms == tick["created_at_ms"]


def test_repository_session_exposes_market_tick_current_repository() -> None:
    session = repositories_for_connection(
        _ScriptedConnection([]),
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )

    assert isinstance(session.market_tick_current_dirty_targets, MarketTickCurrentDirtyTargetRepository)
    assert isinstance(session.market_tick_current, MarketTickCurrentRepository)


def _tick_row(*, tick_id: str) -> dict[str, Any]:
    return {
        "target_type": "chain_token",
        "target_id": "solana:abc",
        "observed_at_ms": 1_700_000_000_000,
        "received_at_ms": 1_700_000_000_001,
        "tick_id": tick_id,
        "source_tier": "tier1_ws",
        "source_provider": "okx_dex_ws",
        "chain": "solana",
        "token_address": "abc",
        "exchange": None,
        "instrument": None,
        "pricefeed_id": None,
        "price_usd": "1.23",
        "liquidity_usd": "1000",
        "volume_24h_usd": "2000",
        "open_interest_usd": None,
        "market_cap_usd": "3000",
        "holders": 42,
        "raw_payload_json": {"p": "1.23"},
        "payload_hash": "payload-hash",
        "created_at_ms": 1_700_000_000_002,
    }


def _dirty_claim() -> dict[str, Any]:
    return {
        "target_type": "chain_token",
        "target_id": "solana:abc",
        "payload_hash": "claim-hash",
        "lease_owner": "market_tick_current_projection",
        "attempt_count": 1,
    }


class _ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]] | None], *, rowcount: object = 0) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.rowcount = rowcount
        self.commits = 0

    def execute(self, sql: str, params: Any | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchone(self) -> dict[str, Any] | None:
        if not self.results:
            self.rowcount = 0
            return None
        result = self.results.pop(0)
        if result is None or not result:
            self.rowcount = 0
            return None
        self.rowcount = 1
        return result[0]

    def fetchall(self) -> list[dict[str, Any]]:
        if not self.results:
            self.rowcount = 0
            return []
        result = self.results.pop(0)
        assert isinstance(result, list)
        self.rowcount = len(result)
        return result

    def commit(self) -> None:
        self.commits += 1


class _MissingTransactionConnection:
    transaction = None

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _MissingTransactionConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        raise AssertionError("SQL must not run without connection transaction")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("manual commit fallback must not run")


class _RowcountConnection:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.sql: list[str] = []
        self.params: list[Any] = []

    def execute(self, sql: str, params: Any | None = None) -> _RowcountCursor:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return _RowcountCursor(rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)


class _RowcountCursor:
    def __init__(self, *, rowcount: object, omit_rowcount: bool) -> None:
        if not omit_rowcount:
            self.rowcount = rowcount


class _CurrentRowcountConnection:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None,
        rowcount: object = 1,
        omit_rowcount: bool = False,
    ) -> None:
        self.row = row
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.sql: list[str] = []
        self.params: list[Any] = []

    def execute(self, sql: str, params: Any | None = None) -> _CurrentRowcountCursor:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return _CurrentRowcountCursor(row=self.row, rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)


class _CurrentRowcountCursor:
    def __init__(self, *, row: dict[str, Any] | None, rowcount: object, omit_rowcount: bool) -> None:
        self.row = row
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _StatefulCurrentConnection:
    def __init__(self, *, existing_created_at_ms: int) -> None:
        self.current_created_at_ms = existing_created_at_ms
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.pending_row: dict[str, Any] | None = None
        self.rowcount = 0

    def execute(self, sql: str, params: Any | None = None) -> _StatefulCurrentConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        if "INSERT INTO market_tick_current" in str(sql):
            changed = self.current_created_at_ms != params["created_at_ms"]
            if changed and "created_at_ms = EXCLUDED.created_at_ms" in str(sql):
                self.current_created_at_ms = params["created_at_ms"]
            self.pending_row = {"changed": changed} if changed else None
            self.rowcount = 1 if changed else 0
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self.pending_row
