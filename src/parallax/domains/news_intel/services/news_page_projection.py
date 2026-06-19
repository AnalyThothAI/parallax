from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.types.news_page_search import build_news_page_search_text

_RESOLVED_TOKEN_STATUSES = frozenset({"exact_address", "known_symbol", "unique_by_context"})
_IGNORED_TOKEN_STATUSES = frozenset({"non_crypto", "nil"})
_AGENT_NOTIFICATION_ADMISSION_STATUSES = frozenset({"eligible", "eligible_refresh"})
_NOTIFIABLE_DECISION_CLASSES = frozenset({"driver", "watch"})


def build_news_page_row(
    *,
    item: dict[str, Any],
    token_mentions: list[dict[str, Any]],
    fact_candidates: list[dict[str, Any]],
    story: dict[str, Any] | None = None,
    agent_brief: dict[str, Any] | None = None,
    computed_at_ms: int,
) -> dict[str, Any]:
    news_item_id = str(item["news_item_id"])
    story_payload = _story_payload(story=story, news_item_id=news_item_id)
    story_key = str(story_payload["story_key"])
    representative_news_item_id = str(story_payload["representative_news_item_id"])
    market_scope = _market_scope_payload(item, news_item_id=news_item_id)
    agent_admission_status = _required_item_text(item, "agent_admission_status", news_item_id=news_item_id)
    agent_admission_reason = _required_item_text(item, "agent_admission_reason", news_item_id=news_item_id)
    agent_representative_news_item_id = _required_item_text(
        item,
        "agent_representative_news_item_id",
        news_item_id=news_item_id,
    )
    agent_admission = _agent_admission_payload(item=item, news_item_id=news_item_id)
    _require_matching_agent_admission(
        agent_admission,
        "status",
        agent_admission_status,
        news_item_id=news_item_id,
    )
    _require_matching_agent_admission(
        agent_admission,
        "reason",
        agent_admission_reason,
        news_item_id=news_item_id,
    )
    _require_matching_agent_admission(
        agent_admission,
        "representative_news_item_id",
        agent_representative_news_item_id,
        news_item_id=news_item_id,
    )
    token_lanes = [_token_lane(row) for row in token_mentions]
    fact_lanes = [_fact_lane(row) for row in fact_candidates]
    source_payload = _source_payload(item, news_item_id=news_item_id)
    agent_payload = _agent_signal_payload(
        _compact_agent_brief(agent_brief, news_item_id=news_item_id),
        admission_status=agent_admission_status,
        admission_reason=agent_admission_reason,
        representative_news_item_id=agent_representative_news_item_id,
        admission=agent_admission,
        news_item_id=news_item_id,
    )
    agent_status = _required_agent_signal_status(agent_payload, news_item_id=news_item_id)
    content_class = _required_item_text(item, "content_class", news_item_id=news_item_id)
    content_tags = _required_item_list(item, "content_tags_json", news_item_id=news_item_id)
    content_classification = _required_item_mapping(item, "content_classification_json", news_item_id=news_item_id)
    row = {
        "row_id": _stable_id("news-page-row", NEWS_PAGE_PROJECTION_VERSION, story_key),
        "news_item_id": news_item_id,
        "representative_news_item_id": representative_news_item_id,
        "story_key": story_key,
        "story": story_payload,
        "latest_at_ms": _item_published_at_ms(item),
        "lifecycle_status": _lifecycle(item=item, token_lanes=token_lanes, fact_lanes=fact_lanes),
        "headline": str(item.get("title") or ""),
        "summary": str(item.get("summary") or ""),
        "source_domain": str(item.get("source_domain") or ""),
        "canonical_url": _public_url(item.get("canonical_url")),
        "token_lanes": token_lanes,
        "fact_lanes": fact_lanes,
        "signal": _page_signal(
            agent_signal=agent_payload,
            agent_admission_status=agent_admission_status,
            market_scope=market_scope,
        ),
        "provider_rating": _provider_rating_payload(item, news_item_id=news_item_id),
        "token_impacts": [],
        "content_class": content_class,
        "content_tags": content_tags,
        "content_classification": content_classification,
        "source": source_payload,
        "agent_brief": agent_payload,
        "agent_status": agent_status,
        "agent_brief_computed_at_ms": agent_payload.get("computed_at_ms"),
        "market_scope": market_scope,
        "agent_admission_status": agent_admission_status,
        "agent_admission_reason": agent_admission_reason,
        "agent_admission": agent_admission,
        "agent_representative_news_item_id": agent_representative_news_item_id,
        "duplicate_count": int(story_payload["member_count"]),
        "source_ids_json": _json_list(story_payload.get("source_ids")),
        "source_domains_json": _json_list(story_payload["source_domains"]),
        "provider_article_keys_json": _json_list(story_payload.get("provider_article_keys")),
        "computed_at_ms": _required_positive_int(
            computed_at_ms,
            field_name="computed_at_ms",
            news_item_id=news_item_id,
        ),
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }
    row["search_text"] = build_news_page_search_text(row)
    return row


