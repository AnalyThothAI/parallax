from __future__ import annotations

import httpx

from gmgn_twitter_intel.market.gmgn_openapi_client import GmgnOpenApiClient


def test_gmgn_openapi_client_fetches_token_info_with_normal_auth_and_cache():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-APIKEY"] == "gmgn-test"
        assert request.url.path == "/v1/token/info"
        assert request.url.params["chain"] == "sol"
        assert request.url.params["address"] == "So11111111111111111111111111111111111111112"
        assert request.url.params["timestamp"]
        assert request.url.params["client_id"]
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "address": "So11111111111111111111111111111111111111112",
                    "symbol": "SOL",
                    "name": "Solana",
                    "price": "150.5",
                    "circulating_supply": "1000",
                    "logo": "https://example.test/sol.png",
                },
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        first = client.get_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
        second = client.get_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
    finally:
        client.close()

    assert first == second
    assert first is not None
    assert first.symbol == "SOL"
    assert first.price == 150.5
    assert first.market_cap == 150500.0
    assert requests[0].content == b""
    assert len(requests) == 1


def test_gmgn_openapi_client_maps_internal_solana_chain_to_openapi_sol():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["chain"] == "sol"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "address": "So11111111111111111111111111111111111111112",
                    "symbol": "SOL",
                    "price": "150.5",
                },
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        info = client.get_token_info(chain="solana", address="So11111111111111111111111111111111111111112")
    finally:
        client.close()

    assert info is not None
    assert info.chain == "solana"
