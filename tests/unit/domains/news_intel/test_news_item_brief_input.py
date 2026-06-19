from __future__ import annotations

import pytest

from parallax.domains.news_intel.services.news_item_brief_input import (
    BODY_EXCERPT_MAX_CHARS,
    MAX_ENTITY_LANES,
    MAX_FACT_LANES,
    build_news_item_brief_input_packet,
    news_item_brief_material_input_payload,
)
from parallax.domains.news_intel.services.news_market_scope import classify_news_market_scope
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
            "agent_admission_json": {"status": "eligible", "reason": "ready_market_driver", "score": 91},
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
    assert BODY_EXCERPT_MAX_CHARS == 1200
    assert MAX_ENTITY_LANES == 24
    assert MAX_FACT_LANES == 20
    assert len(packet.news_item.body_excerpt) <= BODY_EXCERPT_MAX_CHARS
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


def test_packet_does_not_restore_market_scope_from_agent_admission_basis() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-energy",
            "title": "Gulf flare-up raises crude supply risk",
            "summary": "The event raised WTI crude supply concerns.",
            "body_text": "No item market scope field is present on this malformed item.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:energy",
            "agent_admission_json": {
                "status": "eligible",
                "reason": "eligible",
                "basis": {"market_scope": ["energy_geopolitics", "commodity", "crypto"]},
            },
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert packet.market_scope == []


def test_packet_does_not_restore_similarity_or_material_delta_from_agent_admission_basis() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-basis-context",
            "title": "Basis context should not repair packet fields",
            "summary": "Admission basis is audit context, not packet context fallback.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:basis-context",
            "agent_admission_json": {
                "status": "eligible_refresh",
                "reason": "material_delta",
                "similarity": {"similar_story": True, "representative_news_item_id": "item-old"},
                "material_delta": {"has_delta": True, "reasons": ["new_source"]},
                "basis": {
                    "market_scope": ["crypto"],
                },
            },
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert packet.similarity == {}
    assert packet.material_delta == {}


def test_packet_does_not_restore_context_from_legacy_item_aliases() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-alias-context",
            "title": "Alias context should not repair packet fields",
            "summary": "Only explicit *_json packet fields are accepted.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:alias-context",
            "market_scope": ["crypto"],
            "agent_admission": {"status": "eligible", "reason": "alias"},
            "similarity": {"similar_story": True},
            "material_delta": {"has_delta": True},
        },
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert packet.market_scope == []
    assert packet.agent_admission == {}
    assert packet.similarity == {}
    assert packet.material_delta == {}


