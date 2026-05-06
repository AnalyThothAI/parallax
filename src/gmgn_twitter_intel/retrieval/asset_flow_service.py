from __future__ import annotations

import time
from typing import Any

WINDOW_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}


class AssetFlowService:
    def __init__(self, *, assets):
        self.assets = assets

    def asset_flow(
        self,
        *,
        window: str,
        limit: int,
        scope: str,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_now_ms = int(now_ms or time.time() * 1000)
        window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
        rows = self.assets.recent_asset_attributions(
            since_ms=resolved_now_ms - window_ms,
            watched_only=scope == "matched",
            limit=max(1000, int(limit) * 50),
        )
        grouped = _group_rows(rows, window_ms=window_ms, now_ms=resolved_now_ms)
        resolved = [payload for payload in grouped.values() if payload["_lane"] == "resolved"]
        attention = [payload for payload in grouped.values() if payload["_lane"] == "attention"]
        resolved.sort(key=_sort_key)
        attention.sort(key=_sort_key)
        return {
            "resolved_assets": [_public_row(row) for row in resolved[:limit]],
            "attention_candidates": [_public_row(row) for row in attention[:limit]],
            "projection": {
                "status": "fresh",
                "version": "asset-flow-v1",
                "source": "asset_attributions",
                "source_max_received_at_ms": max((int(row.get("received_at_ms") or 0) for row in rows), default=0),
                "computed_at_ms": resolved_now_ms,
            },
        }


def _group_rows(rows: list[dict[str, Any]], *, window_ms: int, now_ms: int) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    five_min_ago = now_ms - WINDOW_MS["5m"]
    one_hour_ago = now_ms - WINDOW_MS["1h"]
    for row in rows:
        asset_id = str(row["asset_id"])
        payload = grouped.setdefault(asset_id, _initial_payload(row))
        decision_time_ms = int(row.get("decision_time_ms") or 0)
        payload["_latest_seen_ms"] = max(payload["_latest_seen_ms"], decision_time_ms)
        payload["_authors"].add(str(row.get("author_handle") or ""))
        if row.get("is_watched"):
            payload["attention"]["watched_mentions"] += 1
        if decision_time_ms >= five_min_ago:
            payload["attention"]["mentions_5m"] += 1
        if decision_time_ms >= one_hour_ago:
            payload["attention"]["mentions_1h"] += 1
        payload["attention"]["mentions_window"] += 1
    for payload in grouped.values():
        payload["attention"]["unique_authors"] = len({author for author in payload["_authors"] if author})
        payload["attention"]["latest_seen_ms"] = payload["_latest_seen_ms"] or None
    return grouped


def _initial_payload(row: dict[str, Any]) -> dict[str, Any]:
    lane = "resolved" if _is_resolved_row(row) else "attention"
    status = _resolution_status(row)
    return {
        "_lane": lane,
        "_authors": set(),
        "_latest_seen_ms": 0,
        "asset": {
            "asset_id": row["asset_id"],
            "symbol": row.get("canonical_symbol"),
            "asset_type": row.get("asset_type"),
            "identity_status": row.get("identity_status"),
        },
        "primary_venue": _venue(row) if row.get("venue_id") else None,
        "attention": {
            "mentions_5m": 0,
            "mentions_1h": 0,
            "mentions_window": 0,
            "unique_authors": 0,
            "watched_mentions": 0,
            "latest_seen_ms": None,
        },
        "resolution": {
            "status": status,
            "candidates": [],
        },
        "decision": "investigate" if lane == "attention" else "watch",
    }


def _is_resolved_row(row: dict[str, Any]) -> bool:
    return (
        row.get("attribution_status") in {"direct", "selected"}
        and row.get("identity_status") == "resolved"
        and bool(row.get("venue_id"))
    )


def _resolution_status(row: dict[str, Any]) -> str:
    if row.get("attribution_status") == "ambiguous" or row.get("identity_status") == "ambiguous":
        return "ambiguous"
    if _is_resolved_row(row):
        return "resolved"
    return "unresolved"


def _venue(row: dict[str, Any]) -> dict[str, Any]:
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


def _sort_key(row: dict[str, Any]) -> tuple[int, int]:
    return (-int(row["attention"]["mentions_window"]), -int(row.get("_latest_seen_ms") or 0))


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset": row["asset"],
        "primary_venue": row["primary_venue"],
        "attention": row["attention"],
        "resolution": row["resolution"],
        "decision": row["decision"],
    }
