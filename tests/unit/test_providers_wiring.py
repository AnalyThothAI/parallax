from __future__ import annotations

import httpx
import pytest

from gmgn_twitter_intel.app.runtime import providers_wiring
from gmgn_twitter_intel.app.runtime.providers_wiring import (
    GmgnDexMarketProvider,
    OkxDexDiscoveryProvider,
    OkxDexQuoteProvider,
    okx_chain_indexes_to_chain_ids,
)
from gmgn_twitter_intel.domains.asset_market.providers import DexTokenQuoteRequest
from gmgn_twitter_intel.integrations.gmgn.openapi_client import GmgnOpenApiClient
from gmgn_twitter_intel.integrations.okx.models import OkxDexTokenCandidate, OkxDexTokenPrice
from gmgn_twitter_intel.platform.config.settings import Settings


def test_asset_market_wires_okx_quote_separately_from_discovery_and_gmgn_exact_roles(monkeypatch) -> None:
    okx_created: list[FakeDexDiscoveryProvider] = []
    okx_quote_created: list[FakeDexQuoteProvider] = []
    gmgn_created: list[FakeGmgnDexMarketProvider] = []

    def fake_okx(settings: Settings) -> FakeDexDiscoveryProvider:
        provider = FakeDexDiscoveryProvider()
        okx_created.append(provider)
        return provider

    def fake_okx_quote(settings: Settings) -> FakeDexQuoteProvider:
        provider = FakeDexQuoteProvider()
        okx_quote_created.append(provider)
        return provider

    def fake_gmgn(settings: Settings) -> FakeGmgnDexMarketProvider:
        provider = FakeGmgnDexMarketProvider()
        gmgn_created.append(provider)
        return provider

    monkeypatch.setattr(providers_wiring, "_okx_dex_discovery_market", fake_okx)
    monkeypatch.setattr(providers_wiring, "_okx_dex_quote_market", fake_okx_quote)
    monkeypatch.setattr(providers_wiring, "_gmgn_dex_market", fake_gmgn)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_and_gmgn(),
        start_collector=True,
    ).asset_market

    assert providers.dex_discovery_market is not None
    assert providers.dex_quote_market is not None
    assert providers.dex_quote_market is okx_quote_created[0]
    assert providers.dex_candle_market is gmgn_created[0]
    assert providers.dex_profile_market is gmgn_created[0]
    assert providers.dex_discovery_market is not providers.dex_quote_market
    assert not hasattr(providers.dex_discovery_market, "token_quotes")
    assert len(okx_created) == 1
    assert len(okx_quote_created) == 1
    assert len(gmgn_created) == 1


def test_okx_dex_ws_market_provider_is_wired_separately_from_discovery_and_gmgn(monkeypatch) -> None:
    monkeypatch.setattr(providers_wiring, "_okx_dex_discovery_market", lambda settings: FakeDexDiscoveryProvider())
    monkeypatch.setattr(providers_wiring, "_okx_dex_quote_market", lambda settings: FakeDexQuoteProvider())
    monkeypatch.setattr(providers_wiring, "_gmgn_dex_market", lambda settings: FakeGmgnDexMarketProvider())
    monkeypatch.setattr(providers_wiring, "_okx_dex_ws_market", lambda settings: FakeDexStreamProvider())

    providers = providers_wiring.wire_providers(
        _settings_with_okx_dex_ws_and_gmgn_enabled(),
        start_collector=True,
    ).asset_market

    assert providers.dex_discovery_market is not None
    assert providers.dex_quote_market is not None
    assert providers.stream_dex_market is not None
    assert providers.stream_dex_market is not providers.dex_discovery_market
    assert providers.stream_dex_market is not providers.dex_quote_market


def test_okx_dex_ws_market_uses_worker_subscription_limit(monkeypatch) -> None:
    created: list[FakeOkxDexWebSocketMarketProvider] = []

    def fake_provider(**kwargs):
        provider = FakeOkxDexWebSocketMarketProvider(**kwargs)
        created.append(provider)
        return provider

    monkeypatch.setattr(providers_wiring, "OkxDexWebSocketMarketProvider", fake_provider)

    provider = providers_wiring._okx_dex_ws_market(
        Settings(
            ws_token="secret",
            providers={
                "okx": {
                    "cex_sync_enabled": False,
                    "dex_api_key": "okx-key",
                    "dex_secret_key": "okx-secret",
                    "dex_passphrase": "okx-passphrase",
                }
            },
            workers={"live_price_gateway": {"subscription_limit": 37}},
        )
    )

    assert provider._provider is created[0]
    assert created[0].subscription_limit == 37


