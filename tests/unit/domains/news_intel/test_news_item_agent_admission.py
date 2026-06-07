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
        "content_class": "us_equity",
        "content_classification_json": {"policy_version": "news_content_classification_v1"},
        "provider_signal_json": {"source": "provider", "status": "ready", "score": 95},
    }
    item.update(overrides)
    return item


def test_score_95_non_crypto_item_is_market_wide_eligible() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(analysis_admission_status="page_only"),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext.empty(),
        now_ms=NOW_MS,
    )

    assert admission.eligible is True
    assert admission.status == "eligible"
    assert admission.reason == "provider_score_high"
    assert admission.representative_news_item_id == "news-1"


def test_low_score_item_is_below_threshold_even_when_crypto_admitted() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(
            provider_signal_json={"source": "provider", "status": "ready", "score": 72},
            analysis_admission_status="admitted",
        ),
        entities=[],
        token_mentions=[{"display_symbol": "BTC"}],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext.empty(),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "score_below_threshold"
    assert admission.reason == "below_score_threshold"


def test_exact_duplicate_uses_representative_pointer() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            exact_duplicate={
                "exact_duplicate": True,
                "match_type": "same_provider_article_id",
                "matched_news_item_id": "news-rep",
            }
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "exact_duplicate"
    assert admission.reason == "same_provider_article_id"
    assert admission.representative_news_item_id == "news-rep"


def test_similar_story_without_delta_is_covered() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            similar_story={
                "similar_story": True,
                "reason": "same_story_key",
                "representative_news_item_id": "news-story-rep",
            },
            material_delta={"has_delta": False},
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "similar_story_covered"
    assert admission.reason == "same_story_key"
    assert admission.representative_news_item_id == "news-story-rep"


def test_similar_story_burst_without_delta_is_suppressed() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            similar_story={
                "similar_story": True,
                "burst": True,
                "representative_news_item_id": "news-story-rep",
            },
            material_delta={"has_delta": False},
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is False
    assert admission.status == "similar_story_burst"


def test_similar_story_with_material_delta_is_refresh_eligible() -> None:
    admission = decide_news_item_agent_admission(
        item=_item(),
        entities=[],
        token_mentions=[],
        fact_candidates=[],
        context=NewsItemAgentAdmissionContext(
            similar_story={"similar_story": True, "representative_news_item_id": "news-story-rep"},
            material_delta={"has_delta": True, "reason": "source_role_upgrade"},
        ),
        now_ms=NOW_MS,
    )

    assert admission.eligible is True
    assert admission.status == "eligible_refresh"
    assert admission.reason == "source_role_upgrade"
    assert admission.representative_news_item_id == "news-story-rep"
