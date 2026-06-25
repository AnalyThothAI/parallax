from __future__ import annotations

from typing import Any

from parallax.domains.cex_market_intel.providers import CoinglassDerivativesProvider


def enrich_rows_with_coinglass(
    rows: list[dict[str, Any]],
    *,
    client: CoinglassDerivativesProvider | None,
    now_ms: int,
    limit: int,
    level_limit: int,
) -> list[dict[str, Any]]:
    enrichment_limit = _required_nonnegative_int(limit, "coinglass_detail_enrichment_limit_required")
    parsed_level_limit = _required_nonnegative_int(level_limit, "coinglass_detail_level_limit_required")
    if client is None or enrichment_limit <= 0:
        return [_coinglass_unavailable(row) for row in rows]
    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index >= enrichment_limit:
            enriched.append(_coinglass_unavailable(row))
            continue
        enriched.append(
            enrich_row_with_coinglass(
                row=row,
                client=client,
                now_ms=now_ms,
                level_limit=parsed_level_limit,
            )
        )
    return enriched


def enrich_row_with_coinglass(
    *,
    row: dict[str, Any],
    client: CoinglassDerivativesProvider,
    now_ms: int,
    level_limit: int,
) -> dict[str, Any]:
    base_symbol = _required_symbol(row, "base_symbol")
    inherited_degraded_reasons = _inherited_degraded_reasons(row)
    payload = dict(row)
    if "degraded_reasons" in row:
        payload["degraded_reasons"] = inherited_degraded_reasons
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
    if degraded_reasons or "degraded_reasons" in row:
        payload["degraded_reasons"] = [*inherited_degraded_reasons, *degraded_reasons]
    return payload


def _lookback(time_type: str) -> str:
    return {"1": "2h", "2": "8h", "4": "48h"}.get(time_type, "")


def _coinglass_unavailable(row: dict[str, Any]) -> dict[str, Any]:
    inherited_degraded_reasons = _inherited_degraded_reasons(row)
    payload = {**row, "coinglass_status": "unavailable"}
    if "degraded_reasons" in row:
        payload["degraded_reasons"] = inherited_degraded_reasons
    return payload


def _required_symbol(row: dict[str, Any], field: str) -> str:
    value = _symbol(row.get(field))
    if not value:
        raise ValueError(f"coinglass_detail_identity_required:{field}")
    return value


def _inherited_degraded_reasons(row: dict[str, Any]) -> list[str]:
    if "degraded_reasons" not in row or row.get("degraded_reasons") is None:
        return []
    value = row.get("degraded_reasons")
    if not isinstance(value, list | tuple):
        raise ValueError("coinglass_detail_degraded_reasons_invalid")
    reasons: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("coinglass_detail_degraded_reason_invalid:item")
        reasons.append(item.strip())
    return reasons


def _symbol(value: Any) -> str:
    return str(value or "").strip().upper()


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
    values: list[float] = []
    for point in points:
        value = _float_or_none(point.get(value_key))
        if value is not None:
            values.append(value)
    return round(sum(values), 6) if values else None


def _latest_value(payload: dict[str, Any], key: str) -> float | None:
    points = _data_points(payload)
    if not points:
        return None
    return _float_or_none(points[-1].get(key))


def _level_bands(payload: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    parsed_limit = _required_nonnegative_int(limit, "coinglass_detail_level_limit_required")
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
    return bands[:parsed_limit]


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


def _required_nonnegative_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(error_code)
    if value < 0:
        raise ValueError(error_code)
    return int(value)