def _provider_rating_payload(item: Mapping[str, Any], *, news_item_id: str) -> dict[str, Any]:
    rating = _optional_item_mapping(item, "provider_signal_json", news_item_id=news_item_id)
    payload = _compact_mapping(
        {
            "provider": rating.get("provider"),
            "status": rating.get("status"),
            "direction": rating.get("direction"),
            "signal": rating.get("signal"),
            "score": _optional_rating_score(rating.get("score"), news_item_id=news_item_id),
            "grade": rating.get("grade"),
            "method": rating.get("method"),
        }
    )
    return payload if any(value is not None for value in payload.values()) else {}


def _token_lane(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("resolution_status") or "")
    return {
        "lane": _token_lane_name(status),
        "resolution_status": status,
        "symbol": row.get("display_symbol") or row.get("observed_symbol"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "display_name": row.get("display_name"),
        "reason_codes": _optional_lane_list(row, "reason_codes_json", lane_name="token"),
        "candidate_targets": _optional_lane_list(row, "candidate_targets_json", lane_name="token"),
    }


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
        "rejection_reasons": _optional_lane_list(row, "rejection_reasons_json", lane_name="fact"),
        "affected_targets": _optional_lane_list(row, "affected_targets_json", lane_name="fact"),
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


def _source_payload(item: dict[str, Any], *, news_item_id: str) -> dict[str, Any]:
    return _compact_mapping(
        {
            "source_id": item.get("source_id"),
            "provider_type": item.get("provider_type"),
            "source_domain": item.get("source_domain"),
            "source_name": item.get("source_name"),
            "source_role": item.get("source_role"),
            "trust_tier": item.get("trust_tier"),
            "coverage_tags": _optional_item_list(item, "coverage_tags_json", news_item_id=news_item_id),
            "source_quality_status": _required_item_text(
                item,
                "source_quality_status",
                news_item_id=news_item_id,
            ),
        }
    )


def _market_scope_payload(item: Mapping[str, Any], *, news_item_id: str) -> dict[str, Any]:
    payload = _required_item_mapping(item, "market_scope_json", news_item_id=news_item_id)
    scope = _required_payload_list(payload, "scope", payload_name="market_scope", news_item_id=news_item_id)
    primary = _required_payload_text(payload, "primary", payload_name="market_scope", news_item_id=news_item_id)
    status = _required_payload_text(payload, "status", payload_name="market_scope", news_item_id=news_item_id)
    reason = _required_payload_text(payload, "reason", payload_name="market_scope", news_item_id=news_item_id)
    basis = _required_payload_mapping(payload, "basis", payload_name="market_scope", news_item_id=news_item_id)
    version = _required_payload_text(payload, "version", payload_name="market_scope", news_item_id=news_item_id)
    return _compact_mapping(
        {
            **payload,
            "scope": scope,
            "primary": primary,
            "status": status,
            "reason": reason,
            "basis": basis,
            "version": version,
        }
    )


def _story_payload(*, story: Mapping[str, Any] | None, news_item_id: str) -> dict[str, Any]:
    if not isinstance(story, Mapping):
        raise ValueError(f"news_page_projection_story_required:{news_item_id}")
    story_key = _required_story_text(story, "story_key", news_item_id=news_item_id)
    representative_news_item_id = _required_story_text(
        story,
        "representative_news_item_id",
        news_item_id=news_item_id,
    )
    member_news_item_ids = _required_story_list(story, "member_news_item_ids", news_item_id=news_item_id)
    source_domains = _required_story_list(story, "source_domains", news_item_id=news_item_id)
    member_count = _required_story_positive_int(story, "member_count", news_item_id=news_item_id)
    payload = {
        **dict(story),
        "story_key": story_key,
        "representative_news_item_id": representative_news_item_id,
        "member_news_item_ids": member_news_item_ids,
        "member_count": member_count,
        "source_domains": [str(domain) for domain in source_domains if str(domain)],
    }
    source_ids = [
        str(source_id)
        for source_id in _optional_story_list(story, "source_ids", news_item_id=news_item_id)
        if str(source_id)
    ]
    if source_ids:
        payload["source_ids"] = source_ids
    provider_article_keys = [
        str(provider_key)
        for provider_key in _optional_story_list(story, "provider_article_keys", news_item_id=news_item_id)
        if str(provider_key)
    ]
    if provider_article_keys:
        payload["provider_article_keys"] = provider_article_keys
    return _compact_mapping(payload)


def _required_story_text(story: Mapping[str, Any], field_name: str, *, news_item_id: str) -> str:
    value = str(story.get(field_name) or "").strip()
    if not value:
        raise ValueError(f"news_page_projection_story_{field_name}_required:{news_item_id}")
    return value


def _required_story_list(story: Mapping[str, Any], field_name: str, *, news_item_id: str) -> list[str]:
    values = [str(value) for value in _json_list(story.get(field_name)) if str(value)]
    if not values:
        raise ValueError(f"news_page_projection_story_{field_name}_required:{news_item_id}")
    return values


def _optional_story_list(story: Mapping[str, Any], field_name: str, *, news_item_id: str) -> list[Any]:
    value = _json_value(story.get(field_name))
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"news_page_projection_story_{field_name}_required:{news_item_id}")
    return list(value)


