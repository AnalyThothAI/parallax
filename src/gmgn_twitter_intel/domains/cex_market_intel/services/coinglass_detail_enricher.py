from __future__ import annotations

from typing import Any


def enrich_rows_with_coinglass(
    rows: list[dict[str, Any]],
    *,
    client: Any | None,
    now_ms: int,
    limit: int,
    level_limit: int = 6,
) -> list[dict[str, Any]]:
    if client is None or limit <= 0:
        return rows
    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index >= limit:
            enriched.append(row)
            continue
        enriched.append(enrich_row_with_coinglass(row=row, client=client, now_ms=now_ms, level_limit=level_limit))
    return enriched


def enrich_row_with_coinglass(
    *,
    row: dict[str, Any],
    client: Any,
    now_ms: int,
    level_limit: int = 6,
) -> dict[str, Any]:
    base_symbol = str(row.get("base_symbol") or "").strip().upper()
    if not base_symbol:
        return {**row, "coinglass_status": "unavailable", "degraded_reasons": ["coinglass_symbol_missing"]}
    payload = dict(row)
    degraded_reasons: list[str] = []
    try:
        for time_type, field in (("1", "oi_change_pct_1h"), ("2", "oi_change_pct_4h"), ("4", "oi_change_pct_24h")):
            history = client.fetch_oi_history(symbol=base_symbol, time_type=time_type, lookback=_lookback(time_type))
            payload[field] = _change_pct_from_points(history, value_keys=("usd", "openInterest"))
    except Exception as exc:
        degraded_reasons.append(f"coinglass_oi_{type(exc).__name__}")
    try:
        for time_type, field in (("1", "cvd_delta_1h"), ("2", "cvd_delta_4h"), ("4", "cvd_delta_24h")):
            history = client.fetch_cvd_history(symbol=base_symbol, time_type=time_type, lookback=_lookback(time_type))
            payload[field] = _sum_delta(history, value_key="delta")
    except Exception as exc:
        degraded_reasons.append(f"coinglass_cvd_{type(exc).__name__}")
    try:
        history = client.fetch_long_short_ratio_history(symbol=base_symbol, time_type="2", lookback="8h")
        payload["long_short_ratio"] = _latest_value(history, "longShortRatio")
    except Exception as exc:
        degraded_reasons.append(f"coinglass_long_short_{type(exc).__name__}")
    try:
        history = client.fetch_top_trader_position_history(symbol=base_symbol, time_type="2", lookback="8h")
        payload["top_trader_position_ratio"] = _latest_value(history, "longShortRatio")
    except Exception as exc:
        degraded_reasons.append(f"coinglass_top_trader_{type(exc).__name__}")
    try:
        levels = client.fetch_liquidation_levels(symbol=base_symbol, range="7d")
        payload["level_bands"] = _level_bands(levels, limit=level_limit)
    except Exception as exc:
        degraded_reasons.append(f"coinglass_levels_{type(exc).__name__}")
    payload["coinglass_status"] = "ready" if not degraded_reasons else "partial"
    payload["coinglass_observed_at_ms"] = int(now_ms)
    if degraded_reasons:
        payload["degraded_reasons"] = [*list(row.get("degraded_reasons") or []), *degraded_reasons]
    return payload


def _lookback(time_type: str) -> str:
    return {"1": "2h", "2": "8h", "4": "48h"}.get(time_type, "")


def _change_pct_from_points(payload: dict[str, Any], *, value_keys: tuple[str, ...]) -> float | None:
    points = _data_points(payload)
    if len(points) < 2:
        return None
    previous = _first_numeric(points[0], value_keys)
    current = _first_numeric(points[-1], value_keys)
    if previous is None or current is None or previous == 0:
        return None
    return round(((current - previous) / previous) * 100.0, 6)


def _sum_delta(payload: dict[str, Any], *, value_key: str) -> float | None:
    points = _data_points(payload)
    values = [_float_or_none(point.get(value_key)) for point in points]
    values = [value for value in values if value is not None]
    return round(sum(values), 6) if values else None


def _latest_value(payload: dict[str, Any], key: str) -> float | None:
    points = _data_points(payload)
    if not points:
        return None
    return _float_or_none(points[-1].get(key))


def _level_bands(payload: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    rows = payload.get("levels") or payload.get("data") or []
    if not isinstance(rows, list):
        return []
    bands: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        price = _float_or_none(item.get("price"))
        size = _float_or_none(item.get("size"))
        if price is None:
            continue
        side = _int_or_none(item.get("side"))
        bands.append(
            {
                "kind": "support" if side == 1 else "resistance" if side == 2 else "liquidation",
                "price": price,
                "size": size,
                "score": None if size is None else max(0.0, min(1.0, size / 1_000_000_000.0)),
            }
        )
    bands.sort(key=lambda item: float(item.get("size") or 0), reverse=True)
    return bands[: max(0, int(limit))]


def _data_points(payload: dict[str, Any]) -> list[dict[str, Any]]:
    points = payload.get("data") or payload.get("points") or []
    if not isinstance(points, list):
        return []
    return [point for point in points if isinstance(point, dict)]


def _first_numeric(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _float_or_none(row.get(key))
        if value is not None:
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
