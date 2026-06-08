from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from typing import Any

from parallax.domains.news_intel.runtime.news_projection_work import (
    enqueue_item_brief_work,
    enqueue_page_reprojection,
)
from parallax.domains.news_intel.services.news_item_agent_admission import (
    decide_news_item_agent_admission,
)
from parallax.domains.news_intel.services.news_item_agent_policy import news_item_agent_brief_priority
from parallax.domains.news_intel.services.news_market_scope import classify_news_market_scope
from parallax.domains.news_intel.services.news_story_identity import build_news_story_identity
from parallax.domains.news_intel.types.news_item_agent_admission import (
    NewsItemAgentAdmission,
    NewsItemAgentAdmissionContext,
)

_REPAIR_REASON = "ops_news_market_signal_repair"


def repair_news_market_signal(
    repos: Any,
    *,
    since_hours: float,
    min_score: int,
    execute: bool,
    now_ms: int,
) -> dict[str, Any]:
    since_ms = int(now_ms) - int(max(0.0, float(since_hours)) * 3_600_000)
    rows = [
        dict(row)
        for row in repos.news.list_news_market_signal_repair_candidates(
            since_ms=since_ms,
            min_score=max(0, int(min_score)),
        )
    ]
    prepared = [_prepare_repair_item(row) for row in rows]
    contexts = repos.news.load_agent_admission_repair_contexts(
        items=[decision["item"] for decision in prepared],
        now_ms=int(now_ms),
    )
    decisions = [
        _repair_decision(
            decision,
            context=_mapping(contexts.get(str(decision["news_item_id"]))),
            now_ms=int(now_ms),
        )
        for decision in prepared
    ]
    eligible = [decision for decision in decisions if decision["admission"].eligible]

    updated_items = 0
    enqueued_dirty_targets = 0
    if execute and decisions:
        with _transaction(repos):
            for decision in decisions:
                updated_items += int(
                    repos.news.update_item_market_scope_and_agent_admission(
                        news_item_id=decision["news_item_id"],
                        market_scope=decision["market_scope"],
                        story_identity=decision["story_identity"],
                        admission=decision["admission"],
                        now_ms=int(now_ms),
                        commit=False,
                    )
                )
            watermarks = {decision["news_item_id"]: decision["source_watermark_ms"] for decision in decisions}
            enqueued_dirty_targets += enqueue_page_reprojection(
                repos,
                news_item_ids=[decision["news_item_id"] for decision in decisions],
                source_watermark_ms_by_news_item_id=watermarks,
                reason=_REPAIR_REASON,
                now_ms=int(now_ms),
                commit=False,
            )
            enqueued_dirty_targets += enqueue_item_brief_work(
                repos,
                news_item_ids=[_brief_target_id(decision) for decision in eligible],
                priority_by_news_item_id=_brief_priorities(eligible),
                source_watermark_ms_by_news_item_id=_brief_watermarks(eligible),
                reason=_REPAIR_REASON,
                now_ms=int(now_ms),
                commit=False,
            )

    status_counts = Counter(str(decision["admission"].status) for decision in decisions)
    reason_counts = Counter(str(decision["admission"].reason) for decision in decisions)
    scope_counts = Counter(str(decision["market_scope"].primary) for decision in decisions)
    return {
        "dry_run": not bool(execute),
        "since_ms": since_ms,
        "min_score": max(0, int(min_score)),
        "matched_items": len(decisions),
        "updated_items": int(updated_items),
        "enqueued_dirty_targets": int(enqueued_dirty_targets),
        "eligible_items": len(eligible),
        "suppressed_items": len(decisions) - len(eligible),
        "agent_admission_status_counts": dict(sorted(status_counts.items())),
        "agent_admission_reason_counts": dict(sorted(reason_counts.items())),
        "market_scope_counts": dict(sorted(scope_counts.items())),
    }


