from __future__ import annotations

from typing import Any

from parallax.integrations.model_execution.execution_gateway import AgentExecutionGateway
from parallax.integrations.model_execution.news_item_brief_agent_client import (
    LiteLLMNewsItemBriefClient,
)
from parallax.platform.agent_execution import AgentRuntimePolicy
from parallax.platform.config.settings import Settings


def litellm_news_item_brief_provider(
    *,
    agent_gateway: AgentExecutionGateway,
) -> LiteLLMNewsItemBriefClient:
    return LiteLLMNewsItemBriefClient(
        agent_gateway=agent_gateway,
    )


def build_agent_execution_gateway(
    settings: Settings,
    *,
    llm_gateway: object | None,
    telemetry: Any | None = None,
) -> AgentExecutionGateway:
    gateway = _require_llm_gateway(llm_gateway)
    policy = AgentRuntimePolicy.model_validate(settings.workers.agent_runtime.model_dump(mode="json"))
    return AgentExecutionGateway(
        llm_gateway=gateway,
        base_url=settings.llm_base_url,
        trace_enabled=settings.llm_trace_enabled,
        trace_include_sensitive_data=settings.llm_trace_include_sensitive_data,
        policy=policy,
        telemetry=telemetry,
    )


def _require_llm_gateway(llm_gateway: object | None) -> object:
    if llm_gateway is None:
        raise RuntimeError("LLMGateway is required for configured LiteLLM providers")
    return llm_gateway


__all__ = [
    "build_agent_execution_gateway",
    "litellm_news_item_brief_provider",
]
