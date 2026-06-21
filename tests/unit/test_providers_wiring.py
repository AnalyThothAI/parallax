from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from parallax.app.runtime import providers_wiring
from parallax.app.runtime.provider_wiring import asset_market as asset_market_wiring
from parallax.app.runtime.provider_wiring import binance as binance_wiring
from parallax.app.runtime.provider_wiring import gmgn as gmgn_wiring
from parallax.app.runtime.provider_wiring import model_execution as model_execution_wiring
from parallax.app.runtime.provider_wiring import news as news_wiring
from parallax.app.runtime.provider_wiring import okx as okx_wiring
from parallax.app.runtime.provider_wiring.gmgn import GmgnDexMarketProvider
from parallax.app.runtime.provider_wiring.okx import (
    OkxDexDiscoveryProvider,
    OkxDexQuoteProvider,
    okx_chain_indexes_to_chain_ids,
)
from parallax.domains.asset_market.providers import (
    DexProviderTemporarilyUnavailable,
    DexTokenQuote,
    DexTokenQuoteRequest,
)
from parallax.integrations.gmgn.openapi_client import GmgnOpenApiClient
from parallax.integrations.gmgn.openapi_gateway import GmgnOpenApiGateway
from parallax.integrations.okx.http_utils import OkxPaymentRequiredError
from parallax.integrations.okx.models import OkxDexTokenCandidate, OkxDexTokenPrice
from parallax.platform.config.settings import Settings


def test_asset_market_wires_okx_quote_separately_from_discovery_and_gmgn_exact_roles(monkeypatch) -> None:
    okx_created: list[FakeDexDiscoveryProvider] = []
    okx_quote_created: list[FakeDexQuoteProvider] = []
    gmgn_created: list[FakeGmgnDexMarketProvider] = []
    binance_created: list[FakeBinanceWeb3ProfileProvider] = []

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

    def fake_binance(settings: Settings) -> FakeBinanceWeb3ProfileProvider:
        provider = FakeBinanceWeb3ProfileProvider()
        binance_created.append(provider)
        return provider

    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", fake_okx)
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", fake_okx_quote)
    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", fake_gmgn)
    monkeypatch.setattr(binance_wiring, "binance_web3_profile_market", fake_binance)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_and_gmgn(),
        start_collector=True,
    ).asset_market

    assert providers.dex_discovery_market is not None
    assert providers.dex_quote_market is not None
    assert isinstance(providers.dex_quote_market, asset_market_wiring.FallbackDexQuoteProvider)
    assert providers.dex_candle_market is gmgn_created[0]
    assert [(source.provider, source.market) for source in providers.dex_profile_sources] == [
        ("gmgn_dex_profile", gmgn_created[0]),
        ("binance_web3_profile", binance_created[0]),
    ]
    assert providers.dex_discovery_market is not providers.dex_quote_market
    assert not hasattr(providers.dex_discovery_market, "token_quotes")
    assert len(okx_created) == 1
    assert len(okx_quote_created) == 1
    assert len(gmgn_created) == 1
    assert len(binance_created) == 1


def test_asset_market_quote_provider_prefers_gmgn_facts_and_falls_back_to_okx(monkeypatch) -> None:
    gmgn_quote = DexTokenQuote(
        chain_id="eip155:1",
        address="0xgmgn",
        observed_at_ms=1,
        price_usd=2.0,
        raw={"source_provider": "gmgn_dex_quote"},
        market_cap_usd=2000.0,
        liquidity_usd=300.0,
        volume_24h_usd=400.0,
        holders=50,
    )
    okx_quote = DexTokenQuote(
        chain_id="eip155:1",
        address="0xokx",
        observed_at_ms=2,
        price_usd=1.0,
        raw={"source_provider": "okx_dex_rest"},
        market_cap_usd=None,
        liquidity_usd=None,
        volume_24h_usd=None,
        holders=None,
    )
    okx_quote_provider = FakeDexQuoteProvider([okx_quote])
    gmgn_provider = FakeGmgnDexMarketProvider([gmgn_quote])

    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: FakeDexDiscoveryProvider())
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: okx_quote_provider)
    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", lambda settings: gmgn_provider)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_and_gmgn(),
        start_collector=True,
    ).asset_market

    quotes = providers.dex_quote_market.token_quotes(
        [
            DexTokenQuoteRequest(chain_id="eip155:1", address="0xgmgn"),
            DexTokenQuoteRequest(chain_id="eip155:1", address="0xokx"),
        ]
    )

    assert [(quote.address, quote.market_cap_usd) for quote in quotes] == [("0xgmgn", 2000.0), ("0xokx", None)]
    assert gmgn_provider.quote_requests == [[("eip155:1", "0xgmgn"), ("eip155:1", "0xokx")]]
    assert okx_quote_provider.quote_requests == [[("eip155:1", "0xokx")]]


