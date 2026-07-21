from __future__ import annotations

from typing import Any

from parallax.domains.news_intel.services.news_story_brief_stage import (
    build_news_story_brief_stage,
    news_story_brief_stage_instructions,
)
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_PROMPT_VERSION,
    NEWS_STORY_BRIEF_SCHEMA_VERSION,
    NewsStoryBriefInputPacket,
    NewsStoryBriefPayload,
)
from parallax.platform.agent_execution import AgentCapacityReservation


class LiteLLMNewsStoryBriefClient:
    provider = "litellm"

    def __init__(self, *, agent_gateway: Any) -> None:
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        self._agent_gateway = agent_gateway

    @property
    def model(self) -> str:
        return self._agent_gateway.model

    @property
    def artifact_version_hash(self) -> str:
        return self._agent_gateway.artifact_version_hash(
            output_type=NewsStoryBriefPayload,
            prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
            instructions=news_story_brief_stage_instructions(),
        )

    def try_reserve_execution(self, *, rate_units: int = 1) -> AgentCapacityReservation:
        return self._agent_gateway.try_reserve(rate_units=rate_units)

    def request_audit(self, *, run_id: str, packet: NewsStoryBriefInputPacket) -> dict[str, Any]:
        stage = build_news_story_brief_stage(packet=packet, run_id=run_id)
        return self._agent_gateway.request_audit(stage).model_dump(mode="json")

    async def brief_story(
        self,
        *,
        run_id: str,
        packet: NewsStoryBriefInputPacket,
        reservation: AgentCapacityReservation | None = None,
    ) -> dict[str, Any]:
        stage = build_news_story_brief_stage(packet=packet, run_id=run_id)
        execution = await self._agent_gateway.execute(stage, reservation=reservation)
        payload = _coerce_news_story_brief_payload(execution.final_output)
        return {
            "payload": payload.model_dump(mode="json"),
            "agent_run_audit": execution.audit.model_dump(mode="json"),
        }

    async def aclose(self) -> None:
        return None


def _coerce_news_story_brief_payload(value: Any) -> NewsStoryBriefPayload:
    if isinstance(value, NewsStoryBriefPayload):
        return value
    return NewsStoryBriefPayload.model_validate(value)


__all__ = ["LiteLLMNewsStoryBriefClient"]
