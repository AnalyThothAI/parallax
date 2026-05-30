from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from gmgn_twitter_intel.domains.news_intel.services.news_item_brief_runtime import (
    build_news_item_brief_stage,
)
from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import (
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
        story=None,
        token_mentions=[],
        fact_candidates=[],
        story_members=[],
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
        story=None,
        token_mentions=[],
        fact_candidates=[],
        story_members=[],
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
