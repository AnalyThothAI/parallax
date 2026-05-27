from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.news_intel.services.news_item_brief_runtime import (
    build_news_item_brief_stage,
)
from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NewsItemBriefInputPacket,
    NewsItemBriefPayload,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
)
from gmgn_twitter_intel.platform.agent_hashing import artifact_hash_for, json_sha256


class OpenAIAgentsNewsItemBriefClient:
    provider = "openai"

    def __init__(
        self,
        *,
        agent_gateway: Any,
    ) -> None:
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        self._agent_gateway = agent_gateway

    @property
    def model(self) -> str:
        return self._agent_gateway.model_for_lane("news.item_brief")

    @property
    def artifact_version_hash(self) -> str:
        return artifact_hash_for(
            model=self.model,
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(StrictJsonOutputSchema(NewsItemBriefPayload).json_schema()),
        )

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        return self._agent_gateway.try_reserve(lane, rate_units=rate_units)

    def request_audit(self, *, run_id: str, packet: NewsItemBriefInputPacket) -> dict[str, Any]:
        stage = build_news_item_brief_stage(packet=packet, run_id=run_id)
        return self._agent_gateway.request_audit(stage).model_dump(mode="json")

    async def brief_item(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]:
        stage = build_news_item_brief_stage(packet=packet, run_id=run_id)
        execution = await self._agent_gateway.execute(stage, reservation=reservation)
        payload = _coerce_news_item_brief_payload(execution.final_output)
        return {
            "payload": payload.model_dump(mode="json"),
            "agent_run_audit": execution.audit.model_dump(mode="json"),
        }

    async def aclose(self) -> None:
        return None


def _coerce_news_item_brief_payload(value: Any) -> NewsItemBriefPayload:
    if isinstance(value, NewsItemBriefPayload):
        return value
    return NewsItemBriefPayload.model_validate(value)


__all__ = ["OpenAIAgentsNewsItemBriefClient"]
