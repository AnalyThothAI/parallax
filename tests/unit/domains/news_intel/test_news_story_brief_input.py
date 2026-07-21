from __future__ import annotations

import pytest

from parallax.domains.news_intel.services.news_story_brief_input import (
    build_news_story_brief_input_packet,
    news_story_brief_material_input_payload,
)
from parallax.domains.news_intel.types.news_story_brief import (
    NewsStoryBriefAgentConfig,
    story_brief_key_for,
)
from parallax.platform.agent_hashing import json_sha256, text_sha256


def _agent_config() -> NewsStoryBriefAgentConfig:
    return NewsStoryBriefAgentConfig(
        model="gpt-5-mini",
        artifact_version_hash="artifact-v1",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        validator_version="validator-v1",
        guardrail_version="guardrail-v1",
    )


def _story(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "story_key": "listing:binance:foo:2026-06-18",
        "story_identity_version": "news_story_identity_v2",
        "story_identity_json": {"basis": "exchange_listing", "venue": "binance"},
        "market_scope_json": {"scope": ["crypto"], "primary": "crypto"},
        "agent_admission_json": {"status": "eligible", "reason": "material_delta"},
        "material_delta_json": {"status": "material", "changed_fields": ["source_role"]},
        "similarity_json": {"exact_duplicate": False},
        "row_id": "news_page_rows_v5:listing:binance:foo:2026-06-18",
        "projection_version": "news_page_rows_v5",
        "computed_at_ms": 1_779_000_099_999,
    }
    payload.update(overrides)
    return payload


def _item(news_item_id: str, title: str, *, published_at_ms: int) -> dict[str, object]:
    return {
        "news_item_id": news_item_id,
        "source_domain": "example.com",
        "source_name": "Example Wire",
        "source_role": "official_exchange",
        "trust_tier": "high",
        "title": title,
        "summary": f"Summary for {title}",
        "body_text": f"Body for {title}",
        "canonical_url": f"https://example.com/{news_item_id}",
        "published_at_ms": published_at_ms,
        "content_hash": f"sha256:{news_item_id}",
        "event_type": "exchange_listing",
        "market_scope_json": ["crypto"],
    }


def test_story_packet_hash_stable_for_equivalent_member_order() -> None:
    story = _story()
    representative = _item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)
    member = _item("news-2", "FOO listing confirmed", published_at_ms=1_779_000_010_000)

    first = build_news_story_brief_input_packet(
        story=story,
        representative_item=representative,
        member_items=[representative, member],
        entities=[{"entity_id": "entity-foo", "raw_value": "FOO", "entity_type": "crypto_asset"}],
        token_mentions=[
            {
                "mention_id": "mention-foo",
                "observed_symbol": "FOO",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:foo",
            }
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-listing",
                "event_type": "exchange_listing",
                "claim": "Binance will list FOO.",
                "realis": "actual",
                "validation_status": "accepted",
            }
        ],
        agent_config=_agent_config(),
    )
    reordered = build_news_story_brief_input_packet(
        story=story,
        representative_item=representative,
        member_items=[member, representative],
        entities=[{"entity_id": "entity-foo", "raw_value": "FOO", "entity_type": "crypto_asset"}],
        token_mentions=[
            {
                "mention_id": "mention-foo",
                "observed_symbol": "FOO",
                "resolution_status": "known_symbol",
                "target_type": "asset",
                "target_id": "asset:foo",
            }
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-listing",
                "event_type": "exchange_listing",
                "claim": "Binance will list FOO.",
                "realis": "actual",
                "validation_status": "accepted",
            }
        ],
        agent_config=_agent_config(),
    )

    expected_story_brief_key = text_sha256("news-story-brief|news_story_identity_v2|listing:binance:foo:2026-06-18")
    assert first.story_brief_key == expected_story_brief_key
    assert first.story_brief_key == story_brief_key_for(
        story_identity_version="news_story_identity_v2",
        story_key="listing:binance:foo:2026-06-18",
    )
    assert first.member_news_item_ids == ["news-1", "news-2"]
    assert first.input_hash == reordered.input_hash
    assert first.input_hash == json_sha256(news_story_brief_material_input_payload(first))


