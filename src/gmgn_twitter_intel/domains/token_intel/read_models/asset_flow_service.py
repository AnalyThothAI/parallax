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
    def __init__(self, *, token_radar: Any, profiles: Any, live_market_gateway: Any | None = None) -> None:
        self.token_radar = token_radar
        self.profiles = profiles
        self.live_market_gateway = live_market_gateway

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
        public_rows = [
            _overlay_live_market(_public_row(row), gateway=self.live_market_gateway, now_ms=now_ms) for row in rows
        ]
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
        "anchor_price": _anchor_price_from_snapshot(factor_snapshot),
        "live_market": _missing_live_market(factor_snapshot),
        "resolution": row.get("resolution_json") or {},
        "score": _composite_from_snapshot(factor_snapshot),
        "factor_snapshot": factor_snapshot,
        "data_health": row.get("data_health_json") or {},
        "source_event_ids": row.get("source_event_ids_json") or [],
    }


def _overlay_live_market(row: dict[str, Any], *, gateway: Any | None, now_ms: int | None) -> dict[str, Any]:
    if gateway is None:
        return row
    target = _mapping(row.get("target"))
    target_type = str(target.get("target_type") or "").strip()
    target_id = str(target.get("target_id") or "").strip()
    if not target_type or not target_id:
        return row
    snapshot = _mapping(gateway.snapshot(target_type=target_type, target_id=target_id, now_ms=now_ms))
    if not snapshot:
        return row
    return {
        **row,
        "live_market": {
            **snapshot,
            "target_type": snapshot.get("target_type") or target_type,
            "target_id": snapshot.get("target_id") or target_id,
        },
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


def _anchor_price_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    market = _mapping(snapshot.get("market"))
    subject = _mapping(snapshot.get("subject"))
    readiness = _mapping(market.get("event_price_readiness"))
    status = str(readiness.get("status") or ("ready" if market.get("anchor_price_usd") is not None else "missing"))
    return {
        "status": status,
        "target_type": subject.get("target_type"),
        "target_id": subject.get("target_id"),
        "price_usd": market.get("anchor_price_usd"),
        "price_quote": market.get("anchor_price_quote"),
        "quote_symbol": market.get("anchor_quote_symbol"),
        "price_basis": market.get("anchor_price_basis"),
        "provider": market.get("provider"),
        "anchor_observed_at_ms": market.get("anchor_observed_at_ms"),
        "event_received_at_ms": market.get("social_signal_start_ms"),
        "anchor_lag_ms": market.get("anchor_lag_ms"),
    }


def _missing_live_market(snapshot: dict[str, Any]) -> dict[str, Any]:
    target_key = _target_key_from_snapshot(snapshot)
    return {
        "target_type": target_key[0] if target_key else None,
        "target_id": target_key[1] if target_key else None,
        "status": "missing",
        "price_usd": None,
        "price_quote": None,
        "quote_symbol": None,
        "price_basis": "unavailable",
        "provider": None,
        "observed_at_ms": None,
        "received_at_ms": None,
        "age_ms": None,
    }


def _anchor_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    ready = sum(1 for row in rows if _mapping(row.get("anchor_price")).get("status") == "ready")
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


def _target_key_from_snapshot(snapshot: Any) -> tuple[str, str] | None:
    if not isinstance(snapshot, dict):
        return None
    subject = _mapping(snapshot.get("subject"))
    target_type = str(subject.get("target_type") or "").strip()
    target_id = str(subject.get("target_id") or "").strip()
    if not target_type or not target_id:
        return None
    return (target_type, target_id)


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
            "anchor_coverage": {"status": "pending", "ready": 0, "missing": 0, "total": 0},
        },
    }
