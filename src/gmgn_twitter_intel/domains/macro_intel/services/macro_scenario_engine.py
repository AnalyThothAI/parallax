from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

CHAIN_NODE_COUNT = 7

TRIGGER_INDICATORS = {
    "sofr_above_iorb": ["sofr_iorb_spread_bps"],
    "repo_corridor_pressure": ["sofr_iorb_spread_bps"],
    "rrp_buffer_low": ["net_liquidity_usd_millions"],
    "tga_high": ["net_liquidity_usd_millions"],
    "term_premium_pressure": ["ust_10y_yield_pct", "ust_10y_2y_curve_pct"],
    "deep_curve_inversion": ["ust_10y_2y_curve_pct"],
    "vix_elevated": ["vix"],
    "hy_oas_stress": ["hy_oas_pct"],
    "hy_oas_distress": ["hy_oas_pct"],
}


def build_macro_scenario(
    *,
    chain: Mapping[str, Any],
    panels: Mapping[str, Any],
    features: Mapping[str, Any],
    triggers: Sequence[Mapping[str, Any]],
    data_gaps: Sequence[str],
) -> dict[str, Any]:
    current_regime = _current_regime(chain=chain, panels=panels)
    confirmations = _confirmations(chain=chain, panels=panels, triggers=triggers)
    contradictions = _contradictions(chain=chain, panels=panels, current_regime=current_regime)
    watch_triggers = _watch_triggers(current_regime=current_regime, features=features, data_gaps=data_gaps)
    invalidations = _invalidations(current_regime)
    trade_map = _trade_map(current_regime)
    return {
        "current_regime": current_regime,
        "confidence": _confidence(
            chain=chain,
            confirmations=confirmations,
            contradictions=contradictions,
            current_regime=current_regime,
        ),
        "time_window": _time_window(current_regime),
        "confirmations": confirmations,
        "contradictions": contradictions,
        "watch_triggers": watch_triggers,
        "invalidations": invalidations,
        "trade_map": trade_map,
    }


def _current_regime(*, chain: Mapping[str, Any], panels: Mapping[str, Any]) -> str:
    if not _has_observed_chain(chain):
        return "data_gap"
    liquidity = _regime(chain, "liquidity")
    fed_corridor = _regime(chain, "fed_corridor")
    rates = _regime(chain, "rates")
    credit = _regime(chain, "credit") or _panel_regime(panels, "credit")
    volatility = _regime(chain, "volatility")
    cross_asset = _regime(chain, "cross_asset")

    if liquidity == "funding_stress" or fed_corridor == "corridor_pressure":
        return "funding_stress"
    if credit in {"low_quality_stress", "credit_led_derisking"}:
        return "credit_stress"
    if rates == "term_premium_pressure":
        return "term_premium_pressure"
    if liquidity == "tightening" or rates in {"front_end_tightening", "policy_tight_growth_scare"}:
        return "tightening"
    if liquidity == "easing" and cross_asset in {"risk_on_confirmation", "equity_context_available"}:
        return "risk_on_liquidity"
    if rates == "reflation" and volatility not in {"panic", "near_term_stress"}:
        return "reflation"
    return "neutral"


