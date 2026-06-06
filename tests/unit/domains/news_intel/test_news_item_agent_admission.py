from __future__ import annotations

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
            analysis_admission_status="page_only",
            analysis_admission_reason="non_crypto_subject",
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
