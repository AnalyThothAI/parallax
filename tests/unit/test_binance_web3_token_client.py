from __future__ import annotations

from gmgn_twitter_intel.integrations.binance.web3_token_client import BinanceWeb3TokenClient


def test_binance_web3_token_client_maps_domain_chains_and_normalizes_icon_urls():
    http = _HttpClient(
        {
            "code": "000000",
            "success": True,
            "data": {
                "tokenId": "CC1F457B",
                "name": "Tether USD",
                "symbol": "USDT",
                "chainId": "56",
                "chainName": "BSC",
                "contractAddress": "0x55d398326f99059ff775485246999027b3197955",
                "decimals": 18,
                "icon": "/images/web3-data/public/token/logos/usdt.png",
                "links": [
                    {"label": "website", "link": "https://tether.to/"},
                    {"label": "x", "link": "https://twitter.com/Tether_to"},
                    {"label": "tg", "link": "https://t.me/tether"},
                ],
                "description": "USD stablecoin",
            },
        }
    )

    metadata = BinanceWeb3TokenClient(http_client=http).token_metadata(
        chain_id="eip155:56",
        address="0x55d398326f99059ff775485246999027b3197955",
    )

    assert metadata is not None
    assert metadata.chain_id == "eip155:56"
    assert metadata.address == "0x55d398326f99059ff775485246999027b3197955"
    assert metadata.logo_url == "https://bin.bnbstatic.com/images/web3-data/public/token/logos/usdt.png"
    assert metadata.website == "https://tether.to/"
    assert metadata.twitter_url == "https://twitter.com/Tether_to"
    assert metadata.telegram == "https://t.me/tether"
    assert metadata.raw["source_provider"] == "binance_web3_profile"
    assert http.requests == [
        (
            "/bapi/defi/v1/public/wallet-direct/buw/wallet/dex/market/token/meta/info/ai",
            {
                "chainId": "56",
                "contractAddress": "0x55d398326f99059ff775485246999027b3197955",
            },
        )
    ]


def test_binance_web3_token_client_returns_none_for_unsupported_chain_without_http_call():
    http = _HttpClient({"code": "000000", "success": True, "data": {}})

    metadata = BinanceWeb3TokenClient(http_client=http).token_metadata(chain_id="ton", address="EQ...")

    assert metadata is None
    assert http.requests == []


class _HttpClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, *, params: dict[str, str]):
        self.requests.append((path, dict(params)))
        return _Response(self.payload)


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload
