from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel._constants import EQUITY_EVENT_BRIEF_SCHEMA_VERSION
from gmgn_twitter_intel.domains.pulse_lab.providers import PulseAgentRuntimeContract, PulseDecisionResult
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_decision_runtime import (
    PulseDecisionRuntimeService,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import DecisionRoute
from gmgn_twitter_intel.integrations.openai_agents.agent_execution_gateway import AgentExecutionGateway
from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import InstructorSafetyNet
from gmgn_twitter_intel.integrations.openai_agents.narrative_intel_agent_client import OpenAIAgentsNarrativeIntelClient
from gmgn_twitter_intel.integrations.openai_agents.news_item_brief_agent_client import (
    OpenAIAgentsNewsItemBriefClient,
)
from gmgn_twitter_intel.integrations.openai_agents.pulse_decision_agent_client import OpenAIAgentsPulseDecisionClient
from gmgn_twitter_intel.integrations.openai_agents.social_event_agent_client import OpenAIAgentsSocialEventClient
from gmgn_twitter_intel.integrations.openai_agents.watchlist_summary_agent_client import (
    OpenAIAgentsWatchlistSummaryClient,
)
from gmgn_twitter_intel.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentRuntimePolicy,
)
from gmgn_twitter_intel.platform.agent_hashing import artifact_hash_for, json_sha256
from gmgn_twitter_intel.platform.config.settings import Settings


