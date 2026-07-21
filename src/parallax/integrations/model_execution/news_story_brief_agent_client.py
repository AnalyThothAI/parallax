from __future__ import annotations

from typing import Any

from parallax.domains.news_intel.services.news_story_brief_stage import (
    build_news_story_brief_stage,
    news_story_brief_prompt_text_hash,
)
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_PROMPT_VERSION,
    NEWS_STORY_BRIEF_SCHEMA_VERSION,
    NewsStoryBriefInputPacket,
    NewsStoryBriefPayload,
)
from parallax.integrations.model_execution.output_schema import StrictJsonOutputSchema
from parallax.platform.agent_execution import RUNTIME_VERSION, AgentCapacityReservation
from parallax.platform.agent_hashing import artifact_hash_for, json_sha256


class LiteLLMNewsStoryBriefClient:
    provider = "litellm"

    def __init__(self, *, agent_gateway: Any) -> None:
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        self._agent_gateway = agent_gateway

    @property
    def model(self) -> str:
        return self._agent_gateway.model_for_lane("news.story_brief")

    @property
    def artifact_version_hash(self) -> str:
        return artifact_hash_for(
            model=self.model,
            prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(StrictJsonOutputSchema(NewsStoryBriefPayload).json_schema()),
            prompt_text_hash=news_story_brief_prompt_text_hash(),
        )

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        return self._agent_gateway.try_reserve(lane, rate_units=rate_units)

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
