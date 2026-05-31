from __future__ import annotations

import pytest

from parallax.integrations.gmgn.openapi_client import (
    GmgnOpenApiProviderUnavailableError,
    GmgnOpenApiTransientError,
    GmgnTokenInfo,
    GmgnTokenInfoLookup,
)
from parallax.integrations.gmgn.openapi_gateway import GmgnOpenApiGateway


def test_gmgn_openapi_gateway_caches_token_info_before_consuming_route_weight():
    clock = FakeClock()
    raw_client = FakeRawClient(token_info_results=[_lookup("SOL")])
    gateway = GmgnOpenApiGateway(
        raw_client,
        token_info_cache_ttl_seconds=60,
        rate_capacity=1,
        rate_per_second=1,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    first = gateway.lookup_token_info(chain="solana", address="So11111111111111111111111111111111111111112")
    second = gateway.lookup_token_info(chain="solana", address="So11111111111111111111111111111111111111112")

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert first.info == second.info
    assert raw_client.info_calls == [("solana", "So11111111111111111111111111111111111111112")]
    assert clock.sleeps == []


def test_gmgn_openapi_gateway_applies_route_weight_between_openapi_calls():
    clock = FakeClock()
    raw_client = FakeRawClient(token_info_results=[_lookup("A"), _lookup("B")])
    gateway = GmgnOpenApiGateway(
        raw_client,
        token_info_cache_ttl_seconds=0,
        rate_capacity=1,
        rate_per_second=1,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    gateway.lookup_token_info(chain="sol", address="A11111111111111111111111111111111111111111")
    gateway.lookup_token_info(chain="sol", address="B11111111111111111111111111111111111111111")

    assert raw_client.info_calls == [
        ("sol", "A11111111111111111111111111111111111111111"),
        ("sol", "B11111111111111111111111111111111111111111"),
    ]
    assert clock.sleeps == [pytest.approx(1.0)]


def test_gmgn_openapi_gateway_opens_circuit_after_provider_block_and_short_circuits_next_call():
    clock = FakeClock()
    raw_client = FakeRawClient(
        token_info_results=[
            GmgnOpenApiProviderUnavailableError("GET /v1/token/info blocked by Cloudflare challenge HTTP 403"),
            _lookup("NEVER"),
        ]
    )
    gateway = GmgnOpenApiGateway(
        raw_client,
        token_info_cache_ttl_seconds=0,
        provider_cooldown_seconds=300,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    with pytest.raises(GmgnOpenApiProviderUnavailableError, match="Cloudflare challenge"):
        gateway.lookup_token_info(chain="sol", address="blocked")
    with pytest.raises(GmgnOpenApiProviderUnavailableError, match="circuit open"):
        gateway.lookup_token_info(chain="sol", address="still-blocked")

    assert raw_client.info_calls == [("sol", "blocked")]


def test_gmgn_openapi_gateway_retries_transient_error_once():
    clock = FakeClock()
    raw_client = FakeRawClient(
        token_info_results=[
            GmgnOpenApiTransientError("GET /v1/token/info transient HTTP 503"),
            _lookup("SOL"),
        ]
    )
    gateway = GmgnOpenApiGateway(
        raw_client,
        token_info_cache_ttl_seconds=0,
        retry_attempts=2,
        retry_initial_wait_seconds=0,
        retry_max_wait_seconds=0,
        retry_jitter_seconds=0,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    lookup = gateway.lookup_token_info(chain="sol", address="So11111111111111111111111111111111111111112")

    assert lookup.info is not None
    assert lookup.info.symbol == "SOL"
    assert raw_client.info_calls == [
        ("sol", "So11111111111111111111111111111111111111112"),
        ("sol", "So11111111111111111111111111111111111111112"),
    ]


def test_gmgn_openapi_gateway_does_not_retry_provider_unavailable():
    raw_client = FakeRawClient(
        token_info_results=[
            GmgnOpenApiProviderUnavailableError("GET /v1/token/info provider unavailable: retry later"),
            _lookup("NEVER"),
        ]
    )
    gateway = GmgnOpenApiGateway(raw_client, token_info_cache_ttl_seconds=0)

    with pytest.raises(GmgnOpenApiProviderUnavailableError, match="provider unavailable"):
        gateway.lookup_token_info(chain="sol", address="blocked")

    assert raw_client.info_calls == [("sol", "blocked")]


class FakeRawClient:
    def __init__(self, *, token_info_results: list[object]) -> None:
        self.token_info_results = list(token_info_results)
        self.info_calls: list[tuple[str, str]] = []

    def lookup_token_info(self, *, chain: str, address: str) -> GmgnTokenInfoLookup:
        self.info_calls.append((chain, address))
        result = self.token_info_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClock:
    def __init__(self) -> None:
        self.value = 1_000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


def _lookup(symbol: str) -> GmgnTokenInfoLookup:
    return GmgnTokenInfoLookup(
        info=GmgnTokenInfo(
            chain="solana",
            address="So11111111111111111111111111111111111111112",
            symbol=symbol,
            name=symbol,
            icon_url=None,
            banner_url=None,
            decimals=None,
            price=None,
            previous_price=None,
            market_cap=None,
            liquidity=None,
            holder_count=None,
            circulating_supply=None,
            total_supply=None,
            max_supply=None,
            website=None,
            twitter_username=None,
            telegram=None,
            gmgn_url=None,
            geckoterminal_url=None,
            description=None,
            pool=None,
            dev=None,
            stat=None,
            link=None,
            raw={"symbol": symbol},
        ),
        cache_status="miss",
    )
