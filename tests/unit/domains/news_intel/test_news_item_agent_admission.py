from __future__ import annotations

import pytest

from parallax.domains.news_intel.services.news_item_agent_admission import (
    NewsItemAgentAdmissionContext,
    decide_news_item_agent_admission,
)

NOW_MS = 2_000_000_000_000


def _item(**overrides):
    item = {
        "news_item_id": "news-1",
        "published_at_ms": NOW_MS - 60_000,
        "lifecycle_status": "processed",
        "content_classification_json": {"policy_version": "news_content_classification_v1"},
        "provider_signal_json": {"source": "provider", "status": "ready", "score": 95},
        "source_role": "news",
    }
    item.update(overrides)
    return item


def test_high_score_us_equity_page_only_item_is_eligible() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(
            title="NVIDIA shares rise after AI chip demand update",
        ),
        entities=[{"entity_id": "entity-nvda", "raw_value": "NVIDIA", "entity_type": "company"}],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext.empty(),
        now_ms=NOW_MS,
    )

    assert admission.eligible is True
    assert admission.status == "eligible"
    assert admission.reason == "eligible"


def test_low_provider_rating_market_news_is_not_agent_eligible() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(
            title="Ford shares fall after supplier disruption",
            provider_signal_json={"source": "provider", "status": "ready", "score": 42},
        ),
        entities=[{"entity_id": "entity-f", "raw_value": "Ford", "entity_type": "company", "symbol": "F"}],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext.empty(),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "needs_review"
    assert admission.reason == "provider_rating_below_threshold"
    assert admission.basis["provider_rating"]["score"] == 42
    assert admission.basis["provider_rating"]["min_score"] == 80


def test_missing_provider_rating_market_news_is_not_agent_eligible() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(
            title="Ford shares fall after supplier disruption",
            provider_signal_json={"source": "provider", "status": "partial"},
        ),
        entities=[{"entity_id": "entity-f", "raw_value": "Ford", "entity_type": "company", "symbol": "F"}],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext.empty(),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "needs_review"
    assert admission.reason == "provider_rating_missing"
    assert admission.basis["provider_rating"]["score"] is None
    assert admission.basis["provider_rating"]["min_score"] == 80


@pytest.mark.parametrize("score", [True, "95", 95.5])
def test_provider_rating_rejects_malformed_score_without_int_repair(score: object) -> None:
    with pytest.raises(ValueError, match="news_item_agent_admission_provider_rating_score_required"):
        decide_news_item_agent_admission(
            item=_item(
                title="Ford shares rise after analyst upgrade",
                provider_signal_json={"source": "provider", "status": "ready", "score": score},
            ),
            entities=[{"entity_id": "entity-f", "raw_value": "Ford", "entity_type": "company", "symbol": "F"}],
            token_mentions=[],
            fact_candidates=[],
            context=NewsItemAgentAdmissionContext.empty(),
            now_ms=NOW_MS,
        )


@pytest.mark.parametrize(
    ("item_overrides", "match"),
    [
        pytest.param(
            {"content_classification_json": '{"policy_version":"news_content_classification_v1"}'},
            "news_item_agent_admission_content_classification_json_required",
            id="classification_string",
        ),
        pytest.param(
            {"source_policy_json": '{"status":"disabled"}'},
            "news_item_agent_admission_source_policy_json_required",
            id="source_policy_string",
        ),
        pytest.param(
            {"provider_signal_json": '{"source":"provider","status":"ready","score":95}'},
            "news_item_agent_admission_provider_signal_json_required",
            id="provider_signal_string",
        ),
    ],
)
def test_agent_admission_rejects_malformed_present_item_json_fields(
    item_overrides: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        decide_news_item_agent_admission(
            item=_item(**item_overrides),
            entities=[],
            token_mentions=[],
            fact_candidates=[],
            context=NewsItemAgentAdmissionContext.empty(),
            now_ms=NOW_MS,
        )


def test_high_score_old_item_is_not_filtered_by_agent_age_gate() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(
            published_at_ms=NOW_MS - 24 * 3_600_000,
            title="Oil prices rise after Gulf shipping disruption",
        ),
        entities=[{"entity_id": "entity-wti", "raw_value": "WTI crude", "entity_type": "commodity"}],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext.empty(),
        now_ms=NOW_MS,
    )

    assert admission.eligible is True
    assert admission.status == "eligible"
    assert admission.reason == "eligible"


def test_exact_duplicate_uses_representative_and_skips_agent() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(provider_article_keys_json=["opennews:123"]),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            exact_duplicate_candidates=[
                {
                    "news_item_id": "news-rep",
                    "provider_article_keys": ["opennews:123"],
                    "published_at_ms": 1_000,
                    "lifecycle_status": "processed",
                    "agent_admission_status": "eligible",
                }
            ],
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "exact_duplicate"
    assert admission.representative_news_item_id == "news-rep"


