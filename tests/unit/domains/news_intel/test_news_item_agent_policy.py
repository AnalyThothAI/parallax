from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_policy import news_item_agent_brief_priority


def _item(**overrides):
    item = {
        "news_item_id": "news-1",
        "provider_signal_json": {
            "source": "provider",
            "status": "ready",
            "score": 80,
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


def test_news_item_agent_brief_priority_does_not_penalize_low_scores_beyond_sort_order() -> None:
    assert news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 79}),
    ) == news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 80}),
    ) + 1
