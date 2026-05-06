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
        rows = self.assets.asset_flow_rows(
            since_ms=resolved_now_ms - window_ms,
            watched_only=scope == "matched",
            limit=max(0, int(limit)),
            now_ms=resolved_now_ms,
        )
        payloads = [_initial_payload(row) for row in rows]
        resolved = [payload for payload in payloads if payload["_lane"] == "resolved"]
        attention = [payload for payload in payloads if payload["_lane"] == "attention"]
        resolved.sort(key=_sort_key)
        attention.sort(key=_sort_key)
        return {
            "resolved_assets": [_public_row(row) for row in resolved[:limit]],
            "attention_candidates": [_public_row(row) for row in attention[:limit]],
            "projection": {
                "status": "fresh",
                "version": "asset-flow-v1",
                "source": "asset_attributions",
                "source_max_received_at_ms": max(
                    (int(row.get("source_max_received_at_ms") or row.get("received_at_ms") or 0) for row in rows),
                    default=0,
                ),
                "computed_at_ms": resolved_now_ms,
            },
        }


def _initial_payload(row: dict[str, Any]) -> dict[str, Any]:
    lane = "resolved" if _is_resolved_row(row) else "attention"
    status = _resolution_status(row)
    latest_seen_ms = int(row.get("latest_seen_ms") or row.get("decision_time_ms") or 0)
    return {
        "_lane": lane,
        "_latest_seen_ms": latest_seen_ms,
        "asset": {
            "asset_id": row["asset_id"],
            "symbol": row.get("canonical_symbol"),
            "asset_type": row.get("asset_type"),
            "identity_status": row.get("asset_identity_status") or row.get("identity_status"),
        },
        "primary_venue": _venue(row) if row.get("venue_id") else None,
        "attention": {
            "mentions_5m": int(row.get("mentions_5m") or 0),
            "mentions_1h": int(row.get("mentions_1h") or 0),
            "mentions_window": int(row.get("mentions_window") or 0),
            "unique_authors": int(row.get("unique_authors") or 0),
            "watched_mentions": int(row.get("watched_mentions") or 0),
            "latest_seen_ms": latest_seen_ms or None,
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