def _required_story_positive_int(story: Mapping[str, Any], field_name: str, *, news_item_id: str) -> int:
    value = _positive_int(story.get(field_name))
    if value is None:
        raise ValueError(f"news_page_projection_story_{field_name}_required:{news_item_id}")
    return value


def _agent_admission_payload(
    *,
    item: Mapping[str, Any],
    news_item_id: str,
) -> dict[str, Any]:
    payload = _required_item_mapping(item, "agent_admission_json", news_item_id=news_item_id)
    status = _required_payload_text(payload, "status", payload_name="agent_admission", news_item_id=news_item_id)
    reason = _required_payload_text(payload, "reason", payload_name="agent_admission", news_item_id=news_item_id)
    representative_news_item_id = _required_payload_text(
        payload,
        "representative_news_item_id",
        payload_name="agent_admission",
        news_item_id=news_item_id,
    )
    basis = _required_payload_mapping(payload, "basis", payload_name="agent_admission", news_item_id=news_item_id)
    version = _required_payload_text(payload, "version", payload_name="agent_admission", news_item_id=news_item_id)
    return _compact_mapping(
        {
            **payload,
            "status": status,
            "reason": reason,
            "representative_news_item_id": representative_news_item_id,
            "basis": basis,
            "version": version,
        }
    )


def _required_item_text(item: Mapping[str, Any], field_name: str, *, news_item_id: str) -> str:
    value = item.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_page_projection_item_{field_name}_required:{news_item_id}")
    return value.strip()


def _required_item_mapping(item: Mapping[str, Any], field_name: str, *, news_item_id: str) -> dict[str, Any]:
    value = _json_value(item.get(field_name))
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_projection_item_{field_name}_required:{news_item_id}")
    return _compact_mapping(dict(value))


def _optional_item_mapping(item: Mapping[str, Any], field_name: str, *, news_item_id: str) -> dict[str, Any]:
    value = _json_value(item.get(field_name))
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_projection_item_{field_name}_required:{news_item_id}")
    return _compact_mapping(dict(value))


def _required_item_list(item: Mapping[str, Any], field_name: str, *, news_item_id: str) -> list[Any]:
    value = _json_value(item.get(field_name))
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"news_page_projection_item_{field_name}_required:{news_item_id}")
    return list(value)


