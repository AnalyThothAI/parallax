from __future__ import annotations

import httpx
import pytest
from curl_cffi import CurlOpt

import gmgn_twitter_intel.integrations.gmgn.openapi_client as gmgn_openapi_client_module
from gmgn_twitter_intel.integrations.gmgn.openapi_client import CURL_IPRESOLVE_V4, GmgnOpenApiClient


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
                    "decimals": 9,
                    "price": "150.5",
                    "liquidity": "2500000.25",
                    "holder_count": "12345",
                    "circulating_supply": "1000",
                    "total_supply": "1000",
                    "max_supply": "1000",
                    "logo": "https://example.test/sol.png",
                    "banner": "https://example.test/banner.png",
                    "pool": {"exchange": "raydium", "pool_address": "pool-1"},
                    "link": {
                        "website": "https://solana.com",
                        "twitter_username": "solana",
                        "telegram": "https://t.me/solana",
                        "gmgn": "https://gmgn.ai/sol/token/So11111111111111111111111111111111111111112",
                        "geckoterminal": "https://www.geckoterminal.com/solana/tokens/So11111111111111111111111111111111111111112",
                        "description": "Layer 1",
                    },
                },
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        first = client.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
        second = client.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
    finally:
        client.close()

    assert first.info == second.info
    assert first.info is not None
    assert first.info.symbol == "SOL"
    assert first.info.decimals == 9
    assert first.info.price == 150.5
    assert first.info.market_cap == 150500.0
    assert first.info.liquidity == 2500000.25
    assert first.info.holder_count == 12345
    assert first.info.circulating_supply == 1000.0
    assert first.info.website == "https://solana.com"
    assert first.info.twitter_username == "solana"
    assert first.info.telegram == "https://t.me/solana"
    assert first.info.gmgn_url == "https://gmgn.ai/sol/token/So11111111111111111111111111111111111111112"
    assert first.info.geckoterminal_url.startswith("https://www.geckoterminal.com/")
    assert first.info.description == "Layer 1"
    assert first.info.pool == {"exchange": "raydium", "pool_address": "pool-1"}
    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert requests[0].content == b""
    assert len(requests) == 1


def test_gmgn_openapi_client_reads_nested_price_object_market_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/token/info"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "address": "0x0fb006edd8d6c128b83d2461dbfe74b318952886",
                    "symbol": "PENIS",
                    "decimals": 9,
                    "price": {
                        "price": "0.000028486255",
                        "volume_24h": "26133.3652616",
                    },
                    "liquidity": "18230.629102955",
                    "holder_count": "551",
                    "circulating_supply": "999999999",
                },
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        info = client.lookup_token_info(
            chain="eip155:1",
            address="0x0fb006edd8d6c128b83d2461dbfe74b318952886",
        ).info
    finally:
        client.close()

    assert info is not None
    assert info.price == 0.000028486255
    assert info.market_cap == pytest.approx(28_486.254971513744)
    assert info.liquidity == pytest.approx(18_230.629102955)
    assert info.holder_count == 551


def test_gmgn_openapi_client_force_ipv4_sets_curl_ipresolve(monkeypatch):
    sessions = []

    class FakeCurlSession:
        def __init__(self, **kwargs):
            sessions.append(kwargs)

        def close(self):
            pass

    monkeypatch.setattr(
        "gmgn_twitter_intel.integrations.gmgn.openapi_client.curl_requests.Session",
        FakeCurlSession,
    )

    client = GmgnOpenApiClient(api_key="gmgn-test")
    client.close()

    assert sessions == [
        {
            "impersonate": "chrome",
            "curl_options": {CurlOpt.IPRESOLVE: CURL_IPRESOLVE_V4},
        }
    ]