def test_story_brief_key_is_stable_when_representative_changes() -> None:
    story = _story()
    first = build_news_story_brief_input_packet(
        story=story,
        representative_item=_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000),
        member_items=[_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)],
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )
    second = build_news_story_brief_input_packet(
        story=story,
        representative_item=_item("news-2", "FOO listing confirmed", published_at_ms=1_779_000_010_000),
        member_items=[_item("news-2", "FOO listing confirmed", published_at_ms=1_779_000_010_000)],
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert first.story_brief_key == second.story_brief_key
    assert first.input_hash != second.input_hash


def test_story_packet_hash_excludes_projection_runtime_fields() -> None:
    base = build_news_story_brief_input_packet(
        story=_story(computed_at_ms=1, row_id="row-a"),
        representative_item=_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000),
        member_items=[_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)],
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )
    rerun = build_news_story_brief_input_packet(
        story=_story(computed_at_ms=2, row_id="row-b"),
        representative_item=_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000),
        member_items=[_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)],
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    payload = news_story_brief_material_input_payload(base)
    assert base.input_hash == rerun.input_hash
    assert "row_id" not in payload
    assert "projection_version" not in payload
    assert "computed_at_ms" not in payload


def test_story_packet_requires_explicit_member_items() -> None:
    with pytest.raises(ValueError, match="news_story_brief_member_items_required"):
        build_news_story_brief_input_packet(
            story=_story(),
            representative_item=_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000),
            member_items=[],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