def _optional_item_list(item: Mapping[str, Any], field_name: str, *, news_item_id: str) -> list[Any]:
    value = _json_value(item.get(field_name))
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"news_page_projection_item_{field_name}_required:{news_item_id}")
    return list(value)


def _optional_lane_list(row: Mapping[str, Any], field_name: str, *, lane_name: str) -> list[Any]:
    value = _json_value(row.get(field_name))
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"news_page_projection_{lane_name}_lane_{field_name}_required")
    return list(value)


def _required_payload_text(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    payload_name: str,
    news_item_id: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_page_projection_{payload_name}_{field_name}_required:{news_item_id}")
    return value.strip()


def _required_payload_list(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    payload_name: str,
    news_item_id: str,
) -> list[str]:
    values = [str(value) for value in _json_list(payload.get(field_name)) if str(value)]
    if not values:
        raise ValueError(f"news_page_projection_{payload_name}_{field_name}_required:{news_item_id}")
    return values


def _required_payload_mapping(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    payload_name: str,
    news_item_id: str,
) -> dict[str, Any]:
    value = _json_value(payload.get(field_name))
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_projection_{payload_name}_{field_name}_required:{news_item_id}")
    return _compact_mapping(dict(value))


def _optional_payload_mapping(
    payload: Mapping[str, Any],
    field_name: str,
    *,
    payload_name: str,
    news_item_id: str,
) -> dict[str, Any]:
    value = _json_value(payload.get(field_name))
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_projection_{payload_name}_{field_name}_required:{news_item_id}")
    return _compact_mapping(dict(value))


def _require_matching_agent_admission(
    admission: Mapping[str, Any],
    field_name: str,
    expected: str,
    *,
    news_item_id: str,
) -> None:
    actual = str(admission.get(field_name) or "").strip()
    if actual != expected:
        raise ValueError(f"news_page_projection_agent_admission_{field_name}_mismatch:{news_item_id}")


def _agent_signal_payload(
    agent_payload: Mapping[str, Any],
    *,
    admission_status: str,
    admission_reason: str,
    representative_news_item_id: str,
    admission: Mapping[str, Any],
    news_item_id: str,
) -> dict[str, Any]:
    payload = dict(agent_payload)
    if admission_status in {"exact_duplicate", "similar_story_covered", "similar_story_burst", "materially_superseded"}:
        payload["status"] = admission_status
    payload["agent_admission_status"] = admission_status
    payload["agent_admission_reason"] = admission_reason
    payload["representative_news_item_id"] = representative_news_item_id
    basis = _required_payload_mapping(
        admission,
        "basis",
        payload_name="agent_admission",
        news_item_id=news_item_id,
    )
    similarity = _optional_payload_mapping(
        basis,
        "similar_story",
        payload_name="agent_admission",
        news_item_id=news_item_id,
    )
    if similarity:
        payload["similarity"] = similarity
    duplicate = _optional_payload_mapping(
        basis,
        "exact_duplicate",
        payload_name="agent_admission",
        news_item_id=news_item_id,
    )
    if duplicate:
        payload["duplicate"] = duplicate
    return _compact_mapping(payload)


def _compact_agent_brief(agent_brief: Mapping[str, Any] | None, *, news_item_id: str) -> dict[str, Any]:
    if agent_brief is None:
        return {"status": "pending"}
    if not isinstance(agent_brief, Mapping):
        raise ValueError(f"news_page_projection_agent_brief_required:{news_item_id}")
    status = _required_agent_brief_text(agent_brief, "status", news_item_id=news_item_id)
    direction = _required_agent_brief_text(agent_brief, "direction", news_item_id=news_item_id)
    decision_class = _required_agent_brief_text(agent_brief, "decision_class", news_item_id=news_item_id)
    brief_json = _required_agent_brief_mapping(agent_brief, "brief_json", news_item_id=news_item_id)
    bull_view = _optional_agent_brief_mapping(brief_json, "bull_view", news_item_id=news_item_id)
    bear_view = _optional_agent_brief_mapping(brief_json, "bear_view", news_item_id=news_item_id)
    data_gaps = _optional_agent_brief_list(brief_json, "data_gaps", news_item_id=news_item_id)
    market_impacts = _optional_agent_brief_list(brief_json, "market_impacts", news_item_id=news_item_id)
    return _compact_mapping(
        {
            "status": status,
            "direction": direction,
            "decision_class": decision_class,
            "title_zh": brief_json.get("title_zh"),
            "summary_zh": brief_json.get("summary_zh"),
            "market_read_zh": brief_json.get("market_read_zh"),
            "bull_strength": bull_view.get("strength"),
            "bear_strength": bear_view.get("strength"),
            "data_gap_count": len(data_gaps),
            "computed_at_ms": _optional_int(
                agent_brief.get("computed_at_ms"),
                field_name="agent_brief_computed_at_ms",
                news_item_id=news_item_id,
            ),
            "bull_view": bull_view or None,
            "bear_view": bear_view or None,
            "market_impacts": _agent_market_impacts(market_impacts, news_item_id=news_item_id),
        }
    )


def _required_agent_brief_text(agent_brief: Mapping[str, Any], field_name: str, *, news_item_id: str) -> str:
    value = agent_brief.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_page_projection_agent_brief_{field_name}_required:{news_item_id}")
    return value.strip()


def _required_agent_brief_mapping(
    agent_brief: Mapping[str, Any],
    field_name: str,
    *,
    news_item_id: str,
) -> dict[str, Any]:
    value = _json_value(agent_brief.get(field_name))
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_projection_agent_brief_json_required:{news_item_id}")
    return _compact_mapping(dict(value))


def _optional_agent_brief_mapping(
    brief_json: Mapping[str, Any],
    field_name: str,
    *,
    news_item_id: str,
) -> dict[str, Any]:
    value = _json_value(brief_json.get(field_name))
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_projection_agent_brief_{field_name}_required:{news_item_id}")
    return _compact_mapping(dict(value))


def _optional_agent_brief_list(
    brief_json: Mapping[str, Any],
    field_name: str,
    *,
    news_item_id: str,
) -> list[Any]:
    value = _json_value(brief_json.get(field_name))
    if value is None:
        return []
    if not isinstance(value, list | tuple | set):
        raise ValueError(f"news_page_projection_agent_brief_{field_name}_required:{news_item_id}")
    return list(value)


def _agent_market_impacts(value: Any, *, news_item_id: str) -> list[dict[str, Any]]:
    impacts: list[dict[str, Any]] = []
    for impact in value:
        if not isinstance(impact, Mapping):
            raise ValueError(f"news_page_projection_agent_market_impact_required:{news_item_id}")
        label = str(impact.get("label") or "").strip()
        if not label:
            raise ValueError(f"news_page_projection_agent_market_impact_label_required:{news_item_id}")
        impacts.append(
            _compact_mapping(
                {
                    "label": label,
                    "market_type": impact.get("market_type"),
                    "target_id": impact.get("target_id"),
                    "target_type": impact.get("target_type"),
                    "impact_direction": impact.get("impact_direction"),
                    "reason_zh": impact.get("reason_zh"),
                }
            )
        )
    return impacts[:12]


def _page_signal(
    *,
    agent_signal: Mapping[str, Any],
    agent_admission_status: str,
    market_scope: Mapping[str, Any],
) -> dict[str, Any]:
    if _required_agent_signal_status(agent_signal) == "ready":
        direction = _required_agent_signal_text(agent_signal, "direction")
        return _signal_with_independent_state(
            {
                "source": "agent",
                "status": "ready",
                "direction": direction,
                "label_zh": _direction_label(direction),
                "title_zh": agent_signal.get("title_zh"),
                "summary_zh": agent_signal.get("summary_zh"),
                "method": "news_story_brief",
            },
            agent_signal=agent_signal,
            agent_admission_status=agent_admission_status,
            market_scope=market_scope,
        )
    return _signal_with_independent_state(
        {
            "source": "partial",
            "status": "partial",
            "direction": "neutral",
            "label_zh": "中性",
            "method": "pending",
        },
        agent_signal=agent_signal,
        agent_admission_status=agent_admission_status,
        market_scope=market_scope,
    )


def _signal_with_independent_state(
    signal: Mapping[str, Any],
    *,
    agent_signal: Mapping[str, Any],
    agent_admission_status: str,
    market_scope: Mapping[str, Any],
) -> dict[str, Any]:
    agent_status = _required_agent_signal_status(agent_signal)
    decision_class = None
    if agent_status == "ready":
        decision_class = _required_agent_signal_text(agent_signal, "decision_class")
    in_app_eligible = _alert_eligible(
        agent_signal=agent_signal,
        agent_admission_status=agent_admission_status,
    )
    external_push_ready, external_push_block_reason = _external_push_readiness(agent_signal)
    return {
        "display_signal": _compact_mapping(signal),
        "agent_signal": dict(agent_signal),
        "alert_eligibility": _compact_mapping(
            {
                "agent_status": agent_status,
                "decision_class": decision_class,
                "market_scope": dict(market_scope) if market_scope else None,
                "in_app_eligible": in_app_eligible,
                "external_push_ready": external_push_ready,
                "external_push_block_reason": external_push_block_reason,
                "external_push_basis": "agent_brief" if external_push_ready else None,
            }
        ),
    }


def _alert_eligible(
    *,
    agent_signal: Mapping[str, Any],
    agent_admission_status: str,
) -> bool:
    if agent_admission_status not in _AGENT_NOTIFICATION_ADMISSION_STATUSES:
        return False
    if _required_agent_signal_status(agent_signal) != "ready":
        return False
    return _required_agent_signal_text(agent_signal, "decision_class") in _NOTIFIABLE_DECISION_CLASSES


def _external_push_readiness(agent_signal: Mapping[str, Any]) -> tuple[bool, str | None]:
    if _required_agent_signal_status(agent_signal) != "ready":
        return False, "agent_brief_not_ready"
    if _required_agent_signal_text(agent_signal, "decision_class") not in _NOTIFIABLE_DECISION_CLASSES:
        return False, "decision_not_notifiable"
    if not _agent_publishable_summary(agent_signal):
        return False, "agent_brief_missing_summary"
    return True, None


def _agent_publishable_summary(agent_signal: Mapping[str, Any]) -> bool:
    value = agent_signal.get("summary_zh")
    return isinstance(value, str) and bool(value.strip())


def _required_agent_signal_status(agent_signal: Mapping[str, Any], *, news_item_id: str | None = None) -> str:
    value = agent_signal.get("status")
    if not isinstance(value, str) or not value.strip():
        suffix = f":{news_item_id}" if news_item_id else ""
        raise ValueError(f"news_page_projection_agent_signal_status_required{suffix}")
    return value.strip()


def _required_agent_signal_text(agent_signal: Mapping[str, Any], field_name: str) -> str:
    value = agent_signal.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_page_projection_agent_signal_{field_name}_required")
    return value.strip()


def _direction_label(direction: str) -> str:
    if direction == "bullish":
        return "利好"
    if direction == "bearish":
        return "利空"
    return "中性"


def _compact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if item is not None}


def _json_list(value: Any) -> list[Any]:
    value = _json_value(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return []


def _json_value(value: Any) -> Any:
    return getattr(value, "obj", value)


def _required_positive_int(value: Any, *, field_name: str, news_item_id: str) -> int:
    parsed = _optional_int(value, field_name=field_name, news_item_id=news_item_id)
    if parsed is None:
        raise ValueError(f"news_page_projection_{field_name}_required:{news_item_id}")
    return parsed


def _optional_int(value: Any, *, field_name: str, news_item_id: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"news_page_projection_{field_name}_required:{news_item_id}")
    return value


def _item_published_at_ms(item: Mapping[str, Any]) -> int:
    value = _positive_int(item.get("published_at_ms"))
    if value is not None:
        return value
    news_item_id = str(item.get("news_item_id") or "").strip()
    suffix = f":{news_item_id}" if news_item_id else ""
    raise ValueError(f"news_page_projection_published_at_required{suffix}")


def _positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return value if value > 0 else None


def _optional_rating_score(value: Any, *, news_item_id: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"news_page_projection_provider_rating_score_required:{news_item_id}")
    return value


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