@pytest.mark.parametrize(
    ("formal_key", "error"),
    [
        pytest.param("agent_admission_json", "news_item_brief_agent_admission_json_required", id="admission"),
        pytest.param("similarity_json", "news_item_brief_similarity_json_required", id="similarity"),
        pytest.param("material_delta_json", "news_item_brief_material_delta_json_required", id="material_delta"),
    ],
)
@pytest.mark.parametrize("bad_value", [["not", "object"], "not-json", '{"status": "eligible"}'])
def test_packet_rejects_malformed_present_context_objects(formal_key: str, error: str, bad_value: object) -> None:
    item = {
        "news_item_id": "item-bad-context",
        "title": "Malformed context should fail closed",
        "summary": "Formal context fields must be objects when present.",
        "published_at_ms": 1_779_000_000_000,
        "content_hash": "sha256:bad-context",
        formal_key: bad_value,
    }

    with pytest.raises(ValueError, match=error):
        build_news_item_brief_input_packet(
            item=item,
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


@pytest.mark.parametrize("bad_value", ['["crypto"]', "crypto", {"scope": ["crypto"]}])
def test_packet_rejects_malformed_present_market_scope_json(bad_value: object) -> None:
    with pytest.raises(ValueError, match="news_item_brief_market_scope_json_required"):
        build_news_item_brief_input_packet(
            item={
                "news_item_id": "item-bad-market-scope",
                "title": "Malformed market scope should fail closed",
                "summary": "Formal market scope must be an array when present.",
                "published_at_ms": 1_779_000_000_000,
                "content_hash": "sha256:bad-market-scope",
                "market_scope_json": bad_value,
            },
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


@pytest.mark.parametrize(
    ("lane_kind", "field_name", "bad_value", "error"),
    [
        pytest.param(
            "entity",
            "candidate_targets_json",
            {"target_id": "asset:bad"},
            "news_item_brief_entity_candidate_targets_json_required",
            id="entity_candidate_targets_object",
        ),
        pytest.param(
            "token",
            "candidate_targets_json",
            {"target_id": "asset:bad"},
            "news_item_brief_token_candidate_targets_json_required",
            id="token_candidate_targets_object",
        ),
        pytest.param(
            "token",
            "candidate_targets_json",
            ["not-a-target-object"],
            "news_item_brief_token_candidate_targets_json_required",
            id="token_candidate_targets_scalar_member",
        ),
        pytest.param(
            "fact",
            "affected_targets_json",
            {"symbol": "BTC"},
            "news_item_brief_fact_affected_targets_json_required",
            id="fact_affected_targets_object",
        ),
        pytest.param(
            "fact",
            "rejection_reasons_json",
            "target_identity_not_production_eligible",
            "news_item_brief_fact_rejection_reasons_json_required",
            id="fact_rejection_reasons_string",
        ),
    ],
)
def test_packet_rejects_malformed_present_lane_arrays(
    lane_kind: str,
    field_name: str,
    bad_value: object,
    error: str,
) -> None:
    item = {
        "news_item_id": "item-bad-lane",
        "title": "Malformed lane arrays should fail closed",
        "summary": "Present lane arrays must keep their projected shape.",
        "published_at_ms": 1_779_000_000_000,
        "content_hash": "sha256:bad-lane",
    }
    entities = [
        {
            "entity_id": "entity-foo",
            "raw_value": "FOO",
            "entity_type": "crypto_asset",
            "candidate_targets_json": [],
        }
    ]
    token_mentions = [
        {
            "mention_id": "token-foo",
            "observed_symbol": "FOO",
            "resolution_status": "known_symbol",
            "target_type": "asset",
            "target_id": "asset:foo",
            "candidate_targets_json": [],
        }
    ]
    fact_candidates = [
        {
            "fact_candidate_id": "fact-foo",
            "event_type": "listing",
            "claim": "FOO was listed.",
            "realis": "actual",
            "validation_status": "accepted",
            "affected_targets_json": [],
            "rejection_reasons_json": [],
        }
    ]
    if lane_kind == "entity":
        entities[0][field_name] = bad_value
    elif lane_kind == "token":
        token_mentions[0][field_name] = bad_value
    else:
        fact_candidates[0][field_name] = bad_value

    with pytest.raises(ValueError, match=error):
        build_news_item_brief_input_packet(
            item=item,
            entities=entities,
            token_mentions=token_mentions,
            fact_candidates=fact_candidates,
            agent_config=_agent_config(),
        )


def test_packet_ignores_provider_token_impacts_for_agent_scope_refs_and_hash() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-energy-btc",
            "title": "Gulf flare-up raises crude supply risk",
            "summary": "The event raised WTI crude supply concerns.",
            "body_text": "The formal item market scope field drives packet scope.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:energy-btc",
            "market_scope_json": ["energy_geopolitics", "commodity"],
            "agent_admission_json": {
                "status": "eligible",
                "reason": "eligible",
                "basis": {"market_scope": ["energy_geopolitics", "commodity"]},
            },
            "provider_signal_json": {"source": "provider", "provider": "opennews", "status": "ready"},
            "provider_token_impacts_json": [
                {"symbol": "BTC", "market_type": "cex", "score": 40, "signal": "proxy", "grade": "C"}
            ],
        },
        entities=[{"entity_id": "entity-wti", "raw_value": "WTI crude futures", "entity_type": "commodity"}],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    payload = news_item_brief_material_input_payload(packet)
    assert not hasattr(packet, "provider_signal_evidence")
    assert "provider_signal_evidence" not in packet.model_dump(mode="json")
    assert all(not ref.startswith("provider:") for ref in packet.evidence_refs)
    assert packet.market_scope == ["energy_geopolitics", "commodity"]

    without_provider = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-energy-btc",
            "title": "Gulf flare-up raises crude supply risk",
            "summary": "The event raised WTI crude supply concerns.",
            "body_text": "The formal item market scope field drives packet scope.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:energy-btc",
            "market_scope_json": ["energy_geopolitics", "commodity"],
            "agent_admission_json": {
                "status": "eligible",
                "reason": "eligible",
                "basis": {"market_scope": ["energy_geopolitics", "commodity"]},
            },
        },
        entities=[{"entity_id": "entity-wti", "raw_value": "WTI crude futures", "entity_type": "commodity"}],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )
    assert packet.input_hash == without_provider.input_hash
    assert "provider_signal_json" not in payload
    assert "provider_token_impacts_json" not in payload


