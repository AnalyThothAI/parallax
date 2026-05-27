from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel._constants import (
    EQUITY_EVENT_BRIEF_PROMPT_VERSION,
    EQUITY_EVENT_BRIEF_SCHEMA_VERSION,
)
from gmgn_twitter_intel.domains.equity_event_intel.services.brief_runtime import build_equity_event_brief_stage
from gmgn_twitter_intel.domains.equity_event_intel.types import (
    EQUITY_EVENT_BRIEF_LANE,
    EquityEventBriefInputPacket,
    EquityEventBriefPayload,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.platform.agent_execution import RUNTIME_VERSION, AgentCapacityReservation
from gmgn_twitter_intel.platform.agent_hashing import artifact_hash_for, json_sha256


class OpenAIAgentsEquityEventBriefClient:
    provider = "openai"

    def __init__(self, *, agent_gateway: Any) -> None:
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        self._agent_gateway = agent_gateway

    @property
    def model(self) -> str:
        return self._agent_gateway.model_for_lane(EQUITY_EVENT_BRIEF_LANE)

    @property
    def artifact_version_hash(self) -> str:
        return artifact_hash_for(
            model=self.model,
            prompt_version=EQUITY_EVENT_BRIEF_PROMPT_VERSION,
            schema_version=EQUITY_EVENT_BRIEF_SCHEMA_VERSION,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(StrictJsonOutputSchema(EquityEventBriefPayload).json_schema()),
        )

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        return self._agent_gateway.try_reserve(lane, rate_units=rate_units)

    def request_audit(self, *, run_id: str, packet: EquityEventBriefInputPacket) -> dict[str, Any]:
        stage = build_equity_event_brief_stage(packet=packet, run_id=run_id)
        return self._agent_gateway.request_audit(stage).model_dump(mode="json")

    async def brief_event(
        self,
        *,
        run_id: str,
        packet: EquityEventBriefInputPacket,
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]:
        stage = build_equity_event_brief_stage(packet=packet, run_id=run_id)
        execution = await self._agent_gateway.execute(stage, reservation=reservation)
        payload = _coerce_equity_event_brief_payload(execution.final_output)
        return {
            "payload": payload.model_dump(mode="json"),
            "agent_run_audit": execution.audit.model_dump(mode="json"),
        }

    async def aclose(self) -> None:
        return None


def _coerce_equity_event_brief_payload(value: Any) -> EquityEventBriefPayload:
    if isinstance(value, EquityEventBriefPayload):
        return value
    return EquityEventBriefPayload.model_validate(value)


__all__ = ["OpenAIAgentsEquityEventBriefClient"]
