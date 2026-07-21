from __future__ import annotations

from parallax.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    IngestionProviders,
    NewsIntelProviders,
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
        gmgn,
        model_execution,
        news,
    )

    return WiredProviders(
        ingestion=IngestionProviders(
            upstream_client_factory=gmgn.gmgn_upstream_factory(settings) if start_collector else None,
        ),
        asset_market=asset_market.wire_asset_market(settings),
        news_intel=NewsIntelProviders(
            feed_client=news.news_feed_client(settings)
            if settings.news_intel.enabled and settings.workers.news_fetch.enabled
            else None,
            story_brief_provider=model_execution.litellm_news_story_brief_provider(
                agent_gateway=_require_agent_execution_gateway(agent_execution_gateway),
            )
            if settings.news_agent_execution_enabled
            else None,
        ),
    )


def _require_agent_execution_gateway(agent_execution_gateway: object | None) -> object:
    if agent_execution_gateway is None:
        raise RuntimeError("AgentExecutionGateway is required for configured LiteLLM providers")
    return agent_execution_gateway


__all__ = [
    "AssetMarketProviders",
    "IngestionProviders",
    "NewsIntelProviders",
    "WiredProviders",
    "wire_providers",
]
