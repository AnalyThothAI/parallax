from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE = 80
NEWS_ITEM_AGENT_BRIEF_MIN_ADMITTED_PROVIDER_SCORE = 65
NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS = 8 * 3_600_000
_EXPLICIT_CRYPTO_EVIDENCE_PREFIXES = (
    "accepted_fact:",
    "resolved_crypto_target:",
    "text:crypto_subject",
)


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
    if str(item.get("analysis_admission_status") or "").strip().lower() != "admitted":
        return NewsItemAgentBriefEligibility(eligible=False, reason="analysis_not_admitted")

    provider_signal = _mapping(item.get("provider_signal_json"))
    if str(provider_signal.get("source") or "").strip().lower() != "provider":
        return NewsItemAgentBriefEligibility(eligible=False, reason="source_not_provider_signal")
    score = _optional_int(provider_signal.get("score"))
    if score is None:
        return NewsItemAgentBriefEligibility(eligible=False, reason="below_score_threshold")
    if score < NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE and (
        score < NEWS_ITEM_AGENT_BRIEF_MIN_ADMITTED_PROVIDER_SCORE or not _has_explicit_crypto_admission_basis(item)
    ):
        return NewsItemAgentBriefEligibility(eligible=False, reason="below_score_threshold")

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
        base_priority = max(0, min(100, 100 - score))
        if score < NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE:
            return base_priority + 100
        return base_priority
    if str(provider_signal.get("status") or "").strip().lower() == "ready":
        return 25
    return 100


def _has_explicit_crypto_admission_basis(item: Mapping[str, Any]) -> bool:
    admission = _mapping(item.get("analysis_admission_json"))
    basis = _mapping(admission.get("basis"))
    for evidence in _list(basis.get("crypto_evidence")):
        text = str(evidence)
        if text == "text:crypto_subject" or text.startswith(_EXPLICIT_CRYPTO_EVIDENCE_PREFIXES):
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


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS",
    "NEWS_ITEM_AGENT_BRIEF_MIN_ADMITTED_PROVIDER_SCORE",
    "NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE",
    "NewsItemAgentBriefEligibility",
    "news_item_agent_brief_eligibility",
    "news_item_agent_brief_priority",
]