def test_asset_market_quote_provider_uses_okx_when_gmgn_primary_raises(monkeypatch) -> None:
    okx_quote = DexTokenQuote(
        chain_id="eip155:1",
        address="0xokx",
        observed_at_ms=2,
        price_usd=1.0,
        raw={"source_provider": "okx_dex_rest"},
        market_cap_usd=None,
        liquidity_usd=None,
        volume_24h_usd=None,
        holders=None,
    )
    okx_quote_provider = FakeDexQuoteProvider([okx_quote])
    gmgn_provider = FailingGmgnDexMarketProvider()

    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: FakeDexDiscoveryProvider())
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: okx_quote_provider)
    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", lambda settings: gmgn_provider)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_and_gmgn(),
        start_collector=True,
    ).asset_market

    quotes = providers.dex_quote_market.token_quotes(
        [
            DexTokenQuoteRequest(chain_id="eip155:1", address="0xokx"),
        ]
    )

    assert [(quote.address, quote.price_usd) for quote in quotes] == [("0xokx", 1.0)]
    assert gmgn_provider.quote_requests == [[("eip155:1", "0xokx")]]
    assert okx_quote_provider.quote_requests == [[("eip155:1", "0xokx")]]


def test_asset_market_configured_gmgn_requires_token_quote_contract(monkeypatch) -> None:
    malformed_gmgn_provider = GmgnWithoutTokenQuotesProvider()

    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: FakeDexDiscoveryProvider())
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: FakeDexQuoteProvider())
    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", lambda settings: malformed_gmgn_provider)

    with pytest.raises(RuntimeError, match="asset_market_token_quotes_required"):
        providers_wiring.wire_providers(
            _settings_with_okx_and_gmgn(),
            start_collector=True,
        )

    assert malformed_gmgn_provider.close_count == 1


def test_asset_market_configured_gmgn_requires_token_profile_contract(monkeypatch) -> None:
    malformed_gmgn_provider = GmgnWithoutTokenProfileProvider()

    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: FakeDexDiscoveryProvider())
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: FakeDexQuoteProvider())
    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", lambda settings: malformed_gmgn_provider)

    with pytest.raises(RuntimeError, match="asset_market_token_profile_required"):
        providers_wiring.wire_providers(
            _settings_with_okx_and_gmgn(),
            start_collector=True,
        )

    assert malformed_gmgn_provider.close_count == 1


