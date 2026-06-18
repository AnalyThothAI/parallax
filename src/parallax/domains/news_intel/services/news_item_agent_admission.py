from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel.services.news_market_scope import classify_news_market_scope
from parallax.domains.news_intel.services.news_material_delta import NewsMaterialDelta, decide_news_material_delta
from parallax.domains.news_intel.services.news_story_similarity import decide_news_story_similarity
from parallax.domains.news_intel.types.news_item_agent_admission import (
    NewsItemAgentAdmission,
    NewsItemAgentAdmissionContext,
    NewsItemAgentAdmissionStatus,
)

_PROVIDER_RATING_AGENT_MIN_SCORE = 80


def decide_news_item_agent_admission(
    *,
    item: Mapping[str, Any],
    entities: Sequence[Mapping[str, Any]],
    token_mentions: Sequence[Mapping[str, Any]],
    fact_candidates: Sequence[Mapping[str, Any]],
    context: NewsItemAgentAdmissionContext,
    now_ms: int,
) -> NewsItemAgentAdmission:
    news_item_id = str(item.get("news_item_id") or "")
    market_scope = classify_news_market_scope(
        item=item,
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
    )
    base_basis: dict[str, Any] = {
        "market_scope": list(market_scope.scope),
        "market_scope_primary": market_scope.primary,
        "market_scope_basis": market_scope.basis,
    }

    base = _base_gate(
        item=item,
        now_ms=now_ms,
        basis=base_basis,
    )
    if base is not None:
        return base
    provider_rating_gate = _provider_rating_gate(item=item, news_item_id=news_item_id, basis=base_basis)
    if provider_rating_gate is not None:
        return provider_rating_gate

    similarity = decide_news_story_similarity(
        item=item,
        exact_duplicate_candidates=_representable_exact_duplicate_candidates(context.exact_duplicate_candidates),
        story_candidates=context.story_candidates,
    )
    base_basis["similarity"] = _similarity_payload(similarity)
    if similarity.exact_duplicate:
        return NewsItemAgentAdmission(
            eligible=False,
            status="exact_duplicate",
            reason=similarity.reason,
            representative_news_item_id=similarity.representative_news_item_id,
            basis=base_basis,
        )

    if similarity.similar_story:
        representative = _representative_candidate(
            similarity.representative_news_item_id,
            context.story_candidates,
        )
        material_delta = _mapping(context.material_delta)
        delta = (
            _material_delta_from_context(material_delta)
            if material_delta
            else decide_news_material_delta(
                item=item,
                representative_item=representative,
                entities=entities,
                representative_entities=_list_of_mappings((representative or {}).get("entities")),
                fact_candidates=fact_candidates,
                representative_fact_candidates=_list_of_mappings((representative or {}).get("fact_candidates")),
            )
        )
        base_basis["material_delta"] = {
            "has_delta": delta.has_delta,
            "reasons": delta.reasons,
            "evidence": delta.evidence,
        }
        if delta.has_delta:
            return NewsItemAgentAdmission(
                eligible=True,
                status="eligible_refresh",
                reason="material_delta",
                representative_news_item_id=news_item_id,
                basis=base_basis,
            )
        status: NewsItemAgentAdmissionStatus = (
            "similar_story_burst" if len(context.story_candidates) >= 3 else "similar_story_covered"
        )
        return NewsItemAgentAdmission(
            eligible=False,
            status=status,
            reason=status,
            representative_news_item_id=similarity.representative_news_item_id,
            basis=base_basis,
        )

    return NewsItemAgentAdmission(
        eligible=True,
        status="eligible",
        reason="eligible",
        representative_news_item_id=news_item_id,
        basis=base_basis,
    )


def _base_gate(
    *,
    item: Mapping[str, Any],
    now_ms: int,
    basis: dict[str, Any],
) -> NewsItemAgentAdmission | None:
    news_item_id = str(item.get("news_item_id") or "")
    if str(item.get("lifecycle_status") or "").strip().lower() != "processed":
        return _skip("needs_review", "item_not_processed", news_item_id, basis)
    if not _mapping(item.get("content_classification_json")):
        return _skip("needs_review", "classification_missing", news_item_id, basis)
    if _is_source_suppressed(item):
        return _skip("source_suppressed", "source_suppressed", news_item_id, basis)

    published_at_ms = _optional_int(item.get("published_at_ms"))
    if published_at_ms is None:
        return _skip("needs_review", "published_at_missing", news_item_id, basis)
    age_ms = int(now_ms) - int(published_at_ms)
    if age_ms < 0:
        return _skip("needs_review", "published_in_future", news_item_id, basis)
    return None


