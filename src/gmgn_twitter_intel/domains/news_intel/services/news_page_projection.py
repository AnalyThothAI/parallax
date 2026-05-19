from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION

_RESOLVED_TOKEN_STATUSES = frozenset({"exact_address", "known_symbol", "unique_by_context"})
_IGNORED_TOKEN_STATUSES = frozenset({"non_crypto", "nil"})


def build_news_page_row(
    *,
    item: dict[str, Any],
    story: dict[str, Any] | None,
    token_mentions: list[dict[str, Any]],
    fact_candidates: list[dict[str, Any]],
    computed_at_ms: int,
) -> dict[str, Any]:
    news_item_id = str(item["news_item_id"])
    token_lanes = [_token_lane(row) for row in token_mentions]
    fact_lanes = [_fact_lane(row) for row in fact_candidates]
    story_payload = _json_object(story)
    source_payload = _source_payload(item)
    return {
        "row_id": _stable_id("news-page-row", NEWS_PAGE_PROJECTION_VERSION, news_item_id),
        "news_item_id": news_item_id,
        "story_id": story_payload.get("story_id"),
        "latest_at_ms": int(item.get("published_at_ms") or computed_at_ms),
        "lifecycle_status": _lifecycle(item=item, token_lanes=token_lanes, fact_lanes=fact_lanes),
        "headline": str(item.get("title") or ""),
        "summary": str(item.get("summary") or ""),
        "source_domain": str(item.get("source_domain") or ""),
        "canonical_url": str(item.get("canonical_url") or ""),
        "token_lanes": token_lanes,
        "fact_lanes": fact_lanes,
        "story": story_payload,
        "source": source_payload,
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


def _token_lane_name(status: str) -> str:
    if status in _RESOLVED_TOKEN_STATUSES:
        return "resolved"
    if status in _IGNORED_TOKEN_STATUSES:
        return "ignored"
    return "attention"


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
            "source_domain": item.get("source_domain"),
            "source_name": item.get("source_name"),
            "source_role": item.get("source_role"),
            "trust_tier": item.get("trust_tier"),
        }
    )


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


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