def test_okx_dex_ws_market_provider_is_wired_separately_from_discovery_and_gmgn(monkeypatch) -> None:
    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: FakeDexDiscoveryProvider())
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: FakeDexQuoteProvider())
    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", lambda settings: FakeGmgnDexMarketProvider())
    monkeypatch.setattr(okx_wiring, "okx_dex_ws_market", lambda settings: FakeDexStreamProvider())

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

    monkeypatch.setattr(okx_wiring, "OkxDexWebSocketMarketProvider", fake_provider)

    provider = okx_wiring.okx_dex_ws_market(
        Settings(
            ws_token="secret",
            providers={
                "okx": {
                    "dex_api_key": "okx-key",
                    "dex_secret_key": "okx-secret",
                    "dex_passphrase": "okx-passphrase",
                }
            },
            workers={"market_tick_stream": {"subscription_limit": 37}},
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

    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", fake_okx)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_dex_credentials(),
        start_collector=True,
    ).asset_market
    assert providers.dex_discovery_market is not None

    providers.dex_discovery_market.close()
    providers.dex_discovery_market.close()

    assert len(created) == 1
    assert created[0].close_count == 1


def test_fallback_quote_provider_close_requires_primary_close_contract() -> None:
    provider = asset_market_wiring.FallbackDexQuoteProvider(primary=FakeDexQuoteProvider(), fallback=None)

    with pytest.raises(AttributeError, match="close"):
        provider.close()


def test_serialized_discovery_provider_close_requires_inner_close_contract() -> None:
    provider = okx_wiring.SerializedDiscoveryProvider(FakeDexDiscoveryProvider())

    with pytest.raises(AttributeError, match="close"):
        provider.close()


def test_asset_market_partial_cleanup_records_missing_close_contract() -> None:
    error = RuntimeError("wiring failed")

    asset_market_wiring._close_partial_providers(error, FakeDexDiscoveryProvider())

    notes = "\n".join(getattr(error, "__notes__", []))
    assert "partial provider cleanup failed" in notes
    assert "AttributeError" in notes
    assert "close" in notes


def test_asset_market_wiring_closes_okx_partial_provider_when_gmgn_wiring_fails(monkeypatch) -> None:
    binance_cex_provider = CloseCountingCexProvider()
    okx_provider = CloseCountingDexDiscoveryProvider()
    okx_quote_provider = CloseCountingDexQuoteProvider()

    monkeypatch.setattr(binance_wiring, "binance_usdm_futures_market", lambda settings: binance_cex_provider)
    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: okx_provider)
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: okx_quote_provider)

    def fail_gmgn(settings: Settings):
        raise RuntimeError("gmgn failed")

    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", fail_gmgn)

    with pytest.raises(RuntimeError, match="gmgn failed"):
        providers_wiring.wire_asset_market_providers(_settings_with_okx_and_gmgn(), start_collector=True)

    assert binance_cex_provider.close_count == 1
    assert okx_provider.close_count == 1
    assert okx_quote_provider.close_count == 1


def test_asset_market_wiring_preserves_gmgn_error_when_partial_cleanup_fails(monkeypatch) -> None:
    binance_cex_provider = CloseFailingCexProvider()
    okx_provider = CloseFailingDexDiscoveryProvider()
    okx_quote_provider = CloseFailingDexQuoteProvider()

    monkeypatch.setattr(binance_wiring, "binance_usdm_futures_market", lambda settings: binance_cex_provider)
    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: okx_provider)
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: okx_quote_provider)

    def fail_gmgn(settings: Settings):
        raise RuntimeError("gmgn failed")

    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", fail_gmgn)

    with pytest.raises(RuntimeError, match="gmgn failed") as exc_info:
        providers_wiring.wire_asset_market_providers(_settings_with_okx_and_gmgn(), start_collector=True)

    assert "cleanup failed" in "\n".join(getattr(exc_info.value, "__notes__", []))
    assert "cex close failed" in "\n".join(getattr(exc_info.value, "__notes__", []))
    assert "close failed" in "\n".join(getattr(exc_info.value, "__notes__", []))
    assert "quote close failed" in "\n".join(getattr(exc_info.value, "__notes__", []))


def test_asset_market_wiring_records_malformed_okx_bundle_fields_during_partial_cleanup(monkeypatch) -> None:
    okx_provider = CloseCountingDexDiscoveryProvider()
    malformed_okx_bundle = SimpleNamespace(dex_discovery_market=okx_provider)

    monkeypatch.setattr(okx_wiring, "wire_okx_provider_bundle", lambda settings: malformed_okx_bundle)

    def fail_gmgn(settings: Settings):
        raise RuntimeError("gmgn failed")

    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", fail_gmgn)

    with pytest.raises(RuntimeError, match="gmgn failed") as exc_info:
        providers_wiring.wire_asset_market_providers(_settings_with_okx_and_gmgn(), start_collector=True)

    notes = "\n".join(getattr(exc_info.value, "__notes__", []))
    assert okx_provider.close_count == 1
    assert "okx_bundle.dex_quote_market" in notes
    assert "okx_bundle.stream_dex_market" in notes


