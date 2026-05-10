from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION

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
                "market_hydration": _market_hydration(rows),
            },
        }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = row.get("factor_snapshot_json") if isinstance(row.get("factor_snapshot_json"), dict) else {}
    market = _market_from_snapshot(factor_snapshot)
    return {
        "intent": row.get("intent_json") or {},
        "target": _target_from_snapshot(factor_snapshot),
        "attention": _attention_from_snapshot(factor_snapshot),
        "market": market,
        "resolution": row.get("resolution_json") or {},
        "price": market,
        "score": _composite_from_snapshot(factor_snapshot),
        "factor_snapshot": factor_snapshot,
        "decision": row.get("decision"),
        "data_health": row.get("data_health_json") or {},
        "source_event_ids": row.get("source_event_ids_json") or [],
    }


def _target_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    subject = snapshot.get("subject") if isinstance(snapshot.get("subject"), dict) else {}
    return {
        "target_type": subject.get("target_type"),
        "target_id": subject.get("target_id"),
        "symbol": subject.get("symbol"),
        "chain": subject.get("chain"),
        "address": subject.get("address"),
        "target_market_type": subject.get("target_market_type"),
    }


def _attention_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    family = _family(snapshot, "social_attention")
    facts = family.get("facts") if isinstance(family.get("facts"), dict) else {}
    return dict(facts)


def _market_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    family = _family(snapshot, "market_quality")
    facts = family.get("facts") if isinstance(family.get("facts"), dict) else {}
    return dict(facts)


def _composite_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    composite = snapshot.get("composite") if isinstance(snapshot.get("composite"), dict) else {}
    return dict(composite)


def _family(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    families = snapshot.get("families") if isinstance(snapshot.get("families"), dict) else {}
    family = families.get(name) if isinstance(families.get(name), dict) else {}
    return family


def _market_hydration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "missing",
            "fresh": 0,
            "stale": 0,
            "missing": 0,
            "pending": 0,
            "total": 0,
        }
    counts = {"fresh": 0, "stale": 0, "missing": 0, "pending": 0}
    for row in rows:
        market = _market_from_snapshot(
            row.get("factor_snapshot_json") if isinstance(row.get("factor_snapshot_json"), dict) else {}
        )
        market_status = str(market.get("market_status") or "")
        observation_status = str(market.get("market_observation_status") or "")
        if market_status in {"fresh", "ready"}:
            counts["fresh"] += 1
        elif market_status == "stale" or observation_status == "stale":
            counts["stale"] += 1
        else:
            counts["missing"] += 1
        if observation_status == "pending_refresh":
            counts["pending"] += 1
    total = len(rows)
    status = "ready" if counts["stale"] == 0 and counts["missing"] == 0 else "partial"
    return {**counts, "status": status, "total": total}