def test_discovery_provider_close_is_idempotent(monkeypatch) -> None:
    created: list[CloseCountingDexDiscoveryProvider] = []

    def fake_okx(settings: Settings) -> CloseCountingDexDiscoveryProvider:
        provider = CloseCountingDexDiscoveryProvider()
        created.append(provider)
        return provider

    monkeypatch.setattr(providers_wiring, "_okx_dex_discovery_market", fake_okx)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_dex_credentials(),
        start_collector=True,
    ).asset_market
    assert providers.dex_discovery_market is not None

    providers.dex_discovery_market.close()
    providers.dex_discovery_market.close()

    assert len(created) == 1
    assert created[0].close_count == 1


def test_asset_market_wiring_closes_okx_partial_provider_when_gmgn_wiring_fails(monkeypatch) -> None:
    okx_provider = CloseCountingDexDiscoveryProvider()
    okx_quote_provider = CloseCountingDexQuoteProvider()

    monkeypatch.setattr(providers_wiring, "_okx_dex_discovery_market", lambda settings: okx_provider)
    monkeypatch.setattr(providers_wiring, "_okx_dex_quote_market", lambda settings: okx_quote_provider)

    def fail_gmgn(settings: Settings):
        raise RuntimeError("gmgn failed")

    monkeypatch.setattr(providers_wiring, "_gmgn_dex_market", fail_gmgn)

    with pytest.raises(RuntimeError, match="gmgn failed"):
        providers_wiring.wire_asset_market_providers(_settings_with_okx_and_gmgn(), start_collector=True)

    assert okx_provider.close_count == 1
    assert okx_quote_provider.close_count == 1


def test_asset_market_wiring_preserves_gmgn_error_when_partial_cleanup_fails(monkeypatch) -> None:
    okx_provider = CloseFailingDexDiscoveryProvider()
    okx_quote_provider = CloseFailingDexQuoteProvider()

    monkeypatch.setattr(providers_wiring, "_okx_dex_discovery_market", lambda settings: okx_provider)
    monkeypatch.setattr(providers_wiring, "_okx_dex_quote_market", lambda settings: okx_quote_provider)

    def fail_gmgn(settings: Settings):
        raise RuntimeError("gmgn failed")

    monkeypatch.setattr(providers_wiring, "_gmgn_dex_market", fail_gmgn)

    with pytest.raises(RuntimeError, match="gmgn failed") as exc_info:
        providers_wiring.wire_asset_market_providers(_settings_with_okx_and_gmgn(), start_collector=True)

    assert "cleanup failed" in "\n".join(getattr(exc_info.value, "__notes__", []))
    assert "close failed" in "\n".join(getattr(exc_info.value, "__notes__", []))
    assert "quote close failed" in "\n".join(getattr(exc_info.value, "__notes__", []))


def test_okx_bundle_wiring_closes_cex_partial_provider_when_discovery_wiring_fails(monkeypatch) -> None:
    cex_provider = CloseCountingCexProvider()

    monkeypatch.setattr(providers_wiring, "_okx_cex_market", lambda settings: cex_provider)

    def fail_discovery(settings: Settings):
        raise RuntimeError("discovery failed")

    monkeypatch.setattr(providers_wiring, "_okx_dex_discovery_market", fail_discovery)

    with pytest.raises(RuntimeError, match="discovery failed"):
        providers_wiring._wire_okx_provider_bundle(_settings_with_okx_cex_and_dex_credentials())

    assert cex_provider.close_count == 1


def test_okx_bundle_wiring_closes_cex_and_discovery_when_stream_wiring_fails(monkeypatch) -> None:
    cex_provider = CloseCountingCexProvider()
    discovery_provider = CloseCountingDexDiscoveryProvider()
    quote_provider = CloseCountingDexQuoteProvider()

    monkeypatch.setattr(providers_wiring, "_okx_cex_market", lambda settings: cex_provider)
    monkeypatch.setattr(providers_wiring, "_okx_dex_discovery_market", lambda settings: discovery_provider)
    monkeypatch.setattr(providers_wiring, "_okx_dex_quote_market", lambda settings: quote_provider)

    def fail_stream(settings: Settings):
        raise RuntimeError("stream failed")

    monkeypatch.setattr(providers_wiring, "_okx_dex_ws_market", fail_stream)

    with pytest.raises(RuntimeError, match="stream failed"):
        providers_wiring._wire_okx_provider_bundle(_settings_with_okx_cex_and_dex_credentials())

    assert cex_provider.close_count == 1
    assert discovery_provider.close_count == 1
    assert quote_provider.close_count == 1