def test_okx_bundle_wiring_closes_discovery_and_quote_when_stream_wiring_fails(monkeypatch) -> None:
    discovery_provider = CloseCountingDexDiscoveryProvider()
    quote_provider = CloseCountingDexQuoteProvider()

    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: discovery_provider)
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: quote_provider)

    def fail_stream(settings: Settings):
        raise RuntimeError("stream failed")

    monkeypatch.setattr(okx_wiring, "okx_dex_ws_market", fail_stream)

    with pytest.raises(RuntimeError, match="stream failed"):
        okx_wiring.wire_okx_provider_bundle(_settings_with_okx_dex_credentials())

    assert discovery_provider.close_count == 1
    assert quote_provider.close_count == 1


def test_okx_bundle_wiring_preserves_original_error_when_partial_cleanup_fails(monkeypatch) -> None:
    discovery_provider = CloseFailingDexDiscoveryProvider()
    quote_provider = CloseFailingDexQuoteProvider()

    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: discovery_provider)
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: quote_provider)

    def fail_stream(settings: Settings):
        raise RuntimeError("stream failed")

    monkeypatch.setattr(okx_wiring, "okx_dex_ws_market", fail_stream)

    with pytest.raises(RuntimeError, match="stream failed") as exc_info:
        okx_wiring.wire_okx_provider_bundle(_settings_with_okx_dex_credentials())

    notes = "\n".join(getattr(exc_info.value, "__notes__", []))
    assert "cleanup failed" in notes
    assert "close failed" in notes
    assert "quote close failed" in notes


def test_litellm_providers_receive_agent_execution_gateway(monkeypatch) -> None:
    gateway = object()
    db_pool = object()
    created: list[object] = []

    def fake_pulse_client(**kwargs):
        client = SimpleNamespace(
            provider="litellm",
            timeout_seconds=120.0,
            artifact_version_hash="artifact:pulse",
            runtime_contract=SimpleNamespace(
                stage_names=("pulse_decision",),
            ),
            _agent_gateway=kwargs["agent_gateway"],
        )
        created.append(client)
        return client

    def fake_news_item_brief_client(**kwargs):
        client = SimpleNamespace(provider="litellm", _agent_gateway=kwargs["agent_gateway"])
        created.append(client)
        return client

    monkeypatch.setattr(model_execution_wiring, "LiteLLMPulseDecisionClient", fake_pulse_client)
    monkeypatch.setattr(model_execution_wiring, "LiteLLMNewsItemBriefClient", fake_news_item_brief_client)

    providers = providers_wiring.wire_providers(
        _settings_with_all_llm_models(),
        start_collector=True,
        agent_execution_gateway=gateway,
        db_pool=db_pool,
    )

    assert providers.pulse_lab.decision_provider is not None
    contract = providers.pulse_lab.decision_provider.runtime_contract
    assert contract.stage_names == ("pulse_decision",)
    assert not hasattr(contract, "safety_net_enabled")
    assert providers.news_intel.brief_provider is not None
    assert providers.news_intel.brief_provider._agent_gateway is gateway
    assert all(getattr(client, "_agent_gateway", None) is gateway for client in created)


def test_litellm_pulse_provider_rejects_removed_tool_budget_config() -> None:
    settings = _settings_with_all_llm_models()
    assert not hasattr(settings.workers.pulse_candidate, "investigator_max_tool_calls")


def test_litellm_provider_wiring_requires_agent_execution_gateway() -> None:
    with pytest.raises(RuntimeError, match="AgentExecutionGateway is required"):
        providers_wiring.wire_providers(
            _settings_with_all_llm_models(),
            start_collector=True,
            agent_execution_gateway=None,
            db_pool=object(),
        )


