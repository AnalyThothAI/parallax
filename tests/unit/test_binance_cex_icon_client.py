from __future__ import annotations

from gmgn_twitter_intel.integrations.binance.cex_icon_client import BinanceCexIconClient


def test_binance_cex_icon_client_normalizes_and_dedupes_symbol_icons():
    http = _HttpClient(
        {
            "code": "000000",
            "data": [
                {
                    "baseAsset": "BTC",
                    "name": "BTC",
                    "logo": "https://bin.bnbstatic.com/slow-btc.png",
                    "rank": 10,
                    "symbol": "BTCUSDT",
                },
                {
                    "baseAsset": "BTC",
                    "name": "BTC",
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

    icons = BinanceCexIconClient(http_client=http).token_icons()

    assert icons == [
        {
            "base_symbol": "BTC",
            "logo_url": "https://bin.bnbstatic.com/btc.png",
            "source": "binance_marketing_symbol_list",
            "source_ref": "binance_marketing_symbol_list:BTC",
        },
        {
            "base_symbol": "ETH",
            "logo_url": "https://bin.bnbstatic.com/eth.png",
            "source": "binance_marketing_symbol_list",
            "source_ref": "binance_marketing_symbol_list:ETH",
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
