from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.providers import PULSE_DECISION_LANE, PulseAgentRuntimeContract, PulseDecisionResult
from parallax.domains.pulse_lab.services.pulse_decision_runtime import (
    PulseDecisionRuntimeService,
)
from parallax.domains.pulse_lab.types.agent_decision import DecisionRoute
from parallax.integrations.model_execution.execution_gateway import AgentExecutionGateway
from parallax.integrations.model_execution.news_item_brief_agent_client import (
    LiteLLMNewsItemBriefClient,
)
from parallax.integrations.model_execution.pulse_decision_agent_client import LiteLLMPulseDecisionClient
from parallax.platform.agent_execution import (
    AgentCapacityReservation,
    AgentRuntimePolicy,
)
from parallax.platform.config.settings import Settings


class LiteLLMPulseDecisionProvider:
    def __init__(self, client: LiteLLMPulseDecisionClient, *, pipeline_timeout_seconds: float) -> None:
        self._client = client
        self._pipeline_timeout_seconds = _positive_timeout_seconds(
            pipeline_timeout_seconds,
            error_code="pulse_decision_pipeline_timeout_seconds_required",
        )

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
        return self._client.model_for_lane(lane)

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        rate_units: int = 1,
        scope: str = "execution",
    ) -> AgentCapacityReservation:
        return self._client.try_reserve_execution(
            lane,
            child_lanes=child_lanes,
            rate_units=rate_units,
            scope=scope,
        )

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
    ) -> PulseDecisionResult:
        result = await self._client.run_decision_pipeline(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
            parent_reservation=parent_reservation,
        )
        return PulseDecisionResult(
            final_decision=result.final_decision,
            agent_run_audit=result.agent_run_audit,
            stage_audits=result.stage_audits,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def litellm_pulse_decision_provider(
    settings: Settings,
    *,
    agent_gateway: AgentExecutionGateway,
) -> LiteLLMPulseDecisionProvider:
    return LiteLLMPulseDecisionProvider(
        LiteLLMPulseDecisionClient(
            decision_runtime=PulseDecisionRuntimeService(),
            agent_gateway=agent_gateway,
        ),
        pipeline_timeout_seconds=_agent_runtime_lane_timeout_seconds(settings, PULSE_DECISION_LANE),
    )


def litellm_news_item_brief_provider(
    settings: Settings,
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


def _agent_runtime_lane_timeout_seconds(settings: Settings, lane: str) -> float:
    lane_policy = settings.workers.agent_runtime.lanes[lane]
    return _positive_timeout_seconds(
        lane_policy.timeout_seconds,
        error_code="agent_runtime_lane_timeout_seconds_required",
    )


def _require_llm_gateway(llm_gateway: object | None) -> object:
    if llm_gateway is None:
        raise RuntimeError("LLMGateway is required for configured LiteLLM providers")
    return llm_gateway


def _positive_timeout_seconds(value: Any, *, error_code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise ValueError(error_code)
    return float(value)


__all__ = [
    "LiteLLMPulseDecisionProvider",
    "build_agent_execution_gateway",
    "litellm_news_item_brief_provider",
    "litellm_pulse_decision_provider",
]