def test_news_item_brief_provider_wiring_requires_agent_execution_gateway_for_news_only_config() -> None:
    settings = Settings(
        ws_token="secret",
        llm={
            "api_key": "sk-test",
        },
        workers={
            "agent_runtime": {"defaults": {"model": "gpt-news"}},
            "news_item_brief": {"enabled": True},
        },
    )

    with pytest.raises(RuntimeError, match="AgentExecutionGateway is required"):
        providers_wiring.wire_providers(
            settings,
            start_collector=False,
            agent_execution_gateway=None,
            db_pool=object(),
        )


def test_news_feed_client_returns_registry_backed_provider_and_closes_underlying_clients(monkeypatch) -> None:
    rss_client = CloseCountingFeedClient()
    cryptopanic_client = CloseCountingFeedClient()

    monkeypatch.setattr(news_wiring, "FeedClient", lambda: rss_client)
    monkeypatch.setattr(news_wiring, "CryptopanicFeedClient", lambda: cryptopanic_client)

    provider = news_wiring.news_feed_client(Settings(ws_token="secret"))

    assert isinstance(provider, news_wiring.RegistryBackedNewsSourceProvider)

    provider.close()
    provider.close()

    assert rss_client.close_count == 1
    assert cryptopanic_client.close_count == 1


def test_litellm_pulse_provider_wiring_does_not_require_db_pool() -> None:
    providers = providers_wiring.wire_providers(
        _settings_with_all_llm_models(),
        start_collector=True,
        agent_execution_gateway=object(),
        db_pool=None,
    )

    assert providers.pulse_lab.decision_provider is not None


def test_unknown_numeric_okx_dex_chain_indexes_round_trip_through_discovery_provider() -> None:
    client = FakeOkxDexClient()
    provider = OkxDexDiscoveryProvider(client)

    chain_ids = okx_chain_indexes_to_chain_ids(("137",))
    provider.search_tokens(query="POL", chain_ids=chain_ids)

    assert chain_ids == ("137",)
    assert client.search_requests == [{"query": "POL", "chain_indexes": ("137",)}]


def test_okx_dex_discovery_maps_x402_to_provider_unavailable() -> None:
    class PaymentRequiredOkxClient(FakeOkxDexClient):
        def search_tokens(self, *, query: str, chain_indexes: tuple[str, ...]):
            raise OkxPaymentRequiredError("OKX /api/v6/dex/market/token/search returned x402 payment required")

    provider = OkxDexDiscoveryProvider(PaymentRequiredOkxClient())

    with pytest.raises(DexProviderTemporarilyUnavailable, match="x402 payment required"):
        provider.search_tokens(query="POL", chain_ids=("eip155:137",))


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
        DexTokenQuote(
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


def test_gmgn_dex_market_wires_gateway_not_raw_openapi_client() -> None:
    provider = gmgn_wiring.gmgn_dex_market(Settings(gmgn={"api_key": "gmgn-test"}))
    try:
        assert isinstance(provider._gateway, GmgnOpenApiGateway)
        assert isinstance(provider._gateway._client, GmgnOpenApiClient)
    finally:
        provider.close()


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
    provider = GmgnDexMarketProvider(GmgnOpenApiGateway(client))
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


def test_binance_web3_dex_profile_provider_maps_metadata_to_domain_profile() -> None:
    client = FakeBinanceWeb3Client()
    provider = binance_wiring.BinanceWeb3DexProfileProvider(client)

    profile = provider.token_profile(chain_id="eip155:56", address="0xabc")

    assert profile is not None
    assert profile.chain_id == "eip155:56"
    assert profile.address == "0xabc"
    assert profile.symbol == "ABC"
    assert profile.name == "ABC Token"
    assert profile.logo_url == "https://bin.bnbstatic.com/images/abc.png"
    assert profile.website == "https://abc.example"
    assert profile.twitter_username == "abc"
    assert profile.telegram == "https://t.me/abc"
    assert profile.description == "profile"
    assert profile.raw == {"source_provider": "binance_web3_profile"}
    assert client.calls == [("eip155:56", "0xabc")]


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


class FakeBinanceWeb3Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def token_metadata(self, *, chain_id: str, address: str):
        self.calls.append((chain_id, address))
        return SimpleNamespace(
            chain_id="eip155:56",
            address="0xabc",
            symbol="ABC",
            name="ABC Token",
            logo_url="https://bin.bnbstatic.com/images/abc.png",
            website="https://abc.example",
            twitter_url="https://twitter.com/abc",
            twitter_username="abc",
            telegram="https://t.me/abc",
            description="profile",
            raw={"source_provider": "binance_web3_profile"},
        )


class FakeDexDiscoveryProvider:
    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]):
        return []


