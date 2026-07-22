from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from parallax.integrations.binance.usdm_futures_client import BinanceUsdmFuturesClient, BinanceUsdmFuturesClientError


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


def test_usdt_perpetual_routes_do_not_restore_retired_multiplier_alias() -> None:
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
                        "multiplier": "1000",
                    }
                ]
            }
        }
    )

    routes = BinanceUsdmFuturesClient(transport=transport).usdt_perpetual_routes()

    assert routes[0].multiplier is None


def test_ticker_24hr_keeps_raw_payload_and_symbol_params() -> None:
    transport = _JsonTransport(
        {
            "/fapi/v1/ticker/24hr?symbol=BTCUSDT": {
                "symbol": "BTCUSDT",
                "lastPrice": "100.5",
                "quoteVolume": "12345.67",
                "volume": "99",
            },
        }
    )
    client = BinanceUsdmFuturesClient(transport=transport)

    ticker = client.ticker_24hr(symbol="btcusdt")

    assert ticker.symbol == "BTCUSDT"
    assert ticker.last_price == 100.5
    assert ticker.quote_volume_24h == 12345.67
    assert ticker.raw["quoteVolume"] == "12345.67"


@pytest.mark.parametrize("value", ("not-a-number", True, "nan", "inf"))
def test_binance_usdm_client_rejects_malformed_present_numeric_fields(value: object) -> None:
    transport = _JsonTransport(
        {
            "/fapi/v1/ticker/24hr?symbol=BTCUSDT": {
                "symbol": "BTCUSDT",
                "lastPrice": value,
            }
        }
    )

    with pytest.raises(BinanceUsdmFuturesClientError, match="Binance numeric field is invalid"):
        BinanceUsdmFuturesClient(transport=transport).ticker_24hr(symbol="BTCUSDT")


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
