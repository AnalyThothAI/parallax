from __future__ import annotations

import math
from calendar import monthrange
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from parallax.domains.macro_intel.services.macro_evidence import (
    evidence_change,
    numeric_series,
    rule_hit,
)

_ASSET_CONCEPTS = (
    "asset:spx",
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
_CORRELATION_PAIRS = (
    ("asset:spy", "asset:qqq"),
    ("asset:spy", "asset:iwm"),
    ("asset:spy", "asset:hyg"),
    ("asset:spy", "asset:tlt"),
    ("asset:spy", "asset:gld"),
    ("asset:spy", "fx:dxy"),
    ("asset:spy", "crypto:btc"),
    ("asset:hyg", "asset:lqd"),
    ("asset:tlt", "fx:dxy"),
    ("crypto:btc", "fx:dxy"),
)
_CRITICAL_RETURN_CONCEPTS = frozenset(("asset:spy", "asset:hyg", "fx:dxy"))
_CRITICAL_CORRELATION_PAIRS = frozenset(
    (
        ("asset:spy", "asset:hyg"),
        ("asset:spy", "fx:dxy"),
    )
)
_NEW_YORK = ZoneInfo("America/New_York")
_REGULAR_CLOSE = time(16, 0)
_EARLY_CLOSE = time(13, 0)


def resolve_market_cutoff(*, computed_at_ms: int) -> date:
    instant = datetime.fromtimestamp(int(computed_at_ms) / 1000, tz=UTC).astimezone(_NEW_YORK)
    candidate = instant.date()
    while True:
        if not _is_us_market_session(candidate):
            candidate -= timedelta(days=1)
            continue
        if candidate == instant.date() and instant.time() < _session_close(candidate):
            candidate -= timedelta(days=1)
            continue
        return candidate


def _is_us_market_session(day: date) -> bool:
    return day.weekday() < 5 and day not in _us_market_holidays(day.year)


def _session_close(day: date) -> time:
    thanksgiving = _nth_weekday(day.year, 11, weekday=3, occurrence=4)
    early_close_days = {
        thanksgiving + timedelta(days=1),
        date(day.year, 7, 3),
        date(day.year, 12, 24),
    }
    return _EARLY_CLOSE if day in early_close_days and _is_us_market_session(day) else _REGULAR_CLOSE


def _us_market_holidays(year: int) -> set[date]:
    holidays = {
        _observed_fixed_holiday(date(year, 1, 1)),
        _nth_weekday(year, 1, weekday=0, occurrence=3),
        _nth_weekday(year, 2, weekday=0, occurrence=3),
        _easter_sunday(year) - timedelta(days=2),
        _last_weekday(year, 5, weekday=0),
        _observed_fixed_holiday(date(year, 7, 4)),
        _nth_weekday(year, 9, weekday=0, occurrence=1),
        _nth_weekday(year, 11, weekday=3, occurrence=4),
        _observed_fixed_holiday(date(year, 12, 25)),
    }
    if year >= 2022:
        holidays.add(_observed_fixed_holiday(date(year, 6, 19)))
    return holidays


def _observed_fixed_holiday(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, *, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, *, weekday: int) -> date:
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def build_cross_asset_rules(
    observations: Sequence[Mapping[str, Any]],
    *,
    evidence: Mapping[str, Mapping[str, Any]],
    market_cutoff: date | None,
) -> dict[str, Any]:
    returns = [
        _asset_return_payload(
            observations,
            concept_key=concept_key,
            cutoff=market_cutoff,
            evidence_item=evidence.get(concept_key),
        )
        for concept_key in _ASSET_CONCEPTS
    ]
    return_20 = {
        item["concept_key"]: item["return_20"]["value"]
        for item in returns
        if item["return_20"]["status"] == "available"
    }
    rule_hits = _direction_rule_hits(return_20, evidence=evidence)
    judgment = _cross_asset_judgment(rule_hits)
    divergences = _divergences(return_20, evidence=evidence)
    correlations_20 = _correlations(observations, evidence=evidence, cutoff=market_cutoff, window=20)
    correlations_60 = _correlations(observations, evidence=evidence, cutoff=market_cutoff, window=60)
    return {
        "judgment": judgment,
        "rule_hits": rule_hits,
        "asset_returns": returns,
        "correlations_20": correlations_20,
        "correlations_60": correlations_60,
        "divergences": divergences,
    }


def cross_asset_freshness(
    base_freshness: Mapping[str, Any],
    rules: Mapping[str, Any],
) -> dict[str, Any]:
    critical_missing = {str(item) for item in base_freshness.get("critical_missing", ()) if str(item)}
    critical_stale = {str(item) for item in base_freshness.get("critical_stale", ()) if str(item)}
    optional_unavailable = {str(item) for item in base_freshness.get("optional_unavailable", ()) if str(item)}
    asset_returns = rules.get("asset_returns")
    if isinstance(asset_returns, Sequence) and not isinstance(asset_returns, str | bytes | bytearray):
        for item in asset_returns:
            if not isinstance(item, Mapping):
                continue
            concept_key = str(item.get("concept_key") or "")
            return_60 = item.get("return_60")
            if not concept_key or not isinstance(return_60, Mapping) or return_60.get("status") == "available":
                continue
            gap = f"cross_asset_return_60:{concept_key}"
            if concept_key in _CRITICAL_RETURN_CONCEPTS:
                critical_missing.add(gap)
            else:
                optional_unavailable.add(gap)
    correlations_60 = rules.get("correlations_60")
    if isinstance(correlations_60, Sequence) and not isinstance(correlations_60, str | bytes | bytearray):
        for item in correlations_60:
            if not isinstance(item, Mapping) or item.get("status") == "available":
                continue
            left = str(item.get("left") or "")
            right = str(item.get("right") or "")
            if not left or not right:
                continue
            gap = f"cross_asset_correlation_60:{left}:{right}"
            if (left, right) in _CRITICAL_CORRELATION_PAIRS:
                critical_missing.add(gap)
            else:
                optional_unavailable.add(gap)
    if critical_missing or critical_stale:
        status = "insufficient_evidence"
    elif optional_unavailable:
        status = "degraded"
    else:
        status = "fresh"
    return {
        "status": status,
        "critical_missing": sorted(critical_missing),
        "critical_stale": sorted(critical_stale),
        "optional_unavailable": sorted(optional_unavailable),
    }


def _asset_return_payload(
    observations: Sequence[Mapping[str, Any]],
    *,
    concept_key: str,
    cutoff: date | None,
    evidence_item: Mapping[str, Any] | None,
) -> dict[str, Any]:
    evidence_ready = evidence_item is not None and evidence_item.get("status") == "available"
    points = numeric_series(observations, concept_key, cutoff=cutoff) if evidence_ready else []
    latest = points[-1] if points else None
    aligned = latest is not None and cutoff is not None and latest["observed_at"] == cutoff
    missing_reason = (
        "evidence_not_current"
        if not evidence_ready
        else "missing_price_history"
        if not points
        else "missing_at_market_cutoff"
    )
    return {
        "concept_key": concept_key,
        "status": "available" if aligned else "unavailable",
        "reason": None if aligned else missing_reason,
        "observed_at": latest["observed_at"].isoformat() if latest else None,
        "source_name": latest["source_name"] if latest else None,
        "series_key": latest["series_key"] if latest else None,
        "return_20": _window_return(points, periods=20, aligned=aligned),
        "return_60": _window_return(points, periods=60, aligned=aligned),
    }


def _window_return(
    points: Sequence[Mapping[str, Any]],
    *,
    periods: int,
    aligned: bool,
) -> dict[str, Any]:
    window = f"{periods}_sessions"
    if points and not aligned:
        return {
            "status": "unavailable",
            "reason": "missing_at_market_cutoff",
            "window": window,
            "value": None,
            "unit": "percent",
            "sample": _sample(points),
            "derivation": None,
        }
    if len(points) <= periods:
        return {
            "status": "unavailable",
            "reason": "insufficient_history",
            "window": window,
            "value": None,
            "unit": "percent",
            "sample": _sample(points),
            "derivation": None,
        }
    prior = points[-periods - 1]
    latest = points[-1]
    if prior["value"] <= 0 or latest["value"] <= 0:
        return {
            "status": "unavailable",
            "reason": "non_positive_price",
            "window": window,
            "value": None,
            "unit": "percent",
            "sample": _sample(points[-periods - 1 :]),
            "derivation": None,
        }
    value = (latest["value"] / prior["value"] - 1.0) * 100.0
    return {
        "status": "available",
        "reason": None,
        "window": window,
        "value": round(value, 10),
        "unit": "percent",
        "sample": _sample(points[-periods - 1 :]),
        "derivation": {
            "formula": "(latest / prior - 1) * 100",
            "inputs": [
                {"observed_at": prior["observed_at"].isoformat(), "value": prior["value"]},
                {"observed_at": latest["observed_at"].isoformat(), "value": latest["value"]},
            ],
            "references": list(dict.fromkeys([prior["series_key"], latest["series_key"]])),
        },
    }


def _correlations(
    observations: Sequence[Mapping[str, Any]],
    *,
    evidence: Mapping[str, Mapping[str, Any]],
    cutoff: date | None,
    window: int,
) -> list[dict[str, Any]]:
    prices_by_concept = {
        concept_key: {
            point["observed_at"]: point["value"]
            for point in (
                numeric_series(observations, concept_key, cutoff=cutoff)
                if (evidence.get(concept_key) or {}).get("status") == "available"
                else []
            )
        }
        for concept_key in _ASSET_CONCEPTS
    }
    return [
        _pair_correlation(
            left,
            right,
            prices_by_concept[left],
            prices_by_concept[right],
            cutoff=cutoff,
            window=window,
        )
        for left, right in _CORRELATION_PAIRS
    ]


def _pair_correlation(
    left: str,
    right: str,
    left_prices: Mapping[date, float],
    right_prices: Mapping[date, float],
    *,
    cutoff: date | None,
    window: int,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "left": left,
        "right": right,
        "window": f"{window}_sessions",
    }
    if cutoff is None or cutoff not in left_prices or cutoff not in right_prices:
        return {
            **base,
            "sample": {"start": None, "end": None, "count": 0},
            "status": "unavailable",
            "reason": "missing_at_market_cutoff",
            "correlation": None,
        }
    common_price_dates = sorted(set(left_prices) & set(right_prices))[-(window + 1) :]
    aligned_returns = [
        (
            current,
            math.log(left_prices[current] / left_prices[previous]),
            math.log(right_prices[current] / right_prices[previous]),
        )
        for previous, current in pairwise(common_price_dates)
        if left_prices[previous] > 0
        and left_prices[current] > 0
        and right_prices[previous] > 0
        and right_prices[current] > 0
    ]
    return_dates = [item[0] for item in aligned_returns]
    sample = {
        "start": common_price_dates[0].isoformat() if common_price_dates else None,
        "end": return_dates[-1].isoformat() if return_dates else None,
        "count": len(aligned_returns),
    }
    base = {**base, "sample": sample}
    if len(aligned_returns) < window:
        return {**base, "status": "unavailable", "reason": "insufficient_overlap", "correlation": None}
    left_values = [item[1] for item in aligned_returns]
    right_values = [item[2] for item in aligned_returns]
    correlation = _pearson(left_values, right_values)
    if correlation is None:
        return {**base, "status": "unavailable", "reason": "zero_variance", "correlation": None}
    return {
        **base,
        "status": "available",
        "reason": None,
        "correlation": round(max(-1.0, min(1.0, correlation)), 10),
    }


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    denominator = math.sqrt(
        sum(value * value for value in left_centered) * sum(value * value for value in right_centered)
    )
    if denominator == 0:
        return None
    return sum(a * b for a, b in zip(left_centered, right_centered, strict=True)) / denominator


def _direction_rule_hits(
    returns: Mapping[str, Any],
    *,
    evidence: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    rules = (
        ("spy_down", _less(returns.get("asset:spy"), -1.0), "trigger", ("asset:spy",)),
        ("hyg_down", _less(returns.get("asset:hyg"), -0.5), "confirmation", ("asset:hyg",)),
        ("btc_down", _less(returns.get("crypto:btc"), -3.0), "confirmation", ("crypto:btc",)),
        ("dollar_up", _greater(returns.get("fx:dxy"), 1.0), "confirmation", ("fx:dxy",)),
        ("vix_up", _greater(evidence_change(evidence, "vol:vix"), 3.0), "confirmation", ("vol:vix",)),
        ("spy_up", _greater(returns.get("asset:spy"), 1.0), "trigger", ("asset:spy",)),
        ("hyg_up", _greater(returns.get("asset:hyg"), 0.5), "confirmation", ("asset:hyg",)),
        ("btc_up", _greater(returns.get("crypto:btc"), 3.0), "confirmation", ("crypto:btc",)),
        ("dollar_down", _less(returns.get("fx:dxy"), -1.0), "confirmation", ("fx:dxy",)),
        ("vix_down", _less(evidence_change(evidence, "vol:vix"), -3.0), "confirmation", ("vol:vix",)),
    )
    for rule_id, matched, outcome, refs in rules:
        if matched:
            hits.append(rule_hit(rule_id, outcome, refs))
    return hits


def _cross_asset_judgment(rule_hits: Sequence[Mapping[str, Any]]) -> str:
    codes = {str(hit["rule_id"]) for hit in rule_hits}
    risk_off = len(codes & {"spy_down", "hyg_down", "btc_down", "dollar_up", "vix_up"})
    risk_on = len(codes & {"spy_up", "hyg_up", "btc_up", "dollar_down", "vix_down"})
    if risk_off >= 3:
        return "risk_off_confirmation"
    if risk_on >= 3:
        return "risk_on_confirmation"
    return "divergent"


def _divergences(
    returns: Mapping[str, Any],
    *,
    evidence: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    divergences: list[dict[str, Any]] = []
    spy = _float(returns.get("asset:spy"))
    btc = _float(returns.get("crypto:btc"))
    hyg = _float(returns.get("asset:hyg"))
    vix = evidence_change(evidence, "vol:vix")
    if spy is not None and btc is not None and spy * btc < 0:
        divergences.append({"code": "equity_crypto_divergence", "evidence_refs": ["asset:spy", "crypto:btc"]})
    if spy is not None and hyg is not None and spy > 0 >= hyg:
        divergences.append({"code": "equity_credit_divergence", "evidence_refs": ["asset:spy", "asset:hyg"]})
    if spy is not None and vix is not None and spy < 0 and vix <= 0:
        divergences.append({"code": "equity_volatility_divergence", "evidence_refs": ["asset:spy", "vol:vix"]})
    return divergences


def _sample(points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "start": points[0]["observed_at"].isoformat() if points else None,
        "end": points[-1]["observed_at"].isoformat() if points else None,
        "count": len(points),
    }


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _less(value: object, threshold: float) -> bool:
    numeric = _float(value)
    return numeric is not None and numeric < threshold


def _greater(value: object, threshold: float) -> bool:
    numeric = _float(value)
    return numeric is not None and numeric > threshold


__all__ = ["build_cross_asset_rules", "cross_asset_freshness", "resolve_market_cutoff"]