def test_unready_exact_duplicate_candidate_does_not_starve_current_item() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(provider_article_keys_json=["opennews:123"]),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            exact_duplicate_candidates=[
                {
                    "news_item_id": "news-raw-rep",
                    "provider_article_keys": ["opennews:123"],
                    "published_at_ms": 1_000,
                    "lifecycle_status": "raw",
                }
            ],
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is True
    assert admission.status == "eligible"
    assert admission.representative_news_item_id == "news-1"


def test_similar_story_without_delta_is_covered_skip() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(story_key="story:hormuz", source_role="news"),
        entities=[{"normalized_value": "iran", "entity_type": "country"}],
        token_mentions=[],
        fact_candidates=[{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
        context=NewsItemAgentAdmissionContext(
            story_candidates=[
                {
                    "news_item_id": "news-rep",
                    "story_key": "story:hormuz",
                    "source_role": "news",
                    "provider_signal_json": {"score": 96},
                    "current_brief": {"status": "ready"},
                    "entities": [{"normalized_value": "iran", "entity_type": "country"}],
                    "fact_candidates": [{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
                }
            ],
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "similar_story_covered"
    assert admission.representative_news_item_id == "news-rep"


def test_agent_admission_rejects_malformed_present_context_arrays() -> None:
    with pytest.raises(ValueError, match="news_item_agent_admission_representative_entities_required"):
        decide_news_item_agent_admission(
            item=_item(story_key="story:hormuz", source_role="news"),
            entities=[{"normalized_value": "iran", "entity_type": "country"}],
            token_mentions=[],
            fact_candidates=[{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
            context=NewsItemAgentAdmissionContext(
                story_candidates=[
                    {
                        "news_item_id": "news-rep",
                        "story_key": "story:hormuz",
                        "source_role": "news",
                        "current_brief": {"status": "ready"},
                        "entities": '[{"normalized_value":"iran","entity_type":"country"}]',
                        "fact_candidates": [{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
                    }
                ],
            ),
            now_ms=NOW_MS,
        )


def test_repository_context_allows_absent_optional_sections() -> None:
    context = NewsItemAgentAdmissionContext.from_repository_context({})

    assert context.exact_duplicate_candidates == []
    assert context.story_candidates == []
    assert context.material_delta == {}


@pytest.mark.parametrize(
    ("repository_context", "error"),
    [
        (
            {"exact_duplicate_candidates": {"news_item_id": "news-rep"}},
            "news_item_agent_admission_context_exact_duplicate_candidates_required",
        ),
        (
            {"exact_duplicate_candidates": ["news-rep"]},
            "news_item_agent_admission_context_exact_duplicate_candidates_required",
        ),
        (
            {"story_candidates": {"news_item_id": "news-rep"}},
            "news_item_agent_admission_context_story_candidates_required",
        ),
        (
            {"story_candidates": ["news-rep"]},
            "news_item_agent_admission_context_story_candidates_required",
        ),
        (
            {"material_delta": "material"},
            "news_item_agent_admission_context_material_delta_required",
        ),
    ],
)
def test_repository_context_rejects_malformed_present_sections(
    repository_context: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        NewsItemAgentAdmissionContext.from_repository_context(repository_context)


def test_similar_story_with_pending_representative_brief_is_covered_skip() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(story_key="story:hormuz", source_role="news"),
        entities=[{"normalized_value": "iran", "entity_type": "country"}],
        token_mentions=[],
        fact_candidates=[{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
        context=NewsItemAgentAdmissionContext(
            story_candidates=[
                {
                    "news_item_id": "news-rep",
                    "story_key": "story:hormuz",
                    "source_role": "news",
                    "agent_admission_status": "eligible",
                    "entities": [{"normalized_value": "iran", "entity_type": "country"}],
                    "fact_candidates": [{"event_type": "geopolitical_risk", "validation_status": "accepted"}],
                }
            ],
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "similar_story_covered"
    assert admission.representative_news_item_id == "news-rep"


def test_similar_story_with_official_source_delta_refreshes() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(story_key="story:hormuz", source_role="official_exchange"),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            story_candidates=[
                {
                    "news_item_id": "news-rep",
                    "story_key": "story:hormuz",
                    "source_role": "specialist_media",
                    "current_brief": {"status": "ready"},
                }
            ],
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is True
    assert admission.status == "eligible_refresh"
    assert admission.representative_news_item_id == "news-1"
    assert "source_role_upgrade" in admission.basis["material_delta"]["reasons"]


def test_similar_story_burst_without_delta_uses_burst_reason() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(story_key="story:hormuz", source_role="news"),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            story_candidates=[
                {
                    "news_item_id": "news-rep",
                    "story_key": "story:hormuz",
                    "source_role": "news",
                    "current_brief": {"status": "ready"},
                },
                {"news_item_id": "news-2", "story_key": "story:hormuz", "source_role": "news"},
                {"news_item_id": "news-3", "story_key": "story:hormuz", "source_role": "news"},
            ],
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "similar_story_burst"
