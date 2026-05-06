from __future__ import annotations

import time
from typing import Any

from .asset_flow_service import WINDOW_MS
from .asset_timeline_cursor import decode_timeline_cursor, encode_timeline_cursor


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
        cursor: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_now_ms = int(now_ms or time.time() * 1000)
        window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
        fetch_limit = max(0, int(limit)) + 1
        rows = self.assets.asset_timeline_rows(
            asset_id=asset_id,
            since_ms=resolved_now_ms - window_ms,
            watched_only=scope == "matched",
            limit=fetch_limit,
            cursor=decode_timeline_cursor(cursor),
        )
        page_rows = rows[: max(0, int(limit))]
        bucket_ms, bucket_label = _bucket(window)
        has_more = len(rows) > len(page_rows)
        next_cursor = encode_timeline_cursor(page_rows[-1]) if has_more and page_rows else None
        return {
            "query": {"asset_id": asset_id, "window": window, "scope": scope, "bucket": bucket_label},
            "summary": _summary(page_rows),
            "market_overlay": _market_overlay(page_rows),
            "buckets": _buckets(
                page_rows,
                bucket_ms=bucket_ms,
                since_ms=resolved_now_ms - window_ms,
                now_ms=resolved_now_ms,
            ),
            "authors": _authors(page_rows),
            "posts": [_post(row, bucket_ms=bucket_ms, since_ms=resolved_now_ms - window_ms) for row in page_rows],
            "cascade": {"edges": [], "unresolved_parents": []},
            "returned_count": len(page_rows),
            "has_more": has_more,
            "next_cursor": next_cursor,
        }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    authors = {str(row.get("author_handle") or "") for row in rows if row.get("author_handle")}
    times = [int(row.get("received_at_ms") or 0) for row in rows]
    return {
        "posts": len(rows),
        "authors": len(authors),
        "effective_authors": len(authors),
        "first_seen_ms": min(times) if times else None,
        "latest_seen_ms": max(times) if times else None,
        "watched_posts": sum(1 for row in rows if row.get("is_watched")),
        "phase": _phase(len(rows), len(authors)),
        "top_author_share": _top_author_share(rows),
        "duplicate_text_share": 0.0,
        "peak_posts_per_bucket": 0,
        "peak_new_authors_per_bucket": 0,
        "reproduction_rate": None,
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


def _bucket(window: str) -> tuple[int, str]:
    if window == "5m":
        return 30 * 1000, "30s"
    if window == "4h":
        return 15 * 60 * 1000, "15m"
    if window == "24h":
        return 60 * 60 * 1000, "1h"
    return 5 * 60 * 1000, "5m"


def _buckets(rows: list[dict[str, Any]], *, bucket_ms: int, since_ms: int, now_ms: int) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for row in rows:
        received_at_ms = int(row.get("received_at_ms") or 0)
        start_ms = since_ms + ((received_at_ms - since_ms) // bucket_ms) * bucket_ms
        bucket = grouped.setdefault(
            start_ms,
            {
                "start_ms": start_ms,
                "end_ms": min(start_ms + bucket_ms, now_ms),
                "posts": 0,
                "authors": set(),
                "new_authors": 0,
                "watched_posts": 0,
                "duplicate_text_share": 0.0,
                "price": None,
                "price_change_from_start_pct": None,
            },
        )
        bucket["posts"] += 1
        if row.get("author_handle"):
            bucket["authors"].add(str(row["author_handle"]))
        if row.get("is_watched"):
            bucket["watched_posts"] += 1
    public = []
    seen_authors: set[str] = set()
    for start_ms in sorted(grouped):
        bucket = grouped[start_ms]
        authors = set(bucket["authors"])
        new_authors = len(authors - seen_authors)
        seen_authors.update(authors)
        public.append({**bucket, "authors": len(authors), "new_authors": new_authors})
    return public


def _authors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        handle = str(row.get("author_handle") or "")
        if not handle:
            continue
        received_at_ms = int(row.get("received_at_ms") or 0)
        item = grouped.setdefault(
            handle,
            {
                "handle": handle,
                "first_seen_ms": received_at_ms,
                "latest_seen_ms": received_at_ms,
                "posts": 0,
                "followers": None,
                "role": "watched" if row.get("is_watched") else "amplifier",
                "quality_score": None,
            },
        )
        item["posts"] += 1
        item["first_seen_ms"] = min(int(item["first_seen_ms"]), received_at_ms)
        item["latest_seen_ms"] = max(int(item["latest_seen_ms"]), received_at_ms)
        if row.get("is_watched"):
            item["role"] = "watched"
    return sorted(grouped.values(), key=lambda item: (-int(item["posts"]), int(item["first_seen_ms"])))


def _post(row: dict[str, Any], *, bucket_ms: int, since_ms: int) -> dict[str, Any]:
    received_at_ms = int(row.get("received_at_ms") or 0)
    bucket_start_ms = since_ms + ((received_at_ms - since_ms) // bucket_ms) * bucket_ms
    confidence = float(row.get("confidence") or 0.0)
    watched = bool(row.get("is_watched"))
    return {
        "event_id": row.get("event_id"),
        "tweet_id": row.get("tweet_id"),
        "asset_id": row.get("asset_id"),
        "symbol": row.get("canonical_symbol"),
        "handle": row.get("author_handle"),
        "author_handle": row.get("author_handle"),
        "text": row.get("text_clean") or row.get("text"),
        "url": row.get("canonical_url"),
        "received_at_ms": row.get("received_at_ms"),
        "bucket_start_ms": bucket_start_ms,
        "is_watched": row.get("is_watched"),
        "is_first_seen_by_watched_for_token": watched,
        "event_type": "watched_asset_mention" if watched else "public_asset_mention",
        "attribution_status": row.get("attribution_status"),
        "confidence": row.get("confidence"),
        "reference": None,
        "post_quality": {
            "score_version": "asset_post_quality_v1",
            "score": min(100, round(45 + confidence * 35 + (15 if watched else 0))),
            "reasons": ["watched_asset_evidence"] if watched else ["asset_mention"],
            "risks": ["public_stream_coverage"],
            "contributions": [],
            "risk_caps": [],
        },
    }


def _phase(posts: int, authors: int) -> str:
    if posts <= 1:
        return "seed"
    if authors <= 1:
        return "concentration"
    if posts >= 5 and authors >= 3:
        return "expansion"
    return "ignition"


def _top_author_share(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    counts: dict[str, int] = {}
    for row in rows:
        handle = str(row.get("author_handle") or "")
        if handle:
            counts[handle] = counts.get(handle, 0) + 1
    return (max(counts.values()) / len(rows)) if counts else 0.0
