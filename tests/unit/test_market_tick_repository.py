from __future__ import annotations

from decimal import Decimal
from typing import Any

from gmgn_twitter_intel.domains.asset_market.repositories.market_tick_repository import (
    MarketTickRepository,
    market_tick_id,
)
from gmgn_twitter_intel.domains.asset_market.types import MarketTick


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


def test_insert_tick_rejects_non_deterministic_tick_id() -> None:
    conn = _ScriptedConnection([])

    try:
        MarketTickRepository(conn).insert_tick(_tick(tick_id="tick-1"))
    except ValueError as exc:
        assert "market tick id must be deterministic" in str(exc)
    else:
        raise AssertionError("expected insert_tick to reject a mismatched tick_id")

    assert conn.sql == []


def test_insert_market_tick_is_idempotent_without_update() -> None:
    conn = _ScriptedConnection([])
    tick = _tick()

    repository = MarketTickRepository(conn)
    assert repository.insert_tick(tick) == tick.tick_id
    assert repository.insert_tick(tick) == tick.tick_id

    sql = "\n".join(conn.sql)
    assert "INSERT INTO market_ticks" in sql
    assert "ON CONFLICT(target_type, target_id, source_provider, observed_at_ms) DO NOTHING" in sql
    assert "RETURNING tick_id" in sql
    assert "UPDATE market_ticks" not in sql
    assert conn.commits == 0
    assert len(conn.params) == 2
    assert conn.params[0]["tick_id"] == tick.tick_id
    assert conn.params[0]["holders"] == 1234
    assert conn.params[0]["raw_payload_json"].obj == {"pair": "abc"}


def test_insert_market_tick_strips_nul_bytes_from_raw_payload() -> None:
    conn = _ScriptedConnection([])
    tick = _tick(raw_payload_json={"symbol\x00": "ZEC\x00", "links": ["https://x.example/\x00zec"]})

    MarketTickRepository(conn).insert_tick(tick)

    assert conn.params[0]["raw_payload_json"].obj == {
        "symbol": "ZEC",
        "links": ["https://x.example/zec"],
    }


def test_insert_ticks_returns_actual_inserted_count() -> None:
    first_tick = _tick(observed_at_ms=1_700_000_000_000)
    duplicate_tick = _tick(observed_at_ms=1_700_000_000_000)
    conn = _ScriptedConnection([{"tick_id": first_tick.tick_id}, None])

    count = MarketTickRepository(conn).insert_ticks([first_tick, duplicate_tick])

    assert count == 1
    assert len(conn.sql) == 2


def test_insert_ticks_returning_ids_returns_only_inserted_ids() -> None:
    first_tick = _tick(observed_at_ms=1_700_000_000_000)
    second_tick = _tick(observed_at_ms=1_700_000_000_001)
    conn = _ScriptedConnection([{"tick_id": first_tick.tick_id}, {"tick_id": second_tick.tick_id}])

    inserted_ids = MarketTickRepository(conn).insert_ticks_returning_ids([first_tick, second_tick])

    assert inserted_ids == [first_tick.tick_id, second_tick.tick_id]


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


def test_latest_for_target_uses_received_age_and_order() -> None:
    conn = _ScriptedConnection([None])

    row = MarketTickRepository(conn).latest_for_target(
        target_type="cex_symbol",
        target_id="OKX:BTC-USDT",
        max_age_ms=60_000,
        now_ms=1_700_000_200_000,
    )

    assert row is None
    sql = conn.sql[-1]
    assert "received_at_ms >= %(min_received_at_ms)s" in sql
    assert "ORDER BY observed_at_ms DESC, received_at_ms DESC, tick_id DESC" in sql
    assert conn.params[-1]["min_received_at_ms"] == 1_700_000_140_000


def test_first_between_uses_inclusive_observed_range_and_ascending_order() -> None:
    conn = _ScriptedConnection([{"tick_id": "tick-early"}])

    row = MarketTickRepository(conn).first_between(
        target_type="chain_token",
        target_id="solana:abc",
        start_ms=1_700_000_000_000,
        end_ms=1_700_000_010_000,
    )

    assert row == {"tick_id": "tick-early"}
    sql = conn.sql[-1]
    assert "observed_at_ms >= %(start_ms)s" in sql
    assert "observed_at_ms <= %(end_ms)s" in sql
    assert "ORDER BY observed_at_ms ASC, received_at_ms ASC, tick_id ASC" in sql
    assert conn.params[-1]["start_ms"] == 1_700_000_000_000
    assert conn.params[-1]["end_ms"] == 1_700_000_010_000


class _ScriptedConnection:
    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self.rows = list(rows)
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.commits = 0

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _ScriptedConnection:
        self.sql.append(str(sql))
        self.params.append(params or {})
        return self

    def fetchone(self) -> dict[str, Any] | None:
        if not self.rows:
            return None
        return self.rows.pop(0)

    def commit(self) -> None:
        self.commits += 1


def _tick(
    *,
    tick_id: str | None = None,
    observed_at_ms: int = 1_700_000_000_000,
    raw_payload_json: dict[str, Any] | None = None,
) -> MarketTick:
    tick_id = tick_id or market_tick_id(
        target_type="chain_token",
        target_id="solana:abc",
        source_provider="okx_dex_ws",
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
        source_provider="okx_dex_ws",
        observed_at_ms=observed_at_ms,
        received_at_ms=1_700_000_000_100,
        price_usd=Decimal("1.23"),
        liquidity_usd=Decimal("1000"),
        volume_24h_usd=Decimal("5000"),
        market_cap_usd=Decimal("100000"),
        holders=1234,
        created_at_ms=1_700_000_000_200,
        raw_payload_json=raw_payload_json or {"pair": "abc"},
    )
