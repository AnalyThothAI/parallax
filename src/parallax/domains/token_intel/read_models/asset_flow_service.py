from __future__ import annotations

from typing import Any

from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION

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
        venue: str,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        publication_state = self.token_radar.latest_publication_state(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=(window,),
            scopes=(scope,),
            venues=(venue,),
        ).get((window, scope, venue))
        row_limit = max(0, int(limit)) * 2
        publication_status = str((publication_state or {}).get("latest_attempt_status") or "")
        rows = self.token_radar.latest_current_rows(
            window=window,
            scope=scope,
            venue=venue,
            limit=row_limit,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        )
        state_row_count = int((publication_state or {}).get("current_row_count") or 0)
        state_source_rows = int((publication_state or {}).get("current_source_rows") or 0)
        if publication_status == "ready" and (bool(rows) or state_row_count == 0):
            projection_status = "fresh"
            projection_reason = None
        elif rows:
            projection_status = "stale"
            projection_reason = (
                "projection_window_failed" if publication_status == "failed" else "projection_rows_stale"
            )
        elif publication_status != "ready":
            return _pending_projection_payload(publication_state, venue=venue)
        else:
            projection_status = "stale"
            projection_reason = "projection_rows_missing"

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
        projection_quality_status, projection_degraded_reasons = _projection_quality(
            projection_status=projection_status,
            rows=returned_rows,
            unresolved=unresolved,
        )
        return {
            "targets": targets[:limit],
            "attention": attention[:limit],
            "projection": {
                "status": projection_status,
                "version": TOKEN_RADAR_PROJECTION_VERSION,
                "source": "token_radar_current_rows",
                "venue": venue,
                "reason": projection_reason,
                "latest_attempt_status": publication_status or "missing",
                "row_count": state_row_count or len(rows),
                "source_rows": state_source_rows or len(rows),
                "source_max_received_at_ms": max(
                    (int(row.get("source_max_received_at_ms") or 0) for row in rows),
                    default=0,
                ),
                "source_frontier_ms": (publication_state or {}).get("current_source_frontier_ms"),
                "computed_at_ms": computed_at_ms,
                "error": (publication_state or {}).get("latest_attempt_error"),
                "anchor_coverage": _anchor_coverage(returned_rows),
                "quality_status": projection_quality_status,
                "degraded_reasons": projection_degraded_reasons,
                "unresolved": unresolved,
            },
        }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = _mapping(row.get("factor_snapshot_json"))
    score = _composite_from_snapshot(factor_snapshot)
    if row.get("rank_score") is not None:
        score["rank_score"] = _float_or_none(row.get("rank_score"))
    return {
        "_lane": row.get("lane"),
        "intent": row.get("intent_json") or {},
        "target": _target_from_snapshot(factor_snapshot),
        "attention": _attention_from_snapshot(factor_snapshot),
        "market": _market_from_snapshot(factor_snapshot),
        "radar": _radar_from_row(row),
        "resolution": row.get("resolution_json") or {},
        "score": score,
        "quality": {
            "status": row.get("quality_status"),
            "degraded_reasons": _string_list(row.get("degraded_reasons_json")),
        },
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
        snapshot = _mapping(row.get("factor_snapshot_json"))
        subject = _mapping(snapshot.get("subject"))
        intent = _mapping(row.get("intent_json"))
        resolution = _mapping(row.get("resolution_json"))
        status = str(resolution.get("status") or subject.get("status") or row.get("resolution_status") or "").strip()
        if status == "NIL":
            nil_count += 1
        elif status == "AMBIGUOUS":
            ambiguous_count += 1
        symbol = subject.get("symbol") or intent.get("display_symbol") or intent.get("symbol")
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


def _projection_quality(
    *,
    projection_status: str,
    rows: list[dict[str, Any]],
    unresolved: dict[str, Any],
) -> tuple[str, list[str]]:
    if projection_status == "failed":
        return "failed", ["projection_window_failed"]

    reasons: list[str] = []
    row_statuses: list[str] = []
    for row in rows:
        quality = _mapping(row.get("quality"))
        status = str(quality.get("status") or "ready")
        row_statuses.append(status)
        reasons.extend(_string_list(quality.get("degraded_reasons")))

    if int(unresolved.get("identity_missing_count") or 0) > 0:
        reasons.append("identity_missing")

    degraded_reasons = _dedupe_strings(reasons)
    if row_statuses and all(status == "insufficient" for status in row_statuses):
        return "insufficient", degraded_reasons
    if any(status in {"degraded", "insufficient", "failed"} for status in row_statuses) or degraded_reasons:
        return "degraded", degraded_reasons
    return "ready", []


def _pending_quality(reason: str) -> tuple[str, list[str]]:
    if reason == "projection_window_failed":
        return "failed", [reason]
    return "insufficient", [reason]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return _dedupe_strings([str(item) for item in value if str(item)])


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _pending_projection_payload(publication_state: dict[str, Any] | None, *, venue: str) -> dict[str, Any]:
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
    quality_status, degraded_reasons = _pending_quality(reason)
    return {
        "targets": [],
        "attention": [],
        "projection": {
            "status": projection_status,
            "version": TOKEN_RADAR_PROJECTION_VERSION,
            "source": "token_radar_current_rows",
            "venue": venue,
            "reason": reason,
            "latest_attempt_status": publication_status or "missing",
            "row_count": int((publication_state or {}).get("current_row_count") or 0),
            "source_rows": int((publication_state or {}).get("current_source_rows") or 0),
            "source_max_received_at_ms": 0,
            "source_frontier_ms": (publication_state or {}).get("current_source_frontier_ms"),
            "computed_at_ms": (publication_state or {}).get("current_published_at_ms"),
            "error": (publication_state or {}).get("latest_attempt_error"),
            "anchor_coverage": {"status": projection_status, "ready": 0, "missing": 0, "total": 0},
            "quality_status": quality_status,
            "degraded_reasons": degraded_reasons,
        },
    }
