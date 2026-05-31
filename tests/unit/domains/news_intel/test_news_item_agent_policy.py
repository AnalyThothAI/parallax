from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_policy import (
    NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
    needs_news_item_agent_brief,
    news_item_agent_brief_priority,
)


def test_news_item_agent_brief_requires_provider_score_at_or_above_analysis_floor() -> None:
    assert (
        needs_news_item_agent_brief(
            {
                "provider_signal_json": {
                    "source": "provider",
                    "status": "ready",
                    "score": NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
                }
            }
        )
        is True
    )
    assert (
        needs_news_item_agent_brief(
            {
                "provider_signal_json": {
                    "source": "provider",
                    "status": "ready",
                    "score": NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE - 1,
                }
            }
        )
        is False
    )
    assert needs_news_item_agent_brief({"provider_signal_json": {"source": "provider", "status": "ready"}}) is False
    assert needs_news_item_agent_brief({"provider_signal_json": {}}) is False


def test_news_item_agent_brief_priority_keeps_higher_provider_scores_first() -> None:
    assert news_item_agent_brief_priority({"provider_signal_json": {"source": "provider", "score": 95}}) < (
        news_item_agent_brief_priority({"provider_signal_json": {"source": "provider", "score": 72}})
    )
