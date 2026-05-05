from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections import defaultdict
from typing import Any

from .token_baseline import token_baseline

BASELINE_LIMITS = {
    "5m": 24,
    "1h": 48,
    "4h": 24,
    "24h": 14,
}
WINDOW_MS = {
    "5m": 300_000,
    "1h": 3_600_000,
    "4h": 4 * 3_600_000,
    "24h": 86_400_000,
}


class RollingTokenFlow:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def token_flow(
        self,
        *,
        window: str,
        limit: int,
        watched_only: bool = False,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        size_ms = WINDOW_MS[window]
        reference_ms = now_ms if now_ms is not None else _now_ms()
        return self._token_flow_window(
            window=window,
            window_start_ms=reference_ms - size_ms,
            window_end_ms=reference_ms,
            limit=limit,
            watched_only=watched_only,
        )

    def _token_flow_window(
        self,
        *,
        window: str,
        window_start_ms: int,
        window_end_ms: int,
        limit: int,
        watched_only: bool,
    ) -> list[dict[str, Any]]:
        mention_rows = self._token_mentions_for_window(
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            watched_only=watched_only,
        )
        if not mention_rows:
            return []

        groups = self._group_mentions(
            mention_rows,
            window=window,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
        )
        current_identity_keys = set(groups)
        token_ids = {str(group["token_id"]) for group in groups.values() if group.get("token_id")}
        baseline_counts = self._baseline_slot_counts(
            token_ids=token_ids,
            current_identity_keys=current_identity_keys,
            window_start_ms=window_start_ms,
            window_size_ms=WINDOW_MS[window],
            sample_count=BASELINE_LIMITS.get(window, 24),
            watched_only=watched_only,
        )
        bounds = self._mention_bounds(
            token_ids=token_ids,
            current_identity_keys=current_identity_keys,
            watched_only=watched_only,
        )
        for identity_key, group in groups.items():
            slot_counts = baseline_counts.get(identity_key, [0] * BASELINE_LIMITS.get(window, 24))
            baseline = token_baseline(slot_counts=slot_counts, current_mentions=int(group["mention_count"]))
            group["baseline"] = baseline
            group["previous_mentions"] = int(slot_counts[-1]) if slot_counts else 0
            bound = bounds.get(identity_key, {})
            group["global_first_seen_ms"] = bound.get("first_seen_ms")
            group["global_latest_seen_ms"] = bound.get("latest_seen_ms")
            group["global_first_watched_seen_ms"] = bound.get("first_watched_seen_ms")

        rows = sorted(
            groups.values(),
            key=lambda item: (
                int(item["watched_mention_count"]),
                float(item["velocity"]),
                int(item["mention_count"]),
                int(item["window_end_ms"]),
            ),
            reverse=True,
        )
        return rows[: max(0, int(limit))]

    def _group_mentions(
        self,
        rows: list[sqlite3.Row],
        *,
        window: str,
        window_start_ms: int,
        window_end_ms: int,
    ) -> dict[str, dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        author_maps: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        total_mentions = 0
        total_watched_mentions = 0
        for raw_row in rows:
            row = dict(raw_row)
            identity = _tradeable_token_identity(row)
            identity_key = str(identity["identity_key"])
            group = groups.get(identity_key)
            if group is None:
                group = {
                    **identity,
                    "window_id": _id("token_window", identity_key, window, str(window_start_ms)),
                    "window": window,
                    "window_start_ms": window_start_ms,
                    "window_end_ms": window_end_ms,
                    "mention_count": 0,
                    "direct_mention_count": 0,
                    "symbol_mention_count": 0,
                    "weighted_mention_count": 0.0,
                    "attribution_confidence_sum": 0.0,
                    "attribution_count": 0,
                    "selected_symbol_mentions": 0,
                    "candidate_count": 0,
                    "attribution_reasons": [],
                    "attribution_risks": [],
                    "watched_mention_count": 0,
                    "unique_author_count": 0,
                    "watched_author_count": 0,
                    "weighted_reach": 0.0,
                    "market_mindshare": 0.0,
                    "watched_mindshare": 0.0,
                    "velocity": 0.0,
                    "top_authors": [],
                    "top_events": [],
                    "events_for_diffusion": [],
                    "first_seen_ms": None,
                    "latest_seen_ms": None,
                    "first_watched_seen_ms": None,
                    "created_at_ms": window_start_ms,
                    "updated_at_ms": window_end_ms,
                }
                groups[identity_key] = group

            is_watched = bool(row.get("is_watched"))
            followers = int(row.get("author_followers") or 0)
            received_at_ms = int(row["received_at_ms"])
            attribution_status = str(row.get("attribution_status") or "")
            attribution_weight = float(row.get("attribution_weight") or 0.0)
            attribution_confidence = float(row.get("attribution_confidence") or 0.0)
            mention_identity_key = str(row.get("mention_identity_key") or row.get("identity_key") or "")
            group["mention_count"] = int(group["mention_count"]) + 1
            group["weighted_mention_count"] = float(group["weighted_mention_count"]) + attribution_weight
            group["attribution_confidence_sum"] = float(group["attribution_confidence_sum"]) + attribution_confidence
            group["attribution_count"] = int(group["attribution_count"]) + 1
            group["candidate_count"] = max(int(group["candidate_count"]), int(row.get("candidate_count") or 0))
            group["direct_mention_count"] = int(group["direct_mention_count"]) + (
                1 if attribution_status == "direct" else 0
            )
            is_symbol_selected = attribution_status == "selected" and mention_identity_key.startswith("symbol:")
            group["symbol_mention_count"] = int(group["symbol_mention_count"]) + (1 if is_symbol_selected else 0)
            group["selected_symbol_mentions"] = int(group["selected_symbol_mentions"]) + (
                1 if is_symbol_selected else 0
            )
            group["watched_mention_count"] = int(group["watched_mention_count"]) + (1 if is_watched else 0)
            group["velocity"] = float(group["mention_count"]) / ((window_end_ms - window_start_ms) / 60_000)
            group["first_seen_ms"] = _min_or_value(group["first_seen_ms"], received_at_ms)
            group["latest_seen_ms"] = _max_or_value(group["latest_seen_ms"], received_at_ms)
            if is_watched:
                group["first_watched_seen_ms"] = _min_or_value(group["first_watched_seen_ms"], received_at_ms)
            group["attribution_reasons"] = _dedupe(
                [*group["attribution_reasons"], *_json_list(row.get("reasons_json"))]
            )
            group["attribution_risks"] = _dedupe([*group["attribution_risks"], *_json_list(row.get("risks_json"))])

            author_handle = row.get("author_handle")
            if author_handle:
                author_map = author_maps[identity_key]
                author = author_map.get(
                    str(author_handle),
                    {
                        "handle": str(author_handle),
                        "count": 0,
                        "followers": 0,
                        "watched_count": 0,
                        "latest_received_at_ms": 0,
                    },
                )
                author["count"] = int(author["count"]) + 1
                author["followers"] = max(int(author["followers"]), followers)
                author["watched_count"] = int(author["watched_count"]) + (1 if is_watched else 0)
                author["latest_received_at_ms"] = max(int(author["latest_received_at_ms"]), received_at_ms)
                author_map[str(author_handle)] = author

            group["top_events"].append(
                {
                    "event_id": row.get("event_id"),
                    "author_handle": row.get("event_author_handle") or row.get("author_handle"),
                    "text_clean": row.get("text_clean"),
                    "canonical_url": row.get("canonical_url"),
                    "is_watched": (
                        row.get("event_is_watched")
                        if row.get("event_is_watched") is not None
                        else row.get("is_watched")
                    ),
                    "received_at_ms": received_at_ms,
                    "mention_source": row.get("source"),
                    "source": row.get("source"),
                    "attribution_status": attribution_status,
                    "attribution_confidence": attribution_confidence,
                    "attribution_weight": attribution_weight,
                    "mention_identity_key": mention_identity_key,
                }
            )
            group["events_for_diffusion"].append(
                {
                    "event_id": row.get("event_id"),
                    "author_handle": row.get("event_author_handle") or row.get("author_handle"),
                    "author_followers": row.get("author_followers"),
                    "text_clean": row.get("text_clean"),
                    "search_text": row.get("search_text"),
                    "received_at_ms": received_at_ms,
                    "is_watched": (
                        row.get("event_is_watched")
                        if row.get("event_is_watched") is not None
                        else row.get("is_watched")
                    ),
                    "mention_source": row.get("source"),
                    "source": row.get("source"),
                    "attribution_status": attribution_status,
                    "attribution_confidence": attribution_confidence,
                    "attribution_weight": attribution_weight,
                    "mention_identity_key": mention_identity_key,
                }
            )
            total_mentions += 1
            total_watched_mentions += 1 if is_watched else 0

        for identity_key, group in groups.items():
            authors = sorted(
                author_maps[identity_key].values(),
                key=lambda item: (
                    int(item.get("count") or 0),
                    int(item.get("followers") or 0),
                    int(item.get("latest_received_at_ms") or 0),
                ),
                reverse=True,
            )
            group["top_authors"] = authors[:20]
            group["unique_author_count"] = len(authors)
            group["watched_author_count"] = sum(1 for item in authors if int(item.get("watched_count") or 0) > 0)
            group["weighted_reach"] = sum(int(item.get("followers") or 0) for item in authors)
            attribution_count = int(group.get("attribution_count") or 0)
            group["avg_attribution_confidence"] = (
                float(group.get("attribution_confidence_sum") or 0.0) / attribution_count
                if attribution_count
                else 0.0
            )
            group["top_events"] = sorted(
                group["top_events"],
                key=lambda item: int(item.get("received_at_ms") or 0),
                reverse=True,
            )[:20]
            group["market_mindshare"] = (float(group["mention_count"]) / total_mentions) if total_mentions else 0.0
            group["watched_mindshare"] = (
                float(group["watched_mention_count"]) / total_watched_mentions if total_watched_mentions else 0.0
            )
        return groups

    def _token_mentions_for_window(
        self,
        *,
        window_start_ms: int,
        window_end_ms: int,
        watched_only: bool,
    ) -> list[sqlite3.Row]:
        watched_clause = "AND eta.is_watched = 1" if watched_only else ""
        return self.conn.execute(
            f"""
            SELECT
              eta.*,
              e.author_handle AS event_author_handle,
              e.text_clean,
              e.search_text,
              e.canonical_url,
              e.is_watched AS event_is_watched
            FROM event_token_attributions eta
            LEFT JOIN events e ON e.event_id = eta.event_id
            WHERE eta.received_at_ms >= ?
              AND eta.received_at_ms < ?
              AND eta.token_id IS NOT NULL
              AND eta.attribution_status IN ('direct', 'selected')
              AND eta.attribution_weight > 0
              AND eta.chain IS NOT NULL
              AND eta.address IS NOT NULL
              AND eta.chain NOT IN ('unknown', 'evm', 'evm_unknown')
              {watched_clause}
            ORDER BY eta.received_at_ms DESC, eta.event_id DESC
            """,
            (window_start_ms, window_end_ms),
        ).fetchall()

    def _baseline_slot_counts(
        self,
        *,
        token_ids: set[str],
        current_identity_keys: set[str],
        window_start_ms: int,
        window_size_ms: int,
        sample_count: int,
        watched_only: bool,
    ) -> dict[str, list[int]]:
        baseline_start_ms = window_start_ms - sample_count * window_size_ms
        rows = self._raw_token_mentions(
            start_ms=baseline_start_ms,
            end_ms=window_start_ms,
            token_ids=token_ids,
            watched_only=watched_only,
        )
        counts: dict[str, list[int]] = defaultdict(lambda: [0] * sample_count)
        for raw_row in rows:
            row = dict(raw_row)
            identity_key = str(row["token_id"])
            if identity_key not in current_identity_keys:
                continue
            slot_index = (int(row["received_at_ms"]) - baseline_start_ms) // window_size_ms
            if 0 <= slot_index < sample_count:
                counts[identity_key][slot_index] += 1
        return counts

    def _mention_bounds(
        self,
        *,
        token_ids: set[str],
        current_identity_keys: set[str],
        watched_only: bool,
    ) -> dict[str, dict[str, Any]]:
        bounds: dict[str, dict[str, Any]] = {}
        for raw_row in self._indexed_mention_bound_rows(token_ids=token_ids, watched_only=watched_only):
            row = dict(raw_row)
            identity_key = str(row["token_id"])
            if identity_key not in current_identity_keys:
                continue
            current = bounds.setdefault(
                identity_key,
                {"first_seen_ms": None, "latest_seen_ms": None, "first_watched_seen_ms": None},
            )
            current["first_seen_ms"] = _min_or_value(current["first_seen_ms"], int(row["first_seen_ms"]))
            current["latest_seen_ms"] = _max_or_value(current["latest_seen_ms"], int(row["latest_seen_ms"]))
            if row.get("first_watched_seen_ms") is not None:
                current["first_watched_seen_ms"] = _min_or_value(
                    current["first_watched_seen_ms"],
                    int(row["first_watched_seen_ms"]),
                )
        return bounds

    def _indexed_mention_bound_rows(
        self,
        *,
        token_ids: set[str],
        watched_only: bool,
    ) -> list[sqlite3.Row]:
        if not token_ids:
            return []
        watched_clause = "AND is_watched = 1" if watched_only else ""
        placeholders = ",".join("?" for _ in token_ids)
        return self.conn.execute(
            f"""
            SELECT
              token_id,
              MIN(received_at_ms) AS first_seen_ms,
              MAX(received_at_ms) AS latest_seen_ms,
              MIN(CASE WHEN is_watched = 1 THEN received_at_ms END) AS first_watched_seen_ms
            FROM event_token_attributions
            WHERE token_id IN ({placeholders})
              AND attribution_status IN ('direct', 'selected')
              AND attribution_weight > 0
              AND chain IS NOT NULL
              AND address IS NOT NULL
              AND chain NOT IN ('unknown', 'evm', 'evm_unknown')
              {watched_clause}
            GROUP BY token_id
            """,
            sorted(token_ids),
        ).fetchall()

    def _raw_token_mentions(
        self,
        *,
        start_ms: int | None,
        end_ms: int | None,
        token_ids: set[str],
        watched_only: bool,
    ) -> list[sqlite3.Row]:
        if not token_ids:
            return []
        clauses = []
        params: list[Any] = []
        if start_ms is not None:
            clauses.append("received_at_ms >= ?")
            params.append(start_ms)
        if end_ms is not None:
            clauses.append("received_at_ms < ?")
            params.append(end_ms)
        placeholders = ",".join("?" for _ in token_ids)
        clauses.extend(
            [
                f"token_id IN ({placeholders})",
                "attribution_status IN ('direct', 'selected')",
                "attribution_weight > 0",
                "chain IS NOT NULL",
                "address IS NOT NULL",
                "chain NOT IN ('unknown', 'evm', 'evm_unknown')",
            ]
        )
        params.extend(sorted(token_ids))
        if watched_only:
            clauses.append("is_watched = 1")
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.conn.execute(f"SELECT * FROM event_token_attributions {where_clause}", params).fetchall()


def _tradeable_token_identity(row: dict[str, Any]) -> dict[str, Any]:
    symbol = _normalize_symbol(str(row.get("symbol") or row.get("address") or "UNKNOWN"))
    return {
        "identity_key": str(row["token_id"]),
        "token_id": str(row["token_id"]),
        "identity_status": str(row["identity_status"]),
        "chain": row.get("chain"),
        "address": row.get("address"),
        "symbol": symbol,
    }


def _normalize_symbol(symbol: str) -> str:
    text = symbol.strip().lstrip("$")
    return text.upper() if text.isascii() else text


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _min_or_value(current: Any, value: int) -> int:
    return value if current is None else min(int(current), value)


def _max_or_value(current: Any, value: int) -> int:
    return value if current is None else max(int(current), value)


def _json_list(value: Any) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _now_ms() -> int:
    return int(time.time() * 1000)
