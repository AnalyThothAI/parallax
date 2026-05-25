from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"


def test_search_read_paths_do_not_reach_runtime_asset_market_providers() -> None:
    source = (SRC / "app/surfaces/api/routes_search.py").read_text()

    forbidden = (
        "runtime.providers",
        "cex_market",
        "dex_candle_market",
    )
    assert [token for token in forbidden if token in source] == []


def test_market_candles_read_model_has_no_provider_io() -> None:
    source = (SRC / "domains/asset_market/read_models/market_candles_service.py").read_text()

    forbidden = (
        "providers import MarketCandle",
        ".candles(",
        "token_candles(",
        "cex_market",
        "dex_candle_market",
    )
    assert [token for token in forbidden if token in source] == []


def test_stocks_radar_api_and_read_model_do_not_reach_quote_provider() -> None:
    route_source = (SRC / "app/surfaces/api/routes_radar.py").read_text()
    service_source = (SRC / "domains/token_intel/read_models/stocks_radar_service.py").read_text()

    assert "stock_quote_provider" not in route_source
    assert "quote_provider" not in route_source
    assert "quote_provider" not in service_source
    assert "ThreadPoolExecutor" not in service_source
    assert ".quote(" not in service_source
