from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NewsItemBriefInputPacket,
    NewsItemBriefPayload,
)
from gmgn_twitter_intel.platform.agent_execution import AgentStageSpec


@lru_cache(maxsize=1)
def news_item_brief_instructions() -> str:
    return (Path(__file__).resolve().parents[1] / "prompts" / "news_item_brief.md").read_text(encoding="utf-8")


def build_news_item_brief_stage(*, packet: NewsItemBriefInputPacket, run_id: str) -> AgentStageSpec:
    news_item_id = packet.news_item.news_item_id
    return AgentStageSpec(
        lane=NEWS_ITEM_BRIEF_LANE,
        stage="news_item_brief",
        instructions=news_item_brief_instructions(),
        input_payload=packet.model_dump(mode="json", exclude={"input_hash"}),
        output_type=NewsItemBriefPayload,
        prompt_version=packet.prompt_version,
        schema_version=packet.schema_version,
        workflow_name=NEWS_ITEM_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_ITEM_BRIEF_AGENT_NAME,
        group_id=f"news_item:{news_item_id}",
        trace_metadata={
            "news_item_id": news_item_id,
            "run_id": str(run_id),
            "input_hash": packet.input_hash,
            "prompt_version": packet.prompt_version,
            "schema_version": packet.schema_version,
        },
    )


__all__ = ["build_news_item_brief_stage", "news_item_brief_instructions"]
