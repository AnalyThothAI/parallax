from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.providers import MarketCandle
from gmgn_twitter_intel.domains.asset_market.read_models.market_candles_service import MarketCandlesService


def test_market_candles_service_enriches_cex_payload_with_ohlc_series():
    service = MarketCandlesService(cex_market=FakeCexMarket(), dex_candle_market=None)

    market_candles = service.enrich_market_candles(
        {
            "target_type": "CexToken",
            "target_id": "cex_token:BONK",
            "provider": "okx",
            "native_market_id": "BONK-USDT",
        },
        window="24h",
    )

    assert market_candles["price_series_type"] == "ohlc"
    assert market_candles["candle_status"] == "ready"
    assert market_candles["candle_source"] == "binance_cex_candles"
    assert market_candles["candle_bar"] == "1H"
    assert market_candles["candles"][0]["open"] == 0.000027
    assert market_candles["candles"][0]["high"] == 0.0000285
    assert market_candles["candles"][0]["low"] == 0.0000268
    assert market_candles["candles"][0]["close"] == 0.0000281


def test_market_candles_service_enriches_dex_payload_with_ohlc_series():
    service = MarketCandlesService(cex_market=None, dex_candle_market=FakeDexMarket())

    market_candles = service.enrich_market_candles(
        {
            "target_type": "Asset",
            "target_id": "asset:eip155:56:erc20:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "chain_id": "eip155:56",
            "address": "0x8F32420F2E3728C49399b00DD0A796602d984444",
        },
        window="1h",
    )

    assert market_candles["price_series_type"] == "ohlc"
    assert market_candles["candle_status"] == "ready"
    assert market_candles["candle_source"] == "gmgn_dex_candles"
    assert market_candles["candle_bar"] == "5m"
    assert market_candles["candles"][0]["volume_usd"] == 625.0


def test_market_candles_service_keeps_anchor_line_when_provider_is_unavailable():
    service = MarketCandlesService(cex_market=None, dex_candle_market=None)

    market_candles = service.enrich_market_candles(
        {"target_type": "CexToken", "target_id": "cex_token:BONK", "native_market_id": "BONK-USDT"},
        window="24h",
    )

    assert market_candles["price_series_type"] == "anchor_line"
    assert market_candles["candle_status"] == "unsupported"
    assert market_candles["candles"] == []


class FakeCexMarket:
    def candles(self, *, inst_id: str, bar: str, limit: int) -> list[MarketCandle]:
        assert inst_id == "BONK-USDT"
        assert bar == "1H"
        assert limit == 48
        return [
            MarketCandle(
                time_ms=1_778_083_200_000,
                open=0.000027,
                high=0.0000285,
                low=0.0000268,
                close=0.0000281,
                volume=1000.0,
                volume_quote=0.0281,
                volume_usd=None,
                confirmed=True,
                raw={},
            )
        ]


class FakeDexMarket:
    def token_candles(self, *, chain_id: str, address: str, bar: str, limit: int) -> list[MarketCandle]:
        assert chain_id == "eip155:56"
        assert address == "0x8F32420F2E3728C49399b00DD0A796602d984444"
        assert bar == "5m"
        assert limit == 24
        return [
            MarketCandle(
                time_ms=1_778_085_000_000,
                open=0.12,
                high=0.13,
                low=0.11,
                close=0.125,
                volume=5000.0,
                volume_quote=None,
                volume_usd=625.0,
                confirmed=False,
                raw={},
            )
        ]
