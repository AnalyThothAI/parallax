from __future__ import annotations

from parallax.domains.news_intel.services.news_item_brief_stage import news_item_brief_instructions
from parallax.domains.news_intel.services.news_story_brief_input import news_story_brief_material_input_payload
from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefPayload
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_AGENT_NAME,
    NEWS_STORY_BRIEF_LANE,
    NEWS_STORY_BRIEF_WORKFLOW_NAME,
    NewsStoryBriefInputPacket,
)
from parallax.platform.agent_execution import AgentStageSpec
from parallax.platform.agent_hashing import text_sha256
from parallax.platform.agent_knowledge import render_agent_instructions

_NEWS_STORY_BRIEF_KNOWLEDGE_REFS = ("market_research_harness",)
_NEWS_STORY_BRIEF_READ_ONLY_TOOL_REFS = ("news.story_current_briefs",)
_STORY_DELTA_INSTRUCTIONS = """
The input is a story-level packet, not a single article packet. Treat representative_item as the lead article,
member_items as the bounded story evidence set, and evidence refs beginning with story:member: as source-backed
story evidence. Produce one current market brief for the whole story.
""".strip()


def news_story_brief_stage_instructions() -> str:
    return render_agent_instructions(
        "\n\n".join([news_item_brief_instructions(), _STORY_DELTA_INSTRUCTIONS]),
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
        output_type=NewsItemBriefPayload,
        prompt_version=packet.prompt_version,
        schema_version=packet.schema_version,
        workflow_name=NEWS_STORY_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_STORY_BRIEF_AGENT_NAME,
        group_id=f"news_story:{packet.story_key}",
        knowledge_refs=_NEWS_STORY_BRIEF_KNOWLEDGE_REFS,
        read_only_tool_refs=_NEWS_STORY_BRIEF_READ_ONLY_TOOL_REFS,
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
    "news_story_brief_prompt_text_hash",
    "news_story_brief_stage_instructions",
]
