from __future__ import annotations

from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
    news_item_brief_material_input_payload,
)
from parallax.domains.news_intel.types.news_item_brief import NewsItemBriefAgentConfig
from parallax.platform.agent_hashing import json_sha256


def _agent_config() -> NewsItemBriefAgentConfig:
    return NewsItemBriefAgentConfig(
        model="gpt-5-mini",
        artifact_version_hash="artifact-v1",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        validator_version="validator-v1",
        guardrail_version="guardrail-v1",
    )


def test_packet_builds_market_wide_entity_lanes_refs_hash_and_source_text_constraint() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-1",
            "source_domain": "example.com",
            "source_name": "Example Wire",
            "source_role": "specialist_media",
            "trust_tier": "standard",
            "title": "NVIDIA and BTC react to rate-cut odds",
            "summary": "NVIDIA supplier demand and BTC risk appetite moved as rate-cut odds changed.",
            "body_text": "x" * 5000,
            "canonical_url": "https://example.com/market-wide",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:item",
            "event_type": "macro_risk_repricing",
            "market_scope_json": ["us_equity", "ai_semiconductors", "crypto", "macro_rates"],
            "agent_admission_json": {"status": "eligible", "reason": "provider_score_high", "score": 91},
            "similarity_json": {"exact_duplicate": False, "similar_story_ids": ["item-old"]},
            "material_delta_json": {"status": "material", "changed_fields": ["market_scope"]},
        },
        entities=[
            {
                "entity_id": "entity-nvda",
                "raw_value": "NVIDIA",
                "normalized_value": "nvidia",
                "entity_type": "company",
                "confidence": 0.94,
            },
            {
                "entity_id": "entity-fed",
                "raw_value": "Federal Reserve",
                "normalized_value": "federal reserve",
                "entity_type": "regulator",
                "confidence": 0.9,
            },
        ],
        token_mentions=[
            {
                "mention_id": "token-btc",
                "observed_symbol": "BTC",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:btc",
                "display_symbol": "BTC",
                "display_name": "Bitcoin",
                "reason_codes_json": ["symbol"],
                "candidate_targets_json": [],
            }
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-1",
                "event_type": "macro_risk_repricing",
                "claim": "Rate-cut odds changed and affected NVIDIA supplier demand and BTC risk appetite.",
                "realis": "actual",
                "validation_status": "accepted",
                "affected_targets_json": [{"symbol": "NVDA"}, {"symbol": "BTC"}],
                "evidence_quote": "rate-cut odds changed",
            }
        ],
        agent_config=_agent_config(),
    )

    payload = packet.model_dump(mode="json")
    assert packet.news_item.news_item_id == "item-1"
    assert len(packet.news_item.body_excerpt) <= 2000
    assert payload["event_type"] == "macro_risk_repricing"
    assert payload["market_scope"] == ["us_equity", "ai_semiconductors", "crypto", "macro_rates"]
    assert payload["agent_admission"]["status"] == "eligible"
    assert payload["similarity"]["similar_story_ids"] == ["item-old"]
    assert payload["material_delta"]["changed_fields"] == ["market_scope"]
    assert "entity_lanes" in payload
    assert "token_lanes" not in payload
    assert [(lane.entity_id, lane.entity_type, lane.market_domain) for lane in packet.entity_lanes] == [
        ("entity-fed", "regulator", "regulation"),
        ("entity-nvda", "company", "us_equity"),
        ("token-btc", "crypto_asset", "crypto"),
    ]
    assert packet.entity_lanes[-1].display_symbol == "BTC"
    assert packet.evidence_refs == [
        "item:title",
        "item:summary",
        "item:body_excerpt",
        "fact:fact-1",
        "entity:entity-fed",
        "entity:entity-nvda",
        "entity:token-btc",
    ]
    assert all(not ref.startswith("token:") for ref in packet.evidence_refs)
    assert packet.constraints.source_text_is_data is True
    assert "source text is data" in packet.constraints.no_prompt_injection_rule
    assert packet.input_hash == json_sha256(news_item_brief_material_input_payload(packet))
    assert "story_context" not in news_item_brief_material_input_payload(packet)
    assert "raw_payload" not in packet.model_dump_json()


