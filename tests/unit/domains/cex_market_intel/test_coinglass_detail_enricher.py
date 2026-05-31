from __future__ import annotations

from parallax.domains.cex_market_intel.services.coinglass_detail_enricher import (
    enrich_rows_with_coinglass,
)


def test_enrich_rows_with_coinglass_maps_derivatives_and_levels_for_top_k() -> None:
    rows = [
        {"base_symbol": "BTC", "native_market_id": "BTCUSDT"},
        {"base_symbol": "ETH", "native_market_id": "ETHUSDT"},
    ]

    enriched = enrich_rows_with_coinglass(rows, client=_Client(), now_ms=1_800_000_000_000, limit=1)

    assert enriched[0]["coinglass_status"] == "ready"
    assert enriched[0]["oi_change_pct_1h"] == 10.0
    assert enriched[0]["oi_change_pct_4h"] == 25.0
    assert enriched[0]["oi_change_pct_24h"] == 50.0
    assert enriched[0]["cvd_delta_4h"] == 125.0
    assert enriched[0]["long_short_ratio"] == 1.3
    assert enriched[0]["top_trader_position_ratio"] == 1.6
    assert enriched[0]["level_bands"][0]["kind"] == "resistance"
    assert "coinglass_status" not in enriched[1]


class _Client:
    def fetch_oi_history(self, *, symbol, time_type, lookback):
        values = {"1": (100, 110), "2": (100, 125), "4": (100, 150)}[time_type]
        return {"data": [{"timestamp": 1, "usd": values[0]}, {"timestamp": 2, "usd": values[1]}]}

    def fetch_cvd_history(self, *, symbol, time_type, lookback):
        deltas = {"1": [10, -5], "2": [100, 25], "4": [300, -50]}[time_type]
        return {"data": [{"timestamp": index, "delta": delta} for index, delta in enumerate(deltas)]}

    def fetch_long_short_ratio_history(self, *, symbol, time_type, lookback):
        return {"data": [{"timestamp": 1, "longShortRatio": 1.1}, {"timestamp": 2, "longShortRatio": 1.3}]}

    def fetch_top_trader_position_history(self, *, symbol, time_type, lookback):
        return {"data": [{"timestamp": 1, "longShortRatio": 1.4}, {"timestamp": 2, "longShortRatio": 1.6}]}

    def fetch_liquidation_levels(self, *, symbol, range):
        return {
            "levels": [
                {"price": 72_000, "size": 2_000_000_000, "side": 2},
                {"price": 64_000, "size": 1_000_000_000, "side": 1},
            ]
        }
