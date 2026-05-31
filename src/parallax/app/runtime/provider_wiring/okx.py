from __future__ import annotations

from threading import Lock
from typing import Any

from parallax.app.runtime.provider_wiring.types import OkxProviderBundle
from parallax.domains.asset_market.providers import (
    DexMarketFactUpdate,
    DexMarketStreamProvider,
    DexTokenCandidate,
    DexTokenDiscoveryProvider,
    DexTokenQuote,
    DexTokenQuoteProvider,
    DexTokenQuoteRequest,
    MarketCapability,
    ProviderHealth,
)
from parallax.integrations.okx.chains import OKX_CHAIN_INDEX_TO_CHAIN, OKX_CHAIN_TO_CHAIN_INDEX
from parallax.integrations.okx.dex_client import EVM_ADDRESS_RE, OkxDexClient
from parallax.integrations.okx.dex_ws_client import OkxDexWebSocketMarketProvider
from parallax.platform.config.settings import Settings


class OkxDexDiscoveryProvider:
    def __init__(self, client: OkxDexClient) -> None:
        self._client = client

    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]) -> list[DexTokenCandidate]:
        chain_indexes = tuple(index for chain_id in chain_ids if (index := okx_chain_index(chain_id)))
        if not chain_indexes:
            return []
        return [
            _dex_token_candidate(candidate)
            for candidate in self._client.search_tokens(query=query, chain_indexes=chain_indexes)
        ]

    def close(self) -> None:
        self._client.close()


class OkxDexQuoteProvider:
    def __init__(self, client: OkxDexClient) -> None:
        self._client = client

    def token_quotes(self, tokens: list[DexTokenQuoteRequest]) -> list[DexTokenQuote]:
        request_items: list[dict[str, str]] = []
        for token in tokens:
            chain_index = okx_chain_index(token.chain_id)
            if not chain_index:
                continue
            request_items.append(
                {
                    "chainIndex": chain_index,
                    "tokenContractAddress": _normalize_address(token.address),
                }
            )
        if not request_items:
            return []
        return [
            DexTokenQuote(
                chain_id=okx_index_to_chain_id(price.chain_index) or str(price.chain_index),
                address=_normalize_address(price.address),
                observed_at_ms=price.observed_at_ms,
                price_usd=price.price_usd,
                raw=price.raw,
                market_cap_usd=None,
                liquidity_usd=None,
                volume_24h_usd=None,
                holders=None,
            )
            for price in self._client.token_prices(request_items)
        ]

    def close(self) -> None:
        self._client.close()


class SerializedDiscoveryProvider:
    def __init__(self, provider: DexTokenDiscoveryProvider) -> None:
        self._provider = provider
        self._lock = Lock()
        self._closed = False

    def search_tokens(self, *, query: str, chain_ids: tuple[str, ...]) -> list[DexTokenCandidate]:
        with self._lock:
            return self._provider.search_tokens(query=query, chain_ids=chain_ids)

    def close(self) -> None:
        close = getattr(self._provider, "close", None)
        if not close:
            return
        with self._lock:
            if self._closed:
                return
            close()
            self._closed = True


class OkxDexWebSocketMarketProviderAdapter:
    def __init__(self, provider: OkxDexWebSocketMarketProvider) -> None:
        self._provider = provider

    async def replace_subscriptions(self, targets: list[Any]) -> None:
        mapped_targets: list[dict[str, str]] = []
        for target in targets:
            chain_index = okx_chain_index(target.chain_id)
            if not chain_index:
                continue
            mapped_targets.append(
                {
                    "chainIndex": chain_index,
                    "tokenContractAddress": _normalize_address(target.address),
                }
            )
        await self._provider.replace_subscriptions(mapped_targets)

    async def iter_price_info(self):
        async for update in self._provider.iter_price_info():
            yield _domain_dex_market_fact_update(update)

    async def aclose(self) -> None:
        await self._provider.aclose()

    def close(self) -> None:
        # Synchronous close is only safe before the WS session connects.
        if getattr(self._provider, "_websocket", None) is not None:
            raise RuntimeError("use aclose() for connected OKX DEX WS provider cleanup")

    def connection_state_payload(self) -> dict[str, Any]:
        payload = getattr(self._provider, "connection_state_payload", None)
        if payload:
            return payload()
        return {"provider": "okx_dex_ws", "state": "disconnected", "last_state_change_at_ms": None}


