from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from gmgn_twitter_intel.domains.evidence.interfaces import decode_event_row
from gmgn_twitter_intel.domains.token_intel.interfaces import EventTokenProjectionQuery
from gmgn_twitter_intel.domains.watchlist_intel.types import (
    WatchlistTimelineCursorError,
    decode_watchlist_timeline_cursor,
    encode_watchlist_timeline_cursor,
    normalize_watchlist_handle,
)


class WatchlistIntelRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def timeline(self, *, handle: str, scope: str, cursor: str | None, limit: int) -> dict[str, Any]:
        normalized = normalize_watchlist_handle(handle)
        parsed_scope = _timeline_scope(scope)
        parsed_limit = max(0, int(limit))
        clauses = ["lower(e.author_handle) = %s"]
        params: list[Any] = [normalized]
        if cursor:
            try:
                cursor_received_at_ms, cursor_event_id = decode_watchlist_timeline_cursor(cursor)
            except WatchlistTimelineCursorError:
                raise
            clauses.append("(e.received_at_ms, e.event_id) < (%s, %s)")
            params.extend([cursor_received_at_ms, cursor_event_id])
        rows = self.conn.execute(
            f"""
            SELECT
              e.*
            FROM events e
            WHERE {" AND ".join(clauses)}
            ORDER BY e.received_at_ms DESC, e.event_id DESC
            LIMIT %s
            """,
            (*params, parsed_limit + 1),
        ).fetchall()
        decoded = [_decode_timeline_row(dict(row)) for row in rows]
        visible = decoded[:parsed_limit]
        resolutions = self.token_resolutions_for_events(tuple(str(item["event_id"]) for item in visible))
        for item in visible:
            item["token_resolutions"] = resolutions.get(str(item["event_id"]), [])
        has_more = len(decoded) > parsed_limit
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = encode_watchlist_timeline_cursor(
                received_at_ms=int(last["received_at_ms"]),
                event_id=str(last["event_id"]),
            )
        return {
            "query": {"handle": normalized, "scope": parsed_scope, "limit": parsed_limit},
            "items": visible,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def handles_overview(self, *, handles: Sequence[str], since_ms: int) -> list[dict[str, Any]]:
        normalized = [normalize_watchlist_handle(handle) for handle in handles]
        if not normalized:
            return []
        return [self._handle_overview_counts(handle=handle, since_ms=since_ms) for handle in normalized]

    def _handle_overview_counts(self, *, handle: str, since_ms: int) -> dict[str, Any]:
        last_event = self.conn.execute(
            """
            SELECT received_at_ms
            FROM events
            WHERE lower(author_handle) = %s
            ORDER BY received_at_ms DESC, event_id DESC
            LIMIT 1
            """,
            (handle,),
        ).fetchone()
        recent_source = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM events
            WHERE lower(author_handle) = %s
              AND received_at_ms >= %s
            """,
            (handle, int(since_ms)),
        ).fetchone()
        return _decode_handle_overview_row(
            {
                "handle": handle,
                "last_source_event_at_ms": last_event["received_at_ms"] if last_event else None,
                "recent_source_event_count": int(recent_source["count"] if recent_source else 0),
                "recent_signal_event_count": 0,
                "total_signal_event_count": 0,
            }
        )

    def handle_overview(self, *, handle: str, scope: str, since_ms: int, limit: int = 500) -> dict[str, Any]:
        normalized = normalize_watchlist_handle(handle)
        parsed_scope = _timeline_scope(scope)
        cluster_limit = max(0, int(limit))
        clauses = ["lower(e.author_handle) = %s", "e.received_at_ms >= %s"]
        params: list[Any] = [normalized, int(since_ms)]
        rows = self.conn.execute(
            f"""
            SELECT
              e.*
            FROM events e
            WHERE {" AND ".join(clauses)}
            ORDER BY e.received_at_ms DESC, e.event_id DESC
            """,
            tuple(params),
        ).fetchall()
        events = [_decode_timeline_row(dict(row)) for row in rows]
        event_ids = tuple(str(item["event_id"]) for item in events)
        resolutions_by_event = self.token_resolutions_for_events(event_ids)
        for item in events:
            item["token_resolutions"] = resolutions_by_event.get(str(item["event_id"]), [])
        clusters = _overview_clusters(events)
        source_event_count = len(events)
        signal_event_count = 0
        last_source_event_at_ms = max((int(item.get("received_at_ms") or 0) for item in events), default=None)
        candidate_mention_count = _cluster_count(clusters["candidate_mention_clusters"])
        resolved_token_count = _cluster_count(clusters["resolved_token_clusters"])
        public_clusters = _limit_overview_clusters(clusters, cluster_limit)
        risk_notes = list(clusters["risk_notes"])
        if candidate_mention_count:
            risk_notes.append("candidate_mentions_unresolved")
        return {
            "query": {"handle": normalized, "scope": parsed_scope},
            "metrics": {
                "source_event_count": source_event_count,
                "signal_event_count": signal_event_count,
                "resolved_token_count": resolved_token_count,
                "candidate_mention_count": candidate_mention_count,
                "narrative_count": _cluster_count(clusters["narrative_clusters"]),
                "last_source_event_at_ms": last_source_event_at_ms,
            },
            "resolved_token_clusters": public_clusters["resolved_token_clusters"],
            "candidate_mention_clusters": public_clusters["candidate_mention_clusters"],
            "narrative_clusters": public_clusters["narrative_clusters"],
            "clusters_truncated": _overview_clusters_truncated(clusters, cluster_limit),
            "risk_notes": sorted(dict.fromkeys(risk_notes)),
        }

    def token_resolutions_for_events(self, event_ids: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
        return EventTokenProjectionQuery(self.conn).for_events(event_ids)

def _decode_timeline_row(row: dict[str, Any]) -> dict[str, Any]:
    event = decode_event_row(row)
    return {
        "event_id": str(row.get("event_id") or ""),
        "received_at_ms": int(row.get("received_at_ms") or 0),
        "author_handle": row.get("author_handle"),
        "action": row.get("action"),
        "text_clean": row.get("text_clean") or row.get("text"),
        "canonical_url": row.get("canonical_url"),
        "cashtags": _loads(row.get("cashtags_json"), []),
        "hashtags": _loads(row.get("hashtags_json"), []),
        "mentions": _loads(row.get("mentions_json"), []),
        "event": event,
        "social_event": None,
    }


def _decode_handle_overview_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "handle": str(row.get("handle") or ""),
        "last_source_event_at_ms": _optional_int(row.get("last_source_event_at_ms")),
        "recent_source_event_count": int(row.get("recent_source_event_count") or 0),
        "recent_signal_event_count": int(row.get("recent_signal_event_count") or 0),
        "total_signal_event_count": int(row.get("total_signal_event_count") or 0),
    }


def _overview_clusters(events: list[dict[str, Any]]) -> dict[str, Any]:
    resolved: dict[str, dict[str, Any]] = {}
    candidates: dict[str, dict[str, Any]] = {}
    narratives: dict[str, dict[str, Any]] = {}
    resolved_symbols: set[str] = set()

    for item in events:
        for resolution in _list(item.get("token_resolutions")):
            symbol = _token_symbol(resolution)
            target_id = str(resolution.get("target_id") or "")
            target_type = str(resolution.get("target_type") or "")
            key = f"{target_type}:{target_id}" if target_id else f"symbol:{symbol}"
            label = _money_label(symbol or target_id.rsplit(":", maxsplit=1)[-1])
            resolved_symbols.add(_symbol_key(symbol or label))
            cluster = resolved.setdefault(
                key,
                {
                    "label": label,
                    "count": 0,
                    "query": label,
                    "kind": "resolved_token",
                    "target_type": target_type or None,
                    "target_id": target_id or None,
                    "symbol": symbol,
                    "source": "token_resolutions",
                },
            )
            cluster["count"] += 1

    for item in events:
        for cashtag in _list(item.get("cashtags")):
            symbol = _clean_symbol(cashtag)
            if not symbol:
                continue
            key = _symbol_key(symbol)
            if key in resolved_symbols or key in candidates:
                continue
            _increment_cluster(
                candidates,
                key,
                label=_money_label(symbol),
                query=_money_label(symbol),
                kind="candidate_mention",
                source="event_cashtags",
            )
        for hashtag in _list(item.get("hashtags")):
            term = _clean_hashtag(hashtag)
            if term:
                _increment_cluster(
                    narratives,
                    f"hashtag:{term.lower()}",
                    label=f"#{term}",
                    query=f"#{term}",
                    kind="narrative",
                    source="event_hashtags",
                )
    return {
        "resolved_token_clusters": _sorted_clusters(resolved.values()),
        "candidate_mention_clusters": _sorted_clusters(candidates.values()),
        "narrative_clusters": _sorted_clusters(narratives.values()),
        "risk_notes": [],
    }


def _increment_cluster(
    clusters: dict[str, dict[str, Any]],
    key: str,
    *,
    label: str,
    query: str,
    kind: str,
    source: str,
) -> None:
    cluster = clusters.setdefault(
        key,
        {
            "label": label,
            "count": 0,
            "query": query,
            "kind": kind,
            "source": source,
        },
    )
    cluster["count"] += 1


def _sorted_clusters(clusters: Any) -> list[dict[str, Any]]:
    return sorted(
        (dict(cluster) for cluster in clusters),
        key=lambda item: (-int(item.get("count") or 0), str(item.get("label") or "").lower()),
    )


def _cluster_count(clusters: list[dict[str, Any]]) -> int:
    return sum(int(cluster.get("count") or 0) for cluster in clusters)


def _limit_overview_clusters(clusters: dict[str, Any], limit: int) -> dict[str, Any]:
    return {
        "resolved_token_clusters": clusters["resolved_token_clusters"][:limit],
        "candidate_mention_clusters": clusters["candidate_mention_clusters"][:limit],
        "narrative_clusters": clusters["narrative_clusters"][:limit],
    }


def _overview_clusters_truncated(clusters: dict[str, Any], limit: int) -> bool:
    return any(
        len(clusters[key]) > limit
        for key in ("resolved_token_clusters", "candidate_mention_clusters", "narrative_clusters")
    )


def _token_symbol(value: dict[str, Any]) -> str | None:
    symbol = _clean_symbol(value.get("symbol"))
    if symbol:
        return symbol
    target_id = str(value.get("target_id") or "")
    if str(value.get("target_type") or "") == "CexToken" and target_id:
        return _clean_symbol(target_id.rsplit(":", maxsplit=1)[-1])
    return None


def _clean_symbol(value: Any) -> str | None:
    symbol = str(value or "").strip().lstrip("$").upper()
    return symbol or None


def _clean_hashtag(value: Any) -> str | None:
    tag = str(value or "").strip().lstrip("#")
    return tag or None


def _money_label(value: str) -> str:
    symbol = _clean_symbol(value) or str(value or "").strip()
    return f"${symbol}" if symbol and not symbol.startswith("$") else symbol


def _symbol_key(value: Any) -> str:
    return (_clean_symbol(value) or "").upper()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _timeline_scope(value: str) -> str:
    if value in {"signal", "all"}:
        return value
    raise ValueError("invalid_scope")


def _loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    if not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


__all__ = ["WatchlistIntelRepository"]
