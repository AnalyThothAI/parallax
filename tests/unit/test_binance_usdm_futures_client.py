from __future__ import annotations

import json
from typing import Any

import httpx

from parallax.integrations.binance.usdm_futures_client import BinanceUsdmFuturesClient


def test_usdt_perpetual_routes_filter_exchange_info_without_symbol_slicing() -> None:
    transport = _JsonTransport(
        {
            "/fapi/v1/exchangeInfo": {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                    },
                    {
                        "symbol": "1000PEPEUSDT",
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "baseAsset": "1000PEPE",
                        "quoteAsset": "USDT",
                        "contractSize": "1000",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "status": "BREAK",
                        "contractType": "PERPETUAL",
                        "baseAsset": "ETH",
                        "quoteAsset": "USDT",
                    },
                    {
                        "symbol": "BTCUSDC",
                        "status": "TRADING",
                        "contractType": "PERPETUAL",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDC",
                    },
                    {
                        "symbol": "SOLUSDT_240628",
                        "status": "TRADING",
                        "contractType": "CURRENT_QUARTER",
                        "baseAsset": "SOL",
                        "quoteAsset": "USDT",
                    },
                ]
            }
        }
    )

    routes = BinanceUsdmFuturesClient(transport=transport).usdt_perpetual_routes()

    assert [route.native_market_id for route in routes] == ["1000PEPEUSDT", "BTCUSDT"]
    assert routes[0].provider == "binance"
    assert routes[0].feed_type == "cex_swap"
    assert routes[0].quote_symbol == "USDT"
    assert routes[0].base_symbol == "1000PEPE"
    assert routes[0].multiplier == 1000.0
    assert routes[0].raw["symbol"] == "1000PEPEUSDT"


def test_ticker_24hr_and_premium_index_keep_raw_payload_and_symbol_params() -> None:
    transport = _JsonTransport(
        {
            "/fapi/v1/ticker/24hr?symbol=BTCUSDT": {
                "symbol": "BTCUSDT",
                "lastPrice": "100.5",
                "quoteVolume": "12345.67",
                "volume": "99",
            },
            "/fapi/v1/premiumIndex?symbol=BTCUSDT": {
                "symbol": "BTCUSDT",
                "markPrice": "101.5",
                "indexPrice": "101.2",
                "lastFundingRate": "0.0001",
                "nextFundingTime": 1710000000000,
            },
        }
    )
    client = BinanceUsdmFuturesClient(transport=transport)

    ticker = client.ticker_24hr(symbol="btcusdt")
    premium = client.premium_index(symbol="btcusdt")

    assert ticker.symbol == "BTCUSDT"
    assert ticker.last_price == 100.5
    assert ticker.quote_volume_24h == 12345.67
    assert ticker.raw["quoteVolume"] == "12345.67"
    assert premium.symbol == "BTCUSDT"
    assert premium.mark_price == 101.5
    assert premium.index_price == 101.2
    assert premium.last_funding_rate == 0.0001
    assert premium.next_funding_time_ms == 1710000000000
    assert premium.raw["markPrice"] == "101.5"


def test_open_interest_hist_maps_rows_with_period_and_limit() -> None:
    transport = _JsonTransport(
        {
            "/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&limit=2": [
                {
                    "symbol": "BTCUSDT",
                    "sumOpenInterest": "10.5",
                    "sumOpenInterestValue": "20000.25",
                    "timestamp": 1710000000000,
                }
            ]
        }
    )

    rows = BinanceUsdmFuturesClient(transport=transport).open_interest_hist(
        symbol="btcusdt",
        period="5m",
        limit=2,
    )

    assert len(rows) == 1
    assert rows[0].symbol == "BTCUSDT"
    assert rows[0].period == "5m"
    assert rows[0].open_interest == 10.5
    assert rows[0].open_interest_value == 20000.25
    assert rows[0].time_ms == 1710000000000
    assert rows[0].raw["sumOpenInterest"] == "10.5"


def test_ticker_and_candles_map_simple_market_models() -> None:
    transport = _JsonTransport(
        {
            "/fapi/v1/ticker/price?symbol=BTCUSDT": {
                "symbol": "BTCUSDT",
                "price": "102.5",
                "time": 1710000000123,
            },
            "/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=2": [
                [
                    1710000000000,
                    "100",
                    "110",
                    "90",
                    "105",
                    "12.3",
                    1710000059999,
                    "1291.5",
                    42,
                    "6.0",
                    "630.0",
                    "0",
                ]
            ],
        }
    )
    client = BinanceUsdmFuturesClient(transport=transport)

    ticker = client.ticker("btcusdt")
    candles = client.candles("btcusdt", interval="1m", limit=2)

    assert ticker.symbol == "BTCUSDT"
    assert ticker.price == 102.5
    assert ticker.time_ms == 1710000000123
    assert ticker.raw["price"] == "102.5"
    assert len(candles) == 1
    assert candles[0].symbol == "BTCUSDT"
    assert candles[0].interval == "1m"
    assert candles[0].open_time_ms == 1710000000000
    assert candles[0].close_time_ms == 1710000059999
    assert candles[0].open == 100.0
    assert candles[0].high == 110.0
    assert candles[0].low == 90.0
    assert candles[0].close == 105.0
    assert candles[0].volume == 12.3
    assert candles[0].quote_volume == 1291.5
    assert candles[0].raw[0] == 1710000000000


class _JsonTransport(httpx.MockTransport):
    def __init__(self, responses: dict[str, Any]) -> None:
        self.requests: list[str] = []
        self.responses = responses
        super().__init__(self._handler)

    def _handler(self, request: httpx.Request) -> httpx.Response:
        key = request.url.raw_path.decode()
        self.requests.append(key)
        if key not in self.responses:
            return httpx.Response(404, json={"error": f"missing mock for {key}"})
        return httpx.Response(
            200,
            content=json.dumps(self.responses[key]).encode("utf-8"),
            headers={"content-type": "application/json"},
        )