def _prepare_repair_item(row: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    token_mentions = _dict_list(row.get("token_mentions_json"))
    fact_candidates = _dict_list(row.get("fact_candidates_json"))
    entities = _dict_list(row.get("entities_json"))
    market_scope = classify_news_market_scope(
        item=item,
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
    )
    market_scope_payload = market_scope.to_payload()
    story_identity = build_news_story_identity(
        item=item,
        token_mentions=token_mentions,
        fact_candidates=fact_candidates,
        market_scope=market_scope_payload,
    )
    item.update(
        {
            "market_scope_json": market_scope_payload,
            "story_key": story_identity.story_key,
            "story_identity_json": {
                "story_key": story_identity.story_key,
                "confidence": story_identity.confidence,
                "basis": story_identity.basis,
                "version": story_identity.version,
            },
            "story_identity_version": story_identity.version,
        }
    )
    return {
        "news_item_id": str(row.get("news_item_id") or ""),
        "source_watermark_ms": _int(row.get("source_watermark_ms"), default=_int(row.get("published_at_ms"))),
        "item": item,
        "entities": entities,
        "token_mentions": token_mentions,
        "fact_candidates": fact_candidates,
        "market_scope": market_scope,
        "story_identity": story_identity,
    }


def _repair_decision(
    decision: Mapping[str, Any],
    *,
    context: Mapping[str, Any],
    now_ms: int,
) -> dict[str, Any]:
    admission = decide_news_item_agent_admission(
        item=decision["item"],
        entities=decision["entities"],
        token_mentions=decision["token_mentions"],
        fact_candidates=decision["fact_candidates"],
        context=_agent_admission_context(context, item=decision["item"]),
        now_ms=now_ms,
    )
    return {**dict(decision), "admission": admission}


def _brief_target_id(decision: Mapping[str, Any]) -> str:
    admission = decision["admission"]
    if isinstance(admission, NewsItemAgentAdmission):
        return admission.representative_news_item_id or str(decision["news_item_id"])
    return str(decision["news_item_id"])


def _brief_priorities(decisions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    priorities: dict[str, int] = {}
    for decision in decisions:
        target_id = _brief_target_id(decision)
        priorities[target_id] = news_item_agent_brief_priority(
            item=decision["item"],
        )
    return priorities


def _brief_watermarks(decisions: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    watermarks: dict[str, int] = {}
    for decision in decisions:
        target_id = _brief_target_id(decision)
        source_watermark_ms = _int(decision.get("source_watermark_ms"))
        watermarks[target_id] = max(watermarks.get(target_id, 0), source_watermark_ms)
    return watermarks


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [dict(row) for row in parsed if isinstance(row, Mapping)]
    return []


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


def _agent_admission_context(context: Mapping[str, Any], *, item: Mapping[str, Any]) -> NewsItemAgentAdmissionContext:
    exact_candidates = _dict_list(context.get("exact_duplicate_candidates"))
    story_candidates = _dict_list(context.get("story_candidates"))
    exact_duplicate = _mapping(context.get("exact_duplicate"))
    similar_story = _mapping(context.get("similar_story"))
    if exact_duplicate and not exact_candidates:
        exact_candidates = [_candidate_from_exact_duplicate(exact_duplicate, item=item)]
    if similar_story and not story_candidates:
        story_candidates = [_candidate_from_similar_story(similar_story)]
    return NewsItemAgentAdmissionContext(
        current_brief=_mapping(context.get("current_brief")) or None,
        exact_duplicate_candidates=exact_candidates,
        story_candidates=story_candidates,
        material_delta=_mapping(context.get("material_delta")),
    )


def _candidate_from_exact_duplicate(value: Mapping[str, Any], *, item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "news_item_id": str(value.get("representative_news_item_id") or value.get("matched_news_item_id") or ""),
        "story_key": str(value.get("matched_story_key") or value.get("story_key") or ""),
        "content_hash": str(value.get("content_hash") or item.get("content_hash") or ""),
        "canonical_item_key": str(value.get("canonical_item_key") or item.get("canonical_item_key") or ""),
        "canonical_url": str(value.get("canonical_url") or item.get("canonical_url") or ""),
        "url_identity_kind": str(value.get("url_identity_kind") or item.get("url_identity_kind") or "article"),
        "provider_article_keys_json": value.get("provider_article_keys_json")
        or value.get("provider_article_keys")
        or item.get("provider_article_keys_json")
        or item.get("provider_article_keys")
        or [],
        "lifecycle_status": str(value.get("lifecycle_status") or "processed"),
        "agent_admission_status": str(value.get("agent_admission_status") or "eligible"),
        "current_brief": _mapping(value.get("current_brief")) or {"status": "ready"},
    }


def _candidate_from_similar_story(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "news_item_id": str(value.get("representative_news_item_id") or ""),
        "story_key": str(value.get("story_key") or ""),
        "title_fingerprint": str(value.get("title_fingerprint") or ""),
        "current_brief": _mapping(value.get("current_brief")) or {"status": value.get("fresh_brief_status") or "ready"},
    }


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _transaction(repos: Any) -> Any:
    transaction = getattr(getattr(repos, "conn", None), "transaction", None)
    if transaction is None:
        return nullcontext()
    return transaction()


__all__ = ["repair_news_market_signal"]