def _confirmations(
    *,
    chain: Mapping[str, Any],
    panels: Mapping[str, Any],
    triggers: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    confirmations: list[dict[str, Any]] = []
    for trigger in triggers:
        code = _text(trigger.get("code"))
        if not code:
            continue
        confirmations.append(
            {
                "code": code,
                "description": _text(trigger.get("description")),
                "indicator_keys": TRIGGER_INDICATORS.get(code, []),
                "value": _number(trigger.get("value")),
            }
        )

    chain_confirmations = (
        ("liquidity", {"funding_stress", "tightening"}, "liquidity_tightening"),
        ("fed_corridor", {"corridor_pressure"}, "fed_corridor_pressure"),
        ("rates", {"term_premium_pressure", "policy_tight_growth_scare"}, "rates_pressure"),
        ("volatility", {"near_term_stress", "panic"}, "volatility_stress"),
        ("credit", {"low_quality_stress", "credit_led_derisking"}, "credit_stress"),
        ("cross_asset", {"risk_off_confirmation"}, "cross_asset_risk_off"),
        ("positioning", {"crowded_risk_long", "defensive_short"}, "positioning_extreme"),
    )
    for node_key, regimes, code in chain_confirmations:
        node_regime = _regime(chain, node_key)
        if node_regime in regimes:
            confirmations.append(
                {
                    "code": code,
                    "node": node_key,
                    "regime": node_regime,
                    "evidence": _evidence(chain, node_key)[:3],
                }
            )

    if not _regime(chain, "credit") and _panel_regime(panels, "credit") in {
        "low_quality_stress",
        "credit_led_derisking",
    }:
        confirmations.append(
            {
                "code": "credit_stress",
                "node": "credit",
                "regime": _panel_regime(panels, "credit"),
                "evidence": _panel_evidence(panels, "credit")[:3],
            }
        )
    return _unique_items(confirmations, key_name="code")


def _contradictions(
    *,
    chain: Mapping[str, Any],
    panels: Mapping[str, Any],
    current_regime: str,
) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    volatility = _regime(chain, "volatility") or _panel_regime(panels, "volatility")
    credit = _regime(chain, "credit") or _panel_regime(panels, "credit")
    cross_asset = _regime(chain, "cross_asset") or _panel_regime(panels, "cross_asset")
    liquidity = _regime(chain, "liquidity")

    if current_regime in {"funding_stress", "tightening"}:
        if volatility == "carry":
            contradictions.append({"code": "volatility_carry", "node": "volatility"})
        if credit == "confirmed_risk_on":
            contradictions.append({"code": "credit_spreads_benign", "node": "credit"})
        if cross_asset == "risk_on_confirmation":
            contradictions.append({"code": "risk_assets_confirm_risk_on", "node": "cross_asset"})
    elif current_regime == "term_premium_pressure":
        if liquidity == "easing":
            contradictions.append({"code": "liquidity_easing", "node": "liquidity"})
        if volatility == "carry":
            contradictions.append({"code": "volatility_unconcerned", "node": "volatility"})
    elif current_regime == "risk_on_liquidity":
        if credit in {"low_quality_stress", "credit_led_derisking"}:
            contradictions.append({"code": "credit_stress", "node": "credit"})
        if volatility == "panic":
            contradictions.append({"code": "volatility_panic", "node": "volatility"})
    return contradictions


def _watch_triggers(
    *,
    current_regime: str,
    features: Mapping[str, Any],
    data_gaps: Sequence[str],
) -> list[dict[str, Any]]:
    if current_regime == "data_gap":
        return [
            {
                "code": "macro_core_coverage_recovers",
                "description": "Required macro-core observations arrive for the missing chain nodes.",
                "data_gap_count": len([gap for gap in data_gaps if gap]),
            }
        ]

    if current_regime in {"funding_stress", "tightening"}:
        watch: list[dict[str, Any]] = [
            {
                "code": "repo_pressure_persists_3d",
                "description": "SOFR remains above IORB across multiple observations.",
            },
            {
                "code": "hy_oas_widening_5d",
                "description": "HY OAS widens over five trading days.",
                "delta_5d": _feature_delta(features, "fred:BAMLH0A0HYM2", "5d"),
            },
            {
                "code": "vix_breaks_30",
                "description": "VIX moves from stress into panic territory.",
            },
        ]
        missing_equity_history = (
            _feature_delta(features, "fred:SP500", "20d") is None
            and _feature_delta(features, "stooq:spy.us", "20d") is None
        )
        if missing_equity_history:
            watch.append(
                {
                    "code": "risk_asset_confirmation_missing",
                    "description": "Equity proxy history is missing for risk-asset confirmation.",
                }
            )
        return watch

    if current_regime == "term_premium_pressure":
        return [
            {"code": "real_yield_breakout", "description": "10Y real yield keeps rising."},
            {"code": "breakevens_accelerate", "description": "Inflation compensation confirms the rates move."},
        ]
    if current_regime == "credit_stress":
        return [
            {"code": "hy_oas_distress", "description": "HY OAS crosses distress thresholds."},
            {"code": "hyg_underperforms_lqd", "description": "Credit beta underperforms quality credit."},
        ]
    if current_regime == "risk_on_liquidity":
        return [
            {"code": "liquidity_impulse_fades", "description": "Net liquidity stops improving."},
            {"code": "vix_reprices_higher", "description": "VIX rises back above carry regime."},
        ]
    return [{"code": "macro_regime_breakout", "description": "A chain node leaves neutral regime."}]


def _invalidations(current_regime: str) -> list[dict[str, Any]]:
    if current_regime in {"funding_stress", "tightening"}:
        return [
            {"code": "sofr_iorb_normalizes", "description": "SOFR trades back below or in line with IORB."},
            {"code": "hy_oas_tightens", "description": "HY OAS tightens enough to reject credit stress."},
            {"code": "vix_returns_to_carry", "description": "VIX falls back below 20."},
        ]
    if current_regime == "term_premium_pressure":
        return [
            {"code": "ten_year_yield_reverses", "description": "10Y yield loses the pressure threshold."},
            {"code": "real_yield_recedes", "description": "Real yield impulse fades."},
        ]
    if current_regime == "credit_stress":
        return [{"code": "credit_spreads_normalize", "description": "HY and IG OAS tighten together."}]
    if current_regime == "risk_on_liquidity":
        return [{"code": "liquidity_tightens", "description": "Liquidity node turns tightening or funding stress."}]
    return []


def _trade_map(current_regime: str) -> list[dict[str, Any]]:
    if current_regime in {"funding_stress", "tightening"}:
        return [
            {
                "expression": "risk_down_credit_sensitive",
                "time_window": "1w",
                "confirms_on": ["sofr_above_iorb", "hy_oas_widening_5d", "vix_breaks_30"],
                "invalidates_on": ["sofr_iorb_normalizes", "hy_oas_tightens", "vix_returns_to_carry"],
            }
        ]
    if current_regime == "term_premium_pressure":
        return [
            {
                "expression": "duration_pressure_quality_over_growth",
                "time_window": "2w",
                "confirms_on": ["real_yield_breakout", "breakevens_accelerate"],
                "invalidates_on": ["ten_year_yield_reverses", "real_yield_recedes"],
            }
        ]
    if current_regime == "credit_stress":
        return [
            {
                "expression": "credit_beta_underweight",
                "time_window": "1w",
                "confirms_on": ["hy_oas_distress", "hyg_underperforms_lqd"],
                "invalidates_on": ["credit_spreads_normalize"],
            }
        ]
    if current_regime == "risk_on_liquidity":
        return [
            {
                "expression": "risk_on_liquidity_beta",
                "time_window": "2w",
                "confirms_on": ["liquidity_impulse_persists"],
                "invalidates_on": ["liquidity_tightens", "vix_reprices_higher"],
            }
        ]
    return []


def _confidence(
    *,
    chain: Mapping[str, Any],
    confirmations: Sequence[Mapping[str, Any]],
    contradictions: Sequence[Mapping[str, Any]],
    current_regime: str,
) -> float:
    if current_regime == "data_gap":
        return 0.0
    observed_nodes = [
        node
        for node in chain.values()
        if isinstance(node, Mapping) and _text(node.get("regime")) not in {"", "data_gap"}
    ]
    if not observed_nodes:
        return 0.0
    scores = [_number(node.get("score")) or 0.0 for node in observed_nodes]
    coverage = min(1.0, len(observed_nodes) / CHAIN_NODE_COUNT)
    score_strength = min(1.0, (sum(scores) / len(scores)) / 10.0)
    confidence = 0.15 + 0.45 * coverage + 0.25 * score_strength
    confidence += min(0.2, len(confirmations) * 0.035)
    confidence -= min(0.25, len(contradictions) * 0.08)
    return round(max(0.0, min(0.98, confidence)), 2)


def _time_window(current_regime: str) -> str:
    if current_regime in {"funding_stress", "credit_stress"}:
        return "1w"
    if current_regime in {"term_premium_pressure", "tightening", "risk_on_liquidity", "reflation"}:
        return "2w"
    if current_regime == "data_gap":
        return "3d"
    return "1w"


def _has_observed_chain(chain: Mapping[str, Any]) -> bool:
    return any(
        isinstance(node, Mapping) and _text(node.get("regime")) not in {"", "data_gap"} for node in chain.values()
    )


def _regime(chain: Mapping[str, Any], node_key: str) -> str:
    node = chain.get(node_key)
    if not isinstance(node, Mapping):
        return ""
    return _text(node.get("regime"))


def _evidence(chain: Mapping[str, Any], node_key: str) -> list[str]:
    node = chain.get(node_key)
    if not isinstance(node, Mapping):
        return []
    evidence = node.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, str):
        return []
    return [_text(item) for item in evidence if _text(item)]


def _panel_regime(panels: Mapping[str, Any], panel_key: str) -> str:
    panel = panels.get(panel_key)
    if not isinstance(panel, Mapping):
        return ""
    return _text(panel.get("regime"))


def _panel_evidence(panels: Mapping[str, Any], panel_key: str) -> list[str]:
    panel = panels.get(panel_key)
    if not isinstance(panel, Mapping):
        return []
    evidence = panel.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, str):
        return []
    return [_text(item) for item in evidence if _text(item)]


def _feature_delta(features: Mapping[str, Any], series_key: str, horizon: str) -> float | None:
    feature = features.get(series_key)
    if not isinstance(feature, Mapping):
        return None
    deltas = feature.get("delta")
    if not isinstance(deltas, Mapping):
        return None
    return _number(deltas.get(horizon))


def _unique_items(items: Sequence[Mapping[str, Any]], *, key_name: str) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _text(item.get(key_name))
        if not key or key in unique:
            continue
        unique[key] = dict(item)
    return list(unique.values())


def _text(value: Any) -> str:
    return str(value or "")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["build_macro_scenario"]
