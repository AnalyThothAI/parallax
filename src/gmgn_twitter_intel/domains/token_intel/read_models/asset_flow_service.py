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
        publication = self.token_radar.latest_publications(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=(window,),
            scopes=(scope,),
        ).get((window, scope))
        if not publication or publication.get("published_computed_at_ms") is None:
            return _pending_projection_payload(publication)

        row_limit = max(0, int(limit)) * 2
        rows = self.token_radar.latest_rows(
            window=window,
            scope=scope,
            limit=row_limit,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        )
        market_snapshots = self._current_market_snapshots(rows, now_ms=now_ms)
        public_rows = [
            _public_row(row, market_snapshots.get(target_key) if (target_key := _target_key(row)) is not None else None)
            for row in rows
        ]
        targets = [row for row in public_rows if row.get("_lane") == "resolved"]
        attention = [row for row in public_rows if row.get("_lane") == "attention"]
        for row in [*targets, *attention]:
            row.pop("_lane", None)
        computed_at_ms = max((int(row.get("computed_at_ms") or 0) for row in rows), default=0) or None
        return {
            "targets": targets[:limit],
            "attention": attention[:limit],
            "projection": {
                "status": "fresh",
                "refresh_status": publication.get("refresh_status") or publication.get("status"),
                "version": TOKEN_RADAR_PROJECTION_VERSION,
                "source": "token_radar_rows",
                "reason": publication.get("reason"),
                "row_count": int(publication.get("row_count") or 0),
                "source_rows": int(publication.get("source_rows") or 0),
                "source_max_received_at_ms": int(publication.get("source_max_received_at_ms") or 0)
                or max(
                    (int(row.get("source_max_received_at_ms") or 0) for row in rows),
                    default=0,
                ),
                "computed_at_ms": computed_at_ms if computed_at_ms is not None else publication.get("computed_at_ms"),
                "refresh_started_at_ms": publication.get("refresh_started_at_ms"),
                "refresh_finished_at_ms": publication.get("refresh_finished_at_ms"),
                "error": publication.get("error"),
                "market_hydration": _market_hydration([*targets, *attention]),
            },
        }

    def _current_market_snapshots(
        self,
        rows: list[dict[str, Any]],
        *,
        now_ms: int | None,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        keys = [key for key in dict.fromkeys(_target_key(row) for row in rows) if key is not None]
        subjects = [{"target_type": key[0], "target_id": key[1]} for key in keys]
        if not subjects:
            return {}
        snapshots = self.current_market.current_for_subjects(subjects, now_ms=int(now_ms or 0))
        return snapshots if isinstance(snapshots, dict) else {}


def _public_row(row: dict[str, Any], current_market: dict[str, Any] | None) -> dict[str, Any]:
    raw_factor_snapshot = row.get("factor_snapshot_json")
    factor_snapshot: dict[str, Any] = raw_factor_snapshot if isinstance(raw_factor_snapshot, dict) else {}
    return {
        "_lane": row.get("lane"),
        "intent": row.get("intent_json") or {},
        "target": _target_from_snapshot(factor_snapshot),
        "attention": _attention_from_snapshot(factor_snapshot),
        "current_market": current_market or _missing_current_market(row, factor_snapshot),
        "resolution": row.get("resolution_json") or {},
        "score": _composite_from_snapshot(factor_snapshot),
        "factor_snapshot": factor_snapshot,
        "decision": row.get("decision"),
        "data_health": row.get("data_health_json") or {},
        "source_event_ids": row.get("source_event_ids_json") or [],
    }


def _target_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw_subject = snapshot.get("subject")
    subject: dict[str, Any] = raw_subject if isinstance(raw_subject, dict) else {}
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
    raw_facts = family.get("facts")
    facts: dict[str, Any] = raw_facts if isinstance(raw_facts, dict) else {}
    return dict(facts)


def _composite_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw_composite = snapshot.get("composite")
    composite: dict[str, Any] = raw_composite if isinstance(raw_composite, dict) else {}
    return dict(composite)


def _family(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    raw_families = snapshot.get("families")
    families: dict[str, Any] = raw_families if isinstance(raw_families, dict) else {}
    raw_family = families.get(name)
    family: dict[str, Any] = raw_family if isinstance(raw_family, dict) else {}
    return family


def _target_key(row: dict[str, Any]) -> tuple[str, str] | None:
    target_type = str(row.get("target_type") or "").strip()
    target_id = str(row.get("target_id") or "").strip()
    if target_type and target_id:
        return (target_type, target_id)
    raw_snapshot = row.get("factor_snapshot_json")
    snapshot: dict[str, Any] = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    return _target_key_from_snapshot(snapshot)


def _target_key_from_snapshot(snapshot: Any) -> tuple[str, str] | None:
    if not isinstance(snapshot, dict):
        return None
    raw_subject = snapshot.get("subject")
    subject: dict[str, Any] = raw_subject if isinstance(raw_subject, dict) else {}
    target_type = str(subject.get("target_type") or "").strip()
    target_id = str(subject.get("target_id") or "").strip()
    if not target_type or not target_id:
        return None
    return (target_type, target_id)


def _missing_current_market(row: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    target_key = _target_key(row)
    if target_key is None:
        target_key = _target_key_from_snapshot(snapshot)
    if not snapshot:
        target_key = None
    return {
        "target_type": target_key[0] if target_key else None,
        "target_id": target_key[1] if target_key else None,
        "market_status": "missing",
        "fields": {},
    }


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
        raw_current_market = row.get("current_market")
        current_market: dict[str, Any] = raw_current_market if isinstance(raw_current_market, dict) else {}
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


def _pending_projection_payload(coverage: dict[str, Any] | None) -> dict[str, Any]:
    coverage_status = str((coverage or {}).get("refresh_status") or (coverage or {}).get("status") or "")
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
            "refresh_status": coverage_status or "missing",
            "version": TOKEN_RADAR_PROJECTION_VERSION,
            "source": "token_radar_rows",
            "reason": reason,
            "row_count": int((coverage or {}).get("row_count") or 0),
            "source_rows": int((coverage or {}).get("source_rows") or 0),
            "source_max_received_at_ms": 0,
            "computed_at_ms": (coverage or {}).get("computed_at_ms"),
            "refresh_started_at_ms": (coverage or {}).get("refresh_started_at_ms"),
            "refresh_finished_at_ms": (coverage or {}).get("refresh_finished_at_ms"),
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
