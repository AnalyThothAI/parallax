from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from parallax.domains.news_intel.services.news_story_brief_input import news_story_brief_material_input_payload
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_AGENT_NAME,
    NEWS_STORY_BRIEF_LANE,
    NEWS_STORY_BRIEF_WORKFLOW_NAME,
    NewsStoryBriefInputPacket,
    NewsStoryBriefPayload,
)
from parallax.platform.agent_execution import AgentStageSpec
from parallax.platform.agent_hashing import text_sha256
from parallax.platform.agent_knowledge import render_agent_instructions

_NEWS_STORY_BRIEF_KNOWLEDGE_REFS = ("market_research_harness",)


@lru_cache(maxsize=1)
def news_story_brief_instructions() -> str:
    return (Path(__file__).resolve().parents[1] / "prompts" / "news_story_brief.md").read_text(encoding="utf-8")


def news_story_brief_stage_instructions() -> str:
    return render_agent_instructions(
        news_story_brief_instructions(),
        knowledge_refs=_NEWS_STORY_BRIEF_KNOWLEDGE_REFS,
    )


def news_story_brief_prompt_text_hash() -> str:
    return text_sha256(news_story_brief_stage_instructions())


def build_news_story_brief_stage(*, packet: NewsStoryBriefInputPacket, run_id: str) -> AgentStageSpec:
    return AgentStageSpec(
        lane=NEWS_STORY_BRIEF_LANE,
        stage="news_story_brief",
        instructions=news_story_brief_stage_instructions(),
        input_payload=news_story_brief_material_input_payload(packet),
        output_type=NewsStoryBriefPayload,
        prompt_version=packet.prompt_version,
        schema_version=packet.schema_version,
        workflow_name=NEWS_STORY_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_STORY_BRIEF_AGENT_NAME,
        group_id=f"news_story:{packet.story_key}",
        knowledge_refs=_NEWS_STORY_BRIEF_KNOWLEDGE_REFS,
        trace_metadata={
            "story_brief_key": packet.story_brief_key,
            "story_key": packet.story_key,
            "representative_news_item_id": packet.representative_news_item_id,
            "member_count": len(packet.member_news_item_ids),
            "run_id": str(run_id),
            "input_hash": packet.input_hash,
            "prompt_version": packet.prompt_version,
            "schema_version": packet.schema_version,
        },
    )


__all__ = [
    "build_news_story_brief_stage",
    "news_story_brief_instructions",
    "news_story_brief_prompt_text_hash",
    "news_story_brief_stage_instructions",
]
