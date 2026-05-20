from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import NewsItemBriefAgentConfig
from gmgn_twitter_intel.platform.agent_hashing import json_sha256


def _agent_config() -> NewsItemBriefAgentConfig:
    return NewsItemBriefAgentConfig(
        model="gpt-5-mini",
        artifact_version_hash="artifact-v1",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        validator_version="validator-v1",
        guardrail_version="guardrail-v1",
    )


def test_packet_builds_bounded_evidence_refs_hash_and_source_text_constraint() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-1",
            "source_domain": "example.com",
            "source_name": "Example Wire",
            "source_role": "specialist_media",
            "trust_tier": "standard",
            "title": "Binance adds SOL collateral support",
            "summary": "SOL collateral support is being expanded.",
            "body_text": "x" * 5000,
            "canonical_url": "https://example.com/sol",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:item",
        },
        story={
            "story_id": "story-1",
            "item_count": 2,
            "source_count": 2,
            "representative_title": "SOL collateral support expands",
        },
        token_mentions=[
            {
                "mention_id": "token-1",
                "observed_symbol": "SOL",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:sol",
                "display_symbol": "SOL",
                "display_name": "Solana",
                "reason_codes_json": ["cashtag"],
                "candidate_targets_json": [],
            }
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-1",
                "event_type": "listing",
                "claim": "Binance added SOL collateral support.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [{"symbol": "SOL"}],
                "evidence_quote": "adds SOL collateral support",
            }
        ],
        story_members=[
            {
                "news_item_id": "item-2",
                "source_domain": "other.example",
                "title": "Second source confirms SOL collateral update",
                "published_at_ms": 1_779_000_001_000,
            }
        ],
        agent_config=_agent_config(),
    )

    assert packet.news_item.news_item_id == "item-1"
    assert len(packet.news_item.body_excerpt) <= 2000
    assert packet.evidence_refs == [
        "item:title",
        "item:summary",
        "item:body_excerpt",
        "fact:fact-1",
        "token:token-1",
        "story:item-2",
    ]
    assert packet.constraints.source_text_is_data is True
    assert "source text is data" in packet.constraints.no_prompt_injection_rule
    assert packet.input_hash == json_sha256(packet.model_dump(mode="json", exclude={"input_hash"}))
    assert "raw_payload" not in packet.model_dump_json()


def test_packet_truncates_token_and_fact_lanes_after_stable_sort() -> None:
    item = {
        "news_item_id": "item-1",
        "title": "Many token mentions",
        "summary": "Synthetic item with many mentions and facts.",
        "published_at_ms": 1_779_000_000_000,
        "content_hash": "sha256:item",
    }
    token_mentions = [
        {
            "mention_id": f"token-{index:03d}",
            "observed_symbol": f"T{index:03d}",
            "resolution_status": "known_symbol",
        }
        for index in range(59, -1, -1)
    ]
    fact_candidates = [
        {
            "fact_candidate_id": f"fact-{index:03d}",
            "event_type": "listing",
            "claim": f"Fact {index:03d}",
            "realis": "actual",
            "validation_status": "accepted",
        }
        for index in range(59, -1, -1)
    ]

    packet = build_news_item_brief_input_packet(
        item=item,
        story=None,
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
        story_members=[],
        agent_config=_agent_config(),
    )
    repeat = build_news_item_brief_input_packet(
        item=item,
        story=None,
        token_mentions=list(reversed(token_mentions)),
        fact_candidates=list(reversed(fact_candidates)),
        story_members=[],
        agent_config=_agent_config(),
    )

    assert [lane.mention_id for lane in packet.token_lanes] == [f"token-{index:03d}" for index in range(50)]
    assert [lane.fact_candidate_id for lane in packet.fact_lanes] == [f"fact-{index:03d}" for index in range(50)]
    assert len(packet.token_lanes) == 50
    assert len(packet.fact_lanes) == 50
    assert packet.packet_id == repeat.packet_id
    assert packet.input_hash == repeat.input_hash
