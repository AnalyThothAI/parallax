from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from parallax.domains.news_intel.services.news_item_brief_input import (
    news_item_brief_material_input_payload,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NewsItemBriefInputPacket,
    NewsItemBriefPayload,
)
from parallax.platform.agent_execution import AgentStageSpec
from parallax.platform.agent_hashing import text_sha256
from parallax.platform.agent_knowledge import render_agent_instructions

_NEWS_ITEM_BRIEF_KNOWLEDGE_REFS = ("market_research_harness",)
_NEWS_ITEM_BRIEF_READ_ONLY_TOOL_REFS = ("news.current_briefs",)


@lru_cache(maxsize=1)
def news_item_brief_instructions() -> str:
    return (Path(__file__).resolve().parents[1] / "prompts" / "news_item_brief.md").read_text(encoding="utf-8")


def news_item_brief_stage_instructions() -> str:
    return render_agent_instructions(
        news_item_brief_instructions(),
        knowledge_refs=_NEWS_ITEM_BRIEF_KNOWLEDGE_REFS,
    )


def news_item_brief_prompt_text_hash() -> str:
    return text_sha256(news_item_brief_stage_instructions())


def build_news_item_brief_stage(*, packet: NewsItemBriefInputPacket, run_id: str) -> AgentStageSpec:
    news_item_id = packet.news_item.news_item_id
    return AgentStageSpec(
        lane=NEWS_ITEM_BRIEF_LANE,
        stage="news_item_brief",
        instructions=news_item_brief_stage_instructions(),
        input_payload=news_item_brief_material_input_payload(packet),
        output_type=NewsItemBriefPayload,
        prompt_version=packet.prompt_version,
        schema_version=packet.schema_version,
        workflow_name=NEWS_ITEM_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_ITEM_BRIEF_AGENT_NAME,
        group_id=f"news_item:{news_item_id}",
        knowledge_refs=_NEWS_ITEM_BRIEF_KNOWLEDGE_REFS,
        read_only_tool_refs=_NEWS_ITEM_BRIEF_READ_ONLY_TOOL_REFS,
        trace_metadata={
            "news_item_id": news_item_id,
            "run_id": str(run_id),
            "input_hash": packet.input_hash,
            "prompt_version": packet.prompt_version,
            "schema_version": packet.schema_version,
        },
    )


__all__ = [
    "build_news_item_brief_stage",
    "news_item_brief_instructions",
    "news_item_brief_prompt_text_hash",
    "news_item_brief_stage_instructions",
]
