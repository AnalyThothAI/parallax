from __future__ import annotations

from parallax.domains.cex_market_intel.services.cex_detail_snapshot_builder import (
    build_cex_detail_snapshot,
)


def test_build_cex_detail_snapshot_keeps_non_hourly_oi_delta_out_of_1h_slot() -> None:
    snapshot = build_cex_detail_snapshot(
        row={
            "target_id": "binance:BTCUSDT",
            "cex_token_id": "cex_token:BTC",
            "native_market_id": "BTCUSDT",
            "base_symbol": "BTC",
            "quote_symbol": "USDT",
            "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
            "mark_price": 101.0,
            "open_interest_usd": 1100.0,
            "open_interest_change_pct_1h": 10.0,
            "volume_24h_usd": 10_000_000.0,
            "funding_rate": 0.0001,
            "observed_at_ms": 1_778_000_000_000,
        },
        computed_at_ms=1_778_000_000_000,
        period="5m",
    )

    assert snapshot["snapshot_id"] == "cex-detail:binance:BTCUSDT"
    assert snapshot["target_type"] == "CexToken"
    assert snapshot["target_id"] == "cex_token:BTC"
    assert snapshot["baseline_status"] == "ready"
    assert snapshot["coinglass_status"] == "unavailable"
    assert snapshot["oi_change_pct_1h"] is None
    assert "oi_change_period_5m_not_1h" in snapshot["degraded_reasons"]
    assert "metric:cex:open_interest_usd:BTCUSDT" in [ref["ref_id"] for ref in snapshot["source_refs"]]


def test_build_cex_detail_snapshot_maps_hourly_period_to_hourly_delta() -> None:
    snapshot = build_cex_detail_snapshot(
        row={
            "target_id": "binance:ETHUSDT",
            "cex_token_id": "cex_token:ETH",
            "native_market_id": "ETHUSDT",
            "base_symbol": "ETH",
            "quote_symbol": "USDT",
            "open_interest_usd": 2000.0,
            "open_interest_change_pct_1h": -2.5,
            "observed_at_ms": 1_778_000_000_000,
        },
        computed_at_ms=1_778_000_000_000,
        period="1h",
    )

    assert snapshot["oi_change_pct_1h"] == -2.5
    assert "oi_change_period_1h_not_1h" not in snapshot["degraded_reasons"]
