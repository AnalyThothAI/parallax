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
    def __init__(self, *, token_radar):
        self.token_radar = token_radar

    def asset_flow(
        self,
        *,
        window: str,
        limit: int,
        scope: str,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_now_ms = int(now_ms or time.time() * 1000)
        row_limit = max(0, int(limit)) * 2
        rows = self.token_radar.latest_rows(window=window, scope=scope, limit=row_limit)
        resolved = [_public_row(row) for row in rows if row.get("lane") == "resolved"]
        attention = [_public_row(row) for row in rows if row.get("lane") == "attention"]
        return {
            "resolved_assets": resolved[:limit],
            "attention_candidates": attention[:limit],
            "projection": {
                "status": "fresh",
                "version": "token-radar-v3",
                "source": "token_radar_rows",
                "source_max_received_at_ms": max(
                    (int(row.get("source_max_received_at_ms") or 0) for row in rows),
                    default=0,
                ),
                "computed_at_ms": resolved_now_ms,
            },
        }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent": row.get("intent_json") or {},
        "asset": row.get("asset_json") or {},
        "primary_venue": row.get("primary_venue_json"),
        "attention": row.get("attention_json") or {},
        "resolution": row.get("resolution_json") or {},
        "market": row.get("market_json") or {},
        "score": row.get("score_json") or {},
        "decision": row.get("decision"),
        "data_health": row.get("data_health_json") or {},
    }
