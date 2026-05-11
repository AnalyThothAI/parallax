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
    def __init__(self, *, token_radar: Any, current_market: Any) -> None:
        self.token_radar = token_radar
        self.current_market = current_market

    def asset_flow(
        self,
        *,
        window: str,
        limit: int,
        scope: str,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        coverage = self.token_radar.latest_coverage(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=(window,),
            scopes=(scope,),
        ).get((window, scope))
        if not coverage or coverage.get("status") != "ready":
            return _pending_projection_payload(coverage)

        row_limit = max(0, int(limit)) * 2
        rows = self.token_radar.latest_rows(
            window=window,
            scope=scope,
            limit=row_limit,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        )
        computed_at_ms = max((int(row.get("computed_at_ms") or 0) for row in rows), default=0) or None
        market_read_time_ms = int(now_ms or computed_at_ms or 0)
        subjects = _subjects_from_rows(rows)
        market_snapshots = self.current_market.current_for_subjects(subjects, now_ms=market_read_time_ms)
        public_rows = [
            _public_row(
                row,
                market_snapshots.get(_target_key_from_snapshot(row.get("factor_snapshot_json"))),
            )
            for row in rows
        ]
        targets = [row for row in public_rows if row.get("_lane") == "resolved"]
        attention = [row for row in public_rows if row.get("_lane") == "attention"]
        for row in [*targets, *attention]:
            row.pop("_lane", None)
        return {
            "targets": targets[:limit],
            "attention": attention[:limit],
            "projection": {
                "status": "fresh",
                "version": TOKEN_RADAR_PROJECTION_VERSION,
                "source": "token_radar_rows",
                "reason": coverage.get("reason"),
                "row_count": int(coverage.get("row_count") or 0),
                "source_rows": int(coverage.get("source_rows") or 0),
                "source_max_received_at_ms": max(
                    (int(row.get("source_max_received_at_ms") or 0) for row in rows),
                    default=0,
                ),
                "computed_at_ms": computed_at_ms if computed_at_ms is not None else coverage.get("computed_at_ms"),
                "market_hydration": _market_hydration([*targets, *attention]),
            },
        }


def _public_row(row: dict[str, Any], current_market_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    factor_snapshot = _mapping(row.get("factor_snapshot_json"))
    return {
        "_lane": row.get("lane"),
        "intent": row.get("intent_json") or {},
        "target": _target_from_snapshot(factor_snapshot),
        "attention": _attention_from_snapshot(factor_snapshot),
        "current_market": current_market_snapshot or _missing_current_market(factor_snapshot),
        "resolution": row.get("resolution_json") or {},
        "score": _composite_from_snapshot(factor_snapshot),
        "factor_snapshot": factor_snapshot,
        "data_health": row.get("data_health_json") or {},
        "source_event_ids": row.get("source_event_ids_json") or [],
    }


def _target_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    subject = _mapping(snapshot.get("subject"))
    return {
        "target_type": subject.get("target_type"),
        "target_id": subject.get("target_id"),
        "symbol": subject.get("symbol"),
        "chain": subject.get("chain"),
        "address": subject.get("address"),
        "target_market_type": subject.get("target_market_type"),
    }


def _attention_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    family = _family(snapshot, "attention_heat")
    return _mapping(family.get("facts"))


def _composite_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return _mapping(snapshot.get("composite"))


def _family(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    families = _mapping(snapshot.get("families"))
    return _mapping(families.get(name))


def _target_key_from_snapshot(snapshot: Any) -> tuple[str, str] | None:
    if not isinstance(snapshot, dict):
        return None
    subject = _mapping(snapshot.get("subject"))
    target_type = str(subject.get("target_type") or "").strip()
    target_id = str(subject.get("target_id") or "").strip()
    if not target_type or not target_id:
        return None
    return (target_type, target_id)


def _missing_current_market(snapshot: dict[str, Any]) -> dict[str, Any]:
    target_key = _target_key_from_snapshot(snapshot)
    return {
        "target_type": target_key[0] if target_key else None,
        "target_id": target_key[1] if target_key else None,
        "market_status": "missing",
        "fields": {},
    }


def _subjects_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    subjects: list[dict[str, Any]] = []
    for row in rows:
        snapshot = row.get("factor_snapshot_json")
        key = _target_key_from_snapshot(snapshot)
        if key is None or key in seen:
            continue
        seen.add(key)
        subjects.append({"target_type": key[0], "target_id": key[1]})
    return subjects


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
        current_market = _mapping(row.get("current_market"))
        market_status = str(current_market.get("market_status") or "")
        if market_status in {"fresh", "ready"}:
            counts["fresh"] += 1
        elif market_status in {"partial", "stale"}:
            counts["stale"] += 1
        else:
            counts["missing"] += 1
    total = len(rows)
    status = "ready" if counts["stale"] == 0 and counts["missing"] == 0 else "partial"
    return {**counts, "status": status, "total": total}


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _pending_projection_payload(coverage: dict[str, Any] | None) -> dict[str, Any]:
    coverage_status = str((coverage or {}).get("status") or "")
    if not coverage:
        reason = "projection_window_missing"
    elif coverage_status == "running":
        reason = "projection_window_running"
    elif coverage_status == "failed":
        reason = "projection_window_failed"
    else:
        reason = "projection_window_pending"
    return {
        "targets": [],
        "attention": [],
        "projection": {
            "status": "pending",
            "version": TOKEN_RADAR_PROJECTION_VERSION,
            "source": "token_radar_rows",
            "reason": reason,
            "row_count": int((coverage or {}).get("row_count") or 0),
            "source_rows": int((coverage or {}).get("source_rows") or 0),
            "source_max_received_at_ms": 0,
            "computed_at_ms": (coverage or {}).get("computed_at_ms"),
            "error": (coverage or {}).get("error"),
            "market_hydration": {
                "status": "pending",
                "fresh": 0,
                "stale": 0,
                "missing": 0,
                "pending": 0,
                "total": 0,
            },
        },
    }
