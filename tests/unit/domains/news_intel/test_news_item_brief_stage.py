from __future__ import annotations

from parallax.domains.news_intel.services.news_item_brief_prompt_assembly import (
    build_news_item_brief_synthesizer_prompt,
)
from parallax.domains.news_intel.services.news_item_brief_stage import (
    build_news_item_brief_stage,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    NewsItemBriefBasePacket,
    NewsItemBriefBudgetReport,
    NewsItemBriefNewsItem,
    NewsItemBriefPayload,
    NewsItemBriefSynthesisPacket,
    NewsItemResearchBudget,
    NewsItemResearchPlan,
    NewsItemResearchToolCall,
    NewsResearchToolResult,
    news_item_brief_base_material_identity,
    news_research_tool_material_identity,
)
from parallax.platform.agent_hashing import json_sha256


def test_stage_spec_uses_synthesis_packet_and_builder_prompt() -> None:
    packet = _synthesis_packet()

    stage = build_news_item_brief_stage(packet=packet, run_id="run-1")

    assert stage.lane == NEWS_ITEM_BRIEF_LANE
    assert stage.stage == "news_item_brief_synthesis"
    assert stage.workflow_name == NEWS_ITEM_BRIEF_WORKFLOW_NAME
    assert stage.agent_name == NEWS_ITEM_BRIEF_AGENT_NAME
    assert stage.output_type is NewsItemBriefPayload
    assert stage.group_id == "news_item:item-1"
    assert stage.prompt_version == NEWS_ITEM_BRIEF_PROMPT_VERSION
    assert stage.schema_version == NEWS_ITEM_BRIEF_SCHEMA_VERSION
    assert stage.instructions == build_news_item_brief_synthesizer_prompt()
    research_material = {
        "research_plan": packet.research_plan.model_dump(mode="json"),
        "tool_results": [news_research_tool_material_identity(result) for result in packet.tool_results],
        "tool_catalog_version": NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
    }
    expected_research_packet_hash = json_sha256(research_material)
    expected_synthesis_input_hash = json_sha256(stage.input_payload)
    assert stage.trace_metadata == {
        "phase": "synthesis",
        "news_item_id": "item-1",
        "run_id": "run-1",
        "base_input_hash": packet.base_packet.input_hash,
        "research_packet_hash": expected_research_packet_hash,
        "tool_catalog_version": NEWS_ITEM_RESEARCH_TOOL_CATALOG_VERSION,
        "synthesis_input_hash": expected_synthesis_input_hash,
        "prompt_version": NEWS_ITEM_BRIEF_PROMPT_VERSION,
        "schema_version": NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    }


def test_stage_payload_uses_material_synthesis_packet_without_runtime_fields() -> None:
    packet = _synthesis_packet(input_hash="")

    stage = build_news_item_brief_stage(packet=packet, run_id="run-1")

    assert set(stage.input_payload) == {"base_packet", "research_packet"}
    assert stage.input_payload["base_packet"] == news_item_brief_base_material_identity(packet.base_packet)
    assert "input_hash" not in stage.input_payload["base_packet"]
    tool_result_payload = stage.input_payload["research_packet"]["tool_results"][0]
    assert tool_result_payload == news_research_tool_material_identity(packet.tool_results[0])
    assert "generated_at_ms" not in tool_result_payload
    assert "latency_ms" not in tool_result_payload
    assert "result_hash" not in tool_result_payload
    assert stage.input_payload["research_packet"]["research_packet_hash"].startswith("sha256:")
    assert stage.trace_metadata["synthesis_input_hash"] == stage.input_hash


def _synthesis_packet(*, input_hash: str = "") -> NewsItemBriefSynthesisPacket:
    base_packet = NewsItemBriefBasePacket(
        packet_id="base-packet-1",
        news_item=NewsItemBriefNewsItem(
            news_item_id="item-1",
            title="Protocol treasury update",
            summary="Treasury unlock changed.",
            body_excerpt="Treasury unlock changed after governance vote.",
            published_at_ms=1_779_000_000_000,
            content_hash="sha256:item",
        ),
        base_budget_report=NewsItemBriefBudgetReport(
            material_budget_chars=12_000,
            material_chars=2400,
            original_token_count=2,
            kept_token_count=1,
            original_fact_count=0,
            kept_fact_count=0,
        ),
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        input_hash="sha256:base",
    )
    return NewsItemBriefSynthesisPacket(
        packet_id="synthesis-packet-1",
        base_packet=base_packet,
        research_plan=NewsItemResearchPlan(
            status="ready",
            tool_calls=[
                NewsItemResearchToolCall(
                    tool_call_id="call-1",
                    tool_name="search_news_archive",
                    input={"query": "treasury unlock"},
                    purpose_zh="补充同类事件上下文",
                )
            ],
            budget=NewsItemResearchBudget(max_tool_calls=1, max_total_chars=2000),
            policy_notes_zh="需要同类事件上下文。",
        ),
        tool_results=[
            NewsResearchToolResult(
                tool_call_id="call-1",
                tool_name="search_news_archive",
                status="ok",
                schema_version="news_research_tool_result_v1",
                query_version="search_news_archive_v1",
                source_tables=["news_items"],
                input={"query": "treasury unlock"},
                rows=[{"news_item_id": "item-0", "title": "Earlier treasury unlock"}],
                row_count=1,
                result_hash="sha256:runtime-only",
                generated_at_ms=1_779_000_010_000,
                latency_ms=123,
                evidence_refs=["archive:item-0"],
            )
        ],
        input_hash=input_hash,
    )
