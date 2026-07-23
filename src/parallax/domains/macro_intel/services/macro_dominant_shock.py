from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_dominant_shock(
    *,
    cross_asset: Mapping[str, Any],
    rates_inflation: Mapping[str, Any],
    growth_labor: Mapping[str, Any],
    liquidity_funding: Mapping[str, Any],
    credit: Mapping[str, Any],
) -> dict[str, Any]:
    cross_judgment = str(cross_asset.get("judgment") or "")
    rates_judgment = str(rates_inflation.get("judgment") or "")
    growth_judgment = str(growth_labor.get("judgment") or "")
    liquidity_judgment = str(liquidity_funding.get("judgment") or "")
    credit_state = _mapping_value(credit, "credit_state")
    credit_stage = str(credit_state.get("stage") or "")
    credit_direction = str(credit_state.get("direction") or "")
    cross_codes = _rule_codes(cross_asset)
    rates_codes = _rule_codes(rates_inflation)
    growth_codes = _rule_codes(growth_labor)
    liquidity_codes = _rule_codes(liquidity_funding)
    credit_codes = _rule_codes(credit)
    growth_trigger_code, growth_trigger_refs = _growth_trigger(growth_codes)
    liquidity_trigger_code, liquidity_trigger_refs = _liquidity_trigger(
        liquidity_judgment,
        liquidity_codes,
    )
    candidates = (
        _candidate(
            "liquidity_funding",
            trigger=bool(liquidity_trigger_refs),
            trigger_code=liquidity_trigger_code,
            trigger_refs=liquidity_trigger_refs,
            confirmations=(
                (
                    cross_judgment == "risk_off_confirmation",
                    "cross_asset_risk_off",
                    ("asset:spy", "asset:hyg"),
                ),
                (
                    "credit_spreads_widening" in credit_codes,
                    "credit_spreads_widening",
                    ("credit:hy_oas", "credit:ig_oas"),
                ),
                (
                    "fed_assets_declining" in liquidity_codes and liquidity_trigger_code != "fed_assets_declining",
                    "fed_assets_declining",
                    ("liquidity:fed_assets",),
                ),
            ),
            contradictions=(
                (
                    cross_judgment == "risk_on_confirmation",
                    "cross_asset_risk_on",
                    ("asset:spy", "asset:hyg"),
                ),
                (
                    "credit_spreads_narrowing" in credit_codes,
                    "credit_spreads_narrowing",
                    ("credit:hy_oas", "credit:ig_oas"),
                ),
            ),
            affected_exposures=("usd_funding", "credit_beta", "risk_assets"),
        ),
        _candidate(
            "credit",
            trigger=credit_stage in {"tail_stress", "broadening", "systemic_tightening"}
            and credit_direction == "widening",
            trigger_code=f"credit_stage_{credit_stage}",
            trigger_refs=("credit:hy_oas", "credit:ig_oas", "credit:hy_ccc_oas"),
            confirmations=(
                (
                    cross_judgment == "risk_off_confirmation",
                    "cross_asset_risk_off",
                    ("asset:spy", "asset:hyg"),
                ),
                ("vix_up" in cross_codes, "volatility_confirmation", ("vol:vix",)),
                (
                    liquidity_judgment == "secured_funding_pressure",
                    "funding_confirmation",
                    ("liquidity:sofr", "fed:iorb"),
                ),
            ),
            contradictions=(
                (
                    cross_judgment == "risk_on_confirmation",
                    "cross_asset_risk_on",
                    ("asset:spy", "asset:hyg"),
                ),
            ),
            affected_exposures=("credit_beta", "small_cap", "risk_assets"),
        ),
        _candidate(
            "policy_real_rates",
            trigger=rates_judgment == "real_rate_tightening" and "real_rate_up_20_sessions" in rates_codes,
            trigger_code="real_rate_up_20_sessions",
            trigger_refs=("rates:real_10y", "rates:dgs10"),
            confirmations=(
                ("spy_down" in cross_codes, "equity_pressure", ("asset:spy",)),
                ("btc_down" in cross_codes, "crypto_beta_pressure", ("crypto:btc",)),
                (
                    cross_judgment == "risk_off_confirmation",
                    "cross_asset_risk_off",
                    ("asset:spy", "asset:hyg"),
                ),
            ),
            contradictions=(
                (
                    cross_judgment == "risk_on_confirmation",
                    "cross_asset_risk_on",
                    ("asset:spy", "asset:hyg"),
                ),
            ),
            affected_exposures=("duration", "growth_equity", "long_duration_assets"),
        ),
        _candidate(
            "inflation",
            trigger=rates_judgment == "inflation_pressure" and "breakeven_up_20_sessions" in rates_codes,
            trigger_code="breakeven_up_20_sessions",
            trigger_refs=("inflation:10y_breakeven", "inflation:core_cpi"),
            confirmations=(
                (_asset_return_positive(cross_asset, "asset:uso"), "energy_price_confirmation", ("asset:uso",)),
                (
                    "long_rate_up_20_sessions" in rates_codes,
                    "nominal_rate_confirmation",
                    ("rates:dgs10",),
                ),
            ),
            contradictions=(
                (
                    _asset_return_negative(cross_asset, "asset:uso"),
                    "energy_price_contradiction",
                    ("asset:uso",),
                ),
            ),
            affected_exposures=("duration", "real_assets", "policy_path"),
        ),
        _candidate(
            "growth",
            trigger=growth_judgment == "growth_labor_cooling" and bool(growth_trigger_refs),
            trigger_code=growth_trigger_code,
            trigger_refs=growth_trigger_refs,
            confirmations=(
                (
                    cross_judgment == "risk_off_confirmation",
                    "cross_asset_risk_off",
                    ("asset:spy", "asset:hyg"),
                ),
                (
                    str(_mapping_value(credit, "treasury_spread_quadrant").get("quadrant") or "")
                    == "yields_down_spreads_wider",
                    "growth_scare_quadrant",
                    ("rates:dgs10", "credit:hy_oas"),
                ),
            ),
            contradictions=(
                (
                    growth_judgment == "growth_labor_resilient",
                    "growth_resilience",
                    ("economy:gdp_real", "labor:payrolls"),
                ),
            ),
            affected_exposures=("cyclical_equity", "credit_beta", "growth_expectations"),
        ),
    )
    triggered = [candidate for candidate in candidates if candidate["triggered"]]
    if not triggered:
        return _empty_dominant_shock()
    selected = triggered[0]
    if selected["contradictions"]:
        status = "divergent"
    elif selected["confirmations"]:
        status = "confirmed"
    else:
        status = "provisional"
    hit_evidence = list(
        dict.fromkeys(
            [*selected["primary_trigger"]["evidence_refs"]]
            + [ref for item in selected["confirmations"] for ref in item["evidence_refs"]]
            + [ref for item in selected["contradictions"] for ref in item["evidence_refs"]]
        )
    )
    return {
        "candidate": selected["candidate"],
        "status": status,
        "primary_trigger": selected["primary_trigger"],
        "cross_domain_confirmations": selected["confirmations"],
        "critical_contradictions": selected["contradictions"],
        "affected_exposures": selected["affected_exposures"],
        "rule_version": "macro_dominant_shock_v1",
        "hit_evidence": hit_evidence,
    }


