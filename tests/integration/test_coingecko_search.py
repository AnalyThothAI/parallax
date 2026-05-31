from __future__ import annotations

import httpx

from parallax.integrations.coingecko.search_client import (
    CoingeckoSearchClient,
    CoingeckoSearchHit,
)


def _mock_transport(payload: dict, *, expected_query: str = "TROLL") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/search"
        assert request.url.params.get("query") == expected_query
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_search_returns_platform_hit_for_known_chain() -> None:
    payload = {
        "coins": [
            {
                "id": "trollcoin",
                "symbol": "troll",
                "name": "Troll",
                "platforms": {
                    "ethereum": "0xf8ebf4849f1fa4faf0dff2106a173d3a6cb2eb3a",
                    "binance-smart-chain": "",
                },
            }
        ]
    }
    client = CoingeckoSearchClient(transport=_mock_transport(payload))

    hits = client.search(symbol="TROLL", chain="ethereum")

    assert hits == [
        CoingeckoSearchHit(
            coin_id="trollcoin",
            symbol="troll",
            chain="ethereum",
            address="0xf8ebf4849f1fa4faf0dff2106a173d3a6cb2eb3a",
        )
    ]


def test_search_returns_empty_when_chain_missing() -> None:
    payload = {
        "coins": [{"id": "trollcoin", "symbol": "troll", "name": "Troll", "platforms": {"polygon-pos": "0xabc"}}]
    }
    client = CoingeckoSearchClient(transport=_mock_transport(payload))

    hits = client.search(symbol="TROLL", chain="ethereum")

    assert hits == []


def test_search_unknown_chain_returns_empty() -> None:
    payload = {"coins": [{"id": "x", "symbol": "x", "name": "x", "platforms": {}}]}
    client = CoingeckoSearchClient(transport=_mock_transport(payload))

    assert client.search(symbol="TROLL", chain="monad") == []


def test_search_handles_empty_response() -> None:
    client = CoingeckoSearchClient(transport=_mock_transport({"coins": []}))
    assert client.search(symbol="TROLL", chain="ethereum") == []


def test_search_passes_symbol_as_query() -> None:
    payload = {
        "coins": [
            {
                "id": "pepe",
                "symbol": "pepe",
                "name": "Pepe",
                "platforms": {"ethereum": "0x6982508145454ce325ddbe47a25d4ec3d2311933"},
            }
        ]
    }
    client = CoingeckoSearchClient(transport=_mock_transport(payload, expected_query="PEPE"))

    hits = client.search(symbol="PEPE", chain="ethereum")

    assert hits == [
        CoingeckoSearchHit(
            coin_id="pepe",
            symbol="pepe",
            chain="ethereum",
            address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
        )
    ]
