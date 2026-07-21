from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from parallax.domains.asset_market.repositories.market_tick_repository import (
    MarketTickRepository,
    market_tick_id,
)
from parallax.domains.asset_market.types import MarketTick

_ROWCOUNT_MISSING = object()


def test_market_tick_id_is_deterministic_from_dedupe_key() -> None:
    tick_id = market_tick_id(
        target_type="chain_token",
        target_id="solana:abc",
        source_provider="okx_dex_ws",
        observed_at_ms=1_700_000_000_000,
    )

    assert tick_id.startswith("market_tick:")
    assert tick_id == market_tick_id(
        target_type="chain_token",
        target_id="solana:abc",
        source_provider="okx_dex_ws",
        observed_at_ms=1_700_000_000_000,
    )
    assert tick_id != market_tick_id(
        target_type="chain_token",
        target_id="solana:abc",
        source_provider="okx_dex_ws",
        observed_at_ms=1_700_000_000_001,
    )
    assert tick_id != market_tick_id(
        target_type="chain_token",
        target_id="solana:abc",
        source_provider="okx_dex_rest",
        observed_at_ms=1_700_000_000_000,
    )


def test_insert_ticks_rejects_non_deterministic_tick_id() -> None:
    conn = _ScriptedConnection([])

    try:
        MarketTickRepository(conn).insert_ticks_returning_rows([_tick(tick_id="tick-1")])
    except ValueError as exc:
        assert "market tick id must be deterministic" in str(exc)
    else:
        raise AssertionError("expected insert_tick to reject a mismatched tick_id")

    assert conn.sql == []


def test_insert_market_tick_is_idempotent_without_update() -> None:
    tick = _tick()
    conn = _ScriptedConnection([{"tick_id": tick.tick_id}, None])

    repository = MarketTickRepository(conn)
    assert repository.insert_ticks_returning_rows([tick]) == [{"tick_id": tick.tick_id}]
    assert repository.insert_ticks_returning_rows([tick]) == []

    sql = "\n".join(conn.sql)
    assert "INSERT INTO market_ticks" in sql
    assert "ON CONFLICT(observed_at_ms, target_type, target_id, source_provider) DO NOTHING" in sql
    assert "RETURNING" in sql
    assert "tick_id" in sql
    assert "UPDATE market_ticks" not in sql
    assert "market_tick_current" not in sql
    assert "current_upsert" not in sql
    assert conn.commits == 0
    assert len(conn.params) == 2
    assert conn.params[0]["tick_id"] == tick.tick_id
    assert conn.params[0]["holders"] == 1234
    assert conn.params[0]["open_interest_usd"] is None
    assert conn.params[0]["raw_payload_json"].obj == {"pair": "abc"}


def test_insert_market_tick_appends_only_and_does_not_write_current_projection() -> None:
    conn = _ScriptedConnection([])
    tick = _tick()

    MarketTickRepository(conn).insert_ticks_returning_rows([tick])

    sql = conn.sql[-1]
    normalized_sql = " ".join(sql.split())
    assert "INSERT INTO market_ticks" in normalized_sql
    assert "ON CONFLICT(observed_at_ms, target_type, target_id, source_provider) DO NOTHING" in normalized_sql
    assert "RETURNING" in normalized_sql
    assert "WITH inserted AS" not in normalized_sql
    assert "current_upsert" not in normalized_sql
    assert "market_tick_current" not in normalized_sql
    assert "ON CONFLICT(target_type, target_id) DO UPDATE" not in normalized_sql


def test_insert_market_tick_strips_nul_bytes_from_raw_payload() -> None:
    conn = _ScriptedConnection([])
    tick = _tick(raw_payload_json={"symbol\x00": "ZEC\x00", "links": ["https://x.example/\x00zec"]})

    MarketTickRepository(conn).insert_ticks_returning_rows([tick])

    assert conn.params[0]["raw_payload_json"].obj == {
        "symbol": "ZEC",
        "links": ["https://x.example/zec"],
    }


def test_insert_ticks_returns_only_rows_that_were_inserted() -> None:
    first_tick = _tick(observed_at_ms=1_700_000_000_000)
    duplicate_tick = _tick(observed_at_ms=1_700_000_000_000)
    conn = _ScriptedConnection([{"tick_id": first_tick.tick_id}, None])

    rows = MarketTickRepository(conn).insert_ticks_returning_rows([first_tick, duplicate_tick])

    assert rows == [{"tick_id": first_tick.tick_id}]
    assert len(conn.sql) == 2


def test_insert_market_tick_returning_write_requires_cursor_rowcount() -> None:
    tick = _tick()
    conn = _ScriptedConnection([{"tick_id": tick.tick_id}], rowcounts=[_ROWCOUNT_MISSING])

    with pytest.raises(TypeError, match="market_tick_repository_rowcount_invalid"):
        MarketTickRepository(conn).insert_ticks_returning_rows([tick])


@pytest.mark.parametrize(
    ("rowcount", "row"),
    [
        pytest.param(True, {"tick_id": "tick-1"}, id="bool-true"),
        pytest.param(False, None, id="bool-false"),
        pytest.param("1", {"tick_id": "tick-1"}, id="numeric-string"),
        pytest.param(-1, None, id="negative"),
        pytest.param(2, {"tick_id": "tick-1"}, id="multi-row"),
        pytest.param(0, {"tick_id": "tick-1"}, id="zero-with-row"),
        pytest.param(1, None, id="one-without-row"),
    ],
)
def test_insert_market_tick_returning_write_rejects_invalid_or_mismatched_rowcount(
    rowcount: object,
    row: dict[str, Any] | None,
) -> None:
    tick = _tick()
    conn = _ScriptedConnection([row], rowcounts=[rowcount])

    with pytest.raises(TypeError, match="market_tick_repository_rowcount_invalid"):
        MarketTickRepository(conn).insert_ticks_returning_rows([tick])


