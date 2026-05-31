from __future__ import annotations

from decimal import Decimal
from typing import Any

from parallax.domains.token_intel.queries.event_token_projection_query import (
    EventTokenProjectionQuery,
)


def test_event_token_projection_returns_lean_symbol_and_price_payload() -> None:
    conn = _FakeConn(
        [
            {
                "event_id": "event-1",
                "intent_id": "intent-1",
                "resolution_id": "resolution-1",
                "asset_id": "legacy-asset-id",
                "primary_venue_id": "legacy-venue-id",
                "target_type": "Asset",
                "target_id": "asset:solana:token:TokenA",
                "pricefeed_id": None,
                "resolution_status": "EXACT",
                "identity_status": "legacy-resolved",
                "confidence": Decimal("0.99"),
                "resolver_policy_version": "legacy-v1",
                "reasons_json": ["legacy"],
                "risks_json": [],
                "decision_time_ms": 1_700_000_000_000,
                "created_at_ms": 1_700_000_000_000,
                "reason_codes_json": ["ca_match"],
                "candidate_ids_json": [],
                "lookup_keys_json": ["ca:TokenA"],
                "registry_version": 3,
                "record_status": "current",
                "is_current": True,
                "superseded_at_ms": None,
                "symbol": "VOICE",
                "market_tick_id": "tick-1",
                "market_tick_provider": "gmgn_dex_quote",
                "market_tick_observed_at_ms": 1_700_000_000_500,
                "price_usd": Decimal("0.00042"),
                "price_quote": None,
                "price_quote_symbol": None,
                "quote_symbol": None,
                "market_capture_method": "tier3_inline",
                "market_tick_lag_ms": 500,
            }
        ]
    )

    grouped = EventTokenProjectionQuery(conn).for_events(("event-1",))

    resolution = grouped["event-1"][0]
    assert set(resolution) == {
        "resolution_id",
        "intent_id",
        "event_id",
        "target_type",
        "target_id",
        "pricefeed_id",
        "resolution_status",
        "reason_codes_json",
        "candidate_ids_json",
        "lookup_keys_json",
        "symbol",
        "price",
    }
    assert "tir.target_type IN ('Asset', 'CexToken')" in conn.sql
    assert "tir.target_id IS NOT NULL" in conn.sql
    assert resolution["symbol"] == "VOICE"
    assert resolution["price"] == {
        "status": "ready",
        "provider": "gmgn_dex_quote",
        "pricefeed_id": None,
        "price_usd": 0.00042,
        "price_quote": None,
        "quote_symbol": None,
        "observed_at_ms": 1_700_000_000_500,
        "observation_lag_ms": 500,
        "observation_id": "tick-1",
        "observation_kind": "tier3_inline",
    }


def test_event_token_projection_falls_back_to_latest_market_tick_when_event_capture_is_missing() -> None:
    conn = _FakeConn(
        [
            {
                "event_id": "event-1",
                "intent_id": "intent-1",
                "resolution_id": "resolution-1",
                "target_type": "CexToken",
                "target_id": "cex_token:USELESS",
                "pricefeed_id": "pricefeed:cex:binance:swap:USELESSUSDT",
                "resolution_status": "UNIQUE_BY_CONTEXT",
                "reason_codes_json": ["confirmed_cex_token"],
                "candidate_ids_json": [],
                "lookup_keys_json": ["symbol:USELESS"],
                "symbol": "USELESS",
                "market_tick_id": "latest-tick-1",
                "market_tick_provider": "binance_cex_rest",
                "market_tick_observed_at_ms": 1_700_000_060_000,
                "price_usd": Decimal("0.06103"),
                "price_quote": None,
                "price_quote_symbol": None,
                "quote_symbol": "USDT",
                "market_capture_method": "latest_market_tick",
                "market_tick_lag_ms": 60_000,
            }
        ]
    )

    resolution = EventTokenProjectionQuery(conn).for_event("event-1")[0]

    assert "latest_market_tick" in conn.sql
    assert "COALESCE(event_tick.tick_id, latest_tick.tick_id)" in conn.sql
    assert resolution["price"] == {
        "status": "ready",
        "provider": "binance_cex_rest",
        "pricefeed_id": "pricefeed:cex:binance:swap:USELESSUSDT",
        "price_usd": 0.06103,
        "price_quote": None,
        "quote_symbol": "USDT",
        "observed_at_ms": 1_700_000_060_000,
        "observation_lag_ms": 60_000,
        "observation_id": "latest-tick-1",
        "observation_kind": "latest_market_tick",
    }


def test_event_token_projection_uses_sargable_market_target_for_latest_tick() -> None:
    conn = _FakeConn([])

    EventTokenProjectionQuery(conn).for_events(("event-1", "event-2"))

    assert "requested_events(event_id, request_rank)" in conn.sql
    assert "market_target" in conn.sql
    assert "market_ticks.target_type = market_target.target_type" in conn.sql
    assert "market_ticks.target_id = market_target.target_id" in conn.sql
    assert "OR (" not in conn.sql


def test_event_token_projection_omits_unresolved_public_rows() -> None:
    conn = _FakeConn(
        [
            {
                "event_id": "event-1",
                "intent_id": "intent-1",
                "resolution_id": "resolution-1",
                "target_type": None,
                "target_id": None,
                "pricefeed_id": None,
                "resolution_status": "NIL",
                "reason_codes_json": ["ambiguous"],
                "candidate_ids_json": [],
                "lookup_keys_json": [],
                "symbol": None,
                "market_tick_id": None,
                "market_tick_provider": None,
                "market_tick_observed_at_ms": None,
                "price_usd": None,
                "price_quote": None,
                "price_quote_symbol": None,
                "quote_symbol": None,
                "market_capture_method": None,
                "market_tick_lag_ms": None,
            }
        ]
    )

    assert EventTokenProjectionQuery(conn).for_event("event-1") == []


class _FakeConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _FakeConn:
        self.sql = sql
        self.params = params
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows
