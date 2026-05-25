from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.read_models.market_candles_service import MarketCandlesService


def test_market_candles_service_is_provider_free_for_cex_payloads():
    service = MarketCandlesService()

    market_candles = service.enrich_market_candles(
        {
            "target_type": "CexToken",
            "target_id": "cex_token:BONK",
            "provider": "okx",
            "native_market_id": "BONK-USDT",
        },
        window="24h",
    )

    assert market_candles["price_series_type"] == "anchor_line"
    assert market_candles["candle_status"] == "unsupported"
    assert "candle_source" not in market_candles
    assert market_candles["candle_bar"] == "1H"
    assert market_candles["candles"] == []


def test_market_candles_service_is_provider_free_for_dex_payloads():
    service = MarketCandlesService()

    market_candles = service.enrich_market_candles(
        {
            "target_type": "Asset",
            "target_id": "asset:eip155:56:erc20:0x8f32420f2e3728c49399b00dd0a796602d984444",
            "chain_id": "eip155:56",
            "address": "0x8F32420F2E3728C49399b00DD0A796602d984444",
        },
        window="1h",
    )

    assert market_candles["price_series_type"] == "anchor_line"
    assert market_candles["candle_status"] == "unsupported"
    assert "candle_source" not in market_candles
    assert market_candles["candle_bar"] == "5m"
    assert market_candles["candles"] == []


def test_market_candles_service_preserves_missing_identity_status_without_provider_io():
    service = MarketCandlesService()

    market_candles = service.enrich_market_candles(
        {"target_type": "Asset", "target_id": "asset:eip155:1:erc20:0xabc"},
        window="24h",
    )

    assert market_candles["price_series_type"] == "anchor_line"
    assert market_candles["candle_status"] == "missing_identity"
    assert market_candles["candles"] == []
