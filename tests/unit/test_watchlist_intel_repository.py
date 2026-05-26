from __future__ import annotations

from decimal import Decimal
from typing import Any

from gmgn_twitter_intel.domains.watchlist_intel.repositories.watchlist_intel_repository import (
    WatchlistIntelRepository,
)


def test_token_resolutions_for_events_projects_symbol_and_event_price() -> None:
    conn = _FakeConn(
        [
            {
                "event_id": "event-1",
                "intent_id": "intent-1",
                "resolution_id": "resolution-1",
                "target_type": "Asset",
                "target_id": "asset:solana:token:TokenA",
                "pricefeed_id": None,
                "resolution_status": "EXACT",
                "reason_codes_json": ["ca_match"],
                "candidate_ids_json": [],
                "lookup_keys_json": [],
                "symbol": "VOICE",
                "market_tick_id": "tick-1",
                "market_tick_provider": "gmgn_dex_quote",
                "market_tick_observed_at_ms": 1_700_000_000_000,
                "price_usd": Decimal("0.00042"),
                "price_quote": None,
                "price_quote_symbol": None,
                "quote_symbol": None,
                "market_capture_method": "tier3_inline",
                "market_tick_lag_ms": 500,
            }
        ]
    )

    grouped = WatchlistIntelRepository(conn).token_resolutions_for_events(("event-1",))

    resolution = grouped["event-1"][0]
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
        "observed_at_ms": 1_700_000_000_000,
        "observation_lag_ms": 500,
        "observation_id": "tick-1",
        "observation_kind": "tier3_inline",
    }


def test_signal_events_for_summary_limits_before_event_join() -> None:
    conn = _FakeConn([])

    rows = WatchlistIntelRepository(conn).signal_events_for_summary(handle="Toly", since_ms=0, limit=10)

    assert rows == []
    assert "WITH selected AS" in conn.sql
    assert "normalized_handle = %s" in conn.sql
    assert "LIMIT %s" in conn.sql.split("FROM selected se", maxsplit=1)[0]
    assert "JOIN events e ON e.event_id = se.event_id" in conn.sql
    assert "lower(coalesce" not in conn.sql


class _FakeConn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.sql = ""

    def execute(self, sql: str, *_: Any) -> _FakeConn:
        self.sql = sql
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows
