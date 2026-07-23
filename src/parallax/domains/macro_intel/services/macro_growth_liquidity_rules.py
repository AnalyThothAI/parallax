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


def build_growth_labor_rules(
    observations: Sequence[Mapping[str, Any]],
    *,
    evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    growth_metrics = [
        _release_growth(observations, evidence, "economy:gdp_real", periods=1, annualise_quarterly=True),
        _release_growth(observations, evidence, "economy:industrial_production", periods=1),
        _release_growth(observations, evidence, "consumer:retail_sales", periods=1),
        _release_growth(observations, evidence, "consumer:pce_real", periods=1),
    ]
    rule_hits: list[dict[str, Any]] = []
    claims_change = evidence_change(evidence, "labor:initial_claims")
    unemployment_change = evidence_change(evidence, "labor:unemployment")
    payroll_change = evidence_change(evidence, "labor:payrolls")
    real_gdp_saar = _metric_value(growth_metrics, "economy:gdp_real")
    if claims_change is not None and claims_change >= 25_000:
        rule_hits.append(rule_hit("claims_up_four_releases", "trigger", ["labor:initial_claims"]))
    if unemployment_change is not None and unemployment_change >= 0.2:
        rule_hits.append(rule_hit("unemployment_rate_up", "confirmation", ["labor:unemployment"]))
    if payroll_change is not None and payroll_change < 100:
        rule_hits.append(rule_hit("payroll_growth_below_100k", "confirmation", ["labor:payrolls"]))
    if real_gdp_saar is not None and real_gdp_saar < 1.0:
        rule_hits.append(rule_hit("real_gdp_below_one_pct_saar", "confirmation", ["economy:gdp_real"]))
    if payroll_change is not None and payroll_change >= 200:
        rule_hits.append(rule_hit("payroll_growth_above_200k", "contradiction", ["labor:payrolls"]))
    if real_gdp_saar is not None and real_gdp_saar >= 2.0:
        rule_hits.append(rule_hit("real_gdp_at_least_two_pct_saar", "contradiction", ["economy:gdp_real"]))
    return {
        "judgment": _growth_judgment(rule_hits),
        "rule_hits": rule_hits,
        "growth_metrics": growth_metrics,
    }


def build_liquidity_funding_rules(
    *,
    evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    spreads = [
        _funding_spread(evidence, "sofr_minus_iorb_bps", "liquidity:sofr", "fed:iorb", "secured"),
        _funding_spread(evidence, "bgcr_minus_iorb_bps", "liquidity:bgcr", "fed:iorb", "secured"),
        _funding_spread(evidence, "tgcr_minus_iorb_bps", "liquidity:tgcr", "fed:iorb", "secured"),
        _funding_spread(evidence, "effr_minus_iorb_bps", "fed:effr", "fed:iorb", "unsecured"),
        _funding_spread(evidence, "obfr_minus_iorb_bps", "fed:obfr", "fed:iorb", "unsecured"),
    ]
    net_liquidity = _net_liquidity_accounting_proxy(evidence)
    rule_hits: list[dict[str, Any]] = []
    sofr_spread = _derived_value(spreads, "derived:sofr_minus_iorb_bps")
    reserves_change = evidence_change(evidence, "liquidity:reserve_balances")
    fed_assets_change = evidence_change(evidence, "liquidity:fed_assets")
    tga_change = evidence_change(evidence, "liquidity:tga")
    rrp_value = evidence_value(evidence, "liquidity:on_rrp")
    if sofr_spread is not None and sofr_spread >= 10:
        rule_hits.append(rule_hit("sofr_iorb_at_least_10bps", "trigger", ["liquidity:sofr", "fed:iorb"]))
    if reserves_change is not None and reserves_change < 0:
        rule_hits.append(rule_hit("reserve_balances_declining", "trigger", ["liquidity:reserve_balances"]))
    if fed_assets_change is not None and fed_assets_change < 0:
        rule_hits.append(rule_hit("fed_assets_declining", "confirmation", ["liquidity:fed_assets"]))
    if tga_change is not None and tga_change > 0:
        rule_hits.append(rule_hit("treasury_cash_rising", "confirmation", ["liquidity:tga"]))
    if rrp_value is not None and rrp_value <= 300:
        rule_hits.append(rule_hit("reverse_repo_buffer_low", "confirmation", ["liquidity:on_rrp"]))
    return {
        "judgment": _liquidity_judgment(rule_hits),
        "rule_hits": rule_hits,
        "secured_funding_spreads": [item for item in spreads if item["claim_effect"] == "secured_funding"],
        "unsecured_funding_spreads": [item for item in spreads if item["claim_effect"] == "unsecured_funding"],
        "net_liquidity": net_liquidity,
    }


def _release_growth(
    observations: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
    concept_key: str,
    *,
    periods: int,
    annualise_quarterly: bool = False,
) -> dict[str, Any]:
    points = (
        numeric_series(observations, concept_key)
        if (evidence.get(concept_key) or {}).get("status") == "available"
        else []
    )
    if len(points) <= periods or points[-periods - 1]["value"] == 0:
        return {
            "concept_key": concept_key,
            "status": "unavailable",
            "reason": "insufficient_history",
            "value": None,
            "unit": "percent_saar" if annualise_quarterly else "percent",
            "window": f"{periods}_release",
            "sample": {"start": None, "end": None, "count": len(points)},
            "derivation": None,
        }
    prior = points[-periods - 1]
    latest = points[-1]
    ratio = latest["value"] / prior["value"]
    if annualise_quarterly:
        value = (ratio ** (4 / periods) - 1.0) * 100.0
        formula = "((latest / prior) ** (4 / periods) - 1) * 100"
        unit = "percent_saar"
    else:
        value = (ratio - 1.0) * 100.0
        formula = "(latest / prior - 1) * 100"
        unit = "percent"
    return {
        "concept_key": concept_key,
        "status": "available",
        "reason": None,
        "value": round(value, 10),
        "unit": unit,
        "window": f"{periods}_release",
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
            "references": list(
                dict.fromkeys(value for value in (prior["series_key"], latest["series_key"]) if isinstance(value, str))
            ),
        },
    }


def _funding_spread(
    evidence: Mapping[str, Mapping[str, Any]],
    name: str,
    left_key: str,
    right_key: str,
    funding_kind: str,
) -> dict[str, Any]:
    left, right, inputs, observed_dates, aligned = _evidence_pair(
        evidence,
        left_key=left_key,
        right_key=right_key,
    )
    available = left is not None and right is not None
    reason = None if aligned else "missing_funding_rate" if not available else "unaligned_input_dates"
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
        criticality="critical" if name == "sofr_minus_iorb_bps" else "optional",
        claim_effect=f"{funding_kind}_funding",
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


def _net_liquidity_accounting_proxy(evidence: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    fed_assets = evidence_value(evidence, "liquidity:fed_assets")
    treasury_cash = evidence_value(evidence, "liquidity:tga")
    reverse_repo_billions = evidence_value(evidence, "liquidity:on_rrp")
    inputs = (
        ("liquidity:fed_assets", fed_assets, "millions_usd", 1.0),
        ("liquidity:tga", treasury_cash, "millions_usd", 1.0),
        ("liquidity:on_rrp", reverse_repo_billions, "billions_usd", 1000.0),
    )
    observed_dates = [
        str((evidence.get(concept_key) or {}).get("observed_at") or "")
        for concept_key, _, _, _ in inputs
        if (evidence.get(concept_key) or {}).get("observed_at")
    ]
    available = all(value is not None for _, value, _, _ in inputs)
    value = (
        fed_assets - treasury_cash - reverse_repo_billions * 1000.0
        if fed_assets is not None and treasury_cash is not None and reverse_repo_billions is not None
        else None
    )
    return derived_evidence(
        concept_key="derived:net_liquidity_accounting_proxy",
        role="context",
        value=value,
        unit="millions_usd",
        change=None,
        change_window=None,
        observed_at=min(observed_dates) if observed_dates else None,
        frequency="irregular",
        source_name="derived_accounting_proxy",
        series_key="derived:net_liquidity_accounting_proxy",
        sample_start=min(observed_dates) if observed_dates else None,
        sample_end=max(observed_dates) if observed_dates else None,
        sample_count=3 if available else 0,
        criticality="optional",
        claim_effect="accounting_proxy_context_only",
        formula=("accounting proxy only: Fed assets - TGA - (RRP * 1000); no causal risk-asset inference"),
        inputs=[
            {
                "concept_key": concept_key,
                "source_unit": source_unit,
                "value_millions_usd": None if source_value is None else source_value * scale,
            }
            for concept_key, source_value, source_unit, scale in inputs
        ],
        references=[concept_key for concept_key, _, _, _ in inputs],
        status="available" if available else "unavailable",
        reason=None if available else "missing_accounting_proxy_input",
    )


def _growth_judgment(rule_hits: Sequence[Mapping[str, Any]]) -> str:
    codes = {str(item.get("rule_id") or "") for item in rule_hits}
    deterioration = len(
        codes
        & {
            "claims_up_four_releases",
            "unemployment_rate_up",
            "payroll_growth_below_100k",
            "real_gdp_below_one_pct_saar",
        }
    )
    resilience = len(codes & {"payroll_growth_above_200k", "real_gdp_at_least_two_pct_saar"})
    if deterioration >= 3:
        return "growth_labor_cooling"
    if resilience >= 2:
        return "growth_labor_resilient"
    return "mixed"


def _liquidity_judgment(rule_hits: Sequence[Mapping[str, Any]]) -> str:
    codes = {str(item.get("rule_id") or "") for item in rule_hits}
    if "sofr_iorb_at_least_10bps" in codes:
        return "secured_funding_pressure"
    if {"reserve_balances_declining", "fed_assets_declining"} <= codes:
        return "balance_sheet_drain"
    return "mixed"


def _metric_value(metrics: Sequence[Mapping[str, Any]], concept_key: str) -> float | None:
    for metric in metrics:
        if metric.get("concept_key") == concept_key and metric.get("status") == "available":
            return _number(metric.get("value"))
    return None


def _derived_value(items: Sequence[Mapping[str, Any]], concept_key: str) -> float | None:
    for item in items:
        if item.get("concept_key") == concept_key and item.get("status") == "available":
            return _number(item.get("value"))
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


__all__ = ["build_growth_labor_rules", "build_liquidity_funding_rules"]
