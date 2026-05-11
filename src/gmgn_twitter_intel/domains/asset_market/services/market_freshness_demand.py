from __future__ import annotations

from typing import Any

HOT_MISSING_PRIORITY = 0
HOT_STALE_PRIORITY = 1
WARM_MISSING_PRIORITY = 2
WARM_STALE_PRIORITY = 3
FRESH_PRIORITY = 9


def classify_market_refresh_candidate(
    row: dict[str, Any],
    *,
    now_ms: int,
    hot_since_ms: int,
    hot_stale_after_ms: int,
    warm_stale_after_ms: int,
) -> dict[str, Any]:
    latest_candidate_ms = _int_or_zero(row.get("latest_candidate_received_at_ms"))
    latest_price_ms = _int_or_none(row.get("latest_price_observed_at_ms"))
    is_hot = latest_candidate_ms >= int(hot_since_ms)
    stale_after_ms = int(hot_stale_after_ms if is_hot else warm_stale_after_ms)
    lag_ms = None if latest_price_ms is None else max(0, int(now_ms) - latest_price_ms)
    if latest_price_ms is None:
        status = "missing"
        required = True
    elif lag_ms is not None and lag_ms > stale_after_ms:
        status = "stale"
        required = True
    else:
        status = "fresh"
        required = False
    target_class = "hot" if is_hot else "warm"
    priority = _priority(target_class=target_class, status=status)
    return {
        **row,
        "market_freshness_class": target_class,
        "market_freshness_status": status,
        "market_freshness_lag_ms": lag_ms,
        "market_freshness_slo_ms": stale_after_ms,
        "market_refresh_required": required,
        "market_refresh_priority": priority,
    }


def prioritize_market_refresh_candidates(
    rows: list[dict[str, Any]],
    *,
    now_ms: int,
    hot_since_ms: int,
    hot_stale_after_ms: int,
    warm_stale_after_ms: int,
) -> list[dict[str, Any]]:
    classified = [
        classify_market_refresh_candidate(
            row,
            now_ms=now_ms,
            hot_since_ms=hot_since_ms,
            hot_stale_after_ms=hot_stale_after_ms,
            warm_stale_after_ms=warm_stale_after_ms,
        )
        for row in rows
    ]
    required = [row for row in classified if row["market_refresh_required"]]
    required.sort(
        key=lambda row: (
            int(row["market_refresh_priority"]),
            -_int_or_zero(row.get("candidate_event_count")),
            -_int_or_zero(row.get("latest_candidate_received_at_ms")),
            _int_or_zero(row.get("latest_price_observed_at_ms")),
            str(row.get("asset_id") or ""),
        )
    )
    return required


def _priority(*, target_class: str, status: str) -> int:
    if target_class == "hot" and status == "missing":
        return HOT_MISSING_PRIORITY
    if target_class == "hot" and status == "stale":
        return HOT_STALE_PRIORITY
    if status == "missing":
        return WARM_MISSING_PRIORITY
    if status == "stale":
        return WARM_STALE_PRIORITY
    return FRESH_PRIORITY


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else 0
