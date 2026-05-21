from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_VIEW_PROJECTION_VERSION

CORE_REQUIRED_SERIES = (
    "fred:WALCL",
    "fred:RRPONTSYD",
    "treasury_fiscal:operating_cash_balance",
    "nyfed:SOFR",
    "fred:IORB",
    "fred:DGS2",
    "fred:DGS10",
    "fred:VIXCLS",
    "fred:BAMLH0A0HYM2",
    "fred:BAMLC0A0CM",
)
OPTIONAL_CONFIRMATION_SERIES = ("fred:SP500", "fred:DEXUSEU", "fred:DCOILWTICO", "coingecko:bitcoin:usd")
PANEL_NAMES = ("liquidity", "rates", "volatility", "credit", "cross_asset")


def build_macro_view_snapshot(
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_at_ms: int,
) -> dict[str, Any]:
    latest = _latest_by_series(observations)
    panels, indicators, triggers, panel_gaps = _build_panels(latest)
    core_gaps = [f"missing:{series_key}" for series_key in CORE_REQUIRED_SERIES if series_key not in latest]
    data_gaps = _unique([*core_gaps, *panel_gaps])
    available_scores = [float(panel["score"]) for panel in panels.values() if panel.get("score") is not None]
    overall_score = round(sum(available_scores) / len(available_scores), 2) if available_scores else None
    status = _snapshot_status(latest=latest, data_gaps=data_gaps)
    asof_date = _asof_date(latest=latest, computed_at_ms=computed_at_ms)
    return {
        "snapshot_id": f"macro-view:{MACRO_VIEW_PROJECTION_VERSION}:{int(computed_at_ms)}",
        "projection_version": MACRO_VIEW_PROJECTION_VERSION,
        "asof_date": asof_date,
        "status": status,
        "regime": _overall_regime(panels=panels, status=status, overall_score=overall_score),
        "overall_score": overall_score,
        "panels_json": panels,
        "indicators_json": indicators,
        "triggers_json": triggers,
        "data_gaps_json": data_gaps,
        "source_coverage_json": _source_coverage(latest),
        "computed_at_ms": int(computed_at_ms),
    }