def test_insert_market_tick_returning_write_accepts_zero_rowcount_conflict() -> None:
    tick = _tick()
    conn = _ScriptedConnection([None], rowcounts=[0])

    assert MarketTickRepository(conn).insert_ticks_returning_rows([tick]) == []


def test_latest_at_or_before_uses_observed_window_and_order() -> None:
    conn = _ScriptedConnection([{"tick_id": "tick-1"}])

    row = MarketTickRepository(conn).latest_at_or_before(
        target_type="chain_token",
        target_id="solana:abc",
        at_ms=1_700_000_100_000,
        max_lag_ms=30_000,
    )

    assert row == {"tick_id": "tick-1"}
    sql = conn.sql[-1]
    assert "FROM market_ticks" in sql
    assert "target_type = %(target_type)s" in sql
    assert "target_id = %(target_id)s" in sql
    assert "observed_at_ms <= %(at_ms)s" in sql
    assert "observed_at_ms >= %(min_observed_at_ms)s" in sql
    assert "ORDER BY observed_at_ms DESC, received_at_ms DESC, tick_id DESC" in sql
    assert "LIMIT 1" in sql
    assert conn.params[-1] == {
        "target_type": "chain_token",
        "target_id": "solana:abc",
        "at_ms": 1_700_000_100_000,
        "min_observed_at_ms": 1_700_000_070_000,
    }


def test_nearest_around_uses_bounded_observed_range_and_distance_order() -> None:
    conn = _ScriptedConnection([{"tick_id": "tick-nearest"}])

    row = MarketTickRepository(conn).nearest_around(
        target_type="chain_token",
        target_id="solana:abc",
        at_ms=1_700_000_005_000,
        max_lag_ms=5_000,
    )

    assert row == {"tick_id": "tick-nearest"}
    sql = conn.sql[-1]
    assert "observed_at_ms >= %(min_observed_at_ms)s" in sql
    assert "observed_at_ms <= %(max_observed_at_ms)s" in sql
    assert "ORDER BY ABS(observed_at_ms - %(at_ms)s) ASC" in sql
    assert conn.params[-1]["min_observed_at_ms"] == 1_700_000_000_000
    assert conn.params[-1]["max_observed_at_ms"] == 1_700_000_010_000


def test_latest_target_rebuild_uses_bounded_recursive_stable_key_seek() -> None:
    conn = _ScriptedConnection([{"tick_id": "tick-latest", "target_type": "chain_token", "target_id": "solana:abc"}])

    rows = MarketTickRepository(conn).latest_target_ticks_after(
        after=("chain_token", "eip155:1:0xabc"),
        limit=25,
    )

    assert rows == [{"tick_id": "tick-latest", "target_type": "chain_token", "target_id": "solana:abc"}]
    sql = conn.sql[-1]
    assert "WITH RECURSIVE targets(target_type, target_id, position)" in sql
    assert "WHERE targets.position < %(limit)s" in sql
    assert "(ticks.target_type, ticks.target_id) > (targets.target_type, targets.target_id)" in sql
    assert "SELECT DISTINCT target_type, target_id" not in sql
    assert conn.params[-1] == {
        "after_target_type": "chain_token",
        "after_target_id": "eip155:1:0xabc",
        "limit": 25,
    }


class _ScriptedConnection:
    def __init__(
        self,
        rows: list[dict[str, Any] | None] | None = None,
        *,
        rowcounts: list[object] | None = None,
    ) -> None:
        self.rows = list(rows or [])
        self.rowcounts = list(rowcounts or [])
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _Cursor:
        self.sql.append(str(sql))
        self.params.append(params or {})
        if self.rows:
            row = self.rows.pop(0)
        elif "INSERT INTO market_ticks" in sql and "RETURNING tick_id" in sql and params is not None:
            row = {"tick_id": params["tick_id"]}
        else:
            row = None

        if self.rowcounts:
            rowcount = self.rowcounts.pop(0)
        elif row is None:
            rowcount = 0
        else:
            rowcount = 1
        return _Cursor(row, rowcount=rowcount)

    def commit(self) -> None:
        self.commits += 1


class _Cursor:
    def __init__(self, row: dict[str, Any] | None, *, rowcount: object) -> None:
        self.row = row
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    def fetchall(self) -> list[dict[str, Any]]:
        if self.row is None:
            return []
        return [self.row]


def _tick(
    *,
    tick_id: str | None = None,
    observed_at_ms: int = 1_700_000_000_000,
    received_at_ms: int = 1_700_000_000_100,
    source_provider: str = "okx_dex_ws",
    raw_payload_json: dict[str, Any] | None = None,
) -> MarketTick:
    tick_id = tick_id or market_tick_id(
        target_type="chain_token",
        target_id="solana:abc",
        source_provider=source_provider,  # type: ignore[arg-type]
        observed_at_ms=observed_at_ms,
    )
    return MarketTick(
        tick_id=tick_id,
        target_type="chain_token",
        target_id="solana:abc",
        chain="solana",
        token_address="abc",
        exchange=None,
        instrument=None,
        pricefeed_id="pf-1",
        source_tier="tier1_ws",
        source_provider=source_provider,  # type: ignore[arg-type]
        observed_at_ms=observed_at_ms,
        received_at_ms=received_at_ms,
        price_usd=Decimal("1.23"),
        liquidity_usd=Decimal("1000"),
        volume_24h_usd=Decimal("5000"),
        open_interest_usd=None,
        market_cap_usd=Decimal("100000"),
        holders=1234,
        created_at_ms=1_700_000_000_200,
        raw_payload_json=raw_payload_json or {"pair": "abc"},
    )
