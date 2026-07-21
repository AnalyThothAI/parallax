from __future__ import annotations

import re
from typing import Any, Protocol, cast

from parallax.app.runtime.provider_wiring import binance, gmgn, okx
from parallax.app.runtime.provider_wiring.binance import (
    BinanceUsdmFuturesMarketProvider,
    BinanceWeb3DexProfileProvider,
)
from parallax.app.runtime.provider_wiring.types import AssetMarketProviders, OkxProviderBundle
from parallax.domains.asset_market.providers import (
    DexProfileSource,
    DexTokenProfileProvider,
    DexTokenQuote,
    DexTokenQuoteProvider,
    DexTokenQuoteRequest,
)
from parallax.platform.config.settings import Settings

EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class _SyncCloseProvider(Protocol):
    def close(self) -> None: ...


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
        if self._fallback is not None:
            self._fallback.close()


def wire_asset_market(settings: Settings) -> AssetMarketProviders:
    okx_bundle: OkxProviderBundle | None = None
    binance_cex_market: BinanceUsdmFuturesMarketProvider | None = None
    gmgn_dex_market: object | None = None
    binance_profile_market: BinanceWeb3DexProfileProvider | None = None
    try:
        okx_bundle = okx.wire_okx_provider_bundle(settings)
        binance_enabled = settings.providers.binance.enabled
        binance_cex_market = binance.binance_usdm_futures_market(settings) if binance_enabled else None
        gmgn_dex_market = gmgn.gmgn_dex_market(settings) if settings.gmgn_configured else None
        binance_profile_market = binance.binance_web3_profile_market(settings) if binance_enabled else None
        dex_profile_sources = _dex_profile_sources(
            gmgn_dex_market=gmgn_dex_market,
            binance_profile_market=binance_profile_market,
        )
        return AssetMarketProviders(
            cex_market=binance_cex_market,
            dex_discovery_market=okx_bundle.dex_discovery_market,
            dex_quote_market=_dex_quote_market(
                primary=gmgn_dex_market,
                fallback=okx_bundle.dex_quote_market,
            ),
            dex_candle_market=gmgn_dex_market,
            dex_profile_sources=dex_profile_sources,
            stream_dex_market=okx_bundle.stream_dex_market,
            discovery_chain_ids=okx.okx_chain_indexes_to_chain_ids(settings.providers.okx.dex_chain_indexes),
            provider_health=(
                okx_bundle.health,
                gmgn.gmgn_provider_health(settings),
                binance.binance_provider_health(settings),
            ),
        )
    except Exception as exc:
        okx_cleanup_providers = _okx_bundle_cleanup_providers(exc, okx_bundle)
        _close_partial_providers(
            exc,
            binance_cex_market,
            *okx_cleanup_providers,
            gmgn_dex_market,
            binance_profile_market,
        )
        raise


def _dex_quote_market(
    *,
    primary: object | None,
    fallback: DexTokenQuoteProvider | None,
) -> DexTokenQuoteProvider | None:
    if primary is None:
        return fallback
    primary_quote = _require_token_quote_provider(primary)
    if fallback is not None:
        return FallbackDexQuoteProvider(primary=primary_quote, fallback=fallback)
    return primary_quote


def _dex_profile_sources(
    *,
    gmgn_dex_market: object | None,
    binance_profile_market: BinanceWeb3DexProfileProvider | None,
) -> tuple[DexProfileSource, ...]:
    sources: list[DexProfileSource] = []
    if gmgn_dex_market is not None:
        sources.append(
            DexProfileSource(provider="gmgn_dex_profile", market=_require_token_profile_source(gmgn_dex_market))
        )
    if binance_profile_market is not None:
        sources.append(DexProfileSource(provider="binance_web3_profile", market=binance_profile_market))
    return tuple(sources)


def _require_token_quote_provider(value: object) -> DexTokenQuoteProvider:
    try:
        token_quotes = cast(Any, value).token_quotes
    except AttributeError as exc:
        raise RuntimeError("asset_market_token_quotes_required") from exc
    if not callable(token_quotes):
        raise RuntimeError("asset_market_token_quotes_required")
    return cast(DexTokenQuoteProvider, value)


def _require_token_profile_source(value: object) -> DexTokenProfileProvider:
    try:
        token_profile = cast(Any, value).token_profile
    except AttributeError as exc:
        raise RuntimeError("asset_market_token_profile_required") from exc
    if not callable(token_profile):
        raise RuntimeError("asset_market_token_profile_required")
    return cast(DexTokenProfileProvider, value)


def _okx_bundle_cleanup_providers(
    error: BaseException,
    okx_bundle: OkxProviderBundle | None,
) -> tuple[object | None, object | None, object | None]:
    if okx_bundle is None:
        return (None, None, None)
    try:
        dex_discovery_market = okx_bundle.dex_discovery_market
    except AttributeError as exc:
        _record_okx_bundle_cleanup_field_error(error, "okx_bundle.dex_discovery_market", exc)
        dex_discovery_market = None
    try:
        dex_quote_market = okx_bundle.dex_quote_market
    except AttributeError as exc:
        _record_okx_bundle_cleanup_field_error(error, "okx_bundle.dex_quote_market", exc)
        dex_quote_market = None
    try:
        stream_dex_market = okx_bundle.stream_dex_market
    except AttributeError as exc:
        _record_okx_bundle_cleanup_field_error(error, "okx_bundle.stream_dex_market", exc)
        stream_dex_market = None
    return (dex_discovery_market, dex_quote_market, stream_dex_market)


def _record_okx_bundle_cleanup_field_error(error: BaseException, field: str, exc: AttributeError) -> None:
    error.add_note(f"partial provider cleanup failed: AttributeError: {field}: {exc}")


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
        try:
            cast(_SyncCloseProvider, provider).close()
        except Exception as exc:
            error.add_note(f"partial provider cleanup failed: {type(exc).__name__}: {exc}")


__all__ = [
    "FallbackDexQuoteProvider",
    "wire_asset_market",
]
