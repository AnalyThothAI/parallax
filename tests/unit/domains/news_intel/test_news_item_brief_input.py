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


def test_packet_includes_bounded_context_items_and_evidence_refs() -> None:
    context_items = [
        {
            "context_item_id": f"context-{index:02d}",
            "context_type": "comment",
            "author": f"author-{index}",
            "canonical_url": f"https://example.com/context/{index}",
            "body_text": "c" * 800,
            "published_at_ms": 1_779_000_000_000 + index,
            "engagement_json": {"likes": index, "empty": None},
        }
        for index in range(10)
    ]

    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-context",
            "title": "Context item",
            "summary": "Context summary",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:context-item",
        },
        story=None,
        token_mentions=[],
        fact_candidates=[],
        story_members=[],
        context_items=context_items,
        agent_config=_agent_config(),
    )

    assert [row.context_item_id for row in packet.context_items] == [
        f"context-{index:02d}" for index in range(9, 1, -1)
    ]
    assert all(len(row.body_excerpt) == 500 for row in packet.context_items)
    assert packet.context_items[0].engagement == {"likes": 9}
    assert "context:context-09" in packet.evidence_refs
    assert "context:context-01" not in packet.evidence_refs
    assert packet.input_hash == json_sha256(packet.model_dump(mode="json", exclude={"input_hash"}))


def test_packet_includes_bounded_provider_signal_evidence() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-provider-signal",
            "title": "BTC provider signal",
            "summary": "Provider supplied AI rating and token impacts.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:provider-signal",
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "signal": "long",
                "score": 91,
                "grade": "A",
                "summary_zh": "z" * 900,
                "summary_en": "e" * 900,
                "method": "opennews.aiRating",
            },
            "provider_token_impacts_json": [
                {"symbol": f"T{index:02d}", "score": 100 - index, "signal": "long", "grade": "A"} for index in range(20)
            ],
            "duplicate_count": 17,
            "source_ids_json": [f"source-{index:02d}" for index in range(20)],
            "source_domains_json": [f"source-{index:02d}.example" for index in range(20)],
            "provider_article_keys_json": [f"opennews:{index:02d}" for index in range(20)],
        },
        story=None,
        token_mentions=[],
        fact_candidates=[],
        story_members=[],
        agent_config=_agent_config(),
    )

    evidence = packet.provider_signal_evidence
    assert evidence is not None
    assert evidence.score == 91
    assert evidence.direction == "bullish"
    assert evidence.grade == "A"
    assert len(evidence.summary_zh) == 600
    assert len(evidence.summary_en) == 600
    assert [impact.symbol for impact in evidence.token_impacts] == [f"T{index:02d}" for index in range(12)]
    assert len(evidence.source_ids) == 12
    assert len(evidence.source_domains) == 12
    assert len(evidence.provider_article_keys) == 12
    assert evidence.duplicate_count == 17
    assert "provider:signal" in packet.evidence_refs
    assert "provider:token:T00" in packet.evidence_refs
    assert "provider:token:T12" not in packet.evidence_refs
    assert packet.input_hash == json_sha256(packet.model_dump(mode="json", exclude={"input_hash"}))


def test_packet_context_items_are_deterministic_for_reversed_input() -> None:
    context_items = [
        {
            "context_item_id": f"context-{index:02d}",
            "context_type": "comment",
            "body_text": f"Context body {index}",
            "published_at_ms": 1_779_000_000_000 + index,
        }
        for index in range(10)
    ]
    payload = {
        "item": {
            "news_item_id": "item-context",
            "title": "Context item",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:context-item",
        },
        "story": None,
        "token_mentions": [],
        "fact_candidates": [],
        "story_members": [],
        "agent_config": _agent_config(),
    }

    packet = build_news_item_brief_input_packet(**payload, context_items=context_items)
    repeat = build_news_item_brief_input_packet(**payload, context_items=list(reversed(context_items)))

    assert [row.context_item_id for row in packet.context_items] == [
        f"context-{index:02d}" for index in range(9, 1, -1)
    ]
    assert [row.context_item_id for row in repeat.context_items] == [
        row.context_item_id for row in packet.context_items
    ]
    assert packet.packet_id == repeat.packet_id
    assert packet.input_hash == repeat.input_hash


def test_packet_can_read_context_items_from_item_payload_for_existing_call_sites() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-context",
            "title": "Context item",
            "context_items": [
                {
                    "context_item_id": "context-from-item",
                    "context_type": "reply",
                    "body_text": "reply body",
                    "engagement_json": {"replies": 2},
                }
            ],
        },
        story=None,
        token_mentions=[],
        fact_candidates=[],
        story_members=[],
        agent_config=_agent_config(),
    )

    assert packet.context_items[0].context_item_id == "context-from-item"
    assert packet.context_items[0].context_type == "reply"
    assert "context:context-from-item" in packet.evidence_refs
