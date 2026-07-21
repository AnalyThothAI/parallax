from __future__ import annotations

from typing import Any

from parallax.integrations.model_execution.execution_gateway import AgentExecutionGateway
from parallax.integrations.model_execution.news_story_brief_agent_client import (
    LiteLLMNewsStoryBriefClient,
)
from parallax.platform.config.settings import Settings


def litellm_news_story_brief_provider(
    *,
    agent_gateway: AgentExecutionGateway,
) -> LiteLLMNewsStoryBriefClient:
    return LiteLLMNewsStoryBriefClient(
        agent_gateway=agent_gateway,
    )


def build_agent_execution_gateway(
    settings: Settings,
    *,
    telemetry: Any | None = None,
) -> AgentExecutionGateway:
    return AgentExecutionGateway(
        api_key=settings.llm.api_key or "",
        base_url=settings.llm.base_url,
        policy=settings.workers.agent_runtime,
        telemetry=telemetry,
    )


__all__ = [
    "build_agent_execution_gateway",
    "litellm_news_story_brief_provider",
]
