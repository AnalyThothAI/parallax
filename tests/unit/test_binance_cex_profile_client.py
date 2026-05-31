from __future__ import annotations

from parallax.integrations.binance.cex_profile_client import BinanceCexProfileClient


def test_binance_cex_profile_client_normalizes_and_dedupes_symbol_profiles():
    http = _HttpClient(
        {
            "code": "000000",
            "data": [
                {
                    "baseAsset": "BTC",
                    "name": "Bitcoin",
                    "logo": "https://bin.bnbstatic.com/slow-btc.png",
                    "rank": 10,
                    "symbol": "BTCUSDT",
                },
                {
                    "baseAsset": "BTC",
                    "name": "Bitcoin",
                    "logo": "https://bin.bnbstatic.com/btc.png",
                    "rank": 1,
                    "symbol": "BTCFDUSD",
                },
                {
                    "name": "ETH",
                    "logo": "https://bin.bnbstatic.com/eth.png",
                    "rank": 2,
                    "symbol": "ETHUSDT",
                },
                {
                    "baseAsset": "BAD",
                    "logo": "not-a-url",
                    "rank": 3,
                    "symbol": "BADUSDT",
                },
            ],
        }
    )

    profiles = BinanceCexProfileClient(http_client=http).token_profiles()

    assert profiles == [
        {
            "base_symbol": "BTC",
            "provider": "binance_cex_profile",
            "symbol": "BTC",
            "name": "Bitcoin",
            "logo_url": "https://bin.bnbstatic.com/btc.png",
            "source_ref": "binance_marketing_symbol_list:BTC",
            "raw_payload": {
                "baseAsset": "BTC",
                "name": "Bitcoin",
                "logo": "https://bin.bnbstatic.com/btc.png",
                "rank": 1,
                "symbol": "BTCFDUSD",
            },
        },
        {
            "base_symbol": "ETH",
            "provider": "binance_cex_profile",
            "symbol": "ETH",
            "name": "ETH",
            "logo_url": "https://bin.bnbstatic.com/eth.png",
            "source_ref": "binance_marketing_symbol_list:ETH",
            "raw_payload": {
                "name": "ETH",
                "logo": "https://bin.bnbstatic.com/eth.png",
                "rank": 2,
                "symbol": "ETHUSDT",
            },
        },
    ]
    assert http.requests == ["/bapi/composite/v1/public/marketing/symbol/list"]


class _HttpClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests: list[str] = []

    def get(self, path: str):
        self.requests.append(path)
        return _Response(self.payload)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload
