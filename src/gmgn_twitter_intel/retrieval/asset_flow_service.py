from __future__ import annotations

from typing import Any

from ..pipeline.token_radar_contract import TOKEN_RADAR_PROJECTION_VERSION

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
        row_limit = max(0, int(limit)) * 2
        rows = self.token_radar.latest_rows(
            window=window,
            scope=scope,
            limit=row_limit,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        )
        targets = [_public_row(row) for row in rows if row.get("lane") == "resolved"]
        attention = [_public_row(row) for row in rows if row.get("lane") == "attention"]
        computed_at_ms = max((int(row.get("computed_at_ms") or 0) for row in rows), default=0) or None
        return {
            "targets": targets[:limit],
            "attention": attention[:limit],
            "projection": {
                "status": "fresh" if rows else "missing",
                "version": TOKEN_RADAR_PROJECTION_VERSION,
                "source": "token_radar_rows",
                "source_max_received_at_ms": max(
                    (int(row.get("source_max_received_at_ms") or 0) for row in rows),
                    default=0,
                ),
                "computed_at_ms": computed_at_ms,
            },
        }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent": row.get("intent_json") or {},
        "target": row.get("target_json") or {},
        "attention": row.get("attention_json") or {},
        "resolution": row.get("resolution_json") or {},
        "price": row.get("price_json") or {},
        "score": row.get("score_json") or {},
        "decision": row.get("decision"),
        "data_health": row.get("data_health_json") or {},
        "source_event_ids": row.get("source_event_ids_json") or [],
    }
