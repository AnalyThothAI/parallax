from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE = 80
NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS = 8 * 3_600_000


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
    if str(item.get("lifecycle_status") or "").strip().lower() != "processed":
        return NewsItemAgentBriefEligibility(eligible=False, reason="item_not_processed")
    if not _mapping(item.get("content_classification_json")):
        return NewsItemAgentBriefEligibility(eligible=False, reason="classification_missing")

    provider_signal = _mapping(item.get("provider_signal_json"))
    if str(provider_signal.get("source") or "").strip().lower() != "provider":
        return NewsItemAgentBriefEligibility(eligible=False, reason="source_not_provider_signal")
    score = _optional_int(provider_signal.get("score"))
    if score is None or score < NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE:
        return NewsItemAgentBriefEligibility(eligible=False, reason="below_score_threshold")
    if not _has_processed_market_context(
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
    ):
        return NewsItemAgentBriefEligibility(eligible=False, reason="no_processed_market_context")

    published_at_ms = _optional_int(item.get("published_at_ms"))
    if published_at_ms is None:
        return NewsItemAgentBriefEligibility(eligible=False, reason="published_at_missing")
    age_ms = int(now_ms) - int(published_at_ms)
    if age_ms < 0:
        return NewsItemAgentBriefEligibility(eligible=False, reason="published_in_future")
    if age_ms > max(0, int(max_published_age_ms)):
        return NewsItemAgentBriefEligibility(eligible=False, reason="published_too_old")
    return NewsItemAgentBriefEligibility(eligible=True, reason="eligible")


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
        return max(0, min(100, 100 - score))
    if str(provider_signal.get("status") or "").strip().lower() == "ready":
        return 25
    return 100


def _has_processed_market_context(
    *,
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
) -> bool:
    for mention in token_mentions:
        if str(mention.get("resolution_status") or "").strip().lower() not in {"", "non_crypto", "nil"}:
            return True
    for candidate in fact_candidates:
        if str(candidate.get("validation_status") or candidate.get("status") or "").strip().lower() != "rejected":
            return True
    return False


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