def test_okx_bundle_wiring_preserves_original_error_when_partial_cleanup_fails(monkeypatch) -> None:
    cex_provider = CloseFailingCexProvider()

    monkeypatch.setattr(providers_wiring, "_okx_cex_market", lambda settings: cex_provider)

    def fail_discovery(settings: Settings):
        raise RuntimeError("discovery failed")

    monkeypatch.setattr(providers_wiring, "_okx_dex_discovery_market", fail_discovery)

    with pytest.raises(RuntimeError, match="discovery failed") as exc_info:
        providers_wiring._wire_okx_provider_bundle(_settings_with_okx_cex_and_dex_credentials())

    notes = "\n".join(getattr(exc_info.value, "__notes__", []))
    assert "cleanup failed" in notes
    assert "cex close failed" in notes


def test_openai_providers_receive_llm_gateway() -> None:
    gateway = FakeGateway()

    providers = providers_wiring.wire_providers(
        _settings_with_all_llm_models(),
        start_collector=True,
        llm_gateway=gateway,
    )

    assert providers.social_enrichment.event_enrichment is not None
    assert providers.social_enrichment.event_enrichment._llm_gateway is gateway
    assert providers.pulse_lab.decision_provider is not None
    assert providers.pulse_lab.decision_provider._client._llm_gateway is gateway
    assert providers.watchlist_intel.summary_provider is not None
    assert providers.watchlist_intel.summary_provider._llm_gateway is gateway


def test_openai_provider_wiring_requires_llm_gateway() -> None:
    with pytest.raises(RuntimeError, match="LLMGateway is required"):
        providers_wiring.wire_providers(
            _settings_with_all_llm_models(),
            start_collector=True,
            llm_gateway=None,
        )


def test_unknown_numeric_okx_dex_chain_indexes_round_trip_through_discovery_provider() -> None:
    client = FakeOkxDexClient()
    provider = OkxDexDiscoveryProvider(client)

    chain_ids = okx_chain_indexes_to_chain_ids(("137",))
    provider.search_tokens(query="POL", chain_ids=chain_ids)

    assert chain_ids == ("137",)
    assert client.search_requests == [{"query": "POL", "chain_indexes": ("137",)}]


def test_okx_dex_quote_provider_maps_token_price_batch_to_quotes() -> None:
    client = FakeOkxDexClient()
    provider = OkxDexQuoteProvider(client)

    quotes = provider.token_quotes(
        [
            DexTokenQuoteRequest(
                chain_id="eip155:1",
                address="0xF280B16eF293d8E534e370794EF26Bf312694126",
            ),
            DexTokenQuoteRequest(chain_id="unknown-chain", address="0x0000000000000000000000000000000000000000"),
        ]
    )

    assert client.price_requests == [
        [
            {
                "chainIndex": "1",
                "tokenContractAddress": "0xf280b16ef293d8e534e370794ef26bf312694126",
            }
        ]
    ]
    assert quotes == [
        providers_wiring.DexTokenQuote(
            chain_id="eip155:1",
            address="0xf280b16ef293d8e534e370794ef26bf312694126",
            observed_at_ms=123456789,
            price_usd=0.42,
            raw={"chainIndex": "1", "tokenContractAddress": "0xF280B16eF293d8E534e370794EF26Bf312694126"},
            market_cap_usd=None,
            liquidity_usd=None,
            volume_24h_usd=None,
            holders=None,
        )
    ]


def test_gmgn_dex_market_provider_maps_token_info_to_quote_and_profile() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/token/info"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "address": "0xf280b16ef293d8e534e370794ef26bf312694126",
                    "symbol": "ASTEROID",
                    "name": "Asteroid Shiba",
                    "price": "0.0003",
                    "circulating_supply": "420690000000",
                    "liquidity": "3000000",
                    "holder_count": "25000",
                    "volume_24h": "100000",
                    "logo": "https://example.test/logo.png",
                    "banner": "https://example.test/banner.png",
                    "link": {
                        "website": "https://asteroideth.io/",
                        "twitter_username": "MascotAsteroid",
                        "telegram": "https://t.me/AsteroidShibaCTO",
                    },
                },
            },
        )

    client = GmgnOpenApiClient(
        api_key="gmgn-test",
        base_url="https://openapi.example.test",
        transport=httpx.MockTransport(handler),
    )
    provider = GmgnDexMarketProvider(client)
    try:
        quotes = provider.token_quotes(
            [DexTokenQuoteRequest(chain_id="eip155:1", address="0xf280b16ef293d8e534e370794ef26bf312694126")]
        )
        profile = provider.token_profile(
            chain_id="eip155:1",
            address="0xf280b16ef293d8e534e370794ef26bf312694126",
        )
    finally:
        provider.close()

    assert len(quotes) == 1
    assert quotes[0].chain_id == "eip155:1"
    assert quotes[0].price_usd == 0.0003
    assert quotes[0].market_cap_usd == pytest.approx(126207000.0)
    assert quotes[0].liquidity_usd == 3000000.0
    assert quotes[0].holders == 25000
    assert quotes[0].volume_24h_usd == 100000.0
    assert profile is not None
    assert profile.website == "https://asteroideth.io/"
    assert profile.twitter_username == "MascotAsteroid"


