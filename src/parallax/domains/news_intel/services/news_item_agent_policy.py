from __future__ import annotations

from collections.abc import Mapping
from typing import Any

NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE = 70


def needs_news_item_agent_brief(item: Mapping[str, Any]) -> bool:
    provider_signal = _mapping(item.get("provider_signal_json"))
    if str(provider_signal.get("source") or "").strip().lower() != "provider":
        return False
    score = _optional_int(provider_signal.get("score"))
    return score is not None and score >= NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE


def news_item_agent_brief_priority(item: Mapping[str, Any]) -> int:
    provider_signal = _mapping(item.get("provider_signal_json"))
    if str(provider_signal.get("source") or "").strip().lower() != "provider":
        return 100
    score = _optional_int(provider_signal.get("score"))
    if score is not None:
        return max(0, min(100, 100 - score))
    if str(provider_signal.get("status") or "").strip().lower() == "ready":
        return 25
    return 100


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE",
    "needs_news_item_agent_brief",
    "news_item_agent_brief_priority",
]
