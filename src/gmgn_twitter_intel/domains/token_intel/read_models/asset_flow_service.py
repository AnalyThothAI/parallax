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
    def __init__(self, *, token_radar: Any) -> None:
        self.token_radar = token_radar

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
        targets = [
            _public_row(row)
            for row in rows
            if row.get("lane") == "resolved"
        ]
        attention = [
            _public_row(row)
            for row in rows
            if row.get("lane") == "attention"
        ]
        computed_at_ms = max((int(row.get("computed_at_ms") or 0) for row in rows), default=0) or None
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


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = row.get("factor_snapshot_json") if isinstance(row.get("factor_snapshot_json"), dict) else {}
    return {
        "intent": row.get("intent_json") or {},
        "target": _target_from_snapshot(factor_snapshot),
        "attention": _attention_from_snapshot(factor_snapshot),
        "current_market": _current_market_from_snapshot(factor_snapshot),
        "resolution": row.get("resolution_json") or {},
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


def _target_key_from_snapshot(snapshot: Any) -> tuple[str, str] | None:
    if not isinstance(snapshot, dict):
        return None
    subject = snapshot.get("subject") if isinstance(snapshot.get("subject"), dict) else {}
    target_type = str(subject.get("target_type") or "").strip()
    target_id = str(subject.get("target_id") or "").strip()
    if not target_type or not target_id:
        return None
    return (target_type, target_id)


_MARKET_FIELD_FACT_KEYS = (
    "price_usd",
    "price_quote",
    "quote_symbol",
    "price_basis",
    "market_cap_usd",
    "liquidity_usd",
    "holders",
    "volume_24h_usd",
    "open_interest_usd",
)


def _current_market_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    target_key = _target_key_from_snapshot(snapshot)
    families = snapshot.get("families") if isinstance(snapshot.get("families"), dict) else {}
    market_quality = families.get("market_quality") if isinstance(families.get("market_quality"), dict) else {}
    facts = market_quality.get("facts") if isinstance(market_quality.get("facts"), dict) else {}
    market_status = str(facts.get("market_status") or "").strip()
    statuses = facts.get("field_statuses") if isinstance(facts.get("field_statuses"), dict) else {}
    fields = {
        key: _snapshot_market_field(value=facts.get(key), status=statuses.get(key))
        for key in _MARKET_FIELD_FACT_KEYS
        if facts.get(key) is not None or statuses.get(key) is not None
    }
    if not fields and market_status in {"", "missing"}:
        return _missing_current_market(snapshot)
    return {
        "target_type": target_key[0] if target_key else None,
        "target_id": target_key[1] if target_key else None,
        "market_status": market_status or "missing",
        "fields": fields,
    }


def _snapshot_market_field(*, value: Any, status: Any) -> dict[str, Any]:
    resolved_status = str(status or ("ready" if value is not None else "missing"))
    return {
        "value": value,
        "status": resolved_status,
        "observed_at_ms": None,
        "age_ms": None,
        "provider": None,
        "source_observation_id": None,
    }


def _missing_current_market(snapshot: dict[str, Any]) -> dict[str, Any]:
    target_key = _target_key_from_snapshot(snapshot)
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
<<<<<<< HEAD
        raw_price = row.get("price_json")
        price: dict[str, Any] = raw_price if isinstance(raw_price, dict) else {}
        market_status = str(price.get("market_status") or "")
        observation_status = str(price.get("market_observation_status") or "")
=======
        current_market = row.get("current_market") if isinstance(row.get("current_market"), dict) else {}
        market_status = str(current_market.get("market_status") or "")
>>>>>>> origin/main
        if market_status in {"fresh", "ready"}:
            counts["fresh"] += 1
        elif market_status == "partial" or market_status == "stale":
            counts["stale"] += 1
        else:
            counts["missing"] += 1
    total = len(rows)
    status = "ready" if counts["stale"] == 0 and counts["missing"] == 0 else "partial"
    return {**counts, "status": status, "total": total}


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

