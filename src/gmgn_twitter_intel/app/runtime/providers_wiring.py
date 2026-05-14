from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import (
    CexMarketProvider,
    CexTicker,
    DexMarketFactUpdate,
    DexMarketStreamProvider,
    DexTokenCandidate,
    DexTokenDiscoveryProvider,
    DexTokenProfile,
    DexTokenQuote,
    DexTokenQuoteRequest,
    MarketCandle,
    MarketCapability,
    ProviderHealth,
)
from gmgn_twitter_intel.domains.ingestion.providers import UpstreamClientProtocol
from gmgn_twitter_intel.domains.pulse_lab.providers import PulseDecisionProvider, PulseDecisionResult
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import DecisionRoute
from gmgn_twitter_intel.domains.social_enrichment.providers import SocialEventEnrichmentProvider
from gmgn_twitter_intel.integrations.gmgn.direct_ws import DirectGmgnWebSocketClient
from gmgn_twitter_intel.integrations.gmgn.openapi_client import GmgnOpenApiClient
from gmgn_twitter_intel.integrations.marketlane import MarketlaneQuoteProvider
from gmgn_twitter_intel.integrations.okx.cex_client import OkxCexClient
from gmgn_twitter_intel.integrations.okx.chains import OKX_CHAIN_INDEX_TO_CHAIN, OKX_CHAIN_TO_CHAIN_INDEX
from gmgn_twitter_intel.integrations.okx.dex_client import EVM_ADDRESS_RE, OkxDexClient
from gmgn_twitter_intel.integrations.okx.dex_ws_client import OkxDexWebSocketMarketProvider
from gmgn_twitter_intel.integrations.openai_agents.pulse_decision_agent_client import OpenAIAgentsPulseDecisionClient
from gmgn_twitter_intel.integrations.openai_agents.social_event_agent_client import OpenAIAgentsSocialEventClient
from gmgn_twitter_intel.integrations.openai_agents.watchlist_summary_agent_client import (
    OpenAIAgentsWatchlistSummaryClient,
)
from gmgn_twitter_intel.platform.config.settings import Settings

UpstreamClientFactory = Callable[[Callable[..., Any]], UpstreamClientProtocol | None]


@dataclass(frozen=True, slots=True)
class IngestionProviders:
    upstream_client_factory: UpstreamClientFactory | None = None


@dataclass(frozen=True, slots=True)
class AssetMarketProviders:
    sync_cex_market: CexMarketProvider | None = None
    message_cex_market: CexMarketProvider | None = None
    dex_discovery_market: DexTokenDiscoveryProvider | None = None
    dex_quote_market: object | None = None
    dex_candle_market: object | None = None
    dex_profile_market: object | None = None
    stream_dex_market: DexMarketStreamProvider | None = None
    discovery_chain_ids: tuple[str, ...] = ()
    provider_health: tuple[ProviderHealth, ...] = ()


@dataclass(frozen=True, slots=True)
class OkxProviderBundle:
    sync_cex_market: CexMarketProvider | None
    message_cex_market: CexMarketProvider | None
    dex_discovery_market: DexTokenDiscoveryProvider | None
    stream_dex_market: DexMarketStreamProvider | None
    health: ProviderHealth


@dataclass(frozen=True, slots=True)
class SocialEnrichmentProviders:
    event_enrichment: SocialEventEnrichmentProvider | None = None


@dataclass(frozen=True, slots=True)
class PulseLabProviders:
    decision_provider: PulseDecisionProvider | None = None


@dataclass(frozen=True, slots=True)
class WatchlistIntelProviders:
    summary_provider: object | None = None


@dataclass(frozen=True, slots=True)
class MarketlaneProviders:
    stock_quote_provider: object | None = None


@dataclass(frozen=True, slots=True)
class WiredProviders:
    ingestion: IngestionProviders
    asset_market: AssetMarketProviders
    social_enrichment: SocialEnrichmentProviders
    pulse_lab: PulseLabProviders
    watchlist_intel: WatchlistIntelProviders
    marketlane: MarketlaneProviders


