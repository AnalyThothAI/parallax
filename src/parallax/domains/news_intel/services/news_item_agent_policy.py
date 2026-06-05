from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE = 80
NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS = 8 * 3_600_000
NEWS_ITEM_AGENT_REQUIREMENT_VERSION = "news_item_agent_requirement_v1"
_EXPLICIT_CRYPTO_EVIDENCE_PREFIXES = (
    "accepted_fact:",
    "resolved_crypto_target:",
    "text:crypto_subject",
)


@dataclass(frozen=True, slots=True)
class NewsItemAgentRequirement:
    status: str
    reason: str
    priority: int
    basis: dict[str, Any]
    version: str = NEWS_ITEM_AGENT_REQUIREMENT_VERSION

    @property
    def required(self) -> bool:
        return self.status == "required"

    @property
    def eligible(self) -> bool:
        return self.required


def decide_news_item_agent_requirement(
    *,
    item: Mapping[str, Any],
    now_ms: int,
    max_published_age_ms: int = NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS,
) -> NewsItemAgentRequirement:
    provider_signal = _mapping(item.get("provider_signal_json"))
    score = _optional_int(provider_signal.get("score"))
    published_at_ms = _optional_int(item.get("published_at_ms"))
    basis = {
        "provider_score": score,
        "provider_source": str(provider_signal.get("source") or "").strip().lower(),
        "provider_status": str(provider_signal.get("status") or "").strip().lower(),
        "analysis_admission_status": str(item.get("analysis_admission_status") or "").strip().lower(),
        "content_class": str(item.get("content_class") or "").strip(),
        "crypto_evidence": _crypto_evidence(item),
        "min_provider_score": NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
        "max_published_age_ms": max(0, int(max_published_age_ms)),
        "published_at_ms": published_at_ms,
        "decided_at_ms": int(now_ms),
    }
    if str(item.get("lifecycle_status") or "").strip().lower() != "processed":
        return _requirement(False, "item_not_processed", score=score, basis=basis)
    if not _mapping(item.get("content_classification_json")):
        return _requirement(False, "classification_missing", score=score, basis=basis)
    if str(item.get("analysis_admission_status") or "").strip().lower() != "admitted":
        return _requirement(False, "analysis_not_admitted", score=score, basis=basis)
    if str(provider_signal.get("source") or "").strip().lower() != "provider":
        return _requirement(False, "source_not_provider_signal", score=score, basis=basis)
    if score is None:
        return _requirement(False, "missing_provider_score", score=score, basis=basis)
    if score < NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE:
        return _requirement(False, "below_score_threshold", score=score, basis=basis)
    if published_at_ms is None:
        return _requirement(False, "published_at_missing", score=score, basis=basis)
    age_ms = int(now_ms) - int(published_at_ms)
    basis["published_age_ms"] = age_ms
    if age_ms < 0:
        return _requirement(False, "published_in_future", score=score, basis=basis)
    if age_ms > max(0, int(max_published_age_ms)):
        return _requirement(False, "published_too_old", score=score, basis=basis)
    return _requirement(True, "eligible", score=score, basis=basis)


def news_item_agent_brief_priority(
    *,
    item: Mapping[str, Any],
) -> int:
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


def agent_requirement_payload(requirement: NewsItemAgentRequirement) -> dict[str, Any]:
    return {
        "status": requirement.status,
        "reason": requirement.reason,
        "priority": int(requirement.priority),
        "basis": dict(requirement.basis),
        "version": requirement.version,
    }


def _requirement(
    required: bool,
    reason: str,
    *,
    score: int | None,
    basis: Mapping[str, Any],
) -> NewsItemAgentRequirement:
    return NewsItemAgentRequirement(
        status="required" if required else "not_required",
        reason=reason,
        priority=_priority_from_score(score),
        basis=dict(basis),
    )


def _priority_from_score(score: int | None) -> int:
    if score is None:
        return 100
    return max(0, min(100, 100 - int(score)))


def _crypto_evidence(item: Mapping[str, Any]) -> list[str]:
    admission = _mapping(item.get("analysis_admission_json"))
    basis = _mapping(admission.get("basis"))
    return [
        text
        for evidence in _list(basis.get("crypto_evidence"))
        for text in [str(evidence)]
        if text == "text:crypto_subject" or text.startswith(_EXPLICIT_CRYPTO_EVIDENCE_PREFIXES)
    ]


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
    "NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE",
    "NEWS_ITEM_AGENT_REQUIREMENT_VERSION",
    "NewsItemAgentRequirement",
    "agent_requirement_payload",
    "decide_news_item_agent_requirement",
    "news_item_agent_brief_priority",
]