def test_packet_maps_non_crypto_market_instrument_token_mention_to_equity_lane() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-asml",
            "title": "Musk will attend ASML $ASML employee conference",
            "summary": "",
            "body_text": "ASML considers the Terafab project a serious endeavor.",
            "published_at_ms": 1_779_000_000_000,
            "content_hash": "sha256:asml",
            "agent_admission_json": {"status": "eligible", "reason": "eligible"},
        },
        entities=[],
        token_mentions=[
            {
                "mention_id": "mention-asml",
                "observed_symbol": "ASML",
                "resolution_status": "non_crypto",
                "target_type": "MarketInstrument",
                "target_id": "market_instrument:us_equity:ASML",
                "display_symbol": "ASML",
                "candidate_targets_json": [
                    {"target_type": "MarketInstrument", "target_id": "market_instrument:us_equity:ASML"}
                ],
            }
        ],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert packet.entity_lanes[0].entity_type == "equity"
    assert packet.entity_lanes[0].market_domain == "us_equity"
    assert packet.market_scope == ["us_equity"]


def test_scope_inference_marks_wti_crude_text_as_commodity() -> None:
    scope = classify_news_market_scope(
        item={
            "title": "WTI crude rises as Gulf oil supply risk grows",
            "summary": "Crude and oil shipping risk lifted futures volatility.",
        },
        token_mentions=[],
        fact_candidates=[],
    )

    assert "energy_geopolitics" in scope.scope
    assert "commodities" in scope.scope
    assert "text:commodities" in scope.basis["scope_evidence"]["commodities"]


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

    assert [lane.entity_id for lane in packet.entity_lanes] == [
        f"token-{index:03d}" for index in range(MAX_ENTITY_LANES)
    ]
    assert [lane.fact_candidate_id for lane in packet.fact_lanes] == [
        f"fact-{index:03d}" for index in range(MAX_FACT_LANES)
    ]
    assert len(packet.entity_lanes) == MAX_ENTITY_LANES
    assert len(packet.fact_lanes) == MAX_FACT_LANES
    assert packet.packet_id == repeat.packet_id
    assert packet.input_hash == repeat.input_hash


def test_packet_omits_provider_signal_context_from_agent_input() -> None:
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

    payload = news_item_brief_material_input_payload(packet)
    assert not hasattr(packet, "provider_signal_evidence")
    assert "provider_signal_evidence" not in packet.model_dump(mode="json")
    assert all(not ref.startswith("provider:") for ref in packet.evidence_refs)
    assert packet.market_scope == []
    assert packet.input_hash == json_sha256(payload)


def test_packet_ignores_legacy_context_items_from_item_payload() -> None:
    packet = build_news_item_brief_input_packet(
        item={
            "news_item_id": "item-context",
            "title": "Context item",
            "summary": "Legacy context should not enter the agent packet.",
            "published_at_ms": 1_779_000_000_000,
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
        "agent_admission_json": {"status": "eligible", "reason": "ready_market_driver"},
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


@pytest.mark.parametrize(
    "published_at_ms",
    [
        pytest.param(None, id="missing"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("1779000000000", id="string"),
    ],
)
def test_item_packet_requires_explicit_positive_published_at_ms(published_at_ms: object) -> None:
    with pytest.raises(ValueError, match="news_item_brief_published_at_ms_required"):
        build_news_item_brief_input_packet(
            item={
                "news_item_id": "item-bad-time",
                "title": "BTC ETF flow update",
                "summary": "ETF inflows changed market attention.",
                "body_text": "ETF inflows changed market attention.",
                "canonical_url": "https://example.com/btc-etf-flow",
                "published_at_ms": published_at_ms,
                "content_hash": "sha256:btc-etf-flow",
                "agent_admission_json": {"status": "eligible", "reason": "ready_market_driver"},
                "material_delta_json": {"status": "material", "changed_fields": ["score"]},
            },
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


@pytest.mark.parametrize(
    "resolution_status",
    [
        pytest.param(None, id="missing"),
        pytest.param("", id="blank"),
        pytest.param(123, id="non_string"),
    ],
)
def test_item_packet_requires_token_resolution_status(resolution_status: object) -> None:
    with pytest.raises(ValueError, match="news_item_brief_token_resolution_status_required"):
        build_news_item_brief_input_packet(
            item={
                "news_item_id": "item-token-status",
                "title": "BTC ETF flow update",
                "summary": "ETF inflows changed market attention.",
                "body_text": "ETF inflows changed market attention.",
                "canonical_url": "https://example.com/btc-etf-flow",
                "published_at_ms": 1_779_000_000_000,
                "content_hash": "sha256:btc-etf-flow",
                "agent_admission_json": {"status": "eligible", "reason": "ready_market_driver"},
                "material_delta_json": {"status": "material", "changed_fields": ["score"]},
            },
            entities=[],
            token_mentions=[
                {
                    "mention_id": "token-btc",
                    "observed_symbol": "BTC",
                    "resolution_status": resolution_status,
                    "target_type": "asset",
                    "target_id": "asset:btc",
                    "candidate_targets_json": [],
                }
            ],
            fact_candidates=[],
            agent_config=_agent_config(),
        )
