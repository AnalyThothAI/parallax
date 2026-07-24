from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from tracefold.news.projection.constants import NEWS_PAGE_PROJECTION_VERSION
from tracefold.news.views.page_search import build_news_page_search_text

_RESOLVED_TOKEN_STATUSES = frozenset({"exact_address", "known_symbol", "unique_by_context"})
_IGNORED_TOKEN_STATUSES = frozenset({"non_crypto", "nil"})


def build_news_page_row(
    *,
    item: dict[str, Any],
    token_mentions: list[dict[str, Any]],
    fact_candidates: list[dict[str, Any]],
    story: dict[str, Any] | None,
    computed_at_ms: int,
) -> dict[str, Any]:
    """Project source-backed News facts into the current serving row.

    The projection intentionally has no model admission, model output, inferred
    direction, or notification eligibility.  It is fully rebuildable from the
    persisted News item, entity/fact lanes, and deterministic story grouping.
    """

    news_item_id = _required_item_text(item, "news_item_id", news_item_id="unknown")
    story_payload = _story_payload(story=story, news_item_id=news_item_id)
    story_key = str(story_payload["story_key"])
    source = _source_payload(item, news_item_id=news_item_id)
    token_lanes = [_token_lane(row) for row in token_mentions]
    fact_lanes = [_fact_lane(row) for row in fact_candidates]
    row = {
        "row_id": _stable_id("news-page-row", NEWS_PAGE_PROJECTION_VERSION, story_key),
        "news_item_id": news_item_id,
        "representative_news_item_id": str(story_payload["representative_news_item_id"]),
        "story_key": story_key,
        "story": story_payload,
        "latest_at_ms": _required_positive_int(
            item.get("published_at_ms"),
            field_name="published_at",
            news_item_id=news_item_id,
        ),
        "lifecycle_status": _lifecycle(item=item, token_lanes=token_lanes, fact_lanes=fact_lanes),
        "headline": str(item.get("title") or ""),
        "summary": str(item.get("summary") or ""),
        "source_domain": str(item.get("source_domain") or ""),
        "canonical_url": _public_url(item.get("canonical_url")),
        "canonical_item_key": _required_item_text(item, "canonical_item_key", news_item_id=news_item_id),
        "token_lanes": token_lanes,
        "fact_lanes": fact_lanes,
        "provider_rating": _provider_rating_payload(item, news_item_id=news_item_id),
        "content_class": _required_item_text(item, "content_class", news_item_id=news_item_id),
        "content_tags": _required_item_list(item, "content_tags_json", news_item_id=news_item_id),
        "content_classification": _required_item_mapping(
            item,
            "content_classification_json",
            news_item_id=news_item_id,
        ),
        "source": source,
        "market_scope": _market_scope_payload(item, news_item_id=news_item_id),
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
    row["search_text"] = build_news_page_search_text(
        {
            "headline": row["headline"],
            "summary": row["summary"],
            "source_domain": row["source_domain"],
            "source_json": source,
            "source_ids_json": row["source_ids_json"],
            "source_domains_json": row["source_domains_json"],
            "token_lanes_json": token_lanes,
            "fact_lanes_json": fact_lanes,
        }
    )
    return row


def _provider_rating_payload(item: Mapping[str, Any], *, news_item_id: str) -> dict[str, Any]:
    rating = _optional_item_mapping(item, "provider_signal_json", news_item_id=news_item_id)
    score = rating.get("score")
    if score is not None and (isinstance(score, bool) or not isinstance(score, int | float)):
        raise ValueError(f"news_page_projection_provider_rating_score_required:{news_item_id}")
    return _compact_mapping(
        {
            "provider": rating.get("provider"),
            "status": rating.get("status"),
            "direction": rating.get("direction"),
            "signal": rating.get("signal"),
            "score": score,
            "grade": rating.get("grade"),
            "method": rating.get("method"),
        }
    )


def _token_lane(row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(row.get("resolution_status") or "")
    if status in _RESOLVED_TOKEN_STATUSES:
        lane = "resolved"
    elif status in _IGNORED_TOKEN_STATUSES:
        lane = "ignored"
    else:
        lane = "attention"
    return {
        "lane": lane,
        "resolution_status": status,
        "symbol": row.get("display_symbol") or row.get("observed_symbol"),
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "display_name": row.get("display_name"),
        "reason_codes": _optional_lane_list(row, "reason_codes_json", lane_name="token"),
        "candidate_targets": _optional_lane_list(row, "candidate_targets_json", lane_name="token"),
    }


def _fact_lane(row: Mapping[str, Any]) -> dict[str, Any]:
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
    item: Mapping[str, Any],
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


def _source_payload(item: Mapping[str, Any], *, news_item_id: str) -> dict[str, Any]:
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
    for field_name in ("primary", "status", "reason", "version"):
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"news_page_projection_market_scope_{field_name}_required:{news_item_id}")
    scope = _json_list(payload.get("scope"))
    if not scope:
        raise ValueError(f"news_page_projection_market_scope_scope_required:{news_item_id}")
    if not isinstance(_json_value(payload.get("basis")), Mapping):
        raise ValueError(f"news_page_projection_market_scope_basis_required:{news_item_id}")
    return payload


def _story_payload(*, story: Mapping[str, Any] | None, news_item_id: str) -> dict[str, Any]:
    if not isinstance(story, Mapping):
        raise ValueError(f"news_page_projection_story_required:{news_item_id}")
    payload = dict(story)
    for field_name in ("story_key", "representative_news_item_id"):
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"news_page_projection_story_{field_name}_required:{news_item_id}")
        payload[field_name] = value.strip()
    for field_name in ("member_news_item_ids", "source_domains"):
        values = [str(value) for value in _json_list(payload.get(field_name)) if str(value)]
        if not values:
            raise ValueError(f"news_page_projection_story_{field_name}_required:{news_item_id}")
        payload[field_name] = values
    payload["member_count"] = _required_positive_int(
        payload.get("member_count"),
        field_name="story_member_count",
        news_item_id=news_item_id,
    )
    for field_name in ("source_ids", "provider_article_keys"):
        if field_name in payload:
            payload[field_name] = [str(value) for value in _json_list(payload[field_name]) if str(value)]
    return _compact_mapping(payload)


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
    if field_name not in item or item.get(field_name) is None:
        return []
    return _required_item_list(item, field_name, news_item_id=news_item_id)


def _optional_lane_list(row: Mapping[str, Any], field_name: str, *, lane_name: str) -> list[Any]:
    value = _json_value(row.get(field_name))
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"news_page_projection_{lane_name}_lane_{field_name}_required")
    return list(value)


def _required_positive_int(value: Any, *, field_name: str, news_item_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"news_page_projection_{field_name}_required:{news_item_id}")
    return int(value)


def _public_url(value: Any) -> str:
    url = str(value or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


def _json_list(value: Any) -> list[Any]:
    value = _json_value(value)
    if value is None:
        return []
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError("news_page_projection_json_list_required")
    return list(value)


def _json_value(value: Any) -> Any:
    return getattr(value, "obj", value)


def _compact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if item is not None}


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"news-page:{digest[:32]}"


__all__ = ["build_news_page_row"]