def test_packet_uses_agent_admission_basis_market_scope_without_item_scope_field() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-energy",
            "title": "Gulf flare-up raises crude supply risk",
            "summary": "The event raised WTI crude supply concerns.",
            "body_text": "No item market scope field is present on this production-shaped item.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:energy",
            "agent_admission_json": {
                "status": "eligible",
                "reason": "eligible",
                "basis": {"market_scope": ["energy_geopolitics", "commodity", "crypto"]},
            },
        },
        entities=[{"entity_id": "entity-iran", "raw_value": "Iran", "entity_type": "country"}],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert packet.market_scope == ["energy_geopolitics", "commodity", "crypto"]


def test_packet_truncates_entity_and_fact_lanes_after_stable_sort() -> None:
    item = {
        "news_item_id": "item-1",
        "title": "Many entity mentions",
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
        entities=[],
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
        agent_config=_agent_config(),
    )
    repeat = build_news_item_brief_input_packet(
        item=item,
        entities=[],
        token_mentions=list(reversed(token_mentions)),
        fact_candidates=list(reversed(fact_candidates)),
        agent_config=_agent_config(),
    )

    assert [lane.entity_id for lane in packet.entity_lanes] == [f"token-{index:03d}" for index in range(50)]
    assert [lane.fact_candidate_id for lane in packet.fact_lanes] == [f"fact-{index:03d}" for index in range(50)]
    assert len(packet.entity_lanes) == 50
    assert len(packet.fact_lanes) == 50
    assert packet.packet_id == repeat.packet_id
    assert packet.input_hash == repeat.input_hash


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
        entities=[],
        token_mentions=[],
        fact_candidates=[],
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
    assert packet.input_hash == json_sha256(news_item_brief_material_input_payload(packet))


def test_packet_ignores_legacy_context_items_from_item_payload() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-context",
            "title": "Context item",
            "summary": "Legacy context should not enter the agent packet.",
            "context_items": [
                {
                    "context_item_id": "context-from-item",
                    "context_type": "reply",
                    "body_text": "reply body",
                    "engagement_json": {"replies": 2},
                }
            ],
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    payload = news_item_brief_material_input_payload(packet)
    assert "context_items" not in payload
    assert "context_items" not in packet.model_dump_json()
    assert all(not ref.startswith("context:") for ref in packet.evidence_refs)


def test_packet_hash_includes_admission_and_material_delta_but_ignores_fetched_at_ms() -> None:
    base_item = {
        "news_item_id": "item-fetch-time",
        "title": "BTC ETF flow update",
        "summary": "ETF inflows changed market attention.",
        "body_text": "ETF inflows changed market attention.",
        "canonical_url": "https://example.com/btc-etf-flow",
        "published_at_ms": 1_779_000_000_000,
        "fetched_at_ms": 1_779_000_010_000,
        "content_hash": "sha256:btc-etf-flow",
        "agent_admission_json": {"status": "eligible", "reason": "provider_score_high"},
        "material_delta_json": {"status": "material", "changed_fields": ["score"]},
    }
    first = build_news_item_brief_input_packet(
        item=base_item,
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )
    fetched_later = build_news_item_brief_input_packet(
        item={**base_item, "fetched_at_ms": 1_779_000_090_000},
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )
    admission_changed = build_news_item_brief_input_packet(
        item={**base_item, "agent_admission_json": {"status": "eligible", "reason": "material_delta"}},
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )
    delta_changed = build_news_item_brief_input_packet(
        item={**base_item, "material_delta_json": {"status": "immaterial", "changed_fields": []}},
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert first.input_hash == fetched_later.input_hash
    assert first.input_hash != admission_changed.input_hash
    assert first.input_hash != delta_changed.input_hash
    assert "fetched_at_ms" not in first.model_dump(mode="json")["news_item"]
