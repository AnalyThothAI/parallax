from __future__ import annotations

import time
from typing import Any

from .asset_flow_service import WINDOW_MS
from .asset_timeline_cursor import AssetTimelineCursorError, decode_timeline_cursor, encode_timeline_cursor


class AssetPostsCursorError(Exception):
    pass


class AssetPostsRangeError(Exception):
    pass


class AssetPostsSortError(Exception):
    pass


class AssetPostsService:
    def __init__(self, *, assets):
        self.assets = assets

    def asset_posts(
        self,
        *,
        asset_id: str,
        window: str,
        scope: str,
        post_range: str,
        sort: str,
        limit: int,
        cursor: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        if post_range not in {"current_window", "since_ignition", "all_history"}:
            raise AssetPostsRangeError(post_range)
        if sort not in {"recent", "catalyst"}:
            raise AssetPostsSortError(sort)
        try:
            timeline_cursor = decode_timeline_cursor(cursor)
        except AssetTimelineCursorError as exc:
            raise AssetPostsCursorError(cursor) from exc
        resolved_now_ms = int(now_ms or time.time() * 1000)
        since_ms = (
            0
            if post_range in {"since_ignition", "all_history"}
            else resolved_now_ms - WINDOW_MS.get(window, WINDOW_MS["1h"])
        )
        rows = self.assets.asset_timeline_rows(
            asset_id=asset_id,
            since_ms=since_ms,
            watched_only=scope == "matched",
            limit=max(0, int(limit)) + 1,
            cursor=timeline_cursor,
        )
        page_rows = rows[: max(0, int(limit))]
        has_more = len(rows) > len(page_rows)
        next_cursor = encode_timeline_cursor(page_rows[-1]) if has_more and page_rows else None
        return {
            "query": {
                "asset_id": asset_id,
                "window": window,
                "scope": scope,
                "range": post_range,
                "sort": sort,
            },
            "score_window": {"window": window},
            "total_count": len(page_rows) + (1 if has_more else 0),
            "returned_count": len(page_rows),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "items": [_post(row) for row in page_rows],
        }

def _post(row: dict[str, Any]) -> dict[str, Any]:
    text = row.get("text_clean") or row.get("text")
    watched = bool(row.get("is_watched"))
    confidence = float(row.get("confidence") or 0.0)
    quality_score = min(100, round(45 + confidence * 35 + (15 if watched else 0)))
    reasons = ["watched_asset_evidence"] if watched else ["asset_mention"]
    return {
        "event_id": row.get("event_id"),
        "tweet_id": row.get("tweet_id"),
        "handle": row.get("author_handle"),
        "text": text,
        "url": row.get("canonical_url"),
        "received_at_ms": row.get("received_at_ms"),
        "mention_source": "asset_attribution",
        "attribution_status": row.get("attribution_status"),
        "attribution_confidence": row.get("confidence"),
        "attribution_weight": None,
        "is_watched": row.get("is_watched"),
        "is_first_seen_by_watched_for_token": watched,
        "event_type": "watched_asset_mention" if watched else "public_asset_mention",
        "reference": _reference(row.get("reference_json")),
        "catalyst_score": quality_score if watched else None,
        "catalyst_components": None,
        "post_quality": {
            "score_version": "asset_post_quality_v1",
            "score": quality_score,
            "reasons": reasons,
            "risks": ["public_stream_coverage"],
            "contributions": [
                {
                    "feature": "asset_resolution_confidence",
                    "value": round(confidence * 35, 2),
                    "reason": "asset_attribution",
                }
            ],
            "risk_caps": [],
        },
    }


def _reference(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "tweet_id": value.get("tweet_id"),
        "author_handle": value.get("author_handle") or value.get("handle"),
        "type": value.get("type"),
    }
