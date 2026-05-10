from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import (
    CexMarketProvider,
    CexTicker,
    DexMarketProvider,
    DexTokenCandidate,
    DexTokenPrice,
    DexTokenPriceRequest,
)
from gmgn_twitter_intel.domains.ingestion.providers import UpstreamClientProtocol
from gmgn_twitter_intel.domains.pulse_lab.providers import PulseThesisProvider, PulseThesisResult
from gmgn_twitter_intel.domains.social_enrichment.providers import SocialEventEnrichmentProvider
from gmgn_twitter_intel.integrations.gmgn.direct_ws import DirectGmgnWebSocketClient
from gmgn_twitter_intel.integrations.okx.cex_client import OkxCexClient
from gmgn_twitter_intel.integrations.okx.chains import OKX_CHAIN_INDEX_TO_CHAIN, OKX_CHAIN_TO_CHAIN_INDEX
from gmgn_twitter_intel.integrations.okx.dex_client import EVM_ADDRESS_RE, OkxDexClient
from gmgn_twitter_intel.integrations.openai_agents.pulse_thesis_agent_client import OpenAIAgentsPulseThesisClient
from gmgn_twitter_intel.integrations.openai_agents.social_event_agent_client import OpenAIAgentsSocialEventClient
from gmgn_twitter_intel.platform.config.settings import Settings

UpstreamClientFactory = Callable[[Callable[..., Any]], UpstreamClientProtocol | None]


@dataclass(frozen=True, slots=True)
class IngestionProviders:
    upstream_client_factory: UpstreamClientFactory | None = None


@dataclass(frozen=True, slots=True)
class AssetMarketProviders:
    projection_dex_market: DexMarketProvider | None = None
    sync_cex_market: CexMarketProvider | None = None
    sync_dex_market: DexMarketProvider | None = None
    message_cex_market: CexMarketProvider | None = None
    message_dex_market: DexMarketProvider | None = None
    discovery_dex_market: DexMarketProvider | None = None
    discovery_chain_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SocialEnrichmentProviders:
    event_enrichment: SocialEventEnrichmentProvider | None = None


@dataclass(frozen=True, slots=True)
class PulseLabProviders:
    thesis_provider: PulseThesisProvider | None = None


@dataclass(frozen=True, slots=True)
class WiredProviders:
    ingestion: IngestionProviders
    asset_market: AssetMarketProviders
    social_enrichment: SocialEnrichmentProviders
    pulse_lab: PulseLabProviders


class OkxCexMarketProvider:
    def __init__(self, client: OkxCexClient) -> None:
        self._client = client

    def tickers(self, *, inst_type: str) -> list[CexTicker]:
        return [_cex_ticker(ticker) for ticker in self._client.tickers(inst_type=inst_type)]

    def ticker(self, *, inst_id: str) -> CexTicker | None:
        ticker = self._client.ticker(inst_id=inst_id)
        return _cex_ticker(ticker) if ticker is not None else None

    def close(self) -> None:
        self._client.close()


class OkxDexMarketProvider:
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

    def token_prices(self, tokens: list[DexTokenPriceRequest]) -> list[DexTokenPrice]:
        request_items = [
            {
                "chainIndex": chain_index,
                "tokenContractAddress": _normalize_address(token.address),
            }
            for token in tokens
            if (chain_index := okx_chain_index(token.chain_id))
        ]
        return [_dex_token_price(price) for price in self._client.token_prices(request_items)]

    def close(self) -> None:
        self._client.close()


class OpenAIPulseThesisProvider:
    def __init__(self, client: OpenAIAgentsPulseThesisClient) -> None:
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

    def request_audit(self, *, context: dict[str, Any], run_id: str, job: dict[str, Any]) -> dict[str, Any]:
        return self._client.request_audit(context=context, run_id=run_id, job=job)

    async def write_thesis(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
    ) -> PulseThesisResult:
        result = await self._client.write_thesis(context=context, run_id=run_id, job=job)
        return PulseThesisResult(payload=result.payload, agent_run_audit=result.agent_run_audit)

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
            thesis_provider=_openai_pulse_thesis_provider(settings)
            if settings.pulse_agent_enabled and settings.pulse_agent_configured
            else None,
        ),
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
    return AssetMarketProviders(
        projection_dex_market=_okx_dex_market(settings) if settings.okx_dex_configured else None,
        sync_cex_market=_okx_cex_market(settings) if settings.okx_cex_sync_enabled else None,
        sync_dex_market=_okx_dex_market(settings) if settings.okx_dex_configured else None,
        message_cex_market=_okx_cex_market(settings) if settings.okx_cex_sync_enabled else None,
        message_dex_market=_okx_dex_market(settings) if settings.okx_dex_configured else None,
        discovery_dex_market=_okx_dex_market(settings) if settings.okx_dex_configured else None,
        discovery_chain_ids=okx_chain_indexes_to_chain_ids(settings.okx_dex_chain_indexes),
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


def _okx_dex_market(settings: Settings) -> OkxDexMarketProvider:
    return OkxDexMarketProvider(
        OkxDexClient(
            base_url=settings.okx_dex_base_url,
            api_key=settings.okx_dex_api_key,
            secret_key=settings.okx_dex_secret_key,
            passphrase=settings.okx_dex_passphrase,
            timeout_seconds=settings.okx_timeout_seconds,
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


def _openai_pulse_thesis_provider(settings: Settings) -> OpenAIPulseThesisProvider:
    return OpenAIPulseThesisProvider(
        OpenAIAgentsPulseThesisClient(
            api_key=settings.llm_api_key or "",
            model=settings.pulse_agent_model or "",
            base_url=settings.llm_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            trace_enabled=settings.llm_trace_enabled,
            trace_api_key=settings.llm_trace_api_key,
            trace_include_sensitive_data=settings.llm_trace_include_sensitive_data,
        )
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


def _dex_token_price(price: Any) -> DexTokenPrice:
    return DexTokenPrice(
        chain_id=okx_index_to_chain_id(price.chain_index) or str(price.chain_index),
        address=_normalize_address(price.address),
        observed_at_ms=price.observed_at_ms,
        price_usd=price.price_usd,
        raw=price.raw,
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


__all__ = [
    "AssetMarketProviders",
    "IngestionProviders",
    "OkxCexMarketProvider",
    "OkxDexMarketProvider",
    "PulseLabProviders",
    "SocialEnrichmentProviders",
    "WiredProviders",
    "okx_chain_indexes_to_chain_ids",
    "wire_providers",
]
