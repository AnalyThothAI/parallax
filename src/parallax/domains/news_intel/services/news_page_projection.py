from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION

_RESOLVED_TOKEN_STATUSES = frozenset({"exact_address", "known_symbol", "unique_by_context"})
_IGNORED_TOKEN_STATUSES = frozenset({"non_crypto", "nil"})


def build_news_page_row(
    *,
    item: dict[str, Any],
    token_mentions: list[dict[str, Any]],
    fact_candidates: list[dict[str, Any]],
    agent_brief: dict[str, Any] | None = None,
    story: dict[str, Any] | None = None,
    computed_at_ms: int,
) -> dict[str, Any]:
    news_item_id = str(item["news_item_id"])
    story_payload = _story_payload(story=story, item=item, news_item_id=news_item_id)
    story_key = str(story_payload.get("story_key") or item.get("story_key") or "")
    representative_news_item_id = str(story_payload.get("representative_news_item_id") or news_item_id)
    analysis_admission_status = str(item.get("analysis_admission_status") or "needs_review")
    analysis_admission_reason = str(item.get("analysis_admission_reason") or "")
    analysis_admission = _analysis_admission_payload(
        item=item,
        status=analysis_admission_status,
        reason=analysis_admission_reason,
    )
    provider_signal = _json_object(item.get("provider_signal_json"))
    token_impacts = _provider_token_impacts(item.get("provider_token_impacts_json"))
    impacts_by_symbol = {
        str(impact.get("symbol") or "").upper(): impact for impact in token_impacts if str(impact.get("symbol") or "")
    }
    token_lanes = [_merge_provider_impact(_token_lane(row), impacts_by_symbol) for row in token_mentions]
    fact_lanes = [_fact_lane(row) for row in fact_candidates]
    source_payload = _source_payload(item)
    agent_payload = _compact_agent_brief(
        agent_brief,
        item=item,
    )
    agent_status = str(agent_payload.get("status") or "pending")
    content_tags = _json_list(item.get("content_tags_json"))
    content_classification = _json_object(item.get("content_classification_json"))
    return {
        "row_id": _stable_id("news-page-row", NEWS_PAGE_PROJECTION_VERSION, story_key or news_item_id),
        "news_item_id": news_item_id,
        "representative_news_item_id": representative_news_item_id,
        "story_key": story_key,
        "story": story_payload,
        "latest_at_ms": int(item.get("published_at_ms") or computed_at_ms),
        "lifecycle_status": _lifecycle(item=item, token_lanes=token_lanes, fact_lanes=fact_lanes),
        "headline": str(item.get("title") or ""),
        "summary": str(item.get("summary") or ""),
        "source_domain": str(item.get("source_domain") or ""),
        "canonical_url": _public_url(item.get("canonical_url")),
        "token_lanes": token_lanes,
        "fact_lanes": fact_lanes,
        "signal": _page_signal(
            item=item,
            provider_signal=provider_signal,
            agent_signal=agent_payload,
            analysis_admission_status=analysis_admission_status,
        ),
        "token_impacts": token_impacts,
        "content_class": item.get("content_class"),
        "content_tags": content_tags,
        "content_classification": content_classification,
        "source": source_payload,
        "agent_brief": agent_payload,
        "agent_status": agent_status,
        "agent_brief_computed_at_ms": agent_payload.get("computed_at_ms"),
        "analysis_admission_status": analysis_admission_status,
        "analysis_admission_reason": analysis_admission_reason,
        "analysis_admission": analysis_admission,
        "duplicate_count": int(story_payload.get("member_count") or 1) if story_payload else 1,
        "source_ids_json": _json_list(story_payload.get("source_ids")) if story_payload else [],
        "source_domains_json": _json_list(story_payload.get("source_domains")) if story_payload else [],
        "provider_article_keys_json": _json_list(story_payload.get("provider_article_keys")) if story_payload else [],
        "computed_at_ms": int(computed_at_ms),
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }


def _token_lane(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("resolution_status") or "")
    return {
        "lane": _token_lane_name(status),
        "resolution_status": status,
        "symbol": row.get("display_symbol") or row.get("observed_symbol"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "display_name": row.get("display_name"),
        "reason_codes": _json_list(row.get("reason_codes_json")),
        "candidate_targets": _json_list(row.get("candidate_targets_json")),
    }


def _provider_token_impacts(value: Any) -> list[dict[str, Any]]:
    impacts: list[dict[str, Any]] = []
    for impact in _json_list(value):
        if not isinstance(impact, Mapping):
            continue
        symbol = str(impact.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        impacts.append(
            _compact_mapping(
                {
                    "symbol": symbol,
                    "market_type": impact.get("market_type"),
                    "score": _optional_int_or_none(impact.get("score")),
                    "signal": impact.get("signal"),
                    "grade": impact.get("grade"),
                }
            )
        )
    return impacts


def _merge_provider_impact(
    lane: dict[str, Any],
    impacts_by_symbol: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    symbol = str(lane.get("symbol") or "").upper()
    impact = impacts_by_symbol.get(symbol)
    if not impact:
        return lane
    return _compact_mapping(
        {
            **lane,
            "provider_signal": impact.get("signal"),
            "provider_score": _optional_int_or_none(impact.get("score")),
            "provider_grade": impact.get("grade"),
            "market_type": impact.get("market_type"),
        }
    )


def _token_lane_name(status: str) -> str:
    if status in _RESOLVED_TOKEN_STATUSES:
        return "resolved"
    if status in _IGNORED_TOKEN_STATUSES:
        return "ignored"
    return "attention"


def _public_url(value: Any) -> str:
    url = str(value or "").strip()
    if url.startswith(("http://", "https://")):
        return url
    return ""


def _fact_lane(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "fact_candidate_id": row.get("fact_candidate_id"),
        "event_type": row.get("event_type"),
        "claim": row.get("claim"),
        "realis": row.get("realis"),
        "status": row.get("validation_status"),
        "rejection_reasons": _json_list(row.get("rejection_reasons_json")),
        "affected_targets": _json_list(row.get("affected_targets_json")),
    }


def _lifecycle(
    *,
    item: dict[str, Any],
    token_lanes: list[dict[str, Any]],
    fact_lanes: list[dict[str, Any]],
) -> str:
    if any(row.get("status") == "attention" for row in fact_lanes):
        return "attention"
    if any(row.get("lane") == "attention" for row in token_lanes):
        return "attention"
    if any(row.get("status") == "accepted" for row in fact_lanes):
        return "accepted"
    if fact_lanes:
        return "fact_candidate"
    if token_lanes:
        return "entity_extracted"
    return str(item.get("lifecycle_status") or "raw")


def _source_payload(item: dict[str, Any]) -> dict[str, Any]:
    return _compact_mapping(
        {
            "source_id": item.get("source_id"),
            "provider_type": item.get("provider_type"),
            "source_domain": item.get("source_domain"),
            "source_name": item.get("source_name"),
            "source_role": item.get("source_role"),
            "trust_tier": item.get("trust_tier"),
            "coverage_tags": _json_list(item.get("coverage_tags_json")),
            "source_quality_status": item.get("source_quality_status") or "unknown",
        }
    )


def _story_payload(*, story: Mapping[str, Any] | None, item: Mapping[str, Any], news_item_id: str) -> dict[str, Any]:
    story_key = str((story or {}).get("story_key") or item.get("story_key") or "").strip()
    if not story and not story_key:
        return {}
    source_domains = _json_list((story or {}).get("source_domains"))
    if not source_domains:
        source_domains = _json_list(item.get("source_domains_json"))
    if not source_domains and item.get("source_domain"):
        source_domains = [str(item.get("source_domain"))]
    member_news_item_ids = _json_list((story or {}).get("member_news_item_ids"))
    if not member_news_item_ids:
        member_news_item_ids = [news_item_id]
    payload = {
        **dict(story or {}),
        "story_key": story_key,
        "representative_news_item_id": str((story or {}).get("representative_news_item_id") or news_item_id),
        "member_news_item_ids": [str(member_id) for member_id in member_news_item_ids],
        "member_count": int((story or {}).get("member_count") or len(member_news_item_ids) or 1),
        "source_domains": [str(domain) for domain in source_domains if str(domain)],
    }
    source_ids = [str(source_id) for source_id in _json_list((story or {}).get("source_ids")) if str(source_id)]
    if source_ids:
        payload["source_ids"] = source_ids
    provider_article_keys = [
        str(provider_key)
        for provider_key in _json_list((story or {}).get("provider_article_keys"))
        if str(provider_key)
    ]
    if provider_article_keys:
        payload["provider_article_keys"] = provider_article_keys
    return _compact_mapping(payload)


def _analysis_admission_payload(
    *,
    item: Mapping[str, Any],
    status: str,
    reason: str,
) -> dict[str, Any]:
    payload = _json_object(item.get("analysis_admission_json"))
    if not payload:
        payload = {"status": status, "reason": reason}
    else:
        payload.setdefault("status", status)
        payload.setdefault("reason", reason)
    return payload


def _compact_agent_brief(
    agent_brief: Mapping[str, Any] | None,
    *,
    item: Mapping[str, Any],
) -> dict[str, Any]:
    if agent_brief is None:
        return _missing_agent_brief_state(item=item)
    brief_json = _json_object(agent_brief.get("brief_json") if isinstance(agent_brief, Mapping) else None)
    bull_view = _json_object(brief_json.get("bull_view"))
    bear_view = _json_object(brief_json.get("bear_view"))
    payload = _compact_mapping(
        {
            "status": agent_brief.get("status") or brief_json.get("status") or "pending",
            "direction": agent_brief.get("direction") or brief_json.get("direction"),
            "decision_class": agent_brief.get("decision_class") or brief_json.get("decision_class"),
            "title_zh": brief_json.get("title_zh"),
            "summary_zh": brief_json.get("summary_zh"),
            "market_read_zh": brief_json.get("market_read_zh"),
            "bull_strength": bull_view.get("strength"),
            "bear_strength": bear_view.get("strength"),
            "data_gap_count": len(_json_list(brief_json.get("data_gaps"))),
            "computed_at_ms": _optional_int(agent_brief.get("computed_at_ms")),
            "agent_run_id": agent_brief.get("agent_run_id"),
            "schema_version": agent_brief.get("schema_version") or brief_json.get("schema_version"),
            "prompt_version": agent_brief.get("prompt_version") or brief_json.get("prompt_version"),
            "validator_version": agent_brief.get("validator_version") or brief_json.get("validator_version"),
            "artifact_version_hash": agent_brief.get("artifact_version_hash"),
            "input_hash": agent_brief.get("input_hash"),
            "bull_view": bull_view or None,
            "bear_view": bear_view or None,
            "affected_assets": _agent_affected_assets(brief_json.get("affected_assets")),
        }
    )
    return payload or _missing_agent_brief_state(item=item)


def _missing_agent_brief_state(
    *,
    item: Mapping[str, Any],
) -> dict[str, str]:
    requirement_status = str(item.get("agent_requirement_status") or "").strip().lower()
    requirement_reason = str(item.get("agent_requirement_reason") or "").strip() or "item_not_processed"
    return {
        "status": "pending" if requirement_status == "required" else "not_required",
        "eligibility_reason": "eligible" if requirement_status == "required" else requirement_reason,
        "requirement_status": requirement_status or "not_required",
        "requirement_reason": "eligible" if requirement_status == "required" else requirement_reason,
    }


def _agent_affected_assets(value: Any) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for asset in _json_list(value):
        if not isinstance(asset, Mapping):
            continue
        symbol = str(asset.get("symbol") or asset.get("asset") or "").strip().upper()
        if not symbol:
            continue
        assets.append(
            _compact_mapping(
                {
                    "symbol": symbol,
                    "target_id": asset.get("target_id"),
                    "target_type": asset.get("target_type"),
                    "resolution_status": asset.get("resolution_status"),
                    "impact_direction": asset.get("impact_direction"),
                    "reason_zh": asset.get("reason_zh"),
                }
            )
        )
    return assets[:12]


def _page_signal(
    *,
    item: Mapping[str, Any],
    provider_signal: Mapping[str, Any],
    agent_signal: Mapping[str, Any],
    analysis_admission_status: str,
) -> dict[str, Any]:
    provider_payload = _provider_signal_payload(provider_signal)
    agent_requirement = _agent_requirement_signal(item)
    provider_score = _optional_int_or_none(provider_payload.get("score")) if provider_payload else None
    if str(agent_signal.get("status") or "") == "ready":
        direction = str(agent_signal.get("direction") or "neutral")
        return _signal_with_independent_state(
            {
                "source": "agent",
                "status": "ready",
                "direction": direction,
                "label_zh": _direction_label(direction),
                "score": provider_score,
                "grade": provider_payload.get("grade") if provider_payload else None,
                "title_zh": agent_signal.get("title_zh"),
                "summary_zh": agent_signal.get("summary_zh"),
                "method": "news_item_brief",
            },
            provider_signal=provider_payload,
            agent_signal=agent_signal,
            agent_requirement=agent_requirement,
            analysis_admission_status=analysis_admission_status,
        )
    if provider_payload:
        return _signal_with_independent_state(
            provider_payload,
            provider_signal=provider_payload,
            agent_signal=agent_signal,
            agent_requirement=agent_requirement,
            analysis_admission_status=analysis_admission_status,
        )
    return _signal_with_independent_state(
        {
            "source": "partial",
            "status": "partial",
            "direction": "neutral",
            "label_zh": "中性",
            "method": "pending",
        },
        provider_signal=None,
        agent_signal=agent_signal,
        agent_requirement=agent_requirement,
        analysis_admission_status=analysis_admission_status,
    )


def _provider_signal_payload(provider_signal: Mapping[str, Any]) -> dict[str, Any] | None:
    if provider_signal.get("source") != "provider":
        return None
    return _compact_mapping(
        {
            "source": "provider",
            "provider": provider_signal.get("provider") or "opennews",
            "status": provider_signal.get("status") or "partial",
            "direction": provider_signal.get("direction") or "neutral",
            "label_zh": provider_signal.get("label_zh")
            or _direction_label(str(provider_signal.get("direction") or "neutral")),
            "signal": provider_signal.get("signal"),
            "score": _optional_int_or_none(provider_signal.get("score")),
            "grade": provider_signal.get("grade"),
            "summary_zh": provider_signal.get("summary_zh"),
            "summary_en": provider_signal.get("summary_en"),
            "method": provider_signal.get("method") or "opennews.provider_signal",
        }
    )


def _signal_with_independent_state(
    signal: Mapping[str, Any],
    *,
    provider_signal: Mapping[str, Any] | None,
    agent_signal: Mapping[str, Any],
    agent_requirement: Mapping[str, Any],
    analysis_admission_status: str,
) -> dict[str, Any]:
    agent_status = str(agent_signal.get("status") or "pending")
    provider_score = _optional_int_or_none(provider_signal.get("score")) if provider_signal else None
    in_app_eligible = _alert_eligible(
        agent_signal=agent_signal,
        provider_score=provider_score,
        analysis_admission_status=analysis_admission_status,
    )
    external_push_ready, external_push_block_reason = _external_push_readiness(
        agent_signal,
        analysis_admission_status=analysis_admission_status,
    )
    return {
        "display_signal": _compact_mapping(signal),
        "provider_signal": dict(provider_signal) if provider_signal else None,
        "agent_signal": dict(agent_signal),
        "agent_requirement": dict(agent_requirement),
        "alert_eligibility": _compact_mapping(
            {
                "agent_status": agent_status,
                "decision_class": agent_signal.get("decision_class"),
                "provider_status": provider_signal.get("status") if provider_signal else None,
                "provider_score": provider_score,
                "in_app_eligible": in_app_eligible,
                "external_push_ready": external_push_ready,
                "external_push_block_reason": external_push_block_reason,
                "external_push_basis": "agent_brief" if external_push_ready else None,
            }
        ),
    }


def _agent_requirement_signal(item: Mapping[str, Any]) -> dict[str, Any]:
    requirement_json = _json_object(item.get("agent_requirement_json"))
    basis = _json_object(requirement_json.get("basis"))
    return _compact_mapping(
        {
            "status": item.get("agent_requirement_status") or requirement_json.get("status") or "not_required",
            "reason": item.get("agent_requirement_reason") or requirement_json.get("reason") or "item_not_processed",
            "priority": _optional_int_or_none(
                item.get("agent_requirement_priority") or requirement_json.get("priority")
            ),
            "version": item.get("agent_requirement_version") or requirement_json.get("version"),
            "basis": basis,
        }
    )


def _alert_eligible(
    *,
    agent_signal: Mapping[str, Any],
    provider_score: int | None,
    analysis_admission_status: str,
) -> bool:
    if analysis_admission_status != "admitted":
        return False
    if str(agent_signal.get("status") or "") == "ready" and str(agent_signal.get("decision_class") or "") in {
        "driver",
        "watch",
    }:
        return True
    return provider_score is not None and provider_score >= 70


def _external_push_readiness(
    agent_signal: Mapping[str, Any],
    *,
    analysis_admission_status: str,
) -> tuple[bool, str | None]:
    if analysis_admission_status != "admitted":
        return False, "analysis_not_admitted"
    agent_status = str(agent_signal.get("status") or "")
    if agent_status == "not_required":
        return False, str(agent_signal.get("eligibility_reason") or "agent_not_required")
    if agent_status != "ready":
        return False, "agent_brief_not_ready"
    if not _agent_publishable_summary(agent_signal):
        return False, "agent_brief_missing_summary"
    return True, None


def _agent_publishable_summary(agent_signal: Mapping[str, Any]) -> bool:
    return bool(str(agent_signal.get("summary_zh") or agent_signal.get("market_read_zh") or "").strip())


def _direction_label(direction: str) -> str:
    if direction == "bullish":
        return "利好"
    if direction == "bearish":
        return "利空"
    return "中性"


def _json_object(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return _compact_mapping(dict(value))


def _compact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if item is not None}


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return []


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
