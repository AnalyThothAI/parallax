from __future__ import annotations

import httpx
import pytest
from curl_cffi import CurlOpt

from gmgn_twitter_intel.integrations.gmgn.openapi_client import (
    CURL_IPRESOLVE_V4,
    GmgnOpenApiClient,
    GmgnOpenApiProviderUnavailableError,
    GmgnOpenApiTransientError,
)


def test_gmgn_openapi_client_fetches_token_info_with_normal_auth():
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
        lookup = client.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
    finally:
        client.close()

    assert lookup.info is not None
    assert lookup.info.symbol == "SOL"
    assert lookup.info.decimals == 9
    assert lookup.info.price == 150.5
    assert lookup.info.market_cap == 150500.0
    assert lookup.info.liquidity == 2500000.25
    assert lookup.info.holder_count == 12345
    assert lookup.info.circulating_supply == 1000.0
    assert lookup.info.website == "https://solana.com"
    assert lookup.info.twitter_username == "solana"
    assert lookup.info.telegram == "https://t.me/solana"
    assert lookup.info.gmgn_url == "https://gmgn.ai/sol/token/So11111111111111111111111111111111111111112"
    assert lookup.info.geckoterminal_url.startswith("https://www.geckoterminal.com/")
    assert lookup.info.description == "Layer 1"
    assert lookup.info.pool == {"exchange": "raydium", "pool_address": "pool-1"}
    assert lookup.cache_status == "miss"
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
            "impersonate": "chrome142",
            "curl_options": {CurlOpt.IPRESOLVE: CURL_IPRESOLVE_V4},
        }
    ]


def test_gmgn_openapi_client_identifies_cloudflare_challenge_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text='<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>cf-chl</body></html>',
            headers={"content-type": "text/html; charset=UTF-8", "server": "cloudflare"},
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GmgnOpenApiProviderUnavailableError, match="Cloudflare challenge"):
            client.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
    finally:
        client.close()


def test_gmgn_openapi_client_classifies_rate_limit_as_provider_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "code": 429,
                "error": "RATE_LIMIT_BANNED",
                "message": "retry later",
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GmgnOpenApiProviderUnavailableError, match="provider unavailable"):
            client.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
    finally:
        client.close()


def test_gmgn_openapi_client_uses_rate_limit_reset_as_provider_cooldown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "code": 429,
                "error": "RATE_LIMIT_BANNED",
                "message": "retry later",
                "reset_at": 4_102_444_800,
            },
            headers={"x-ratelimit-reset": "1000"},
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GmgnOpenApiProviderUnavailableError) as exc_info:
            client.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
    finally:
        client.close()

    assert exc_info.value.cooldown_seconds is not None
    assert exc_info.value.cooldown_seconds > 0


def test_gmgn_openapi_client_classifies_non_json_5xx_as_transient():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable", headers={"content-type": "text/html"})

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(GmgnOpenApiTransientError, match="HTTP 503"):
            client.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")
    finally:
        client.close()


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
