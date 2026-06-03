from __future__ import annotations

from typing import Any

from parallax.app.runtime.narrative_bulk_analysis_gate import narrative_bulk_analysis_enabled
from parallax.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    CexMarketIntelProviders,
    IngestionProviders,
    MacrodataProviders,
    NarrativeIntelProviders,
    NewsIntelProviders,
    PulseLabProviders,
    WiredProviders,
)
from parallax.platform.config.settings import Settings


def wire_providers(
    settings: Settings,
    *,
    start_collector: bool,
    agent_execution_gateway: object | None = None,
    db_pool: Any | None = None,
) -> WiredProviders:
    from parallax.app.runtime.provider_wiring import (
        asset_market,
        cex_market_intel,
        gmgn,
        macrodata,
        model_execution,
        news,
    )

    return WiredProviders(
        ingestion=IngestionProviders(
            upstream_client_factory=gmgn.gmgn_upstream_factory(settings) if start_collector else None,
        ),
        asset_market=asset_market.wire_asset_market(settings),
        cex_market_intel=cex_market_intel.wire_cex_market_intel(settings),
        narrative_intel=NarrativeIntelProviders(
            narrative_provider=model_execution.litellm_narrative_intel_provider(
                settings,
                agent_gateway=_require_agent_execution_gateway(agent_execution_gateway),
            )
            if narrative_bulk_analysis_enabled(settings)
            else None,
        ),
        news_intel=NewsIntelProviders(
            feed_client=news.news_feed_client(settings)
            if settings.news_intel.enabled and settings.workers.news_fetch.enabled
            else None,
            brief_provider=model_execution.litellm_news_item_brief_provider(
                settings,
                agent_gateway=_require_agent_execution_gateway(agent_execution_gateway),
            )
            if (
                settings.news_intel.enabled
                and settings.workers.news_item_brief.enabled
                and settings.news_item_brief_configured
            )
            else None,
        ),
        pulse_lab=PulseLabProviders(
            decision_provider=model_execution.litellm_pulse_decision_provider(
                settings,
                agent_gateway=_require_agent_execution_gateway(agent_execution_gateway),
                db_pool=db_pool,
            )
            if settings.workers.pulse_candidate.enabled and settings.pulse_agent_configured
            else None,
        ),
        macrodata=macrodata.wire_macrodata(settings),
        agent_execution_gateway=agent_execution_gateway,
    )


def wire_asset_market_providers(settings: Settings, *, start_collector: bool) -> AssetMarketProviders:
    from parallax.app.runtime.provider_wiring import asset_market

    return asset_market.wire_asset_market_providers(settings, start_collector=start_collector)


def _require_agent_execution_gateway(agent_execution_gateway: object | None) -> object:
    if agent_execution_gateway is None:
        raise RuntimeError("AgentExecutionGateway is required for configured LiteLLM providers")
    return agent_execution_gateway


__all__ = [
    "AssetMarketProviders",
    "CexMarketIntelProviders",
    "IngestionProviders",
    "MacrodataProviders",
    "NarrativeIntelProviders",
    "NewsIntelProviders",
    "PulseLabProviders",
    "WiredProviders",
    "wire_asset_market_providers",
    "wire_providers",
]
