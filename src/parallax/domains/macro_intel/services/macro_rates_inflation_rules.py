from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, SupportsFloat, SupportsIndex

from parallax.domains.macro_intel.services.macro_evidence import (
    derived_evidence,
    evidence_change,
    evidence_value,
    numeric_series,
    rule_hit,
)

_NOMINAL_TENORS = (
    "rates:dgs1mo",
    "rates:dgs3mo",
    "rates:dgs6mo",
    "rates:dgs1",
    "rates:dgs2",
    "rates:dgs3",
    "rates:dgs5",
    "rates:dgs7",
    "rates:dgs10",
    "rates:dgs20",
    "rates:dgs30",
)
_INFLATION_RELEASES = (
    "inflation:cpi",
    "inflation:core_cpi",
    "inflation:ppi",
    "inflation:pce",
    "inflation:core_pce",
    "inflation:gdp_deflator",
    "inflation:mich_1y_expectation",
)


def build_rates_inflation_rules(
    observations: Sequence[Mapping[str, Any]],
    *,
    evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    curve_slopes = [
        _curve_slope(evidence, direct_key="rates:10y2y", long_key="rates:dgs10", short_key="rates:dgs2"),
        _curve_slope(evidence, direct_key="rates:10y3m", long_key="rates:dgs10", short_key="rates:dgs3mo"),
    ]
    curve_shape = classify_curve_shape(curve_slopes, evidence=evidence)
    policy_funding_corridor = _policy_funding_corridor(evidence)
    inflation_releases = [
        _inflation_release(observations, evidence=evidence, concept_key=concept_key)
        for concept_key in _INFLATION_RELEASES
    ]
    rule_hits = _rates_rule_hits(
        evidence=evidence,
        curve_shape=curve_shape,
        policy_funding_corridor=policy_funding_corridor,
        inflation_releases=inflation_releases,
    )
    return {
        "judgment": _rates_judgment(rule_hits, curve_shape=curve_shape),
        "rule_hits": rule_hits,
        "nominal_tenor_order": list(_NOMINAL_TENORS),
        "curve_slopes": curve_slopes,
        "curve_shape": curve_shape,
        "policy_funding_corridor": policy_funding_corridor,
        "inflation_releases": inflation_releases,
    }


def classify_curve_shape(
    curve_slopes: Sequence[Mapping[str, Any]],
    *,
    evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    values = {
        str(item.get("concept_key") or ""): _number(item.get("value"))
        for item in curve_slopes
        if str(item.get("status") or "") == "available"
    }
    two_ten = values.get("rates:10y2y")
    three_month_ten = values.get("rates:10y3m")
    if two_ten is None or three_month_ten is None:
        level_classification = "insufficient_evidence"
    elif two_ten < 0 and three_month_ten < 0:
        level_classification = "inverted"
    elif two_ten >= 0.25 and three_month_ten >= 0.25:
        level_classification = "upward_sloping"
    elif abs(two_ten) <= 0.25 and abs(three_month_ten) <= 0.25:
        level_classification = "flat"
    else:
        level_classification = "mixed"
    two_year_change = evidence_change(evidence, "rates:dgs2")
    ten_year_change = evidence_change(evidence, "rates:dgs10")
    move_classification = _curve_move(two_year_change=two_year_change, ten_year_change=ten_year_change)
    status = (
        "supported"
        if level_classification != "insufficient_evidence" and move_classification != "insufficient_evidence"
        else "insufficient_evidence"
    )
    return {
        "status": status,
        "level_classification": level_classification,
        "move_classification": move_classification,
        "two_year_change": two_year_change,
        "ten_year_change": ten_year_change,
        "change_window": "20_sessions",
        "evidence_refs": ["rates:10y2y", "rates:10y3m", "rates:dgs2", "rates:dgs10"],
        "rule_version": "macro_curve_shape_v1",
    }


def _curve_move(*, two_year_change: float | None, ten_year_change: float | None) -> str:
    if two_year_change is None or ten_year_change is None:
        return "insufficient_evidence"
    slope_change = ten_year_change - two_year_change
    if two_year_change < 0 and ten_year_change < 0:
        if slope_change > 0.05:
            return "bull_steepener"
        if slope_change < -0.05:
            return "bull_flattener"
    elif two_year_change > 0 and ten_year_change > 0:
        if slope_change > 0.05:
            return "bear_steepener"
        if slope_change < -0.05:
            return "bear_flattener"
    return "mixed"


def _curve_slope(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    direct_key: str,
    long_key: str,
    short_key: str,
) -> dict[str, Any]:
    direct = evidence.get(direct_key)
    if direct is not None and str(direct.get("status") or "") == "available":
        return dict(direct)
    long_value, short_value, inputs, observed_dates, aligned = _evidence_pair(
        evidence,
        left_key=long_key,
        right_key=short_key,
    )
    available = long_value is not None and short_value is not None
    reason = None if aligned else "missing_curve_tenor" if not available else "unaligned_input_dates"
    observed_at = observed_dates[0] if aligned else None
    return derived_evidence(
        concept_key=direct_key,
        role="primary",
        value=long_value - short_value if aligned and long_value is not None and short_value is not None else None,
        unit="percent",
        change=None,
        change_window=None,
        observed_at=observed_at,
        frequency="daily",
        source_name="derived",
        series_key=f"derived:{direct_key}",
        sample_start=min(observed_dates) if observed_dates else None,
        sample_end=max(observed_dates) if observed_dates else None,
        sample_count=sum(1 for item in inputs if item["value"] is not None and item["observed_at"] is not None),
        criticality="optional",
        claim_effect="curve_shape",
        formula="long_yield - short_yield",
        inputs=inputs,
        references=[long_key, short_key],
        status="available" if aligned else "unavailable",
        reason=reason,
    )


def _policy_funding_corridor(evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    target_lower = evidence_value(evidence, "fed:target_lower")
    target_upper = evidence_value(evidence, "fed:target_upper")
    effr = evidence_value(evidence, "fed:effr")
    iorb = evidence_value(evidence, "fed:iorb")
    sofr = evidence_value(evidence, "liquidity:sofr")
    spreads = [
        _basis_point_spread(evidence, name="sofr_minus_iorb_bps", left_key="liquidity:sofr", right_key="fed:iorb"),
        _basis_point_spread(evidence, name="effr_minus_iorb_bps", left_key="fed:effr", right_key="fed:iorb"),
    ]
    critical = {"fed:effr": effr, "fed:iorb": iorb, "liquidity:sofr": sofr}
    critical_dates = [str((evidence.get(key) or {}).get("observed_at") or "") for key in critical]
    critical_aligned = all(critical_dates) and len(set(critical_dates)) == 1
    if any(value is None for value in critical.values()) or not critical_aligned:
        state = "insufficient_evidence"
        status = "insufficient_evidence"
    elif (sofr is not None and iorb is not None and (sofr - iorb) * 100 >= 10) or (
        target_upper is not None and sofr is not None and sofr > target_upper
    ):
        state = "secured_funding_pressure"
        status = "supported"
    elif (
        target_lower is not None
        and target_upper is not None
        and effr is not None
        and target_lower <= effr <= target_upper
        and (sofr is None or sofr <= target_upper)
    ):
        state = "orderly"
        status = "supported"
    else:
        state = "mixed"
        status = "supported"
    return {
        "status": status,
        "state": state,
        "evidence_refs": ["fed:target_lower", "fed:target_upper", "fed:effr", "fed:iorb", "liquidity:sofr"],
        "spreads": spreads,
    }


def _basis_point_spread(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    name: str,
    left_key: str,
    right_key: str,
) -> dict[str, Any]:
    left, right, inputs, observed_dates, aligned = _evidence_pair(
        evidence,
        left_key=left_key,
        right_key=right_key,
    )
    available = left is not None and right is not None
    reason = None if aligned else "missing_corridor_rate" if not available else "unaligned_input_dates"
    return derived_evidence(
        concept_key=f"derived:{name}",
        role="confirmation",
        value=(left - right) * 100.0 if aligned and left is not None and right is not None else None,
        unit="basis_points",
        change=None,
        change_window=None,
        observed_at=observed_dates[0] if aligned else None,
        frequency="daily",
        source_name="derived",
        series_key=f"derived:{name}",
        sample_start=min(observed_dates) if observed_dates else None,
        sample_end=max(observed_dates) if observed_dates else None,
        sample_count=sum(1 for item in inputs if item["value"] is not None and item["observed_at"] is not None),
        criticality="critical",
        claim_effect="funding_corridor",
        formula="(left_rate - right_rate) * 100",
        inputs=inputs,
        references=[left_key, right_key],
        status="available" if aligned else "unavailable",
        reason=reason,
    )


def _evidence_pair(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    left_key: str,
    right_key: str,
) -> tuple[float | None, float | None, list[dict[str, Any]], list[str], bool]:
    left = evidence_value(evidence, left_key)
    right = evidence_value(evidence, right_key)
    inputs = [
        {
            "concept_key": concept_key,
            "observed_at": str((evidence.get(concept_key) or {}).get("observed_at") or "") or None,
            "value": value,
        }
        for concept_key, value in ((left_key, left), (right_key, right))
    ]
    observed_dates = [
        str(item["observed_at"]) for item in inputs if item["value"] is not None and item["observed_at"] is not None
    ]
    aligned = (
        left is not None and right is not None and len(observed_dates) == 2 and observed_dates[0] == observed_dates[1]
    )
    return left, right, inputs, observed_dates, aligned


def _inflation_release(
    observations: Sequence[Mapping[str, Any]],
    *,
    evidence: Mapping[str, Mapping[str, Any]],
    concept_key: str,
) -> dict[str, Any]:
    base = dict(evidence[concept_key])
    points = numeric_series(observations, concept_key) if base.get("status") == "available" else []
    is_quarterly = str(base.get("frequency") or "") == "quarterly"
    if str(base.get("unit") or "") == "index":
        release_change = _percentage_change(points, periods=1, window="1_release")
        year_over_year = _percentage_change(
            points,
            periods=4 if is_quarterly else 12,
            window="4_releases" if is_quarterly else "12_releases",
        )
    else:
        release_change = _difference(points, periods=1, window="1_release")
        year_over_year = _unavailable_change("not_applicable")
    return {"evidence": base, "release_change": release_change, "year_over_year": year_over_year}


def _percentage_change(
    points: Sequence[Mapping[str, Any]],
    *,
    periods: int,
    window: str,
) -> dict[str, Any]:
    if len(points) <= periods or points[-periods - 1]["value"] == 0:
        return _unavailable_change("insufficient_history", window=window)
    prior = points[-periods - 1]
    latest = points[-1]
    return _change_result(
        value=(latest["value"] / prior["value"] - 1.0) * 100.0,
        unit="percent",
        window=window,
        prior=prior,
        latest=latest,
        formula="(latest / prior - 1) * 100",
    )


def _difference(
    points: Sequence[Mapping[str, Any]],
    *,
    periods: int,
    window: str,
) -> dict[str, Any]:
    if len(points) <= periods:
        return _unavailable_change("insufficient_history", window=window)
    prior = points[-periods - 1]
    latest = points[-1]
    return _change_result(
        value=latest["value"] - prior["value"],
        unit=latest["unit"] or "unknown",
        window=window,
        prior=prior,
        latest=latest,
        formula="latest - prior",
    )


def _change_result(
    *,
    value: float,
    unit: str,
    window: str,
    prior: Mapping[str, Any],
    latest: Mapping[str, Any],
    formula: str,
) -> dict[str, Any]:
    return {
        "status": "available",
        "reason": None,
        "value": round(value, 10),
        "unit": unit,
        "window": window,
        "sample": {
            "start": prior["observed_at"].isoformat(),
            "end": latest["observed_at"].isoformat(),
            "count": 2,
        },
        "derivation": {
            "formula": formula,
            "inputs": [
                {"observed_at": prior["observed_at"].isoformat(), "value": prior["value"]},
                {"observed_at": latest["observed_at"].isoformat(), "value": latest["value"]},
            ],
            "references": list(dict.fromkeys([prior["series_key"], latest["series_key"]])),
        },
    }


def _unavailable_change(reason: str, *, window: str | None = None) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "value": None,
        "unit": None,
        "window": window,
        "sample": {"start": None, "end": None, "count": 0},
        "derivation": None,
    }


def _rates_rule_hits(
    *,
    evidence: Mapping[str, Mapping[str, Any]],
    curve_shape: Mapping[str, Any],
    policy_funding_corridor: Mapping[str, Any],
    inflation_releases: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    nominal_change = evidence_change(evidence, "rates:dgs10")
    real_change = evidence_change(evidence, "rates:real_10y")
    breakeven_change = evidence_change(evidence, "inflation:10y_breakeven")
    core_cpi_mom = _release_change_value(inflation_releases, "inflation:core_cpi")
    if nominal_change is not None and nominal_change >= 0.25:
        hits.append(rule_hit("long_rate_up_20_sessions", "trigger", ["rates:dgs10"]))
    if real_change is not None and real_change >= 0.25:
        hits.append(rule_hit("real_rate_up_20_sessions", "confirmation", ["rates:real_10y"]))
    if breakeven_change is not None and breakeven_change >= 0.15:
        hits.append(rule_hit("breakeven_up_20_sessions", "trigger", ["inflation:10y_breakeven"]))
    if core_cpi_mom is not None and core_cpi_mom >= 0.25:
        hits.append(rule_hit("core_cpi_release_pressure", "confirmation", ["inflation:core_cpi"]))
    if str(curve_shape.get("level_classification") or "") == "inverted":
        hits.append(rule_hit("curve_inverted", "contradiction", ["rates:10y2y", "rates:10y3m"]))
    if str(policy_funding_corridor.get("state") or "") == "secured_funding_pressure":
        hits.append(rule_hit("secured_funding_pressure", "trigger", ["liquidity:sofr", "fed:iorb"]))
    return hits


def _rates_judgment(rule_hits: Sequence[Mapping[str, Any]], *, curve_shape: Mapping[str, Any]) -> str:
    codes = {str(item.get("rule_id") or "") for item in rule_hits}
    if {"long_rate_up_20_sessions", "real_rate_up_20_sessions"} <= codes:
        return "real_rate_tightening"
    if {"breakeven_up_20_sessions", "core_cpi_release_pressure"} <= codes:
        return "inflation_pressure"
    if "secured_funding_pressure" in codes:
        return "policy_corridor_pressure"
    return str(curve_shape.get("level_classification") or "insufficient_evidence")


def _release_change_value(releases: Sequence[Mapping[str, Any]], concept_key: str) -> float | None:
    for release in releases:
        evidence = release.get("evidence")
        if not isinstance(evidence, Mapping) or evidence.get("concept_key") != concept_key:
            continue
        change = release.get("release_change")
        return _number(change.get("value")) if isinstance(change, Mapping) else None
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, str | bytes | bytearray | SupportsFloat | SupportsIndex):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["build_rates_inflation_rules", "classify_curve_shape"]
