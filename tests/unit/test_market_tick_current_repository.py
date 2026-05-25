from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.asset_market.repositories.market_tick_current_dirty_target_repository import (
    MarketTickCurrentDirtyTargetRepository,
)
from gmgn_twitter_intel.domains.asset_market.repositories.market_tick_current_repository import (
    MarketTickCurrentRepository,
)
from gmgn_twitter_intel.domains.asset_market.services.market_tick_current_rebuild import (
    MarketTickCurrentRebuildService,
)


def test_enqueue_targets_coalesces_by_target() -> None:
    conn = _ScriptedConnection([])

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


def test_rebuild_all_wraps_truncate_and_upserts_in_one_transaction() -> None:
    tick = _tick_row(tick_id="tick-rebuild")
    repos = _RebuildRepos(ticks=[tick])

    result = MarketTickCurrentRebuildService(repos).rebuild_all(now_ms=9999)

    assert result == {"scanned": 1, "changed": 1}
    assert repos.events == [
        "begin",
        "truncate",
        "latest_ticks_for_all_targets",
        ("upsert", "tick-rebuild", 9999),
        "commit",
    ]


def test_rebuild_all_rolls_back_when_upsert_fails() -> None:
    tick = _tick_row(tick_id="tick-fail")
    repos = _RebuildRepos(ticks=[tick], fail_on_upsert=True)

    try:
        MarketTickCurrentRebuildService(repos).rebuild_all(now_ms=9999)
    except RuntimeError as exc:
        assert str(exc) == "rebuild upsert failed"
    else:
        raise AssertionError("expected rebuild failure")

    assert repos.events == [
        "begin",
        "truncate",
        "latest_ticks_for_all_targets",
        ("upsert", "tick-fail", 9999),
        "rollback",
    ]


def test_repository_session_exposes_market_tick_current_repository() -> None:
    session = repositories_for_connection(_ScriptedConnection([]))

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


class _ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]] | None]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.rowcount = 0
        self.commits = 0

    def execute(self, sql: str, params: Any | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchone(self) -> dict[str, Any] | None:
        if not self.results:
            return None
        result = self.results.pop(0)
        if result is None or not result:
            return None
        return result[0]

    def fetchall(self) -> list[dict[str, Any]]:
        if not self.results:
            return []
        result = self.results.pop(0)
        assert isinstance(result, list)
        return result

    def commit(self) -> None:
        self.commits += 1


class _StatefulCurrentConnection:
    def __init__(self, *, existing_created_at_ms: int) -> None:
        self.current_created_at_ms = existing_created_at_ms
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.pending_row: dict[str, Any] | None = None

    def execute(self, sql: str, params: Any | None = None) -> _StatefulCurrentConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        if "INSERT INTO market_tick_current" in str(sql):
            changed = self.current_created_at_ms != params["created_at_ms"]
            if changed and "created_at_ms = EXCLUDED.created_at_ms" in str(sql):
                self.current_created_at_ms = params["created_at_ms"]
            self.pending_row = {"changed": changed} if changed else None
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self.pending_row


class _RebuildRepos:
    def __init__(self, *, ticks: list[dict[str, Any]], fail_on_upsert: bool = False) -> None:
        self.events: list[Any] = []
        self.in_transaction = False
        self.market_tick_current = _RebuildCurrentRepo(self, ticks=ticks, fail_on_upsert=fail_on_upsert)

    def transaction(self) -> _RebuildRepos:
        return self

    def __enter__(self) -> _RebuildRepos:
        self.events.append("begin")
        self.in_transaction = True
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.events.append("rollback" if exc_type is not None else "commit")
        self.in_transaction = False
        return False


class _RebuildCurrentRepo:
    def __init__(self, owner: _RebuildRepos, *, ticks: list[dict[str, Any]], fail_on_upsert: bool) -> None:
        self.owner = owner
        self.ticks = ticks
        self.fail_on_upsert = fail_on_upsert

    def truncate_current(self) -> None:
        assert self.owner.in_transaction is True
        self.owner.events.append("truncate")

    def latest_ticks_for_all_targets(self) -> list[dict[str, Any]]:
        assert self.owner.in_transaction is True
        self.owner.events.append("latest_ticks_for_all_targets")
        return list(self.ticks)

    def upsert_current_from_tick(self, tick_row: dict[str, Any], *, now_ms: int) -> bool:
        assert self.owner.in_transaction is True
        self.owner.events.append(("upsert", tick_row["tick_id"], now_ms))
        if self.fail_on_upsert:
            raise RuntimeError("rebuild upsert failed")
        return True
