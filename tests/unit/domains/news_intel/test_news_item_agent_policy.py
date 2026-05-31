from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_policy import (
    NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS,
    NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
    news_item_agent_brief_eligibility,
    news_item_agent_brief_priority,
)

NOW_MS = 2_000_000_000_000


def test_news_item_agent_brief_requires_provider_score_at_or_above_analysis_floor() -> None:
    assert NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE == 80
    result = news_item_agent_brief_eligibility(
        {
            "published_at_ms": NOW_MS - 60_000,
            "provider_signal_json": {
                "source": "provider",
                "status": "ready",
                "score": NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
            },
        },
        now_ms=NOW_MS,
    )

    assert result.eligible is True
    assert result.reason == "eligible"


def test_news_item_agent_brief_rejects_below_threshold_provider_scores() -> None:
    result = news_item_agent_brief_eligibility(
        {
            "published_at_ms": NOW_MS - 60_000,
            "provider_signal_json": {
                "source": "provider",
                "status": "ready",
                "score": NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE - 1,
            },
        },
        now_ms=NOW_MS,
    )

    assert result.eligible is False
    assert result.reason == "below_score_threshold"


def test_news_item_agent_brief_rejects_non_provider_or_missing_score() -> None:
    non_provider = news_item_agent_brief_eligibility(
        {
            "published_at_ms": NOW_MS - 60_000,
            "provider_signal_json": {"source": "manual", "status": "ready", "score": 100},
        },
        now_ms=NOW_MS,
    )
    missing_score = news_item_agent_brief_eligibility(
        {
            "published_at_ms": NOW_MS - 60_000,
            "provider_signal_json": {"source": "provider", "status": "ready"},
        },
        now_ms=NOW_MS,
    )

    assert non_provider.eligible is False
    assert non_provider.reason == "source_not_provider_signal"
    assert missing_score.eligible is False
    assert missing_score.reason == "below_score_threshold"


def test_news_item_agent_brief_requires_fresh_published_at() -> None:
    assert NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS == 8 * 3_600_000
    missing_published = news_item_agent_brief_eligibility(
        {
            "provider_signal_json": {"source": "provider", "status": "ready", "score": 100},
        },
        now_ms=NOW_MS,
    )
    too_old = news_item_agent_brief_eligibility(
        {
            "published_at_ms": NOW_MS - NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS - 1,
            "provider_signal_json": {"source": "provider", "status": "ready", "score": 100},
        },
        now_ms=NOW_MS,
    )
    future = news_item_agent_brief_eligibility(
        {
            "published_at_ms": NOW_MS + 1,
            "provider_signal_json": {"source": "provider", "status": "ready", "score": 100},
        },
        now_ms=NOW_MS,
    )

    assert missing_published.eligible is False
    assert missing_published.reason == "published_at_missing"
    assert too_old.eligible is False
    assert too_old.reason == "published_too_old"
    assert future.eligible is False
    assert future.reason == "published_in_future"


def test_news_item_agent_brief_priority_keeps_higher_provider_scores_first() -> None:
    assert news_item_agent_brief_priority({"provider_signal_json": {"source": "provider", "score": 95}}) < (
        news_item_agent_brief_priority({"provider_signal_json": {"source": "provider", "score": 72}})
    )