class OpenAINarrativeIntelProvider:
    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def model(self) -> str:
        return self._client.model

    @property
    def artifact_version_hash(self) -> str:
        return self._client.artifact_version_hash

    async def label_mentions(self, **kwargs: Any) -> Any:
        return await self._client.label_mentions(**kwargs)

    async def summarize_discussion(self, **kwargs: Any) -> Any:
        return await self._client.summarize_discussion(**kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()


class OpenAIPulseDecisionProvider:
    def __init__(self, client: OpenAIAgentsPulseDecisionClient, *, pipeline_timeout_seconds: float) -> None:
        self._client = client
        self._pipeline_timeout_seconds = float(pipeline_timeout_seconds)

    @property
    def provider(self) -> str:
        return self._client.provider

    @property
    def model(self) -> str:
        return self._client.model

    @property
    def timeout_seconds(self) -> float:
        return self._pipeline_timeout_seconds

    @property
    def artifact_version_hash(self) -> str:
        return self._client.artifact_version_hash

    @property
    def runtime_contract(self) -> PulseAgentRuntimeContract:
        return self._client.runtime_contract

    def model_for_lane(self, lane: str) -> str:
        gateway = getattr(self._client, "_agent_gateway", None)
        model_for_lane = getattr(gateway, "model_for_lane", None)
        if callable(model_for_lane):
            return str(model_for_lane(lane) or "")
        return self.model

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        scope: str = "execution",
    ) -> AgentCapacityReservation:
        return self._client.try_reserve_execution(lane, child_lanes=child_lanes, scope=scope)

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        return self._client.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
        )

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
        stage_plan: Any | None = None,
    ) -> PulseDecisionResult:
        result = await self._client.run_decision_pipeline(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
            parent_reservation=parent_reservation,
            stage_plan=stage_plan,
        )
        return PulseDecisionResult(
            final_decision=result.final_decision,
            agent_run_audit=result.agent_run_audit,
            stage_audits=result.stage_audits,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class OpenAIEquityEventBriefProvider:
    provider = "openai"

    def __init__(self, *, agent_gateway: AgentExecutionGateway, lane: str) -> None:
        self._agent_gateway = agent_gateway
        self._lane = str(lane or "equity_event.brief")

    @property
    def model(self) -> str:
        return self._agent_gateway.model_for_lane(self._lane)

    @property
    def artifact_version_hash(self) -> str:
        return artifact_hash_for(
            model=self.model,
            prompt_version="equity_event_brief_prompt_v1",
            schema_version=EQUITY_EVENT_BRIEF_SCHEMA_VERSION,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256({}),
        )

    def try_reserve_execution(self, lane: str | None = None) -> AgentCapacityReservation:
        return self._agent_gateway.try_reserve(str(lane or self._lane))

    async def aclose(self) -> None:
        return None


def openai_social_event_provider(
    settings: Settings,
    *,
    agent_gateway: AgentExecutionGateway,
) -> OpenAIAgentsSocialEventClient:
    return OpenAIAgentsSocialEventClient(
        agent_gateway=agent_gateway,
    )


def openai_pulse_decision_provider(
    settings: Settings,
    *,
    agent_gateway: AgentExecutionGateway,
    db_pool: Any | None,
) -> OpenAIPulseDecisionProvider:
    if db_pool is None:
        raise RuntimeError("db_pool is required for OpenAIPulseDecisionProvider")
    return OpenAIPulseDecisionProvider(
        OpenAIAgentsPulseDecisionClient(
            decision_runtime=PulseDecisionRuntimeService(db_pool=db_pool),
            agent_gateway=agent_gateway,
        ),
        pipeline_timeout_seconds=_agent_runtime_lane_timeout_seconds(settings, "pulse.pipeline"),
    )


def openai_narrative_intel_provider(
    settings: Settings,
    *,
    agent_gateway: AgentExecutionGateway,
) -> OpenAINarrativeIntelProvider:
    return OpenAINarrativeIntelProvider(
        OpenAIAgentsNarrativeIntelClient(
            agent_gateway=agent_gateway,
        )
    )


def openai_watchlist_summary_provider(
    settings: Settings,
    *,
    agent_gateway: AgentExecutionGateway,
) -> OpenAIAgentsWatchlistSummaryClient:
    return OpenAIAgentsWatchlistSummaryClient(
        agent_gateway=agent_gateway,
    )


def openai_news_item_brief_provider(
    settings: Settings,
    *,
    agent_gateway: AgentExecutionGateway,
) -> OpenAIAgentsNewsItemBriefClient:
    return OpenAIAgentsNewsItemBriefClient(
        agent_gateway=agent_gateway,
    )


def openai_equity_event_brief_provider(
    settings: Settings,
    *,
    agent_gateway: AgentExecutionGateway,
) -> OpenAIEquityEventBriefProvider:
    return OpenAIEquityEventBriefProvider(
        agent_gateway=agent_gateway,
        lane=settings.equity_event_intel.agent.lane,
    )


def build_agent_execution_gateway(
    settings: Settings,
    *,
    llm_gateway: object | None,
    telemetry: Any | None = None,
) -> AgentExecutionGateway:
    gateway = _require_llm_gateway(llm_gateway)
    policy = AgentRuntimePolicy.model_validate(settings.workers.agent_runtime.model_dump(mode="json"))
    safety_net = _build_safety_net(settings, model=_safety_net_model(settings))
    return AgentExecutionGateway(
        llm_gateway=gateway,
        base_url=settings.llm_base_url,
        trace_enabled=settings.llm_trace_enabled,
        trace_include_sensitive_data=settings.llm_trace_include_sensitive_data,
        policy=policy,
        safety_net=safety_net,
        telemetry=telemetry,
    )


def _build_safety_net(settings: Settings, *, model: str) -> InstructorSafetyNet | None:
    if not settings.llm.instructor_safety_net_enabled:
        return None
    return InstructorSafetyNet(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key or "",
        model=model,
        max_retries=int(settings.llm.instructor_max_retries),
        enabled=True,
    )


def _safety_net_model(settings: Settings) -> str:
    return settings.agent_runtime_default_model


def _agent_runtime_lane_timeout_seconds(settings: Settings, lane: str) -> float:
    lanes = getattr(settings.workers.agent_runtime, "lanes", {}) or {}
    lane_policy = lanes.get(lane)
    if lane_policy is None:
        return 120.0
    return float(getattr(lane_policy, "timeout_seconds", 120.0) or 120.0)


def _require_llm_gateway(llm_gateway: object | None) -> object:
    if llm_gateway is None:
        raise RuntimeError("LLMGateway is required for configured OpenAI providers")
    return llm_gateway


__all__ = [
    "OpenAIEquityEventBriefProvider",
    "OpenAINarrativeIntelProvider",
    "OpenAIPulseDecisionProvider",
    "build_agent_execution_gateway",
    "openai_equity_event_brief_provider",
    "openai_narrative_intel_provider",
    "openai_news_item_brief_provider",
    "openai_pulse_decision_provider",
    "openai_social_event_provider",
    "openai_watchlist_summary_provider",
]
