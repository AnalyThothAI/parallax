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
        payloads = [_initial_payload(row, now_ms=resolved_now_ms) for row in rows]
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


def _initial_payload(row: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    lane = "resolved" if _is_resolved_row(row) else "attention"
    status = _resolution_status(row)
    latest_seen_ms = int(row.get("latest_seen_ms") or row.get("decision_time_ms") or 0)
    return {
        "_lane": lane,
        "_latest_seen_ms": latest_seen_ms,
        "asset": {
            "asset_id": row["asset_id"],
            "symbol": _display_symbol(row),
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
        "market": _market(row, now_ms=now_ms),
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
    if row.get("primary_venue_id"):
        return {
            "venue_id": row.get("primary_venue_id"),
            "venue_type": row.get("primary_venue_type"),
            "exchange": row.get("primary_venue_exchange"),
            "chain": row.get("primary_venue_chain"),
            "address": row.get("primary_venue_address"),
            "inst_id": row.get("primary_venue_inst_id"),
            "base_symbol": row.get("primary_venue_base_symbol"),
            "quote_symbol": row.get("primary_venue_quote_symbol"),
            "inst_type": row.get("primary_venue_inst_type"),
        }
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


def _market(row: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    observed_at_ms = _int_or_none(row.get("market_observed_at_ms"))
    if observed_at_ms is None or not _has_market_data(row):
        return {
            "market_status": "missing",
            "provider": None,
            "price_usd": None,
            "market_cap_usd": None,
            "liquidity_usd": None,
            "volume_24h_usd": None,
            "open_interest_usd": None,
            "holders": None,
            "snapshot_age_ms": None,
            "snapshot_observed_at_ms": None,
            "price_change_5m_pct": None,
            "price_change_1h_pct": None,
            "price_change_24h_pct": None,
            "price_at_social_start": None,
            "price_before_social_start": None,
            "price_change_since_social_pct": None,
            "price_change_before_social_pct": None,
            "market_observation_status": "provider_not_found",
            "price_change_status": "missing_market",
        }
    age_ms = max(0, now_ms - observed_at_ms)
    price_usd = _float_or_none(row.get("market_price_usd"))
    price_at_social_start = _float_or_none(row.get("market_price_at_social_start"))
    price_before_social_start = _float_or_none(row.get("market_price_before_social_start"))
    price_change_5m_pct = _coalesce_ratio(
        row.get("market_price_change_5m_pct"),
        current=price_usd,
        baseline=row.get("market_price_5m_ago"),
    )
    price_change_1h_pct = _coalesce_ratio(
        row.get("market_price_change_1h_pct"),
        current=price_usd,
        baseline=row.get("market_price_1h_ago"),
    )
    price_change_24h_pct = _coalesce_ratio(
        row.get("market_price_change_24h_pct"),
        current=price_usd,
        baseline=row.get("market_price_24h_ago"),
    )
    price_change_since_social_pct = _ratio(price_usd, price_at_social_start)
    price_change_before_social_pct = _ratio(price_at_social_start, price_before_social_start)
    price_change_status = (
        "ready"
        if any(
            value is not None
            for value in (
                price_change_5m_pct,
                price_change_1h_pct,
                price_change_24h_pct,
                price_change_since_social_pct,
                price_change_before_social_pct,
            )
        )
        else "insufficient_history"
    )
    return {
        "market_status": "fresh" if age_ms <= 10 * 60 * 1000 else "stale",
        "provider": row.get("market_provider"),
        "price_usd": price_usd,
        "market_cap_usd": row.get("market_cap_usd"),
        "liquidity_usd": row.get("market_liquidity_usd"),
        "volume_24h_usd": row.get("market_volume_24h_usd"),
        "open_interest_usd": row.get("market_open_interest_usd"),
        "holders": row.get("market_holders"),
        "snapshot_age_ms": age_ms,
        "snapshot_observed_at_ms": observed_at_ms,
        "price_change_5m_pct": price_change_5m_pct,
        "price_change_1h_pct": price_change_1h_pct,
        "price_change_24h_pct": price_change_24h_pct,
        "price_at_social_start": price_at_social_start,
        "price_before_social_start": price_before_social_start,
        "price_change_since_social_pct": price_change_since_social_pct,
        "price_change_before_social_pct": price_change_before_social_pct,
        "market_observation_status": "ready",
        "price_change_status": price_change_status,
    }


def _has_market_data(row: dict[str, Any]) -> bool:
    return any(
        row.get(key) is not None
        for key in (
            "market_price_usd",
            "market_cap_usd",
            "market_liquidity_usd",
            "market_volume_24h_usd",
            "market_open_interest_usd",
            "market_holders",
        )
    )


def _sort_key(row: dict[str, Any]) -> tuple[int, int]:
    return (-int(row["attention"]["mentions_window"]), -int(row.get("_latest_seen_ms") or 0))


def _display_symbol(row: dict[str, Any]) -> str | None:
    canonical = row.get("canonical_symbol")
    if canonical and not _is_address_like_symbol(str(canonical)):
        return str(canonical)
    alias = row.get("display_symbol")
    if alias and not _is_address_like_symbol(str(alias)):
        return str(alias)
    display_name = row.get("display_name")
    if display_name and not _is_address_like_symbol(str(display_name)):
        return str(display_name)
    return None


def _is_address_like_symbol(value: str) -> bool:
    normalized = value.strip().upper()
    if normalized.startswith("0X") and len(normalized) >= 22:
        return all(char in "0123456789ABCDEF" for char in normalized[2:])
    if len(normalized) < 32:
        return False
    if normalized.endswith("PUMP"):
        normalized = normalized[:-4]
    return all(char.isdigit() or ("A" <= char <= "Z") for char in normalized)


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset": row["asset"],
        "primary_venue": row["primary_venue"],
        "attention": row["attention"],
        "resolution": row["resolution"],
        "market": row["market"],
        "decision": row["decision"],
    }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coalesce_ratio(value: Any, *, current: float | None, baseline: Any) -> float | None:
    if value is not None:
        return float(value)
    return _ratio(current, _float_or_none(baseline))


def _ratio(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline is None or baseline <= 0:
        return None
    return (current - baseline) / baseline
