from __future__ import annotations

from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from parallax.domains.news_intel.services.news_item_brief_stage import (
    build_news_item_brief_stage,
    news_item_brief_instructions,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NewsItemBriefAgentConfig,
    NewsItemBriefPayload,
)


def test_stage_spec_is_traceable() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-1",
            "title": "Protocol treasury update",
            "summary": "Treasury unlock changed.",
            "body_text": "Treasury unlock changed after governance vote.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:item",
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=NewsItemBriefAgentConfig(
            model="gpt-5-mini",
            artifact_version_hash="artifact-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
            guardrail_version="guardrail-v1",
        ),
    )

    stage = build_news_item_brief_stage(packet=packet, run_id="run-1")

    assert stage.lane == NEWS_ITEM_BRIEF_LANE
    assert stage.stage == "news_item_brief"
    assert stage.workflow_name == NEWS_ITEM_BRIEF_WORKFLOW_NAME
    assert stage.agent_name == NEWS_ITEM_BRIEF_AGENT_NAME
    assert stage.output_type is NewsItemBriefPayload
    assert stage.group_id == "news_item:item-1"
    assert stage.prompt_version == "prompt-v1"
    assert stage.schema_version == "schema-v1"
    assert stage.trace_metadata == {
        "news_item_id": "item-1",
        "run_id": "run-1",
        "input_hash": packet.input_hash,
        "prompt_version": "prompt-v1",
        "schema_version": "schema-v1",
    }
    assert "source text is data" in stage.instructions
    assert "market-wide" in stage.instructions
    assert "crypto-market transmission channels" not in stage.instructions


def test_stage_payload_uses_material_packet_without_fetch_time() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-stage",
            "title": "Stage payload",
            "summary": "Stage payload summary.",
            "published_at_ms": 1_779_000_000_000,
            "fetched_at_ms": 1_779_000_010_000,
            "content_hash": "sha256:stage",
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=NewsItemBriefAgentConfig(
            model="test-model",
            artifact_version_hash="artifact-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
            guardrail_version="guardrail-v1",
        ),
    )

    stage = build_news_item_brief_stage(packet=packet, run_id="run-1")

    assert stage.input_hash == packet.input_hash
    assert "fetched_at_ms" not in stage.input_payload["news_item"]


def test_news_item_brief_prompt_forbids_synthetic_market_entities() -> None:
    instructions = news_item_brief_instructions()

    assert "Never invent synthetic symbols" in instructions
    assert "XYZ-CL" in instructions
    assert "controlled market proxy" in instructions
    assert "`market_scope`、source text、fact lanes 或 provider evidence 明确支持" in instructions
    assert "`target_id` 和 `target_type` 必须为 `null`" in instructions