def _build_panels(
    latest: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    panels: dict[str, dict[str, Any]] = {}
    indicators: dict[str, dict[str, Any]] = {}
    triggers: list[dict[str, Any]] = []
    data_gaps: list[str] = []
    panels["liquidity"], panel_indicators, panel_triggers, panel_gaps = _liquidity_panel(latest)
    indicators.update(panel_indicators)
    triggers.extend(panel_triggers)
    data_gaps.extend(panel_gaps)
    panels["rates"], panel_indicators, panel_triggers, panel_gaps = _rates_panel(latest)
    indicators.update(panel_indicators)
    triggers.extend(panel_triggers)
    data_gaps.extend(panel_gaps)
    panels["volatility"], panel_indicators, panel_triggers, panel_gaps = _volatility_panel(latest)
    indicators.update(panel_indicators)
    triggers.extend(panel_triggers)
    data_gaps.extend(panel_gaps)
    panels["credit"], panel_indicators, panel_triggers, panel_gaps = _credit_panel(latest)
    indicators.update(panel_indicators)
    triggers.extend(panel_triggers)
    data_gaps.extend(panel_gaps)
    panels["cross_asset"], panel_indicators, panel_triggers, panel_gaps = _cross_asset_panel(latest, panels)
    indicators.update(panel_indicators)
    triggers.extend(panel_triggers)
    data_gaps.extend(panel_gaps)
    return panels, indicators, triggers, data_gaps


def _liquidity_panel(
    latest: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    indicators: dict[str, dict[str, Any]] = {}
    triggers: list[dict[str, Any]] = []
    data_gaps: list[str] = []
    walcl = _usd_millions(latest.get("fred:WALCL"))
    rrp = _usd_millions(latest.get("fred:RRPONTSYD"))
    tga = _usd_millions(latest.get("treasury_fiscal:operating_cash_balance"))
    sofr = _value(latest.get("nyfed:SOFR"))
    iorb = _value(latest.get("fred:IORB"))
    score = 4.0
    evidence: list[str] = []

    if walcl is None or rrp is None or tga is None:
        for series_key, value in (
            ("fred:WALCL", walcl),
            ("fred:RRPONTSYD", rrp),
            ("treasury_fiscal:operating_cash_balance", tga),
        ):
            if value is None:
                data_gaps.append(f"missing:{series_key}")
    else:
        net_liquidity = walcl - rrp - tga
        indicators["net_liquidity_usd_millions"] = _indicator(
            value=net_liquidity,
            unit="millions_usd",
            label="Fed net liquidity",
            observations=[
                latest["fred:WALCL"],
                latest["fred:RRPONTSYD"],
                latest["treasury_fiscal:operating_cash_balance"],
            ],
        )
        evidence.append(f"net_liquidity_usd_millions={net_liquidity:.0f}")
        if rrp <= 300_000:
            score += 1.0
            triggers.append(_trigger("rrp_buffer_low", "ON RRP buffer is below 300bn USD", rrp))
        if tga >= 800_000:
            score += 1.0
            triggers.append(_trigger("tga_high", "TGA is above 800bn USD", tga))

    if sofr is None or iorb is None:
        if sofr is None:
            data_gaps.append("missing:nyfed:SOFR")
        if iorb is None:
            data_gaps.append("missing:fred:IORB")
    else:
        spread_bps = (sofr - iorb) * 100.0
        indicators["sofr_iorb_spread_bps"] = _indicator(
            value=spread_bps,
            unit="bps",
            label="SOFR minus IORB",
            observations=[latest["nyfed:SOFR"], latest["fred:IORB"]],
        )
        evidence.append(f"sofr_iorb_spread_bps={spread_bps:.1f}")
        if spread_bps > 0:
            score += 2.0
            triggers.append(_trigger("sofr_above_iorb", "SOFR is above IORB", spread_bps))
        if spread_bps >= 10:
            score += 1.0
            triggers.append(_trigger("repo_corridor_pressure", "SOFR-IORB is at least 10 bps", spread_bps))

    final_score = _score(score) if evidence else None
    return (
        _panel(
            score=final_score,
            regime=_liquidity_regime(final_score),
            evidence=evidence,
            data_gaps=data_gaps,
        ),
        indicators,
        triggers,
        data_gaps,
    )


def _rates_panel(
    latest: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    indicators: dict[str, dict[str, Any]] = {}
    triggers: list[dict[str, Any]] = []
    data_gaps: list[str] = []
    dgs2 = _value(latest.get("fred:DGS2"))
    dgs10 = _value(latest.get("fred:DGS10"))
    score = 4.0
    evidence: list[str] = []
    if dgs2 is None:
        data_gaps.append("missing:fred:DGS2")
    if dgs10 is None:
        data_gaps.append("missing:fred:DGS10")
    if dgs2 is not None and dgs10 is not None:
        curve = dgs10 - dgs2
        indicators["ust_10y_2y_curve_pct"] = _indicator(
            value=curve,
            unit="percentage_points",
            label="10Y minus 2Y Treasury curve",
            observations=[latest["fred:DGS10"], latest["fred:DGS2"]],
        )
        indicators["ust_10y_yield_pct"] = _indicator(
            value=dgs10,
            unit="percent",
            label="10Y Treasury yield",
            observations=[latest["fred:DGS10"]],
        )
        evidence.append(f"10y={dgs10:.2f}")
        evidence.append(f"10y_2y_curve={curve:.2f}")
        if dgs10 >= 4.5 and curve >= 0.25:
            score += 3.0
            triggers.append(_trigger("term_premium_pressure", "10Y yield is high with a positive curve", dgs10))
        elif curve <= -0.5:
            score += 2.0
            triggers.append(_trigger("deep_curve_inversion", "10Y-2Y curve is deeply inverted", curve))
    final_score = _score(score) if evidence else None
    return (
        _panel(
            score=final_score,
            regime=_rates_regime(
                final_score=final_score,
                dgs10=dgs10,
                curve=(dgs10 - dgs2) if dgs2 and dgs10 else None,
            ),
            evidence=evidence,
            data_gaps=data_gaps,
        ),
        indicators,
        triggers,
        data_gaps,
    )


def _volatility_panel(
    latest: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    vix = _value(latest.get("fred:VIXCLS"))
    if vix is None:
        return (
            _panel(score=None, regime="data_gap", evidence=[], data_gaps=["missing:fred:VIXCLS"]),
            {},
            [],
            ["missing:fred:VIXCLS"],
        )
    indicators = {
        "vix": _indicator(
            value=vix,
            unit="index",
            label="VIX 30D implied volatility",
            observations=[latest["fred:VIXCLS"]],
        )
    }
    triggers: list[dict[str, Any]] = []
    if vix >= 20:
        triggers.append(_trigger("vix_elevated", "VIX is above 20", vix))
    score = 2.5 if vix < 20 else 7.0 if vix < 30 else 9.0
    regime = "carry" if vix < 20 else "near_term_stress" if vix < 30 else "panic"
    return _panel(score=score, regime=regime, evidence=[f"vix={vix:.1f}"], data_gaps=[]), indicators, triggers, []


def _credit_panel(
    latest: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    hy_oas = _value(latest.get("fred:BAMLH0A0HYM2"))
    ig_oas = _value(latest.get("fred:BAMLC0A0CM"))
    indicators: dict[str, dict[str, Any]] = {}
    triggers: list[dict[str, Any]] = []
    data_gaps: list[str] = []
    evidence: list[str] = []
    if hy_oas is None:
        data_gaps.append("missing:fred:BAMLH0A0HYM2")
    else:
        indicators["hy_oas_pct"] = _indicator(
            value=hy_oas,
            unit="percent",
            label="US HY OAS",
            observations=[latest["fred:BAMLH0A0HYM2"]],
        )
        evidence.append(f"hy_oas={hy_oas:.2f}")
    if ig_oas is None:
        data_gaps.append("missing:fred:BAMLC0A0CM")
    else:
        indicators["ig_oas_pct"] = _indicator(
            value=ig_oas,
            unit="percent",
            label="US corporate IG OAS",
            observations=[latest["fred:BAMLC0A0CM"]],
        )
        evidence.append(f"ig_oas={ig_oas:.2f}")
    if hy_oas is None:
        return (
            _panel(score=None, regime="data_gap", evidence=evidence, data_gaps=data_gaps),
            indicators,
            triggers,
            data_gaps,
        )
    if hy_oas >= 7:
        score = 9.0
        regime = "credit_led_derisking"
        triggers.append(_trigger("hy_oas_distress", "HY OAS is above 7%", hy_oas))
    elif hy_oas >= 5:
        score = 7.0
        regime = "low_quality_stress"
        triggers.append(_trigger("hy_oas_stress", "HY OAS is above 5%", hy_oas))
    elif hy_oas >= 3.5:
        score = 5.0
        regime = "watch"
    else:
        score = 3.0
        regime = "confirmed_risk_on"
    return _panel(score=score, regime=regime, evidence=evidence, data_gaps=data_gaps), indicators, triggers, data_gaps


def _cross_asset_panel(
    latest: Mapping[str, Mapping[str, Any]],
    panels: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    spx = _value(latest.get("fred:SP500"))
    if spx is None:
        synthetic_scores = [
            float(panel["score"])
            for key, panel in panels.items()
            if key in {"liquidity", "volatility", "credit"} and panel.get("score") is not None
        ]
        score = round(sum(synthetic_scores) / len(synthetic_scores), 2) if synthetic_scores else None
        regime = "macro_confirmation_pending" if score is not None else "data_gap"
        return (
            _panel(
                score=score,
                regime=regime,
                evidence=["risk_asset_confirmation_missing"] if score is not None else [],
                data_gaps=["missing:fred:SP500"],
            ),
            {},
            [],
            ["missing:fred:SP500"],
        )
    indicators = {
        "sp500_index": _indicator(
            value=spx,
            unit="index",
            label="S&P 500 index",
            observations=[latest["fred:SP500"]],
        )
    }
    return (
        _panel(
            score=4.0,
            regime="equity_context_available",
            evidence=[f"sp500={spx:.1f}"],
            data_gaps=[],
        ),
        indicators,
        [],
        [],
    )


def _panel(*, score: float | None, regime: str, evidence: list[str], data_gaps: list[str]) -> dict[str, Any]:
    return {
        "score": None if score is None else round(float(score), 2),
        "regime": regime,
        "evidence": evidence,
        "data_gaps": _unique(data_gaps),
    }


def _liquidity_regime(score: float | None) -> str:
    if score is None:
        return "data_gap"
    if score >= 8:
        return "funding_stress"
    if score >= 6:
        return "tightening"
    if score <= 3:
        return "easing"
    return "neutral"


def _rates_regime(*, final_score: float | None, dgs10: float | None, curve: float | None) -> str:
    if final_score is None:
        return "data_gap"
    if dgs10 is not None and curve is not None and dgs10 >= 4.5 and curve >= 0.25:
        return "term_premium_pressure"
    if curve is not None and curve <= -0.5:
        return "policy_tight_growth_scare"
    return "neutral"


def _overall_regime(
    *,
    panels: Mapping[str, Mapping[str, Any]],
    status: str,
    overall_score: float | None,
) -> str:
    if status == "empty" or overall_score is None:
        return "data_gap"
    if panels["liquidity"]["regime"] == "funding_stress":
        return "funding_stress"
    if panels["credit"]["regime"] in {"low_quality_stress", "credit_led_derisking"}:
        return "credit_stress"
    if panels["rates"]["regime"] == "term_premium_pressure":
        return "term_premium_pressure"
    if overall_score >= 7:
        return "tightening"
    if overall_score <= 3:
        return "risk_on_liquidity"
    return "neutral"


def _snapshot_status(*, latest: Mapping[str, Mapping[str, Any]], data_gaps: Sequence[str]) -> str:
    if not latest:
        return "empty"
    if data_gaps:
        return "partial"
    return "ready"


def _source_coverage(latest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    observed_core = sum(1 for series_key in CORE_REQUIRED_SERIES if series_key in latest)
    latest_observed_at = None
    if latest:
        latest_observed_at = max(str(observation.get("observed_at") or "") for observation in latest.values())
    return {
        "observed_series_count": observed_core,
        "required_series_count": len(CORE_REQUIRED_SERIES),
        "coverage_ratio": round(observed_core / len(CORE_REQUIRED_SERIES), 4),
        "latest_observed_at": latest_observed_at,
    }


def _latest_by_series(observations: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for observation in observations:
        series_key = str(observation.get("series_key") or "").strip()
        if not series_key:
            continue
        previous = latest.get(series_key)
        if previous is None or _sort_key(observation) > _sort_key(previous):
            latest[series_key] = observation
    return latest


def _sort_key(observation: Mapping[str, Any]) -> tuple[str, str]:
    return (str(observation.get("observed_at") or ""), str(observation.get("source_ts") or ""))


def _asof_date(*, latest: Mapping[str, Mapping[str, Any]], computed_at_ms: int) -> str:
    if latest:
        return max(str(observation.get("observed_at") or "") for observation in latest.values())
    return datetime.fromtimestamp(int(computed_at_ms) / 1000, tz=UTC).date().isoformat()


def _value(observation: Mapping[str, Any] | None) -> float | None:
    if observation is None:
        return None
    value = observation.get("value_numeric")
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usd_millions(observation: Mapping[str, Any] | None) -> float | None:
    value = _value(observation)
    if value is None:
        return None
    unit = str(observation.get("unit") or "").lower() if observation is not None else ""
    if unit == "billions_usd":
        return value * 1000.0
    return value


def _indicator(
    *,
    value: float,
    unit: str,
    label: str,
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "label": label,
        "value": round(float(value), 4),
        "unit": unit,
        "observed_at": max(str(observation.get("observed_at") or "") for observation in observations),
        "sources": sorted({str(observation.get("source_name") or "") for observation in observations}),
        "series_keys": [str(observation.get("series_key") or "") for observation in observations],
    }


def _trigger(code: str, description: str, value: float) -> dict[str, Any]:
    return {"code": code, "description": description, "value": round(float(value), 4)}


def _score(value: float) -> float:
    return round(max(0.0, min(10.0, float(value))), 2)


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


__all__ = ["CORE_REQUIRED_SERIES", "build_macro_view_snapshot"]