class OkxCexMarketProvider:
    def __init__(self, client: OkxCexClient) -> None:
        self._client = client

    def tickers(self, *, inst_type: str) -> list[CexTicker]:
        return [_cex_ticker(ticker) for ticker in self._client.tickers(inst_type=inst_type)]

    def ticker(self, *, inst_id: str) -> CexTicker | None:
        ticker = self._client.ticker(inst_id=inst_id)
        return _cex_ticker(ticker) if ticker is not None else None

    def candles(self, *, inst_id: str, bar: str, limit: int) -> list[MarketCandle]:
        return [_market_candle(candle) for candle in self._client.candles(inst_id=inst_id, bar=bar, limit=limit)]

    def close(self) -> None:
        self._client.close()


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


class GmgnDexMarketProvider:
    def __init__(self, client: GmgnOpenApiClient) -> None:
        self._client = client

    def token_quotes(self, tokens: list[DexTokenQuoteRequest]) -> list[DexTokenQuote]:
        observed_at_ms = int(time.time() * 1000)
        quotes: list[DexTokenQuote] = []
        for token in tokens:
            lookup = self._client.lookup_token_info(chain=token.chain_id, address=token.address)
            info = lookup.info
            if info is None:
                continue
            raw = {**info.raw, "cache_status": lookup.cache_status}
            quotes.append(
                DexTokenQuote(
                    chain_id=info.chain,
                    address=_normalize_address(info.address),
                    observed_at_ms=observed_at_ms,
                    price_usd=info.price,
                    raw=raw,
                    market_cap_usd=info.market_cap,
                    liquidity_usd=info.liquidity,
                    volume_24h_usd=_number_from_mapping(info.raw, "volume_24h_usd", "volume24hUsd", "volume_24h"),
                    holders=info.holder_count,
                )
            )
        return quotes

    def token_candles(self, *, chain_id: str, address: str, bar: str, limit: int) -> list[MarketCandle]:
        return [
            MarketCandle(
                time_ms=candle.time_ms,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                volume_quote=None,
                volume_usd=candle.volume_usd,
                confirmed=None,
                raw=candle.raw,
            )
            for candle in self._client.token_kline(chain=chain_id, address=address, resolution=bar, limit=limit)
        ]

    def token_profile(self, *, chain_id: str, address: str) -> DexTokenProfile | None:
        info = self._client.lookup_token_info(chain=chain_id, address=address).info
        if info is None:
            return None
        return DexTokenProfile(
            chain_id=info.chain,
            address=_normalize_address(info.address),
            symbol=info.symbol,
            name=info.name,
            logo_url=info.icon_url,
            banner_url=info.banner_url,
            website=info.website,
            twitter_username=info.twitter_username,
            telegram=info.telegram,
            gmgn_url=info.gmgn_url,
            geckoterminal_url=info.geckoterminal_url,
            description=info.description,
            raw=info.raw,
        )

    def close(self) -> None:
        self._client.close()


class _SerializedDiscoveryProvider:
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

    async def stream_price_info(self, targets):
        mapped_targets = []
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
        async for update in self._provider.stream_price_info(mapped_targets):
            yield _domain_dex_market_fact_update(update)

    def close(self) -> None:
        close = getattr(self._provider, "close", None)
        if close:
            close()

    def connection_state_payload(self) -> dict[str, Any]:
        payload = getattr(self._provider, "connection_state_payload", None)
        if payload:
            return payload()
        return {"provider": "okx_dex_ws", "state": "disconnected", "last_state_change_at_ms": None}