def wire_okx_provider_bundle(settings: Settings) -> OkxProviderBundle:
    capabilities: set[MarketCapability] = set()
    dex_discovery_market: DexTokenDiscoveryProvider | None = None
    dex_quote_market: DexTokenQuoteProvider | None = None
    stream_dex_market: DexMarketStreamProvider | None = None
    try:
        if settings.okx_dex_configured:
            dex_discovery_market = SerializedDiscoveryProvider(okx_dex_discovery_market(settings))
            dex_quote_market = okx_dex_quote_market(settings)
            capabilities.add(MarketCapability.SEARCH_DEX)
            capabilities.add(MarketCapability.QUOTE_DEX_EXACT)
        if settings.okx_dex_ws_configured:
            stream_dex_market = okx_dex_ws_market(settings)
            capabilities.add(MarketCapability.STREAM_DEX)
        return OkxProviderBundle(
            dex_discovery_market=dex_discovery_market,
            dex_quote_market=dex_quote_market,
            stream_dex_market=stream_dex_market,
            health=ProviderHealth(
                provider="okx",
                capabilities=frozenset(capabilities),
                configured=bool(capabilities),
            ),
        )
    except Exception as exc:
        _close_partial_providers(exc, dex_discovery_market, dex_quote_market, stream_dex_market)
        raise


def okx_dex_discovery_market(settings: Settings) -> OkxDexDiscoveryProvider:
    return OkxDexDiscoveryProvider(
        OkxDexClient(
            base_url=settings.okx_dex_base_url,
            api_key=settings.okx_dex_api_key,
            secret_key=settings.okx_dex_secret_key,
            passphrase=settings.okx_dex_passphrase,
            timeout_seconds=settings.okx_timeout_seconds,
        )
    )


def okx_dex_quote_market(settings: Settings) -> OkxDexQuoteProvider:
    return OkxDexQuoteProvider(
        OkxDexClient(
            base_url=settings.okx_dex_base_url,
            api_key=settings.okx_dex_api_key,
            secret_key=settings.okx_dex_secret_key,
            passphrase=settings.okx_dex_passphrase,
            timeout_seconds=settings.okx_timeout_seconds,
        )
    )


def okx_dex_ws_market(settings: Settings) -> OkxDexWebSocketMarketProviderAdapter:
    return OkxDexWebSocketMarketProviderAdapter(
        OkxDexWebSocketMarketProvider(
            url=settings.okx_dex_ws_url,
            api_key=settings.okx_dex_api_key or "",
            secret_key=settings.okx_dex_secret_key or "",
            passphrase=settings.okx_dex_passphrase or "",
            subscription_limit=settings.workers.market_tick_stream.subscription_limit,
        )
    )


def okx_chain_indexes_to_chain_ids(chain_indexes: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    chain_ids = []
    for value in chain_indexes:
        chain_id = okx_index_to_chain_id(str(value))
        if chain_id:
            chain_ids.append(chain_id)
    return tuple(dict.fromkeys(chain_ids))


def okx_index_to_chain_id(value: str) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if normalized.startswith("eip155:"):
        return normalized
    chain = OKX_CHAIN_INDEX_TO_CHAIN.get(normalized, normalized)
    return _domain_chain_id(chain)


def okx_chain_index(chain_id: Any) -> str | None:
    normalized = str(chain_id or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("eip155:"):
        return normalized.split(":", 1)[1]
    if normalized.isdecimal():
        return normalized
    return OKX_CHAIN_TO_CHAIN_INDEX.get(normalized)


def _dex_token_candidate(candidate: Any) -> DexTokenCandidate:
    return DexTokenCandidate(
        chain_id=okx_index_to_chain_id(candidate.chain_index) or str(candidate.chain_index),
        address=_normalize_address(candidate.address),
        symbol=candidate.symbol,
        name=candidate.name,
        price_usd=candidate.price_usd,
        market_cap_usd=candidate.market_cap_usd,
        liquidity_usd=candidate.liquidity_usd,
        holders=candidate.holders,
        community_recognized=candidate.community_recognized,
        raw=candidate.raw,
    )


def _domain_dex_market_fact_update(update: Any) -> DexMarketFactUpdate:
    return DexMarketFactUpdate(
        chain_id=okx_index_to_chain_id(update.chain_id) or update.chain_id,
        address=_normalize_address(update.address),
        observed_at_ms=update.observed_at_ms,
        price_usd=update.price_usd,
        market_cap_usd=update.market_cap_usd,
        liquidity_usd=update.liquidity_usd,
        volume_24h_usd=update.volume_24h_usd,
        open_interest_usd=update.open_interest_usd,
        holders=update.holders,
        raw=update.raw,
    )


def _domain_chain_id(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("eip155:"):
        return normalized
    if normalized in {"eth", "ethereum"}:
        return "eip155:1"
    if normalized in {"bsc", "bnb", "bnb_chain"}:
        return "eip155:56"
    if normalized == "base":
        return "eip155:8453"
    if normalized in {"sol", "solana"}:
        return "solana"
    if normalized in {"ton", "toncoin"}:
        return "ton"
    return normalized


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
    "OkxDexDiscoveryProvider",
    "OkxDexQuoteProvider",
    "OkxDexWebSocketMarketProvider",
    "OkxDexWebSocketMarketProviderAdapter",
    "SerializedDiscoveryProvider",
    "okx_chain_index",
    "okx_chain_indexes_to_chain_ids",
    "okx_dex_discovery_market",
    "okx_dex_quote_market",
    "okx_dex_ws_market",
    "okx_index_to_chain_id",
    "wire_okx_provider_bundle",
]