class FakeOkxDexClient:
    def __init__(self) -> None:
        self.search_requests: list[dict[str, object]] = []
        self.price_requests: list[list[dict[str, str]]] = []

    def search_tokens(self, *, query: str, chain_indexes: tuple[str, ...]):
        self.search_requests.append({"query": query, "chain_indexes": tuple(chain_indexes)})
        return [
            OkxDexTokenCandidate(
                chain_index="137",
                chain=None,
                address="0x0000000000000000000000000000000000000137",
                symbol="POL",
                name="Polygon Ecosystem Token",
                price_usd=1.0,
                market_cap_usd=None,
                liquidity_usd=None,
                holders=None,
                community_recognized=None,
                raw={"chainIndex": "137", "tokenSymbol": "POL"},
            )
        ]

    def token_prices(self, tokens: list[dict[str, str]]) -> list[OkxDexTokenPrice]:
        self.price_requests.append(tokens)
        return [
            OkxDexTokenPrice(
                chain_index="1",
                address="0xF280B16eF293d8E534e370794EF26Bf312694126",
                observed_at_ms=123456789,
                price_usd=0.42,
                raw={"chainIndex": "1", "tokenContractAddress": "0xF280B16eF293d8E534e370794EF26Bf312694126"},
            )
        ]


class FakeDexDiscoveryProvider:
    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]):
        return []


class FakeDexQuoteProvider:
    def token_quotes(self, tokens):
        return []


class FakeGmgnDexMarketProvider:
    def token_quotes(self, tokens):
        return []

    def token_candles(self, *, chain_id: str, address: str, bar: str, limit: int):
        return []

    def token_profile(self, *, chain_id: str, address: str):
        return None


class FakeDexStreamProvider:
    async def stream_price_info(self, targets):
        if False:
            yield None


class FakeOkxDexWebSocketMarketProvider:
    def __init__(self, **kwargs) -> None:
        self.subscription_limit = kwargs["subscription_limit"]

    async def stream_price_info(self, targets):
        if False:
            yield None


class CloseCountingDexDiscoveryProvider(FakeDexDiscoveryProvider):
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class CloseFailingDexDiscoveryProvider(FakeDexDiscoveryProvider):
    def close(self) -> None:
        raise RuntimeError("close failed")


class CloseCountingDexQuoteProvider(FakeDexQuoteProvider):
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class CloseFailingDexQuoteProvider(FakeDexQuoteProvider):
    def close(self) -> None:
        raise RuntimeError("quote close failed")


class CloseCountingCexProvider:
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class CloseFailingCexProvider:
    def close(self) -> None:
        raise RuntimeError("cex close failed")


class FakeGateway:
    trace_export_enabled = True

    async def run_with_limits(self, worker_name, stage, timeout_s, coro_factory):
        return await coro_factory()

    def openai_client(self, *, model, base_url, timeout_s):
        return object()


def _settings_with_okx_dex_credentials() -> Settings:
    return Settings(
        ws_token="secret",
        providers={
            "okx": {
                "cex_sync_enabled": False,
                "dex_api_key": "okx-key",
                "dex_secret_key": "okx-secret",
                "dex_passphrase": "okx-passphrase",
            }
        },
    )


def _settings_with_okx_cex_and_dex_credentials() -> Settings:
    return Settings(
        ws_token="secret",
        providers={
            "okx": {
                "cex_sync_enabled": True,
                "dex_api_key": "okx-key",
                "dex_secret_key": "okx-secret",
                "dex_passphrase": "okx-passphrase",
            }
        },
    )


def _settings_with_all_llm_models() -> Settings:
    return Settings(
        ws_token="secret",
        llm={
            "api_key": "sk-test",
            "model": "gpt-enrich",
            "pulse_agent_model": "gpt-pulse",
            "watchlist_handle_summary_model": "gpt-summary",
        },
    )


def _settings_with_okx_and_gmgn() -> Settings:
    return Settings(
        ws_token="secret",
        gmgn={"api_key": "gmgn-key"},
        providers={
            "okx": {
                "cex_sync_enabled": False,
                "dex_api_key": "okx-key",
                "dex_secret_key": "okx-secret",
                "dex_passphrase": "okx-passphrase",
            }
        },
    )


def _settings_with_okx_dex_ws_and_gmgn_enabled() -> Settings:
    return Settings(
        ws_token="secret",
        gmgn={"api_key": "gmgn-key"},
        providers={
            "okx": {
                "cex_sync_enabled": False,
                "dex_api_key": "okx-key",
                "dex_secret_key": "okx-secret",
                "dex_passphrase": "okx-passphrase",
            }
        },
    )
