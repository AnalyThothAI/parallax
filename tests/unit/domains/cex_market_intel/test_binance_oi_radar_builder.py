from __future__ import annotations

from types import SimpleNamespace

from parallax.domains.cex_market_intel.services.binance_oi_radar_builder import (
    build_binance_oi_radar_rows,
)


def test_build_binance_oi_radar_rows_scores_and_ranks_binance_universe():
    rows = build_binance_oi_radar_rows(
        universe=[
            {
                "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                "native_market_id": "BTCUSDT",
                "base_symbol": "BTC",
            }
        ],
        client=_Client(),
        now_ms=1_778_000_000_000,
        period="5m",
        limit=10,
    )

    assert rows["processed"] == 1
    assert rows["failed"] == 0
    assert rows["rows"][0]["rank"] == 1
    assert rows["rows"][0]["target_id"] == "binance:BTCUSDT"
    assert rows["rows"][0]["open_interest_usd"] == 1100.0
    assert rows["rows"][0]["open_interest_change_pct_1h"] == 10.0
    assert rows["rows"][0]["funding_rate"] == 0.0001
    assert rows["rows"][0]["score"] > 0


class _Client:
    def ticker_24hr(self):
        return [SimpleNamespace(symbol="BTCUSDT", last_price=100.0, quote_volume_24h=10_000_000.0)]

    def premium_index(self):
        return [SimpleNamespace(symbol="BTCUSDT", mark_price=101.0, last_funding_rate=0.0001)]

    def open_interest_hist(self, *, symbol, period, limit):
        assert symbol == "BTCUSDT"
        assert period == "5m"
        assert limit == 2
        return [
            SimpleNamespace(symbol=symbol, open_interest_value=1000.0, time_ms=1),
            SimpleNamespace(symbol=symbol, open_interest_value=1100.0, time_ms=2),
        ]
