from __future__ import annotations

from parallax.app.runtime import providers_wiring
from parallax.app.runtime.provider_wiring import asset_market as asset_market_wiring
from parallax.app.runtime.provider_wiring import binance as binance_wiring
from parallax.app.runtime.provider_wiring import gmgn as gmgn_wiring
from parallax.app.runtime.provider_wiring import okx as okx_wiring
from parallax.domains.asset_market.providers import MarketCapability, ProviderHealth
from parallax.platform.config.settings import Settings


def test_provider_health_describes_configured_capabilities(monkeypatch) -> None:
    cex = object()
    discovery = FakeDiscoveryProvider()
    quote = FakeQuoteProvider()
    stream = FakeStreamProvider()
    gmgn = FakeGmgnProvider()
    binance = FakeBinanceProvider()

    monkeypatch.setattr(binance_wiring, "binance_usdm_futures_market", lambda settings: cex)
    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: discovery)
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: quote)
    monkeypatch.setattr(okx_wiring, "okx_dex_ws_market", lambda settings: stream)
    monkeypatch.setattr(gmgn_wiring, "gmgn_dex_market", lambda settings: gmgn)
    monkeypatch.setattr(binance_wiring, "binance_web3_profile_market", lambda settings: binance)

    providers = providers_wiring.wire_providers(
        Settings(
            ws_token="secret",
            gmgn={"api_key": "gmgn-key"},
            providers={
                "okx": {
                    "dex_api_key": "okx-key",
                    "dex_secret_key": "okx-secret",
                    "dex_passphrase": "okx-pass",
                }
            },
        ),
        start_collector=True,
    ).asset_market

    assert providers.cex_market is cex
    assert not hasattr(providers, "sync_cex_market")
    assert not hasattr(providers, "message_cex_market")
    assert providers.dex_discovery_market is not None
    assert isinstance(providers.dex_quote_market, asset_market_wiring.FallbackDexQuoteProvider)
    assert providers.stream_dex_market is stream
    health = {entry.provider: entry for entry in providers.provider_health}
    assert health["okx"] == ProviderHealth(
        provider="okx",
        capabilities=frozenset(
            {
                MarketCapability.QUOTE_DEX_EXACT,
                MarketCapability.SEARCH_DEX,
                MarketCapability.STREAM_DEX,
            }
        ),
        configured=True,
    )
    assert health["gmgn"] == ProviderHealth(
        provider="gmgn",
        capabilities=frozenset(
            {
                MarketCapability.QUOTE_DEX_EXACT,
                MarketCapability.PROFILE_DEX_EXACT,
                MarketCapability.CANDLES_DEX_EXACT,
            }
        ),
        configured=True,
    )
    assert health["binance"] == ProviderHealth(
        provider="binance",
        capabilities=frozenset(
            {
                MarketCapability.PROFILE_CEX,
                MarketCapability.PROFILE_DEX_EXACT,
                MarketCapability.QUOTE_CEX,
            }
        ),
        configured=True,
    )


def test_okx_stream_capability_comes_from_credentials_not_enabled_flag(monkeypatch) -> None:
    monkeypatch.setattr(okx_wiring, "okx_dex_discovery_market", lambda settings: FakeDiscoveryProvider())
    monkeypatch.setattr(okx_wiring, "okx_dex_quote_market", lambda settings: FakeQuoteProvider())
    monkeypatch.setattr(okx_wiring, "okx_dex_ws_market", lambda settings: FakeStreamProvider())

    providers = providers_wiring.wire_providers(
        Settings(ws_token="secret"),
        start_collector=True,
    ).asset_market

    okx_health = next(entry for entry in providers.provider_health if entry.provider == "okx")
    assert providers.stream_dex_market is None
    assert MarketCapability.STREAM_DEX not in okx_health.capabilities


class FakeDiscoveryProvider:
    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]):
        return []


class FakeQuoteProvider:
    def token_quotes(self, tokens):
        return []


class FakeStreamProvider:
    async def replace_subscriptions(self, targets) -> None:
        return None

    async def iter_price_info(self):
        if False:
            yield None

    async def aclose(self) -> None:
        return None


class FakeGmgnProvider:
    def token_quotes(self, tokens):
        return []

    def token_candles(self, *, chain_id: str, address: str, bar: str, limit: int):
        return []

    def token_profile(self, *, chain_id: str, address: str):
        return None


class FakeBinanceProvider:
    def token_profile(self, *, chain_id: str, address: str):
        return None
