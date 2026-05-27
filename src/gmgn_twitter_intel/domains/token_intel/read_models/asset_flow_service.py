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
    def __init__(self, *, token_radar: Any, profiles: Any) -> None:
        self.token_radar = token_radar
        self.profiles = profiles

    def asset_flow(
        self,
        *,
        window: str,
        limit: int,
        scope: str,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        publication_state = self.token_radar.latest_publication_state(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=(window,),
            scopes=(scope,),
        ).get((window, scope))
        row_limit = max(0, int(limit)) * 2
        publication_status = str((publication_state or {}).get("latest_attempt_status") or "")
        current_generation = str((publication_state or {}).get("current_generation_id") or "")
        if current_generation:
            rows = self.token_radar.current_rows_for_generation(
                window=window,
                scope=scope,
                generation_id=current_generation,
                limit=row_limit,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            )
        else:
            rows = self.token_radar.latest_current_rows(
                window=window,
                scope=scope,
                limit=row_limit,
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            )
        row_generations = {str(row.get("generation_id") or "") for row in rows if row.get("generation_id")}
        state_row_count = int((publication_state or {}).get("current_row_count") or 0)
        state_source_rows = int((publication_state or {}).get("current_source_rows") or 0)
        matches_current_generation = (
            bool(current_generation)
            and row_generations <= {current_generation}
            and (bool(rows) or state_row_count == 0)
        )
        if publication_status == "ready" and matches_current_generation:
            projection_status = "fresh"
            projection_reason = None
        elif rows:
            projection_status = "stale"
            projection_reason = (
                "projection_window_failed" if publication_status == "failed" else "projection_rows_stale"
            )
        elif publication_status != "ready":
            return _pending_projection_payload(publication_state)
        else:
            projection_status = "stale"
            projection_reason = "projection_generation_mismatch"

        row_computed_at_ms = max((int(row.get("computed_at_ms") or 0) for row in rows), default=0) or None
        published_at_ms = (publication_state or {}).get("current_published_at_ms")
        computed_at_ms = published_at_ms if published_at_ms is not None else row_computed_at_ms
        public_rows = [_public_row(row) for row in rows]
        _hydrate_profiles(public_rows, profiles=self.profiles)
        unresolved = _unresolved_diagnostics(rows)
        targetful_rows = [row for row in public_rows if _mapping(row.get("target")).get("target_id")]
        targets = [row for row in targetful_rows if row.get("_lane") == "resolved"]
        attention = [row for row in targetful_rows if row.get("_lane") == "attention"]
        for row in [*targets, *attention]:
            row.pop("_lane", None)
        returned_rows = [*targets[:limit], *attention[:limit]]
        return {
            "targets": targets[:limit],
            "attention": attention[:limit],
            "projection": {
                "status": projection_status,
                "version": TOKEN_RADAR_PROJECTION_VERSION,
                "source": "token_radar_current_rows",
                "reason": projection_reason,
                "latest_attempt_status": publication_status or "missing",
                "row_count": state_row_count or len(rows),
                "source_rows": state_source_rows or len(rows),
                "source_max_received_at_ms": max(
                    (int(row.get("source_max_received_at_ms") or 0) for row in rows),
                    default=0,
                ),
                "source_frontier_ms": (publication_state or {}).get("current_source_frontier_ms"),
                "generation_id": current_generation or None,
                "row_generation_ids": sorted(row_generations),
                "computed_at_ms": computed_at_ms,
                "error": (publication_state or {}).get("latest_attempt_error"),
                "anchor_coverage": _anchor_coverage(returned_rows),
                "unresolved": unresolved,
            },
        }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = _mapping(row.get("factor_snapshot_json"))
    return {
        "_lane": row.get("lane"),
        "intent": row.get("intent_json") or {},
        "target": _target_from_snapshot(factor_snapshot),
        "attention": _attention_from_snapshot(factor_snapshot),
        "market": _market_from_snapshot(factor_snapshot),
        "radar": _radar_from_row(row),
        "resolution": row.get("resolution_json") or {},
        "score": _composite_from_snapshot(factor_snapshot),
        "factor_snapshot": factor_snapshot,
        "data_health": row.get("data_health_json") or {},
        "source_event_ids": row.get("source_event_ids_json") or [],
    }


def _hydrate_profiles(rows: list[dict[str, Any]], *, profiles: Any) -> None:
    profile_blocks = profiles.profiles_for_targets([_mapping(row.get("target")) for row in rows])
    for row in rows:
        target = _mapping(row.get("target"))
        target_type = str(target.get("target_type") or "")
        target_id = str(target.get("target_id") or "")
        key = (target_type, target_id)
        if key in profile_blocks:
            row["profile"] = profile_blocks[key]


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
    family = _family(snapshot, "social_heat")
    return _mapping(family.get("facts"))


def _market_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return _mapping(snapshot.get("market"))


def _radar_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane": row.get("lane"),
        "rank": _int_or_none(row.get("rank")),
        "listed_at_ms": _int_or_none(row.get("listed_at_ms")),
        "computed_at_ms": _int_or_none(row.get("computed_at_ms")),
        "source_max_received_at_ms": _int_or_none(row.get("source_max_received_at_ms")),
    }