def _provider_rating_gate(
    *,
    item: Mapping[str, Any],
    news_item_id: str,
    basis: dict[str, Any],
) -> NewsItemAgentAdmission | None:
    rating = _provider_rating(item)
    basis["provider_rating"] = rating
    score = rating.get("score")
    if score is None:
        return _skip("needs_review", "provider_rating_missing", news_item_id, basis)
    if int(score) < _PROVIDER_RATING_AGENT_MIN_SCORE:
        return _skip("needs_review", "provider_rating_below_threshold", news_item_id, basis)
    return None


def _provider_rating(item: Mapping[str, Any]) -> dict[str, Any]:
    signal = _mapping(item.get("provider_signal_json"))
    score = _optional_int(signal.get("score"))
    return {
        "score": score,
        "min_score": _PROVIDER_RATING_AGENT_MIN_SCORE,
        "provider": str(signal.get("provider") or "").strip() or None,
        "status": str(signal.get("status") or "").strip() or None,
        "method": str(signal.get("method") or "").strip() or None,
    }


def _skip(
    status: NewsItemAgentAdmissionStatus,
    reason: str,
    news_item_id: str,
    basis: dict[str, Any],
) -> NewsItemAgentAdmission:
    return NewsItemAgentAdmission(
        eligible=False,
        status=status,
        reason=reason,
        representative_news_item_id=news_item_id,
        basis=basis,
    )


def _representative_candidate(
    representative_news_item_id: str,
    candidates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for candidate in candidates:
        if str(candidate.get("news_item_id") or "") == representative_news_item_id:
            return candidate
    return candidates[0] if candidates else None


def _representable_exact_duplicate_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    return [candidate for candidate in candidates if _can_represent_exact_duplicate(candidate)]


def _can_represent_exact_duplicate(candidate: Mapping[str, Any]) -> bool:
    if str(candidate.get("lifecycle_status") or "").strip().lower() != "processed":
        return False
    if str(candidate.get("agent_admission_status") or "").strip().lower() in {"eligible", "eligible_refresh"}:
        return True
    current_brief = _optional_mapping(candidate.get("current_brief"))
    return str((current_brief or {}).get("status") or "").strip().lower() == "ready"


def _similarity_payload(value: Any) -> dict[str, Any]:
    return {
        "exact_duplicate": bool(value.exact_duplicate),
        "similar_story": bool(value.similar_story),
        "reason": str(value.reason),
        "representative_news_item_id": str(value.representative_news_item_id),
        "story_key": str(value.story_key),
        "evidence": dict(value.evidence),
    }


def _is_source_suppressed(item: Mapping[str, Any]) -> bool:
    if item.get("enabled") is False or item.get("source_enabled") is False:
        return True
    policy_status = str(item.get("source_policy_status") or "").strip().lower()
    if policy_status in {"disabled", "suppressed", "blocked"}:
        return True
    policy = _mapping(item.get("source_policy_json"))
    return str(policy.get("status") or "").strip().lower() in {"disabled", "suppressed", "blocked"}


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


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _mapping(value)


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list | tuple):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [dict(row) for row in parsed if isinstance(row, Mapping)]
    return []


def _material_delta_from_context(value: Mapping[str, Any]) -> NewsMaterialDelta:
    return NewsMaterialDelta(
        has_delta=bool(value.get("has_delta")),
        reasons=[str(reason) for reason in _json_list(value.get("reasons"))],
        evidence=_mapping(value.get("evidence")),
    )


def _json_list(value: Any) -> list[Any]:
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
    "NewsItemAgentAdmission",
    "NewsItemAgentAdmissionContext",
    "NewsItemAgentAdmissionStatus",
    "decide_news_item_agent_admission",
]
