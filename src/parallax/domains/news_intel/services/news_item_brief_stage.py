from __future__ import annotations

from parallax.domains.news_intel.services.news_item_brief_input import (
    news_item_brief_synthesis_material_payload,
)
from parallax.domains.news_intel.services.news_item_brief_prompt_assembly import (
    build_news_item_brief_synthesizer_prompt,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    NewsItemBriefPayload,
    NewsItemBriefSynthesisPacket,
)
from parallax.platform.agent_execution import AgentStageSpec
from parallax.platform.agent_hashing import json_sha256


def news_item_brief_instructions() -> str:
    return build_news_item_brief_synthesizer_prompt()


def build_news_item_brief_stage(*, packet: NewsItemBriefSynthesisPacket, run_id: str) -> AgentStageSpec:
    news_item_id = packet.base_packet.news_item.news_item_id
    input_payload = news_item_brief_synthesis_material_payload(packet)
    research_packet_hash = input_payload["research_packet"]["research_packet_hash"]
    synthesis_input_hash = json_sha256(input_payload)
    return AgentStageSpec(
        lane=NEWS_ITEM_BRIEF_LANE,
        stage="news_item_brief_synthesis",
        instructions=news_item_brief_instructions(),
        input_payload=input_payload,
        output_type=NewsItemBriefPayload,
        prompt_version=packet.prompt_version,
        schema_version=packet.schema_version,
        workflow_name=NEWS_ITEM_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_ITEM_BRIEF_AGENT_NAME,
        group_id=f"news_item:{news_item_id}",
        trace_metadata={
            "phase": "synthesis",
            "news_item_id": news_item_id,
            "run_id": str(run_id),
            "base_input_hash": packet.base_packet.input_hash or json_sha256(input_payload["base_packet"]),
            "research_packet_hash": research_packet_hash,
            "tool_catalog_version": NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
            "synthesis_input_hash": synthesis_input_hash,
            "prompt_version": packet.prompt_version,
            "schema_version": packet.schema_version,
        },
    )


__all__ = ["build_news_item_brief_stage", "news_item_brief_instructions"]
