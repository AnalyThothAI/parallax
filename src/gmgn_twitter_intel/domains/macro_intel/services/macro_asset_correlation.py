from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Any

ASSET_CORRELATION_WINDOWS: Mapping[str, int] = {"20d": 20, "60d": 60, "120d": 120}

DEFAULT_ASSET_CORRELATION_CONCEPTS = (
    "asset:spy",
    "asset:qqq",
    "asset:iwm",
    "asset:tlt",
    "asset:hyg",
    "asset:lqd",
    "asset:gld",
    "asset:uso",
    "fx:dxy",
    "crypto:btc",
    "crypto:eth",
)
OPTIONAL_ASSET_CORRELATION_CONCEPTS = ("asset:spx",)
SUPPORTED_ASSET_CORRELATION_CONCEPTS = (
    *DEFAULT_ASSET_CORRELATION_CONCEPTS,
    *OPTIONAL_ASSET_CORRELATION_CONCEPTS,
)

ASSET_CORRELATION_TITLES: Mapping[str, str] = {
    "asset:gld": "GLD",
    "asset:hyg": "HYG",
    "asset:iwm": "IWM",
    "asset:lqd": "LQD",
    "asset:qqq": "QQQ",
    "asset:spx": "S&P 500",
    "asset:spy": "SPY",
    "asset:tlt": "TLT",
    "asset:uso": "USO",
    "crypto:btc": "BTC",
    "crypto:eth": "ETH",
    "fx:dxy": "DXY",
}


def build_macro_asset_correlation(
    observations: Sequence[Mapping[str, Any]],
    *,
    assets: Sequence[str] = DEFAULT_ASSET_CORRELATION_CONCEPTS,
    optional_assets: Sequence[str] = (),
    window: str = "60d",
) -> dict[str, Any]:
    window_days = ASSET_CORRELATION_WINDOWS[window]
    min_sample = _minimum_sample_size(window_days)
    selected_assets = tuple(dict.fromkeys(assets))
    optional_asset_set = set(optional_assets)
    prices_by_asset = _price_series_by_asset(observations, assets=selected_assets)
    returns_by_asset = {
        concept_key: _windowed_returns(prices_by_asset.get(concept_key, []), window_days=window_days)
        for concept_key in selected_assets
    }
    included_assets = tuple(
        concept_key
        for concept_key in selected_assets
        if concept_key not in optional_asset_set or len(returns_by_asset.get(concept_key, [])) >= min_sample
    )
    asof_date = _asof_date(prices_by_asset, included_assets)
    data_gaps: list[dict[str, Any]] = []
    asset_payloads = [
        _asset_payload(concept_key, prices_by_asset.get(concept_key, []), returns_by_asset.get(concept_key, []))
        for concept_key in included_assets
    ]
    data_gaps.extend(
        {
            "code": "insufficient_history",
            "concept_key": asset["concept_key"],
            "sample_size": asset["return_count"],
        }
        for asset in asset_payloads
        if int(asset["return_count"]) < min_sample
    )

    pair_results: list[dict[str, Any]] = []
    matrix_values: dict[tuple[str, str], float | None] = {}
    for left_index, left in enumerate(included_assets):
        matrix_values[(left, left)] = 1.0 if returns_by_asset.get(left) else None
        for right in included_assets[left_index + 1 :]:
            pair = _pair_correlation(
                left,
                right,
                returns_by_asset.get(left, []),
                returns_by_asset.get(right, []),
                min_sample=min_sample,
            )
            pair_results.append(pair)
            matrix_values[(left, right)] = pair["correlation"]
            matrix_values[(right, left)] = pair["correlation"]
            if not pair["available"]:
                data_gaps.append(
                    {
                        "code": pair["reason"],
                        "left": left,
                        "right": right,
                        "sample_size": pair["sample_size"],
                    }
                )

    matrix = [
        {
            "concept_key": concept_key,
            "correlations": {
                other: matrix_values.get((concept_key, other))
                for other in included_assets
            },
        }
        for concept_key in included_assets
    ]

    return {
        "window": window,
        "assets": asset_payloads,
        "matrix": matrix,
        "pairs": pair_results,
        "data_gaps": data_gaps,
        "asof_date": asof_date,
    }


def correlation_query_bounds(window: str) -> dict[str, int]:
    window_days = ASSET_CORRELATION_WINDOWS[window]
    return {
        "lookback_days": window_days * 3,
        "limit_per_series": window_days + 30,
    }


