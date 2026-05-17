from __future__ import annotations

import re
from typing import Any, cast

from gmgn_twitter_intel.app.runtime.provider_wiring import binance, gmgn, okx
from gmgn_twitter_intel.app.runtime.provider_wiring.binance import BinanceWeb3DexProfileProvider
from gmgn_twitter_intel.app.runtime.provider_wiring.types import AssetMarketProviders, OkxProviderBundle
from gmgn_twitter_intel.domains.asset_market.providers import (
    DexProfileSource,
    DexTokenQuote,
    DexTokenQuoteProvider,
    DexTokenQuoteRequest,
)
from gmgn_twitter_intel.platform.config.settings import Settings

EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class FallbackDexQuoteProvider:
    def __init__(self, *, primary: DexTokenQuoteProvider, fallback: DexTokenQuoteProvider | None) -> None:
        self._primary = primary
        self._fallback = fallback

    def token_quotes(self, tokens: list[DexTokenQuoteRequest]) -> list[DexTokenQuote]:
        requests = list(tokens)
        try:
            primary_quotes = self._primary.token_quotes(requests)
        except Exception:
            if self._fallback is None:
                raise
            primary_quotes = []
            missing = requests
        else:
            missing = []
        by_key = {
            _quote_key(quote.chain_id, quote.address): quote for quote in primary_quotes if _quote_has_price(quote)
        }
        if not missing:
            missing = [token for token in requests if _quote_key(token.chain_id, token.address) not in by_key]
        if missing and self._fallback is not None:
            fallback_quotes = self._fallback.token_quotes(missing)
            for fallback_quote in fallback_quotes:
                key = _quote_key(fallback_quote.chain_id, fallback_quote.address)
                if _quote_has_price(fallback_quote):
                    by_key[key] = fallback_quote
        return [
            quote for token in requests if (quote := by_key.get(_quote_key(token.chain_id, token.address))) is not None
        ]

    def close(self) -> None:
        seen: set[int] = set()
        for provider in (self._primary, self._fallback):
            if provider is None or id(provider) in seen:
                continue
            seen.add(id(provider))
            close = getattr(provider, "close", None)
            if close:
                close()


def wire_asset_market(settings: Settings) -> AssetMarketProviders:
    okx_bundle: OkxProviderBundle | None = None
    gmgn_dex_market: object | None = None
    binance_profile_market: BinanceWeb3DexProfileProvider | None = None
    try:
        okx_bundle = okx.wire_okx_provider_bundle(settings)
        gmgn_dex_market = gmgn.gmgn_dex_market(settings) if settings.gmgn_configured else None
        binance_profile_market = binance.binance_web3_profile_market(settings) if settings.binance_enabled else None
        dex_profile_sources = _dex_profile_sources(
            gmgn_dex_market=gmgn_dex_market,
            binance_profile_market=binance_profile_market,
        )
        return AssetMarketProviders(
            sync_cex_market=okx_bundle.sync_cex_market,
            message_cex_market=okx_bundle.message_cex_market,
            dex_discovery_market=okx_bundle.dex_discovery_market,
            dex_quote_market=_dex_quote_market(
                primary=gmgn_dex_market,
                fallback=okx_bundle.dex_quote_market,
            ),
            dex_candle_market=gmgn_dex_market,
            dex_profile_sources=dex_profile_sources,
            stream_dex_market=okx_bundle.stream_dex_market,
            discovery_chain_ids=okx.okx_chain_indexes_to_chain_ids(settings.okx_dex_chain_indexes),
            provider_health=(
                okx_bundle.health,
                gmgn.gmgn_provider_health(settings),
                binance.binance_provider_health(settings),
            ),
        )
    except Exception as exc:
        _close_partial_providers(
            exc,
            getattr(okx_bundle, "sync_cex_market", None),
            getattr(okx_bundle, "message_cex_market", None),
            getattr(okx_bundle, "dex_discovery_market", None),
            getattr(okx_bundle, "dex_quote_market", None),
            getattr(okx_bundle, "stream_dex_market", None),
            gmgn_dex_market,
            binance_profile_market,
        )
        raise


def wire_asset_market_providers(settings: Settings, *, start_collector: bool) -> AssetMarketProviders:
    _ = start_collector
    return wire_asset_market(settings)


def _dex_quote_market(
    *,
    primary: object | None,
    fallback: DexTokenQuoteProvider | None,
) -> DexTokenQuoteProvider | None:
    if not _has_token_quotes(primary):
        return fallback
    primary_quote = cast(DexTokenQuoteProvider, primary)
    if fallback is not None:
        return FallbackDexQuoteProvider(primary=primary_quote, fallback=fallback)
    return primary_quote


def _dex_profile_sources(
    *,
    gmgn_dex_market: object | None,
    binance_profile_market: BinanceWeb3DexProfileProvider | None,
) -> tuple[DexProfileSource, ...]:
    sources: list[DexProfileSource] = []
    if _has_token_profile(gmgn_dex_market):
        sources.append(DexProfileSource(provider="gmgn_dex_profile", market=cast(Any, gmgn_dex_market)))
    if binance_profile_market is not None:
        sources.append(DexProfileSource(provider="binance_web3_profile", market=binance_profile_market))
    return tuple(sources)


def _has_token_quotes(value: object | None) -> bool:
    return callable(getattr(value, "token_quotes", None))


def _has_token_profile(value: object | None) -> bool:
    return callable(getattr(value, "token_profile", None))


def _quote_key(chain_id: Any, address: Any) -> tuple[str, str]:
    return (str(chain_id).strip(), _normalize_address(address))


def _quote_has_price(quote: DexTokenQuote | None) -> bool:
    return quote is not None and quote.price_usd is not None


def _normalize_address(address: Any) -> str:
    text = str(address or "").strip()
    return text.lower() if EVM_ADDRESS_RE.match(text) else text


def _close_partial_providers(error: BaseException, *providers: object | None) -> None:
    seen: set[int] = set()
    for provider in providers:
        if provider is None or id(provider) in seen:
            continue
        seen.add(id(provider))
        close = getattr(provider, "close", None)
        if close is None:
            continue
        try:
            close()
        except Exception as exc:
            error.add_note(f"partial provider cleanup failed: {type(exc).__name__}: {exc}")


__all__ = [
    "FallbackDexQuoteProvider",
    "wire_asset_market",
    "wire_asset_market_providers",
]
