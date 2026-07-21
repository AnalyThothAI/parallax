from __future__ import annotations

from parallax.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    CexMarketIntelProviders,
    IngestionProviders,
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
) -> WiredProviders:
    from parallax.app.runtime.provider_wiring import (
        asset_market,
        cex_market_intel,
        gmgn,
        model_execution,
        news,
    )

    return WiredProviders(
        ingestion=IngestionProviders(
            upstream_client_factory=gmgn.gmgn_upstream_factory(settings) if start_collector else None,
        ),
        asset_market=asset_market.wire_asset_market(settings),
        cex_market_intel=cex_market_intel.wire_cex_market_intel(settings),
        news_intel=NewsIntelProviders(
            feed_client=news.news_feed_client(settings)
            if settings.news_intel.enabled and settings.workers.news_fetch.enabled
            else None,
            brief_provider=model_execution.litellm_news_item_brief_provider(
                agent_gateway=_require_agent_execution_gateway(agent_execution_gateway),
            )
            if (
                settings.news_intel.enabled
                and (settings.workers.news_item_brief.enabled or settings.workers.news_story_brief.enabled)
                and (settings.news_item_brief_configured or settings.news_story_brief_configured)
            )
            else None,
        ),
        pulse_lab=PulseLabProviders(
            decision_provider=model_execution.litellm_pulse_decision_provider(
                settings,
                agent_gateway=_require_agent_execution_gateway(agent_execution_gateway),
            )
            if settings.workers.pulse_candidate.enabled and settings.pulse_agent_configured
            else None,
        ),
        agent_execution_gateway=agent_execution_gateway,
    )


def wire_asset_market_providers(settings: Settings) -> AssetMarketProviders:
    from parallax.app.runtime.provider_wiring import asset_market

    return asset_market.wire_asset_market_providers(settings)


def _require_agent_execution_gateway(agent_execution_gateway: object | None) -> object:
    if agent_execution_gateway is None:
        raise RuntimeError("AgentExecutionGateway is required for configured LiteLLM providers")
    return agent_execution_gateway


__all__ = [
    "AssetMarketProviders",
    "CexMarketIntelProviders",
    "IngestionProviders",
    "NewsIntelProviders",
    "PulseLabProviders",
    "WiredProviders",
    "wire_asset_market_providers",
    "wire_providers",
]