class FakeDexQuoteProvider:
    def __init__(self, quotes=None) -> None:
        self.quotes = list(quotes or [])
        self.quote_requests: list[list[tuple[str, str]]] = []

    def token_quotes(self, tokens):
        self.quote_requests.append([(token.chain_id, token.address) for token in tokens])
        requested = {(token.chain_id, token.address.lower()) for token in tokens}
        return [quote for quote in self.quotes if (quote.chain_id, quote.address.lower()) in requested]


class FakeGmgnDexMarketProvider:
    def __init__(self, quotes=None) -> None:
        self.quotes = list(quotes or [])
        self.quote_requests: list[list[tuple[str, str]]] = []

    def token_quotes(self, tokens):
        self.quote_requests.append([(token.chain_id, token.address) for token in tokens])
        requested = {(token.chain_id, token.address.lower()) for token in tokens}
        return [quote for quote in self.quotes if (quote.chain_id, quote.address.lower()) in requested]

    def token_candles(self, *, chain_id: str, address: str, bar: str, limit: int):
        return []

    def token_profile(self, *, chain_id: str, address: str):
        return None


class FakeBinanceWeb3ProfileProvider:
    def token_profile(self, *, chain_id: str, address: str):
        return None


class FailingGmgnDexMarketProvider(FakeGmgnDexMarketProvider):
    def token_quotes(self, tokens):
        self.quote_requests.append([(token.chain_id, token.address) for token in tokens])
        raise DexProviderTemporarilyUnavailable("GET /v1/token/info blocked by Cloudflare challenge HTTP 403")


class GmgnWithoutTokenQuotesProvider:
    def __init__(self) -> None:
        self.close_count = 0

    def token_candles(self, *, chain_id: str, address: str, bar: str, limit: int):
        return []

    def token_profile(self, *, chain_id: str, address: str):
        return None

    def close(self) -> None:
        self.close_count += 1


class GmgnWithoutTokenProfileProvider:
    def __init__(self) -> None:
        self.close_count = 0

    def token_quotes(self, tokens):
        return []

    def token_candles(self, *, chain_id: str, address: str, bar: str, limit: int):
        return []

    def close(self) -> None:
        self.close_count += 1


class FakeDexStreamProvider:
    async def replace_subscriptions(self, targets) -> None:
        return None

    async def iter_price_info(self):
        if False:
            yield None

    async def aclose(self) -> None:
        return None


class FakeOkxDexWebSocketMarketProvider:
    def __init__(self, **kwargs) -> None:
        self.subscription_limit = kwargs["subscription_limit"]

    async def replace_subscriptions(self, targets) -> None:
        return None

    async def iter_price_info(self):
        if False:
            yield None

    async def aclose(self) -> None:
        return None


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


class CloseCountingFeedClient:
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class CloseFailingCexProvider:
    def close(self) -> None:
        raise RuntimeError("cex close failed")


def _settings_with_okx_dex_credentials() -> Settings:
    return Settings(
        ws_token="secret",
        providers={
            "okx": {
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
        },
        workers={
            "agent_runtime": {
                "defaults": {"model": "gpt-enrich"},
                "lanes": {
                    "pulse.decision": {"model": "gpt-pulse"},
                    "news.item_brief": {"model": "gpt-news"},
                    "news.story_brief": {"model": "gpt-story"},
                },
            },
        },
    )


def _settings_with_okx_and_gmgn() -> Settings:
    return Settings(
        ws_token="secret",
        gmgn={"api_key": "gmgn-key"},
        providers={
            "okx": {
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
                "dex_api_key": "okx-key",
                "dex_secret_key": "okx-secret",
                "dex_passphrase": "okx-passphrase",
            }
        },
    )