def _empty_dominant_shock() -> dict[str, Any]:
    return {
        "candidate": None,
        "status": "insufficient_evidence",
        "primary_trigger": None,
        "cross_domain_confirmations": [],
        "critical_contradictions": [],
        "affected_exposures": [],
        "rule_version": "macro_dominant_shock_v1",
        "hit_evidence": [],
    }


def _candidate(
    candidate: str,
    *,
    trigger: bool,
    trigger_code: str,
    trigger_refs: Sequence[str],
    confirmations: Sequence[tuple[bool, str, Sequence[str]]],
    contradictions: Sequence[tuple[bool, str, Sequence[str]]],
    affected_exposures: Sequence[str],
) -> dict[str, Any]:
    return {
        "candidate": candidate,
        "triggered": bool(trigger),
        "primary_trigger": {"code": trigger_code, "evidence_refs": list(trigger_refs)},
        "confirmations": [
            {"code": code, "evidence_refs": list(refs)} for matched, code, refs in confirmations if matched
        ],
        "contradictions": [
            {"code": code, "evidence_refs": list(refs)} for matched, code, refs in contradictions if matched
        ],
        "affected_exposures": list(affected_exposures),
    }


def _rule_codes(payload: Mapping[str, Any]) -> set[str]:
    hits = payload.get("rule_hits")
    if not isinstance(hits, Sequence) or isinstance(hits, str | bytes | bytearray):
        return set()
    return {
        str(item.get("rule_id") or "") for item in hits if isinstance(item, Mapping) and str(item.get("rule_id") or "")
    }


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _growth_trigger(codes: set[str]) -> tuple[str, tuple[str, ...]]:
    candidates = (
        ("claims_up_four_releases", ("labor:initial_claims",)),
        ("unemployment_rate_up", ("labor:unemployment",)),
        ("payroll_growth_below_100k", ("labor:payrolls",)),
        ("real_gdp_below_one_pct_saar", ("economy:gdp_real",)),
    )
    return next((candidate for candidate in candidates if candidate[0] in codes), ("", ()))


def _liquidity_trigger(judgment: str, codes: set[str]) -> tuple[str, tuple[str, ...]]:
    if judgment == "secured_funding_pressure" and "sofr_iorb_at_least_10bps" in codes:
        return "sofr_iorb_at_least_10bps", ("liquidity:sofr", "fed:iorb")
    if judgment == "balance_sheet_drain" and "reserve_balances_declining" in codes:
        return "reserve_balances_declining", ("liquidity:reserve_balances",)
    return "", ()


def _asset_return_positive(payload: Mapping[str, Any], concept_key: str) -> bool:
    value = _asset_return(payload, concept_key)
    return value is not None and value > 0


def _asset_return_negative(payload: Mapping[str, Any], concept_key: str) -> bool:
    value = _asset_return(payload, concept_key)
    return value is not None and value < 0


def _asset_return(payload: Mapping[str, Any], concept_key: str) -> float | None:
    returns = payload.get("asset_returns")
    if not isinstance(returns, Sequence) or isinstance(returns, str | bytes | bytearray):
        return None
    for item in returns:
        if not isinstance(item, Mapping) or item.get("concept_key") != concept_key:
            continue
        window = item.get("return_20")
        if not isinstance(window, Mapping) or window.get("status") != "available":
            return None
        value = window.get("value")
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)
    return None


__all__ = ["build_dominant_shock"]
