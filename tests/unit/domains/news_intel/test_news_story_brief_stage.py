from __future__ import annotations

from parallax.domains.news_intel.services.news_story_brief_input import build_news_story_brief_input_packet
from parallax.domains.news_intel.services.news_story_brief_stage import build_news_story_brief_stage
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_AGENT_NAME,
    NEWS_STORY_BRIEF_LANE,
    NEWS_STORY_BRIEF_WORKFLOW_NAME,
    NewsStoryBriefAgentConfig,
    NewsStoryBriefPayload,
)


def test_story_stage_is_traceable() -> None:
    representative = {
        "news_item_id": "news-1",
        "title": "Bitcoin ETF flow update",
        "summary": "ETF flow update moved the market.",
        "published_at_ms": 1_779_000_000_000,
        "content_hash": "sha256:item",
    }
    packet = build_news_story_brief_input_packet(
        story={
            "story_key": "news-story:event:btc-etf:t412000",
            "story_identity_version": "news_story_identity_v2",
            "story_identity_json": {"story_key": "news-story:event:btc-etf:t412000"},
            "market_scope_json": {"scope": ["crypto"], "primary": "crypto"},
            "agent_admission_json": {
                "status": "eligible",
                "reason": "eligible",
                "basis": {"market_scope": ["crypto"]},
            },
        },
        representative_item=representative,
        member_items=[representative],
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=NewsStoryBriefAgentConfig(
            model="gpt-5-mini",
            artifact_version_hash="artifact-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
            guardrail_version="guardrail-v1",
        ),
    )

    stage = build_news_story_brief_stage(packet=packet, run_id="run-1")

    assert stage.lane == NEWS_STORY_BRIEF_LANE
    assert stage.stage == "news_story_brief"
    assert stage.workflow_name == NEWS_STORY_BRIEF_WORKFLOW_NAME
    assert stage.agent_name == NEWS_STORY_BRIEF_AGENT_NAME
    assert stage.output_type is NewsStoryBriefPayload
    assert stage.group_id == "news_story:news-story:event:btc-etf:t412000"
    assert stage.trace_metadata["story_key"] == "news-story:event:btc-etf:t412000"
    assert stage.trace_metadata["run_id"] == "run-1"
