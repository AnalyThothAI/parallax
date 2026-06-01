from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_policy import (
    NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS,
    NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
    news_item_agent_brief_eligibility,
    news_item_agent_brief_priority,
)

NOW_MS = 2_000_000_000_000


def _item(**overrides):
    item = {
        "news_item_id": "news-1",
        "published_at_ms": NOW_MS - 60_000,
        "lifecycle_status": "processed",
        "content_class": "exchange_listing",
        "content_classification_json": {"policy_version": "news_content_classification_v1"},
        "provider_signal_json": {
            "source": "provider",
            "status": "ready",
            "score": NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
        },
    }
    item.update(overrides)
    return item


def test_news_item_agent_brief_requires_processed_item_state() -> None:
    result = news_item_agent_brief_eligibility(
        item=_item(lifecycle_status="raw"),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert result.eligible is False
    assert result.reason == "item_not_processed"


def test_news_item_agent_brief_requires_classification() -> None:
    result = news_item_agent_brief_eligibility(
        item=_item(content_classification_json={}),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert result.eligible is False
    assert result.reason == "classification_missing"


def test_news_item_agent_brief_requires_provider_score_at_or_above_analysis_floor() -> None:
    assert NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE == 80
    result = news_item_agent_brief_eligibility(
        item=_item(),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert result.eligible is True
    assert result.reason == "eligible"


def test_news_item_agent_brief_rejects_below_threshold_provider_scores() -> None:
    result = news_item_agent_brief_eligibility(
        item=_item(provider_signal_json={"source": "provider", "status": "ready", "score": 79}),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert result.eligible is False
    assert result.reason == "below_score_threshold"


def test_news_item_agent_brief_rejects_non_provider_or_missing_score() -> None:
    non_provider = news_item_agent_brief_eligibility(
        item=_item(provider_signal_json={"source": "manual", "status": "ready", "score": 100}),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )
    missing_score = news_item_agent_brief_eligibility(
        item=_item(provider_signal_json={"source": "provider", "status": "ready"}),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert non_provider.eligible is False
    assert non_provider.reason == "source_not_provider_signal"
    assert missing_score.eligible is False
    assert missing_score.reason == "below_score_threshold"


def test_news_item_agent_brief_requires_processed_market_context() -> None:
    result = news_item_agent_brief_eligibility(
        item=_item(),
        token_mentions=[],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert result.eligible is False
    assert result.reason == "no_processed_market_context"


def test_news_item_agent_brief_requires_fresh_published_at() -> None:
    assert NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS == 8 * 3_600_000
    missing_published = news_item_agent_brief_eligibility(
        item=_item(published_at_ms=None),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )
    too_old = news_item_agent_brief_eligibility(
        item=_item(published_at_ms=NOW_MS - NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS - 1),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )
    future = news_item_agent_brief_eligibility(
        item=_item(published_at_ms=NOW_MS + 1),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
        now_ms=NOW_MS,
    )

    assert missing_published.eligible is False
    assert missing_published.reason == "published_at_missing"
    assert too_old.eligible is False
    assert too_old.reason == "published_too_old"
    assert future.eligible is False
    assert future.reason == "published_in_future"


def test_news_item_agent_brief_priority_keeps_higher_provider_scores_first() -> None:
    assert news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 95}),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
    ) < news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 72}),
        token_mentions=[{"resolution_status": "known_symbol"}],
        fact_candidates=[],
        context_items=[],
    )
