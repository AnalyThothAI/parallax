from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel.types.news_item_agent_admission import (
    NewsItemAgentAdmission,
    NewsItemAgentAdmissionContext,
    NewsItemAgentAdmissionStatus,
)

NEWS_ITEM_AGENT_MIN_PROVIDER_SCORE = 80
NEWS_ITEM_AGENT_MAX_PUBLISHED_AGE_MS = 8 * 3_600_000


def decide_news_item_agent_admission(
    *,
    item: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    context: NewsItemAgentAdmissionContext | Mapping[str, Any] | None,
    now_ms: int,
    min_provider_score: int = NEWS_ITEM_AGENT_MIN_PROVIDER_SCORE,
    max_published_age_ms: int = NEWS_ITEM_AGENT_MAX_PUBLISHED_AGE_MS,
) -> NewsItemAgentAdmission:
    del entities, token_mentions, fact_candidates
    item_id = _text(item.get("news_item_id"))
    representative_id = _text(item.get("agent_representative_news_item_id")) or item_id
    provider_signal = _mapping(item.get("provider_signal_json"))
    base_basis = {
        "provider_signal": {
            "source": _text(provider_signal.get("source")),
            "status": _text(provider_signal.get("status")),
            "score": _optional_int(provider_signal.get("score")),
        },
        "content_class": _text(item.get("content_class")),
    }

    if _text(item.get("lifecycle_status")).casefold() != "processed":
        return _blocked("needs_review", "item_not_processed", representative_id, base_basis)
    if not _mapping(item.get("content_classification_json")):
        return _blocked("needs_review", "classification_missing", representative_id, base_basis)
    if _source_suppressed(item):
        return _blocked("source_suppressed", "source_suppressed", representative_id, base_basis)
    if _text(provider_signal.get("source")).casefold() != "provider":
        return _blocked("needs_review", "source_not_provider_signal", representative_id, base_basis)

    score = _optional_int(provider_signal.get("score"))
    if score is None or score < int(min_provider_score):
        return _blocked("score_below_threshold", "below_score_threshold", representative_id, base_basis)

    published_at_ms = _optional_int(item.get("published_at_ms"))
    if published_at_ms is None:
        return _blocked("needs_review", "published_at_missing", representative_id, base_basis)
    age_ms = int(now_ms) - int(published_at_ms)
    if age_ms < 0:
        return _blocked("needs_review", "published_in_future", representative_id, base_basis)
    if age_ms > max(0, int(max_published_age_ms)):
        return _blocked("needs_review", "published_too_old", representative_id, base_basis)

    resolved_context = _context_mapping(context)
    exact_duplicate = _mapping(resolved_context.get("exact_duplicate"))
    if _truthy(exact_duplicate.get("exact_duplicate")) or _text(exact_duplicate.get("matched_news_item_id")):
        representative_id = (
            _text(exact_duplicate.get("representative_news_item_id"))
            or _text(exact_duplicate.get("matched_news_item_id"))
            or representative_id
        )
        return _blocked(
            "exact_duplicate",
            _text(exact_duplicate.get("reason")) or _text(exact_duplicate.get("match_type")) or "exact_duplicate",
            representative_id,
            {**base_basis, "exact_duplicate": dict(exact_duplicate)},
        )

    similar_story = _mapping(resolved_context.get("similar_story"))
    has_similar_story = _truthy(similar_story.get("similar_story")) or bool(
        _text(similar_story.get("representative_news_item_id")) or _text(similar_story.get("story_key"))
    )
    if has_similar_story:
        representative_id = _text(similar_story.get("representative_news_item_id")) or representative_id
        material_delta = _mapping(resolved_context.get("material_delta"))
        if _truthy(material_delta.get("has_delta")):
            return NewsItemAgentAdmission(
                eligible=True,
                status="eligible_refresh",
                reason=_text(material_delta.get("reason")) or "material_delta",
                representative_news_item_id=representative_id,
                basis={**base_basis, "similar_story": dict(similar_story), "material_delta": dict(material_delta)},
            )
        status: NewsItemAgentAdmissionStatus = (
            "similar_story_burst" if _truthy(similar_story.get("burst")) else "similar_story_covered"
        )
        return _blocked(
            status,
            _text(similar_story.get("reason")) or status,
            representative_id,
            {**base_basis, "similar_story": dict(similar_story), "material_delta": dict(material_delta)},
        )

    return NewsItemAgentAdmission(
        eligible=True,
        status="eligible",
        reason="provider_score_high",
        representative_news_item_id=representative_id,
        basis=base_basis,
    )


def _blocked(
    status: NewsItemAgentAdmissionStatus,
    reason: str,
    representative_news_item_id: str,
    basis: Mapping[str, Any],
) -> NewsItemAgentAdmission:
    return NewsItemAgentAdmission(
        eligible=False,
        status=status,
        reason=reason,
        representative_news_item_id=representative_news_item_id,
        basis=dict(basis),
    )


def _context_mapping(context: NewsItemAgentAdmissionContext | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(context, NewsItemAgentAdmissionContext):
        return {
            "exact_duplicate": dict(context.exact_duplicate),
            "similar_story": dict(context.similar_story),
            "material_delta": dict(context.material_delta),
        }
    return _mapping(context)


def _source_suppressed(item: Mapping[str, Any]) -> bool:
    if item.get("source_enabled") is False or item.get("enabled") is False:
        return True
    status = _text(item.get("source_quality_status")).casefold()
    return status in {"disabled", "suppressed", "blocked"}


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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return bool(value)


__all__ = [
    "NEWS_ITEM_AGENT_MAX_PUBLISHED_AGE_MS",
    "NEWS_ITEM_AGENT_MIN_PROVIDER_SCORE",
    "NewsItemAgentAdmission",
    "NewsItemAgentAdmissionContext",
    "NewsItemAgentAdmissionStatus",
    "decide_news_item_agent_admission",
]
