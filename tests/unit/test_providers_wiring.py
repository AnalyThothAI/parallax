from __future__ import annotations

from threading import Event, Thread

from gmgn_twitter_intel.app.runtime import providers_wiring
from gmgn_twitter_intel.app.runtime.providers_wiring import OkxDexMarketProvider, okx_chain_indexes_to_chain_ids
from gmgn_twitter_intel.integrations.okx.models import OkxDexTokenCandidate
from gmgn_twitter_intel.platform.config.settings import Settings


def test_okx_dex_market_workers_share_one_provider_budget_when_configured(monkeypatch) -> None:
    created: list[FakeDexMarketProvider] = []

    def fake_okx_dex_market(settings: Settings) -> FakeDexMarketProvider:
        provider = FakeDexMarketProvider()
        created.append(provider)
        return provider

    monkeypatch.setattr(providers_wiring, "_okx_dex_market", fake_okx_dex_market)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_dex_credentials(),
        start_collector=True,
    ).asset_market

    assert providers.sync_dex_market is not None
    assert providers.sync_dex_market is providers.message_dex_market
    assert providers.sync_dex_market is providers.discovery_dex_market
    assert getattr(providers, "projection_dex_market", None) is None
    assert len(created) == 1


def test_okx_dex_ws_market_provider_is_wired_separately_from_rest_provider(monkeypatch) -> None:
    rest_created: list[FakeDexMarketProvider] = []
    stream_created: list[FakeDexStreamProvider] = []

    def fake_okx_dex_market(settings: Settings) -> FakeDexMarketProvider:
        provider = FakeDexMarketProvider()
        rest_created.append(provider)
        return provider

    def fake_okx_dex_ws_market(settings: Settings) -> FakeDexStreamProvider:
        provider = FakeDexStreamProvider()
        stream_created.append(provider)
        return provider

    monkeypatch.setattr(providers_wiring, "_okx_dex_market", fake_okx_dex_market)
    monkeypatch.setattr(providers_wiring, "_okx_dex_ws_market", fake_okx_dex_ws_market)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_dex_ws_enabled(),
        start_collector=True,
    ).asset_market

    assert providers.sync_dex_market is not None
    assert providers.stream_dex_market is not None
    assert providers.stream_dex_market is not providers.sync_dex_market
    assert len(rest_created) == 1
    assert len(stream_created) == 1


def test_shared_okx_dex_market_serializes_search_and_price_calls(monkeypatch) -> None:
    search_entered = Event()
    release_search = Event()
    price_call_entered = Event()
    price_call_attempted = Event()

    class BlockingDexMarketProvider:
        def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]):
            search_entered.set()
            release_search.wait(timeout=2)
            return []

        def token_prices(self, tokens):
            price_call_entered.set()
            return []

    monkeypatch.setattr(providers_wiring, "_okx_dex_market", lambda settings: BlockingDexMarketProvider())
    providers = providers_wiring.wire_providers(
        _settings_with_okx_dex_credentials(),
        start_collector=True,
    ).asset_market
    assert providers.sync_dex_market is not None
    assert providers.message_dex_market is not None

    search_thread = Thread(
        target=providers.sync_dex_market.search_tokens,
        kwargs={"query": "POL", "chain_ids": ("eip155:137",)},
    )

    def call_token_prices() -> None:
        price_call_attempted.set()
        providers.message_dex_market.token_prices([])

    price_thread = Thread(target=call_token_prices)

    search_thread.start()
    assert search_entered.wait(timeout=1)
    price_thread.start()
    assert price_call_attempted.wait(timeout=1)
    try:
        assert not price_call_entered.wait(timeout=0.05)
    finally:
        release_search.set()
        search_thread.join(timeout=1)
        price_thread.join(timeout=1)

    assert price_call_entered.wait(timeout=1)


def test_shared_okx_dex_market_closes_underlying_provider_once(monkeypatch) -> None:
    created: list[CloseCountingDexMarketProvider] = []

    def fake_okx_dex_market(settings: Settings) -> CloseCountingDexMarketProvider:
        provider = CloseCountingDexMarketProvider()
        created.append(provider)
        return provider

    monkeypatch.setattr(providers_wiring, "_okx_dex_market", fake_okx_dex_market)

    providers = providers_wiring.wire_providers(
        _settings_with_okx_dex_credentials(),
        start_collector=True,
    ).asset_market
    assert providers.sync_dex_market is not None
    assert providers.message_dex_market is not None
    assert providers.discovery_dex_market is not None

    providers.sync_dex_market.close()
    providers.message_dex_market.close()
    providers.discovery_dex_market.close()

    assert len(created) == 1
    assert created[0].close_count == 1


def test_unknown_numeric_okx_dex_chain_indexes_round_trip_through_domain_provider() -> None:
    client = FakeOkxDexClient()
    provider = OkxDexMarketProvider(client)

    chain_ids = okx_chain_indexes_to_chain_ids(("137",))
    provider.search_tokens(query="POL", chain_ids=chain_ids)

    assert chain_ids == ("137",)
    assert client.search_requests == [{"query": "POL", "chain_indexes": ("137",)}]


class FakeOkxDexClient:
    def __init__(self) -> None:
        self.search_requests: list[dict[str, object]] = []

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

    def token_prices(self, tokens):
        return []


class FakeDexMarketProvider:
    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]):
        return []

    def token_prices(self, tokens):
        return []


class FakeDexStreamProvider:
    async def stream_price_info(self, targets):
        if False:
            yield None


class CloseCountingDexMarketProvider(FakeDexMarketProvider):
    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


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


def _settings_with_okx_dex_ws_enabled() -> Settings:
    return Settings(
        ws_token="secret",
        providers={
            "okx": {
                "cex_sync_enabled": False,
                "dex_ws_enabled": True,
                "dex_api_key": "okx-key",
                "dex_secret_key": "okx-secret",
                "dex_passphrase": "okx-passphrase",
            }
        },
    )
