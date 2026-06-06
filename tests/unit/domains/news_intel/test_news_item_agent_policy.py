from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_policy import (
    NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
    news_item_agent_brief_priority,
)


def _item(**overrides):
    item = {
        "news_item_id": "news-1",
        "provider_signal_json": {
            "source": "provider",
            "status": "ready",
            "score": NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
        },
    }
    item.update(overrides)
    return item


def test_news_item_agent_brief_priority_keeps_higher_provider_scores_first() -> None:
    assert news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 95}),
    ) < news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 80}),
    )


def test_news_item_agent_brief_priority_pushes_below_floor_behind_ready_market_items() -> None:
    assert news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 79}),
    ) > news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 80}),
    )
