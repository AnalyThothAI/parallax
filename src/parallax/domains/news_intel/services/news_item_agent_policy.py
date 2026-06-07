from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from parallax.domains.news_intel.services.news_item_agent_admission import (
    NEWS_ITEM_AGENT_MAX_PUBLISHED_AGE_MS,
    NEWS_ITEM_AGENT_MIN_PROVIDER_SCORE,
    NewsItemAgentAdmissionContext,
    decide_news_item_agent_admission,
)

NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE = NEWS_ITEM_AGENT_MIN_PROVIDER_SCORE
NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS = NEWS_ITEM_AGENT_MAX_PUBLISHED_AGE_MS


@dataclass(frozen=True, slots=True)
class NewsItemAgentBriefEligibility:
    eligible: bool
    reason: str


def news_item_agent_brief_eligibility(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    now_ms: int,
    max_published_age_ms: int = NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS,
) -> NewsItemAgentBriefEligibility:
    admission = decide_news_item_agent_admission(
        item=item,
        entities=[],
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
        context=NewsItemAgentAdmissionContext.empty(),
        now_ms=now_ms,
        max_published_age_ms=max_published_age_ms,
    )
    return NewsItemAgentBriefEligibility(eligible=admission.eligible, reason=admission.reason)


def news_item_agent_brief_priority(
    *,
    item: Mapping[str, Any],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
) -> int:
    del token_mentions, fact_candidates
    provider_signal = _mapping(item.get("provider_signal_json"))
    if str(provider_signal.get("source") or "").strip().lower() != "provider":
        return 100
    score = _optional_int(provider_signal.get("score"))
    if score is not None:
        base_priority = max(0, min(100, 100 - score))
        return base_priority
    if str(provider_signal.get("status") or "").strip().lower() == "ready":
        return 25
    return 100


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS",
    "NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE",
    "NewsItemAgentBriefEligibility",
    "news_item_agent_brief_eligibility",
    "news_item_agent_brief_priority",
]
