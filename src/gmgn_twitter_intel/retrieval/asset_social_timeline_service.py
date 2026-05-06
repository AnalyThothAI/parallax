from __future__ import annotations

import time
from typing import Any

from .asset_flow_service import WINDOW_MS


class AssetSocialTimelineService:
    def __init__(self, *, assets):
        self.assets = assets

    def timeline(
        self,
        *,
        asset_id: str,
        window: str,
        scope: str,
        limit: int,
        cursor_ms: int | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_now_ms = int(now_ms or time.time() * 1000)
        window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
        rows = self.assets.asset_timeline_rows(
            asset_id=asset_id,
            since_ms=resolved_now_ms - window_ms,
            watched_only=scope == "matched",
            limit=max(0, int(limit)),
            cursor_ms=cursor_ms,
        )
        return {
            "query": {"asset_id": asset_id, "window": window, "scope": scope},
            "summary": _summary(rows),
            "market_overlay": _market_overlay(rows),
            "posts": [_post(row) for row in rows],
            "next_cursor_ms": int(rows[-1]["received_at_ms"]) if len(rows) == limit and rows else None,
        }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    authors = {str(row.get("author_handle") or "") for row in rows if row.get("author_handle")}
    times = [int(row.get("received_at_ms") or 0) for row in rows]
    return {
        "posts": len(rows),
        "authors": len(authors),
        "first_seen_ms": min(times) if times else None,
        "latest_seen_ms": max(times) if times else None,
        "watched_posts": sum(1 for row in rows if row.get("is_watched")),
    }


def _market_overlay(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in rows:
        if not row.get("venue_id"):
            continue
        return {
            "venue_id": row.get("venue_id"),
            "venue_type": row.get("venue_type"),
            "exchange": row.get("exchange"),
            "chain": row.get("chain"),
            "address": row.get("address"),
            "inst_id": row.get("inst_id"),
            "base_symbol": row.get("base_symbol"),
            "quote_symbol": row.get("quote_symbol"),
            "inst_type": row.get("inst_type"),
        }
    return None


def _post(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": row.get("event_id"),
        "asset_id": row.get("asset_id"),
        "symbol": row.get("canonical_symbol"),
        "author_handle": row.get("author_handle"),
        "text": row.get("text"),
        "received_at_ms": row.get("received_at_ms"),
        "is_watched": row.get("is_watched"),
        "attribution_status": row.get("attribution_status"),
        "confidence": row.get("confidence"),
    }