def test_gmgn_openapi_client_throttles_openapi_requests(monkeypatch):
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url.params["address"]))
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "address": str(request.url.params["address"]),
                    "symbol": "TEST",
                    "price": "1",
                },
            },
        )

    clock = {"value": 100.0}
    sleeps: list[float] = []

    def monotonic() -> float:
        return clock["value"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["value"] += seconds

    monkeypatch.setattr(gmgn_openapi_client_module.time, "monotonic", monotonic)
    monkeypatch.setattr(gmgn_openapi_client_module.time, "sleep", sleep)

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
        min_request_interval_seconds=0.5,
    )
    try:
        client.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
        clock["value"] += 0.1
        client.lookup_token_info(chain="sol", address="DezXAZ8z7PnrnRJjz3FjN9xQ9uK5a5n5xbHGbQHpump")
    finally:
        client.close()

    assert requests == [
        "So11111111111111111111111111111111111111112",
        "DezXAZ8z7PnrnRJjz3FjN9xQ9uK5a5n5xbHGbQHpump",
    ]
    assert sleeps == [pytest.approx(0.4)]


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
        info = client.lookup_token_info(chain="solana", address="So11111111111111111111111111111111111111112").info
    finally:
        client.close()

    assert info is not None
    assert info.chain == "solana"


def test_gmgn_openapi_client_lowercases_evm_addresses_for_lookup():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["chain"] == "bsc"
        assert request.url.params["address"] == "0x5f03ddcb6c7d9ed83f21346bb9c97d9e51a84444"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "address": "0x5f03ddcb6c7d9ed83f21346bb9c97d9e51a84444",
                    "symbol": "蛋猫",
                    "price": "0.000015282855",
                    "circulating_supply": "1000000000",
                },
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        info = client.lookup_token_info(chain="bsc", address="0x5f03DDCB6C7d9ed83f21346Bb9c97d9E51a84444").info
    finally:
        client.close()

    assert info is not None
    assert info.chain == "bsc"
    assert info.address == "0x5f03ddcb6c7d9ed83f21346bb9c97d9e51a84444"
    assert info.symbol == "蛋猫"
    assert info.market_cap == 15282.855


def test_gmgn_openapi_client_maps_eip155_chain_ids_to_gmgn_chains():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["chain"] == "eth"
        assert request.url.params["address"] == "0xf280b16ef293d8e534e370794ef26bf312694126"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "address": "0xf280b16ef293d8e534e370794ef26bf312694126",
                    "symbol": "ASTEROID",
                    "price": "0.0003",
                },
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        info = client.lookup_token_info(
            chain="eip155:1",
            address="0xF280B16ef293D8e534e370794Ef26bf312694126",
        ).info
    finally:
        client.close()

    assert info is not None
    assert info.chain == "eip155:1"
    assert info.address == "0xf280b16ef293d8e534e370794ef26bf312694126"


def test_gmgn_openapi_client_fetches_token_kline():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/market/token_kline"
        assert request.url.params["chain"] == "eth"
        assert request.url.params["address"] == "0xf280b16ef293d8e534e370794ef26bf312694126"
        assert request.url.params["resolution"] == "1h"
        assert request.url.params["from"]
        assert request.url.params["to"]
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "list": [
                        {
                            "time": 1_778_584_740_000,
                            "open": "0.00028864074",
                            "high": "0.00028970968",
                            "low": "0.00028864074",
                            "close": "0.00028970968",
                            "volume": "877.2247609",
                            "amount": "3028776.073141976",
                        }
                    ]
                },
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        candles = client.token_kline(
            chain="eip155:1",
            address="0xF280B16ef293D8e534e370794Ef26bf312694126",
            resolution="1H",
            limit=24,
            now_ms=1_778_588_400_000,
        )
    finally:
        client.close()

    assert len(candles) == 1
    assert candles[0].time_ms == 1_778_584_740_000
    assert candles[0].open == 0.00028864074
    assert candles[0].close == 0.00028970968
    assert candles[0].volume_usd == 877.2247609
    assert candles[0].volume == 3028776.073141976