def _anchor_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    ready = sum(
        1 for row in rows if _mapping(_mapping(row.get("market")).get("readiness")).get("anchor_status") == "ready"
    )
    missing = total - ready
    if total == 0:
        status = "missing"
    elif missing == 0:
        status = "ready"
    elif ready > 0:
        status = "partial"
    else:
        status = "missing"
    return {"status": status, "ready": ready, "missing": missing, "total": total}


def _unresolved_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    unresolved = [row for row in rows if not row.get("target_id")]
    symbols: list[str] = []
    nil_count = 0
    ambiguous_count = 0
    for row in unresolved:
        target = _mapping(row.get("target_json"))
        intent = _mapping(row.get("intent_json"))
        resolution = _mapping(row.get("resolution_json"))
        status = str(target.get("status") or resolution.get("status") or row.get("resolution_status") or "").strip()
        if status == "NIL":
            nil_count += 1
        elif status == "AMBIGUOUS":
            ambiguous_count += 1
        symbol = target.get("symbol") or intent.get("display_symbol") or intent.get("symbol")
        if symbol and str(symbol) not in symbols:
            symbols.append(str(symbol))
    return {
        "identity_missing_count": len(unresolved),
        "nil_count": nil_count,
        "ambiguous_count": ambiguous_count,
        "sample_symbols": symbols[:10],
    }


def _composite_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return _mapping(snapshot.get("composite"))


def _family(snapshot: dict[str, Any], name: str) -> dict[str, Any]:
    families = _mapping(snapshot.get("families"))
    return _mapping(families.get(name))


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _pending_projection_payload(publication_state: dict[str, Any] | None) -> dict[str, Any]:
    publication_status = str((publication_state or {}).get("latest_attempt_status") or "")
    if not publication_state:
        projection_status = "pending"
        reason = "projection_window_missing"
    elif publication_status == "failed":
        projection_status = "failed"
        reason = "projection_window_failed"
    else:
        projection_status = "pending"
        reason = "projection_window_pending"
    return {
        "targets": [],
        "attention": [],
        "projection": {
            "status": projection_status,
            "version": TOKEN_RADAR_PROJECTION_VERSION,
            "source": "token_radar_current_rows",
            "reason": reason,
            "latest_attempt_status": publication_status or "missing",
            "row_count": int((publication_state or {}).get("current_row_count") or 0),
            "source_rows": int((publication_state or {}).get("current_source_rows") or 0),
            "source_max_received_at_ms": 0,
            "source_frontier_ms": (publication_state or {}).get("current_source_frontier_ms"),
            "generation_id": (publication_state or {}).get("current_generation_id"),
            "computed_at_ms": (publication_state or {}).get("current_published_at_ms"),
            "error": (publication_state or {}).get("latest_attempt_error"),
            "anchor_coverage": {"status": projection_status, "ready": 0, "missing": 0, "total": 0},
        },
    }
