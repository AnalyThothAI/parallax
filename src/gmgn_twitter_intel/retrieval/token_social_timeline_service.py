from __future__ import annotations

import base64
import json
import math
import sqlite3
import time
from collections import Counter, defaultdict
from typing import Any

from ..pipeline.entity_extractor import normalize_ca
from .diffusion_health import text_fingerprint
from .discussion_quality_scoring import post_quality_score
from .propagation_scoring import propagation_score
from .rolling_token_flow import WINDOW_MS

BUCKET_MS = {
    "30s": 30_000,
    "1m": 60_000,
    "5m": 300_000,
}


class TokenSocialTimelineCursorError(ValueError):
    pass


class TokenSocialTimelineIdentityError(ValueError):
    pass


class TokenSocialTimelineService:
    def __init__(self, *, signals):
        self.signals = signals
        self.conn: sqlite3.Connection = signals.conn

    def timeline(
        self,
        *,
        token_id: str | None = None,
        chain: str | None = None,
        address: str | None = None,
        window: str,
        bucket: str,
        scope: str,
        limit: int,
        cursor: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        reference_ms = now_ms if now_ms is not None else _now_ms()
        window_start_ms = reference_ms - WINDOW_MS[window]
        window_end_ms = reference_ms
        normalized_chain, normalized_address = _normalized_chain_address(chain=chain, address=address)
        summary_rows = [dict(row) for row in self._summary_rows(
            token_id=token_id,
            chain=normalized_chain,
            address=normalized_address,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=scope == "matched",
        )]
        cursor_value = _decode_cursor(cursor) if cursor else None
        requested_limit = max(0, int(limit))
        page_rows = [dict(row) for row in self._post_rows(
            token_id=token_id,
            chain=normalized_chain,
            address=normalized_address,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=scope == "matched",
            limit=requested_limit + 1,
            cursor=cursor_value,
        )]
        has_more = len(page_rows) > requested_limit
        page_items = [_post_item(row) for row in page_rows[:requested_limit]]
        return {
            "query": {
                "token_id": token_id,
                "chain": normalized_chain,
                "address": normalized_address,
                "window": window,
                "bucket": bucket,
                "scope": scope,
            },
            "summary": _summary(summary_rows),
            "buckets": _buckets(summary_rows, bucket_ms=BUCKET_MS[bucket], window_start_ms=window_start_ms),
            "authors": _authors(summary_rows),
            "posts": page_items,
            "returned_count": len(page_items),
            "has_more": has_more,
            "next_cursor": _encode_cursor(page_items[-1]) if has_more and page_items else None,
        }

    def _summary_rows(
        self,
        *,
        token_id: str | None,
        chain: str | None,
        address: str | None,
        window_start_ms: int,
        window_end_ms: int,
        watched_only: bool,
    ) -> list[sqlite3.Row]:
        clauses, params = _base_clauses(
            token_id=token_id,
            chain=chain,
            address=address,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=watched_only,
        )
        return self.conn.execute(
            f"""
            WITH filtered AS (
              SELECT eta.*
              FROM event_token_attributions eta
              WHERE {" AND ".join(clauses)}
            ),
            ranked AS (
              SELECT
                filtered.*,
                ROW_NUMBER() OVER (
                  PARTITION BY filtered.event_id
                  ORDER BY
                    filtered.attribution_weight DESC,
                    filtered.attribution_confidence DESC,
                    filtered.attribution_rank ASC
                ) AS rn
              FROM filtered
            )
            SELECT
              ranked.*,
              e.author_handle AS event_author_handle,
              e.text_clean,
              e.search_text,
              e.canonical_url,
              e.is_watched AS event_is_watched
            FROM ranked
            LEFT JOIN events e ON e.event_id = ranked.event_id
            WHERE ranked.rn = 1
            ORDER BY ranked.received_at_ms DESC, ranked.event_id DESC
            """,
            params,
        ).fetchall()

    def _post_rows(
        self,
        *,
        token_id: str | None,
        chain: str | None,
        address: str | None,
        window_start_ms: int,
        window_end_ms: int,
        watched_only: bool,
        limit: int,
        cursor: tuple[int, str] | None,
    ) -> list[sqlite3.Row]:
        clauses, params = _base_clauses(
            token_id=token_id,
            chain=chain,
            address=address,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=watched_only,
        )
        if cursor is not None:
            cursor_ms, cursor_event_id = cursor
            clauses.append("(eta.received_at_ms < ? OR (eta.received_at_ms = ? AND eta.event_id < ?))")
            params.extend([cursor_ms, cursor_ms, cursor_event_id])
        return self.conn.execute(
            f"""
            WITH filtered AS (
              SELECT eta.*
              FROM event_token_attributions eta
              WHERE {" AND ".join(clauses)}
            ),
            ranked AS (
              SELECT
                filtered.*,
                ROW_NUMBER() OVER (
                  PARTITION BY filtered.event_id
                  ORDER BY
                    filtered.attribution_weight DESC,
                    filtered.attribution_confidence DESC,
                    filtered.attribution_rank ASC
                ) AS rn
              FROM filtered
            )
            SELECT
              ranked.*,
              e.author_handle AS event_author_handle,
              e.text_clean,
              e.search_text,
              e.canonical_url,
              e.is_watched AS event_is_watched
            FROM ranked
            LEFT JOIN events e ON e.event_id = ranked.event_id
            WHERE ranked.rn = 1
            ORDER BY ranked.received_at_ms DESC, ranked.event_id DESC
            LIMIT ?
            """,
            (*params, max(0, int(limit))),
        ).fetchall()


def _base_clauses(
    *,
    token_id: str | None,
    chain: str | None,
    address: str | None,
    window_start_ms: int,
    window_end_ms: int,
    watched_only: bool,
) -> tuple[list[str], list[Any]]:
    clauses = [
        "eta.received_at_ms >= ?",
        "eta.received_at_ms < ?",
        "eta.token_id IS NOT NULL",
        "eta.attribution_status IN ('direct', 'selected')",
        "eta.attribution_weight > 0",
        "eta.chain IS NOT NULL",
        "eta.address IS NOT NULL",
        "eta.chain NOT IN ('unknown', 'evm', 'evm_unknown')",
    ]
    params: list[Any] = [window_start_ms, window_end_ms]
    if token_id:
        clauses.append("eta.token_id = ?")
        params.append(token_id)
    elif chain and address:
        clauses.extend(["eta.chain = ?", "eta.address = ?"])
        params.extend([chain, address])
    else:
        raise TokenSocialTimelineIdentityError("missing_token_identity")
    if watched_only:
        clauses.append("eta.is_watched = 1")
    return clauses, params


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    author_counts = Counter(_handle(row) for row in rows if _handle(row))
    total = len(rows)
    top_author_share = max(author_counts.values(), default=0) / total if total else 0.0
    duplicate_text_share = _duplicate_text_share(rows)
    propagation = propagation_score(
        {
            "mentions": total,
            "independent_authors": len(author_counts),
            "effective_authors": _effective_authors(author_counts),
            "new_authors": len(author_counts),
            "top_author_share": top_author_share,
            "duplicate_text_share": duplicate_text_share,
            "watched_author_count": len({_handle(row) for row in rows if _is_watched(row)}),
        }
    )
    received_values = [int(row["received_at_ms"]) for row in rows if row.get("received_at_ms") is not None]
    return {
        "posts": total,
        "authors": len(author_counts),
        "effective_authors": propagation["effective_authors"],
        "first_seen_ms": min(received_values) if received_values else None,
        "latest_seen_ms": max(received_values) if received_values else None,
        "phase": propagation["phase"],
        "top_author_share": top_author_share,
        "duplicate_text_share": duplicate_text_share,
    }


def _buckets(rows: list[dict[str, Any]], *, bucket_ms: int, window_start_ms: int) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    first_seen_by_author: dict[str, int] = {}
    for row in sorted(rows, key=lambda item: int(item.get("received_at_ms") or 0)):
        received_at_ms = int(row["received_at_ms"])
        bucket_start = window_start_ms + ((received_at_ms - window_start_ms) // bucket_ms) * bucket_ms
        grouped[bucket_start].append(row)
        handle = _handle(row)
        if handle and handle not in first_seen_by_author:
            first_seen_by_author[handle] = bucket_start
    buckets = []
    for start_ms in sorted(grouped):
        bucket_rows = grouped[start_ms]
        buckets.append(
            {
                "start_ms": start_ms,
                "end_ms": start_ms + bucket_ms,
                "posts": len(bucket_rows),
                "new_authors": sum(
                    1
                    for handle, first_bucket in first_seen_by_author.items()
                    if first_bucket == start_ms and any(_handle(row) == handle for row in bucket_rows)
                ),
                "watched_posts": sum(1 for row in bucket_rows if _is_watched(row)),
                "duplicate_text_share": _duplicate_text_share(bucket_rows),
                "price": None,
                "price_change_from_start_pct": None,
            }
        )
    return buckets


def _authors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        handle = _handle(row)
        if handle:
            grouped[handle].append(row)
    author_rows = []
    for handle, author_posts in grouped.items():
        first_seen = min(int(row["received_at_ms"]) for row in author_posts)
        latest_seen = max(int(row["received_at_ms"]) for row in author_posts)
        watched = any(_is_watched(row) for row in author_posts)
        role = _author_role(posts=len(author_posts), watched=watched, first_seen_ms=first_seen, rows=rows)
        author_rows.append(
            {
                "handle": handle,
                "first_seen_ms": first_seen,
                "latest_seen_ms": latest_seen,
                "posts": len(author_posts),
                "followers": max(int(row.get("author_followers") or 0) for row in author_posts),
                "role": role,
                "quality_score": None,
            }
        )
    author_rows.sort(key=lambda item: (-int(item["posts"]), int(item["first_seen_ms"]), str(item["handle"])))
    return author_rows


def _post_item(row: dict[str, Any]) -> dict[str, Any]:
    quality = post_quality_score(
        {
            "text": row.get("text_clean") or row.get("search_text"),
            "mention_source": row.get("source"),
            "attribution_status": row.get("attribution_status"),
            "attribution_confidence": row.get("attribution_confidence"),
            "attribution_weight": row.get("attribution_weight"),
            "is_watched": _is_watched(row),
        }
    )
    return {
        "event_id": row.get("event_id"),
        "handle": _handle(row),
        "received_at_ms": row.get("received_at_ms"),
        "bucket_start_ms": None,
        "text": row.get("text_clean"),
        "url": row.get("canonical_url"),
        "attribution_status": row.get("attribution_status"),
        "is_watched": _is_watched(row),
        "post_quality": quality,
    }


def _page_rows(
    rows: list[dict[str, Any]],
    *,
    limit: int,
    cursor: tuple[int, str] | None,
) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        rows,
        key=lambda item: (int(item.get("received_at_ms") or 0), str(item.get("event_id"))),
        reverse=True,
    )
    if cursor is None:
        return sorted_rows[: limit + 1]
    cursor_ms, cursor_event_id = cursor
    return [
        row
        for row in sorted_rows
        if int(row.get("received_at_ms") or 0) < cursor_ms
        or (int(row.get("received_at_ms") or 0) == cursor_ms and str(row.get("event_id")) < cursor_event_id)
    ][: limit + 1]


def _author_role(*, posts: int, watched: bool, first_seen_ms: int, rows: list[dict[str, Any]]) -> str:
    if watched:
        return "watched"
    first_global = min(int(row["received_at_ms"]) for row in rows) if rows else first_seen_ms
    if first_seen_ms == first_global:
        return "seed"
    if posts > 1:
        return "amplifier"
    return "early_amplifier"


def _duplicate_text_share(rows: list[dict[str, Any]]) -> float:
    if len(rows) < 3:
        return 0.0
    fingerprints = [text_fingerprint(row.get("text_clean") or row.get("search_text")) for row in rows]
    counts = Counter(item for item in fingerprints if item)
    return max(counts.values(), default=0) / len(rows)


def _effective_authors(author_counts: Counter[str]) -> float:
    total = sum(author_counts.values())
    if not total:
        return 0.0
    entropy = -sum((count / total) * math.log(count / total) for count in author_counts.values())
    return round(math.exp(entropy), 4)


def _handle(row: dict[str, Any]) -> str:
    return str(row.get("event_author_handle") or row.get("author_handle") or "").strip().lstrip("@").lower()


def _is_watched(row: dict[str, Any]) -> bool:
    value = row.get("event_is_watched") if row.get("event_is_watched") is not None else row.get("is_watched")
    return bool(value)


def _normalized_chain_address(*, chain: str | None, address: str | None) -> tuple[str | None, str | None]:
    if not address:
        return chain or None, None
    try:
        return normalize_ca(address, chain=chain)
    except ValueError as exc:
        raise TokenSocialTimelineIdentityError("invalid_token_identity") from exc


def _decode_cursor(cursor: str | None) -> tuple[int, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return int(payload["received_at_ms"]), str(payload["event_id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TokenSocialTimelineCursorError("invalid_cursor") from exc


def _encode_cursor(item: dict[str, Any]) -> str:
    payload = json.dumps(
        {"received_at_ms": int(item["received_at_ms"]), "event_id": str(item["event_id"])},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _now_ms() -> int:
    return int(time.time() * 1000)