def _price_series_by_asset(
    observations: Sequence[Mapping[str, Any]],
    *,
    assets: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    selected = set(assets)
    by_key_date: dict[tuple[str, date], Mapping[str, Any]] = {}
    for observation in observations:
        concept_key = str(observation.get("concept_key") or "").strip()
        if concept_key not in selected:
            continue
        observed_at = _date_value(observation.get("observed_at"))
        value = _numeric_value(observation.get("value_numeric", observation.get("value")))
        if observed_at is None or value is None or value <= 0:
            continue
        key = (concept_key, observed_at)
        previous = by_key_date.get(key)
        if previous is None or _source_rank(observation) > _source_rank(previous):
            by_key_date[key] = observation

    grouped: dict[str, list[dict[str, Any]]] = {concept_key: [] for concept_key in assets}
    for (concept_key, observed_at), observation in by_key_date.items():
        value = _numeric_value(observation.get("value_numeric", observation.get("value")))
        if value is None:
            continue
        grouped.setdefault(concept_key, []).append(
            {
                "observed_at": observed_at,
                "value": value,
                "source_name": str(observation.get("source_name") or "").strip(),
                "source_priority": _int_value(observation.get("source_priority")),
                "ingested_at_ms": _int_value(observation.get("ingested_at_ms")),
            }
        )
    for points in grouped.values():
        points.sort(key=lambda point: point["observed_at"])
    return grouped


def _windowed_returns(points: Sequence[Mapping[str, Any]], *, window_days: int) -> list[dict[str, Any]]:
    returns: list[dict[str, Any]] = []
    ordered = sorted(points, key=lambda point: point["observed_at"])
    for previous, current in pairwise(ordered):
        previous_value = _numeric_value(previous.get("value"))
        current_value = _numeric_value(current.get("value"))
        if previous_value is None or current_value is None or previous_value <= 0 or current_value <= 0:
            continue
        returns.append(
            {
                "observed_at": current["observed_at"],
                "return": math.log(current_value / previous_value),
            }
        )
    return returns[-window_days:]


def _pair_correlation(
    left: str,
    right: str,
    left_returns: Sequence[Mapping[str, Any]],
    right_returns: Sequence[Mapping[str, Any]],
    *,
    min_sample: int,
) -> dict[str, Any]:
    left_by_date = {point["observed_at"]: point["return"] for point in left_returns}
    right_by_date = {point["observed_at"]: point["return"] for point in right_returns}
    common_dates = sorted(set(left_by_date) & set(right_by_date))
    left_values = [_float_value(left_by_date[observed_at]) for observed_at in common_dates]
    right_values = [_float_value(right_by_date[observed_at]) for observed_at in common_dates]
    paired = [
        (observed_at, left_value, right_value)
        for observed_at, left_value, right_value in zip(common_dates, left_values, right_values, strict=True)
        if left_value is not None and right_value is not None
    ]
    sample_size = len(paired)
    if sample_size < min_sample:
        return _unavailable_pair(left, right, sample_size=sample_size, reason="insufficient_overlap")
    correlation = _pearson([item[1] for item in paired], [item[2] for item in paired])
    if correlation is None:
        return _unavailable_pair(left, right, sample_size=sample_size, reason="zero_variance")
    return {
        "left": left,
        "right": right,
        "correlation": _round(correlation),
        "sample_size": sample_size,
        "start_date": _date_text(paired[0][0]),
        "end_date": _date_text(paired[-1][0]),
        "available": True,
        "reason": None,
    }


def _asset_payload(
    concept_key: str,
    prices: Sequence[Mapping[str, Any]],
    returns: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    sources = sorted({str(point.get("source_name") or "") for point in prices if point.get("source_name")})
    return_dates = [_date_text(point["observed_at"]) for point in returns]
    latest = prices[-1] if prices else None
    return {
        "concept_key": concept_key,
        "title": ASSET_CORRELATION_TITLES.get(concept_key, concept_key),
        "observations_count": len(prices),
        "return_count": len(returns),
        "start_date": return_dates[0] if return_dates else None,
        "end_date": return_dates[-1] if return_dates else None,
        "latest_observed_at": _date_text(latest["observed_at"]) if latest else None,
        "sources": sources,
    }


def _unavailable_pair(left: str, right: str, *, sample_size: int, reason: str) -> dict[str, Any]:
    return {
        "left": left,
        "right": right,
        "correlation": None,
        "sample_size": sample_size,
        "start_date": None,
        "end_date": None,
        "available": False,
        "reason": reason,
    }


def _pearson(left_values: Sequence[float], right_values: Sequence[float]) -> float | None:
    left_mean = sum(left_values) / len(left_values)
    right_mean = sum(right_values) / len(right_values)
    left_centered = [value - left_mean for value in left_values]
    right_centered = [value - right_mean for value in right_values]
    numerator = sum(left * right for left, right in zip(left_centered, right_centered, strict=True))
    left_variance = sum(value * value for value in left_centered)
    right_variance = sum(value * value for value in right_centered)
    denominator = math.sqrt(left_variance * right_variance)
    if denominator == 0:
        return None
    return numerator / denominator


def _asof_date(prices_by_asset: Mapping[str, Sequence[Mapping[str, Any]]], assets: Sequence[str]) -> str | None:
    dates = [
        point["observed_at"]
        for concept_key in assets
        for point in prices_by_asset.get(concept_key, [])
        if point.get("observed_at") is not None
    ]
    return _date_text(max(dates)) if dates else None


def _minimum_sample_size(window_days: int) -> int:
    return min(window_days, max(10, min(30, window_days // 2)))


def _source_rank(observation: Mapping[str, Any]) -> tuple[int, int]:
    return (
        _int_value(observation.get("source_priority")),
        _int_value(observation.get("ingested_at_ms")),
    )


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, Decimal):
        return float(value) if math.isfinite(float(value)) else None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _float_value(value: Any) -> float | None:
    return value if isinstance(value, float) and math.isfinite(value) else None


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _date_text(value: Any) -> str | None:
    observed_at = _date_value(value)
    return observed_at.isoformat() if observed_at else None


def _round(value: float) -> float:
    return round(max(-1.0, min(1.0, value)), 4)


__all__ = [
    "ASSET_CORRELATION_WINDOWS",
    "DEFAULT_ASSET_CORRELATION_CONCEPTS",
    "OPTIONAL_ASSET_CORRELATION_CONCEPTS",
    "SUPPORTED_ASSET_CORRELATION_CONCEPTS",
    "build_macro_asset_correlation",
    "correlation_query_bounds",
]