def test_story_packet_rejects_member_item_missing_news_item_id() -> None:
    representative = _item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)
    bad_member = {
        "title": "FOO listing confirmed",
        "source_domain": "example.com",
        "published_at_ms": 1_779_000_010_000,
    }

    with pytest.raises(ValueError, match="news_story_brief_member_news_item_id_required"):
        build_news_story_brief_input_packet(
            story=_story(),
            representative_item=representative,
            member_items=[representative, bad_member],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


def test_story_packet_rejects_representative_item_missing_published_at_ms() -> None:
    representative = _item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)
    representative.pop("published_at_ms")

    with pytest.raises(ValueError, match="news_story_brief_representative_published_at_ms_required"):
        build_news_story_brief_input_packet(
            story=_story(),
            representative_item=representative,
            member_items=[_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


@pytest.mark.parametrize("bad_value", [True, "1779000000000", 1_779_000_000_000.5])
def test_story_packet_rejects_representative_item_malformed_published_at_ms(bad_value: object) -> None:
    representative = _item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)
    representative["published_at_ms"] = bad_value

    with pytest.raises(ValueError, match="news_story_brief_representative_published_at_ms_required"):
        build_news_story_brief_input_packet(
            story=_story(),
            representative_item=representative,
            member_items=[representative],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


def test_story_packet_rejects_member_item_missing_published_at_ms() -> None:
    representative = _item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)
    bad_member = _item("news-2", "FOO listing confirmed", published_at_ms=1_779_000_010_000)
    bad_member.pop("published_at_ms")

    with pytest.raises(ValueError, match="news_story_brief_member_published_at_ms_required"):
        build_news_story_brief_input_packet(
            story=_story(),
            representative_item=representative,
            member_items=[representative, bad_member],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


@pytest.mark.parametrize("bad_value", [True, "1779000010000", 1_779_000_010_000.5])
def test_story_packet_rejects_member_item_malformed_published_at_ms(bad_value: object) -> None:
    representative = _item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)
    bad_member = _item("news-2", "FOO listing confirmed", published_at_ms=1_779_000_010_000)
    bad_member["published_at_ms"] = bad_value

    with pytest.raises(ValueError, match="news_story_brief_member_published_at_ms_required"):
        build_news_story_brief_input_packet(
            story=_story(),
            representative_item=representative,
            member_items=[representative, bad_member],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


def test_story_packet_requires_story_agent_admission_without_representative_fallback() -> None:
    story = _story()
    story.pop("agent_admission_json")
    representative = {
        **_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000),
        "agent_admission_json": {"status": "eligible"},
    }

    with pytest.raises(ValueError, match="news_story_brief_agent_admission_json_required"):
        build_news_story_brief_input_packet(
            story=story,
            representative_item=representative,
            member_items=[representative],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


def test_story_packet_requires_story_market_scope_without_representative_fallback() -> None:
    story = _story()
    story.pop("market_scope_json")
    representative = _item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)

    with pytest.raises(ValueError, match="news_story_brief_market_scope_json_required"):
        build_news_story_brief_input_packet(
            story=story,
            representative_item=representative,
            member_items=[representative],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


@pytest.mark.parametrize(
    "story_override",
    [
        pytest.param({"market_scope": ["crypto"]}, id="top_level_alias"),
        pytest.param({"market_scope_json": {"market_scope": ["crypto"]}}, id="scope_key_alias"),
        pytest.param({"market_scope_json": {"market_scope_primary": "crypto"}}, id="primary_key_alias"),
        pytest.param({"market_scope_json": ["crypto"]}, id="bare_list"),
        pytest.param({"market_scope_json": "crypto"}, id="bare_string"),
    ],
)
def test_story_packet_rejects_market_scope_aliases(story_override: dict[str, object]) -> None:
    story = _story()
    story.pop("market_scope_json")
    story.update(story_override)
    representative = _item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)

    with pytest.raises(ValueError, match="news_story_brief_market_scope_json_required"):
        build_news_story_brief_input_packet(
            story=story,
            representative_item=representative,
            member_items=[representative],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


def test_story_packet_requires_story_identity_context() -> None:
    story = _story()
    story.pop("story_identity_json")

    with pytest.raises(ValueError, match="news_story_brief_story_identity_json_required"):
        build_news_story_brief_input_packet(
            story=story,
            representative_item=_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000),
            member_items=[_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


@pytest.mark.parametrize(
    ("formal_key", "error"),
    [
        pytest.param("story_identity_json", "news_story_brief_story_identity_json_required", id="story_identity"),
        pytest.param("agent_admission_json", "news_story_brief_agent_admission_json_required", id="admission"),
        pytest.param("similarity_json", "news_story_brief_similarity_json_required", id="similarity"),
        pytest.param("material_delta_json", "news_story_brief_material_delta_json_required", id="material_delta"),
    ],
)
@pytest.mark.parametrize("bad_value", [["not", "object"], "not-json", '{"status": "eligible"}'])
def test_story_packet_rejects_malformed_present_context_objects(
    formal_key: str,
    error: str,
    bad_value: object,
) -> None:
    story = _story()
    story[formal_key] = bad_value

    with pytest.raises(ValueError, match=error):
        build_news_story_brief_input_packet(
            story=story,
            representative_item=_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000),
            member_items=[_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)],
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            agent_config=_agent_config(),
        )


def test_story_packet_does_not_restore_material_or_similarity_from_agent_admission_basis() -> None:
    story = _story()
    story.pop("material_delta_json")
    story.pop("similarity_json")
    story["agent_admission_json"] = {
        "status": "eligible",
        "reason": "eligible",
        "material_delta": {"has_delta": True},
        "basis": {
            "similarity": {"similar_story": True},
            "material_delta": {"has_delta": True},
        },
    }

    packet = build_news_story_brief_input_packet(
        story=story,
        representative_item=_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000),
        member_items=[_item("news-1", "Binance lists FOO", published_at_ms=1_779_000_000_000)],
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        agent_config=_agent_config(),
    )

    assert packet.material_delta == {}
    assert packet.similarity == {}