class OpenAIPulseDecisionProvider:
    def __init__(self, client: OpenAIAgentsPulseDecisionClient) -> None:
        self._client = client

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def model(self) -> str:
        return self._client.model

    @property
    def timeout_seconds(self) -> float:
        return self._client.timeout_seconds

    @property
    def artifact_version_hash(self) -> str:
        return self._client.artifact_version_hash

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        harness: dict[str, Any],
    ) -> dict[str, Any]:
        return self._client.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            harness=harness,
        )

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        harness: dict[str, Any],
    ) -> PulseDecisionResult:
        result = await self._client.run_decision_pipeline(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            harness=harness,
        )
        return PulseDecisionResult(
            final_decision=result.final_decision,
            agent_run_audit=result.run_audit,
            stage_audits=result.stage_audits,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def wire_providers(settings: Settings, *, start_collector: bool) -> WiredProviders:
    return WiredProviders(
        ingestion=IngestionProviders(
            upstream_client_factory=_gmgn_upstream_factory(settings) if start_collector else None,
        ),
        asset_market=_wire_asset_market(settings, start_collector=start_collector),
        social_enrichment=SocialEnrichmentProviders(
            event_enrichment=_openai_social_event_provider(settings) if settings.llm_configured else None,
        ),
        pulse_lab=PulseLabProviders(
            decision_provider=_openai_pulse_decision_provider(settings)
            if settings.pulse_agent_enabled and settings.pulse_agent_configured
            else None,
        ),
        watchlist_intel=WatchlistIntelProviders(
            summary_provider=_openai_watchlist_summary_provider(settings)
            if settings.watchlist_handle_summary_enabled and settings.watchlist_handle_summary_configured
            else None,
        ),
        marketlane=_wire_marketlane(settings),
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


def _wire_asset_market(settings: Settings, *, start_collector: bool) -> AssetMarketProviders:
    if not start_collector:
        return AssetMarketProviders()
    okx_bundle = _wire_okx_provider_bundle(settings)
    gmgn_dex_market = _gmgn_dex_market(settings) if settings.gmgn_configured else None
    return AssetMarketProviders(
        sync_cex_market=okx_bundle.sync_cex_market,
        message_cex_market=okx_bundle.message_cex_market,
        dex_discovery_market=okx_bundle.dex_discovery_market,
        dex_quote_market=gmgn_dex_market,
        dex_candle_market=gmgn_dex_market,
        dex_profile_market=gmgn_dex_market,
        stream_dex_market=okx_bundle.stream_dex_market,
        discovery_chain_ids=okx_chain_indexes_to_chain_ids(settings.okx_dex_chain_indexes),
        provider_health=(okx_bundle.health, _gmgn_provider_health(settings)),
    )


def _wire_okx_provider_bundle(settings: Settings) -> OkxProviderBundle:
    capabilities: set[MarketCapability] = set()
    shared_cex_market: OkxCexMarketProvider | None = None
    if settings.okx_cex_sync_enabled:
        shared_cex_market = _okx_cex_market(settings)
        capabilities.add(MarketCapability.QUOTE_CEX)
    dex_discovery_market: DexTokenDiscoveryProvider | None = None
    if settings.okx_dex_configured:
        dex_discovery_market = _SerializedDiscoveryProvider(_okx_dex_discovery_market(settings))
        capabilities.add(MarketCapability.SEARCH_DEX)
    stream_dex_market: DexMarketStreamProvider | None = None
    if settings.okx_dex_ws_configured:
        stream_dex_market = _okx_dex_ws_market(settings)
        capabilities.add(MarketCapability.STREAM_DEX)
    return OkxProviderBundle(
        sync_cex_market=shared_cex_market,
        message_cex_market=shared_cex_market,
        dex_discovery_market=dex_discovery_market,
        stream_dex_market=stream_dex_market,
        health=ProviderHealth(
            provider="okx",
            capabilities=frozenset(capabilities),
            configured=bool(capabilities),
        ),
    )


def _gmgn_provider_health(settings: Settings) -> ProviderHealth:
    capabilities = (
        frozenset(
            {
                MarketCapability.QUOTE_DEX_EXACT,
                MarketCapability.PROFILE_DEX_EXACT,
                MarketCapability.CANDLES_DEX_EXACT,
            }
        )
        if settings.gmgn_configured
        else frozenset()
    )
    return ProviderHealth(provider="gmgn", capabilities=capabilities, configured=settings.gmgn_configured)


def _wire_marketlane(settings: Settings) -> MarketlaneProviders:
    if not settings.marketlane_enabled:
        return MarketlaneProviders()
    return MarketlaneProviders(
        stock_quote_provider=MarketlaneQuoteProvider(
            timeout_seconds=settings.marketlane_quote_timeout_seconds,
            cache_ttl_seconds=settings.marketlane_quote_cache_ttl_seconds,
        )
    )


def _gmgn_upstream_factory(settings: Settings) -> UpstreamClientFactory:
    def factory(on_frame: Callable[..., Any]) -> UpstreamClientProtocol:
        return DirectGmgnWebSocketClient(
            app_version=settings.upstream_app_version,
            channels=list(settings.upstream_channels),
            chains=list(settings.upstream_chains),
            proxy=settings.upstream_proxy,
            reconnect_delay=settings.upstream_reconnect_delay,
            heartbeat_interval=settings.upstream_heartbeat_interval,
            idle_timeout=settings.upstream_idle_timeout,
            on_frame=on_frame,
        )

    return factory


def _okx_cex_market(settings: Settings) -> OkxCexMarketProvider:
    return OkxCexMarketProvider(
        OkxCexClient(
            base_url=settings.okx_cex_base_url,
            timeout_seconds=settings.okx_timeout_seconds,
        )
    )


def _okx_dex_discovery_market(settings: Settings) -> OkxDexDiscoveryProvider:
    return OkxDexDiscoveryProvider(
        OkxDexClient(
            base_url=settings.okx_dex_base_url,
            api_key=settings.okx_dex_api_key,
            secret_key=settings.okx_dex_secret_key,
            passphrase=settings.okx_dex_passphrase,
            timeout_seconds=settings.okx_timeout_seconds,
        )
    )


def _gmgn_dex_market(settings: Settings) -> GmgnDexMarketProvider:
    return GmgnDexMarketProvider(
        GmgnOpenApiClient(
            api_key=settings.gmgn_api_key or "",
            base_url=settings.gmgn_openapi_base_url,
            timeout_seconds=settings.gmgn_timeout_seconds,
            cache_ttl_seconds=settings.gmgn_token_info_cache_ttl_seconds,
        )
    )


def _okx_dex_ws_market(settings: Settings) -> OkxDexWebSocketMarketProviderAdapter:
    return OkxDexWebSocketMarketProviderAdapter(
        OkxDexWebSocketMarketProvider(
            url=settings.okx_dex_ws_url,
            api_key=settings.okx_dex_api_key or "",
            secret_key=settings.okx_dex_secret_key or "",
            passphrase=settings.okx_dex_passphrase or "",
            subscription_limit=settings.okx_dex_ws_subscription_limit,
        )
    )


def _openai_social_event_provider(settings: Settings) -> OpenAIAgentsSocialEventClient:
    return OpenAIAgentsSocialEventClient(
        api_key=settings.llm_api_key or "",
        model=settings.llm_model or "",
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        trace_enabled=settings.llm_trace_enabled,
        trace_api_key=settings.llm_trace_api_key,
        trace_include_sensitive_data=settings.llm_trace_include_sensitive_data,
    )


def _openai_pulse_decision_provider(settings: Settings) -> OpenAIPulseDecisionProvider:
    return OpenAIPulseDecisionProvider(
        OpenAIAgentsPulseDecisionClient(
            api_key=settings.llm_api_key or "",
            model=settings.pulse_agent_model or "",
            base_url=settings.llm_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            trace_enabled=settings.llm_trace_enabled,
            trace_api_key=settings.llm_trace_api_key,
            trace_include_sensitive_data=settings.llm_trace_include_sensitive_data,
        )
    )


def _openai_watchlist_summary_provider(settings: Settings) -> OpenAIAgentsWatchlistSummaryClient:
    return OpenAIAgentsWatchlistSummaryClient(
        api_key=settings.llm_api_key or "",
        model=settings.watchlist_handle_summary_model or "",
        base_url=settings.llm_base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        trace_enabled=settings.llm_trace_enabled,
        trace_api_key=settings.llm_trace_api_key,
        trace_include_sensitive_data=settings.llm_trace_include_sensitive_data,
    )


def _cex_ticker(ticker: Any) -> CexTicker:
    return CexTicker(
        inst_id=ticker.inst_id,
        inst_type=ticker.inst_type,
        last_price=ticker.last_price,
        volume_24h=ticker.volume_24h,
        open_interest=ticker.open_interest,
        raw=ticker.raw,
    )


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


def _market_candle(candle: Any) -> MarketCandle:
    return MarketCandle(
        time_ms=int(candle.time_ms),
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
        volume_quote=candle.volume_quote,
        volume_usd=candle.volume_usd,
        confirmed=candle.confirmed,
        raw=candle.raw,
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


def _number_from_mapping(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


__all__ = [
    "AssetMarketProviders",
    "GmgnDexMarketProvider",
    "IngestionProviders",
    "MarketlaneProviders",
    "OkxCexMarketProvider",
    "OkxDexDiscoveryProvider",
    "OkxDexWebSocketMarketProviderAdapter",
    "OkxProviderBundle",
    "PulseLabProviders",
    "SocialEnrichmentProviders",
    "WiredProviders",
    "okx_chain_indexes_to_chain_ids",
    "wire_providers",
]
