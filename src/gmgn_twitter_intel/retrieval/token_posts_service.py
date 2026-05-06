from __future__ import annotations

import base64
import json
import time
from typing import Any

from ..pipeline.entity_extractor import normalize_ca
from .catalyst_ranking_service import CATALYST_BASELINE_MS, CatalystRankingService
from .discussion_quality_scoring import post_quality_score
from .rolling_token_flow import WINDOW_MS

POST_RANGES = {"current_window", "since_ignition", "all_history"}
POST_SORTS = {"recent", "catalyst"}


class TokenPostsCursorError(ValueError):
    pass


class TokenPostsIdentityError(ValueError):
    pass


class TokenPostsRangeError(ValueError):
    pass


class TokenPostsSortError(ValueError):
    pass


class TokenPostsService:
    def __init__(self, *, signals):
        self.signals = signals
        self.conn: Any = signals.conn

    def token_posts(
        self,
        *,
        token_id: str | None = None,
        chain: str | None = None,
        address: str | None = None,
        window: str,
        scope: str,
        limit: int,
        post_range: str = "current_window",
        sort: str = "recent",
        cursor: str | None = None,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        requested_limit = max(0, int(limit))
        reference_ms = now_ms if now_ms is not None else _now_ms()
        normalized_chain, normalized_address = _normalized_chain_address(chain=chain, address=address)
        if post_range not in POST_RANGES:
            raise TokenPostsRangeError("invalid_range")
        if sort not in POST_SORTS:
            raise TokenPostsSortError("invalid_sort")
        selected_range = post_range
        score_window_start_ms = reference_ms - WINDOW_MS[window]
        score_window_end_ms = reference_ms
        window_start_ms, window_end_ms = self._range_bounds(
            token_id=token_id,
            chain=normalized_chain,
            address=normalized_address,
            score_window_start_ms=score_window_start_ms,
            score_window_end_ms=score_window_end_ms,
            watched_only=scope == "matched",
            post_range=selected_range,
        )
        cursor_value = _decode_cursor(cursor) if cursor else None
        if sort == "catalyst":
            return self._catalyst_posts(
                token_id=token_id,
                chain=normalized_chain,
                address=normalized_address,
                window=window,
                scope=scope,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                watched_only=scope == "matched",
                requested_limit=min(requested_limit, 100),
                selected_range=selected_range,
                reference_ms=reference_ms,
            )

        rows = self._post_rows(
            token_id=token_id,
            chain=normalized_chain,
            address=normalized_address,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=scope == "matched",
            limit=requested_limit + 1,
            cursor=cursor_value,
        )
        page_rows = rows[:requested_limit]
        has_more = len(rows) > requested_limit
        total_count = self._total_count(
            token_id=token_id,
            chain=normalized_chain,
            address=normalized_address,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=scope == "matched",
        )
        items = [_post_item(dict(row), reference_ms=reference_ms) for row in page_rows]
        next_cursor = _encode_cursor(items[-1]) if has_more and items else None
        return {
            "query": {
                "token_id": token_id,
                "chain": normalized_chain,
                "address": normalized_address,
                "window": window,
                "scope": scope,
                "sort": sort,
                "range": selected_range,
            },
            "score_window": {"window": window},
            "total_count": total_count,
            "returned_count": len(items),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "items": items,
        }

    def _catalyst_posts(
        self,
        *,
        token_id: str | None,
        chain: str | None,
        address: str | None,
        window: str,
        scope: str,
        window_start_ms: int | None,
        window_end_ms: int,
        watched_only: bool,
        requested_limit: int,
        selected_range: str,
        reference_ms: int,
    ) -> dict[str, Any]:
        pool_start_ms = None if window_start_ms is None else max(0, window_start_ms - CATALYST_BASELINE_MS)
        pool_rows = [
            dict(row)
            for row in self._post_rows(
                token_id=token_id,
                chain=chain,
                address=address,
                window_start_ms=pool_start_ms,
                window_end_ms=window_end_ms,
                watched_only=watched_only,
                limit=1000,
                cursor=None,
            )
        ]
        candidate_rows = [
            row
            for row in pool_rows
            if window_start_ms is None or int(row.get("received_at_ms") or 0) >= window_start_ms
        ]
        candidates = [_post_item(row, reference_ms=reference_ms) | _catalyst_row_fields(row) for row in candidate_rows]
        pool_items = [_post_item(row, reference_ms=reference_ms) | _catalyst_row_fields(row) for row in pool_rows]
        ranked_items = CatalystRankingService().rank(
            candidates=candidates,
            pool=pool_items,
            limit=requested_limit,
        )
        return {
            "query": {
                "token_id": token_id,
                "chain": chain,
                "address": address,
                "window": window,
                "scope": scope,
                "sort": "catalyst",
                "range": selected_range,
            },
            "score_window": {"window": window},
            "total_count": len(candidate_rows),
            "returned_count": len(ranked_items),
            "has_more": False,
            "next_cursor": None,
            "items": ranked_items,
        }

    def _range_bounds(
        self,
        *,
        token_id: str | None,
        chain: str | None,
        address: str | None,
        score_window_start_ms: int,
        score_window_end_ms: int,
        watched_only: bool,
        post_range: str,
    ) -> tuple[int | None, int]:
        if post_range == "all_history":
            return None, score_window_end_ms
        if post_range == "since_ignition":
            first_seen_ms = self._first_seen_in_window(
                token_id=token_id,
                chain=chain,
                address=address,
                window_start_ms=score_window_start_ms,
                window_end_ms=score_window_end_ms,
                watched_only=watched_only,
            )
            return (first_seen_ms if first_seen_ms is not None else score_window_end_ms), score_window_end_ms
        return score_window_start_ms, score_window_end_ms

    def _first_seen_in_window(
        self,
        *,
        token_id: str | None,
        chain: str | None,
        address: str | None,
        window_start_ms: int,
        window_end_ms: int,
        watched_only: bool,
    ) -> int | None:
        clauses, params = _base_clauses(
            token_id=token_id,
            chain=chain,
            address=address,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=watched_only,
        )
        row = self.conn.execute(
            f"""
            SELECT MIN(eta.received_at_ms) AS first_seen_ms
            FROM event_token_attributions eta
            WHERE {" AND ".join(clauses)}
            """,
            params,
        ).fetchone()
        return int(row["first_seen_ms"]) if row and row["first_seen_ms"] is not None else None

    def _post_rows(
        self,
        *,
        token_id: str | None,
        chain: str | None,
        address: str | None,
        window_start_ms: int | None,
        window_end_ms: int,
        watched_only: bool,
        limit: int,
        cursor: tuple[int, str] | None,
    ) -> list[dict[str, Any]]:
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
            clauses.append("(eta.received_at_ms < %s OR (eta.received_at_ms = %s AND eta.event_id < %s))")
            params.extend([cursor_ms, cursor_ms, cursor_event_id])
        where = " AND ".join(clauses)
        return self.conn.execute(
            f"""
            WITH filtered AS (
              SELECT eta.*
              FROM event_token_attributions eta
              WHERE {where}
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
              e.tweet_id,
              e.text_clean,
              e.search_text,
              e.canonical_url,
              e.reference_json,
              e.is_watched AS event_is_watched,
              see.event_type,
              CASE
                WHEN ranked.is_watched = true THEN NOT EXISTS (
                  SELECT 1
                  FROM event_token_attributions previous
                  WHERE previous.identity_key = ranked.identity_key
                    AND previous.received_at_ms < ranked.received_at_ms
                    AND previous.is_watched = true
                    AND previous.token_id IS NOT NULL
                    AND previous.attribution_status IN ('direct', 'selected')
                    AND previous.attribution_weight > 0
                    AND previous.chain IS NOT NULL
                    AND previous.address IS NOT NULL
                    AND previous.chain NOT IN ('unknown', 'evm', 'evm_unknown')
                )
                ELSE false
              END AS is_first_seen_by_watched_for_token
            FROM ranked
            LEFT JOIN events e ON e.event_id = ranked.event_id
            LEFT JOIN social_event_extractions see ON see.event_id = ranked.event_id
            WHERE ranked.rn = 1
            ORDER BY ranked.received_at_ms DESC, ranked.event_id DESC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()

    def _total_count(
        self,
        *,
        token_id: str | None,
        chain: str | None,
        address: str | None,
        window_start_ms: int | None,
        window_end_ms: int,
        watched_only: bool,
    ) -> int:
        clauses, params = _base_clauses(
            token_id=token_id,
            chain=chain,
            address=address,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=watched_only,
        )
        row = self.conn.execute(
            f"""
            SELECT COUNT(DISTINCT eta.event_id) AS count
            FROM event_token_attributions eta
            WHERE {" AND ".join(clauses)}
            """,
            params,
        ).fetchone()
        return int(row["count"] or 0) if row else 0


def _base_clauses(
    *,
    token_id: str | None,
    chain: str | None,
    address: str | None,
    window_start_ms: int | None,
    window_end_ms: int,
    watched_only: bool,
) -> tuple[list[str], list[Any]]:
    clauses = [
        "eta.received_at_ms < %s",
        "eta.token_id IS NOT NULL",
        "eta.attribution_status IN ('direct', 'selected')",
        "eta.attribution_weight > 0",
        "eta.chain IS NOT NULL",
        "eta.address IS NOT NULL",
        "eta.chain NOT IN ('unknown', 'evm', 'evm_unknown')",
    ]
    params: list[Any] = [window_end_ms]
    if window_start_ms is not None:
        clauses.insert(0, "eta.received_at_ms >= %s")
        params.insert(0, window_start_ms)
    if token_id:
        clauses.append("eta.token_id = %s")
        params.append(token_id)
    elif chain and address:
        clauses.extend(["eta.chain = %s", "eta.address = %s"])
        params.extend([chain, address])
    else:
        raise TokenPostsIdentityError("missing_token_identity")
    if watched_only:
        clauses.append("eta.is_watched = true")
    return clauses, params


def _post_item(row: dict[str, Any], *, reference_ms: int) -> dict[str, Any]:
    quality = post_quality_score(
        {
            "text": row.get("text_clean"),
            "mention_source": row.get("source"),
            "is_watched": row.get("event_is_watched")
            if row.get("event_is_watched") is not None
            else row.get("is_watched"),
            "received_at_ms": row.get("received_at_ms"),
            "attribution_status": row.get("attribution_status"),
            "attribution_confidence": row.get("attribution_confidence"),
            "attribution_weight": row.get("attribution_weight"),
            "event_age_ms": _age_ms(reference_ms, _int_or_none(row.get("received_at_ms"))),
        }
    )
    return {
        "event_id": row.get("event_id"),
        "handle": row.get("event_author_handle") or row.get("author_handle"),
        "text": row.get("text_clean"),
        "url": row.get("canonical_url"),
        "received_at_ms": row.get("received_at_ms"),
        "mention_source": row.get("source"),
        "attribution_status": row.get("attribution_status"),
        "attribution_confidence": row.get("attribution_confidence"),
        "attribution_weight": row.get("attribution_weight"),
        "is_watched": bool(
            row.get("event_is_watched") if row.get("event_is_watched") is not None else row.get("is_watched")
        ),
        "is_first_seen_by_watched_for_token": bool(row.get("is_first_seen_by_watched_for_token")),
        "event_type": row.get("event_type"),
        "reference": _reference(row.get("reference_json")),
        "post_quality": quality,
    }


def _catalyst_row_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "tweet_id": row.get("tweet_id"),
        "text_clean": row.get("text_clean"),
        "search_text": row.get("search_text"),
        "reference_json": row.get("reference_json"),
        "event_author_handle": row.get("event_author_handle"),
        "author_handle": row.get("author_handle"),
        "source": row.get("source"),
        "event_is_watched": row.get("event_is_watched"),
    }


def _reference(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    tweet_id = value.get("tweet_id")
    author_handle = value.get("author_handle")
    reference_type = value.get("type")
    if not tweet_id and not author_handle and not reference_type:
        return None
    return {
        "tweet_id": str(tweet_id) if tweet_id is not None else None,
        "author_handle": str(author_handle).strip().lstrip("@").lower() if author_handle else None,
        "type": str(reference_type) if reference_type is not None else None,
    }


def _normalized_chain_address(*, chain: str | None, address: str | None) -> tuple[str | None, str | None]:
    if not address:
        return chain or None, None
    try:
        normalized_chain, normalized_address = normalize_ca(address, chain=chain)
    except ValueError as exc:
        raise TokenPostsIdentityError("invalid_token_identity") from exc
    return normalized_chain, normalized_address


def _decode_cursor(cursor: str | None) -> tuple[int, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return int(payload["received_at_ms"]), str(payload["event_id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TokenPostsCursorError("invalid_cursor") from exc


def _encode_cursor(item: dict[str, Any]) -> str:
    payload = json.dumps(
        {"received_at_ms": int(item["received_at_ms"]), "event_id": str(item["event_id"])},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _age_ms(reference_ms: int, value: int | None) -> int | None:
    if value is None:
        return None
    return max(0, reference_ms - value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _now_ms() -> int:
    return int(time.time() * 1000)
