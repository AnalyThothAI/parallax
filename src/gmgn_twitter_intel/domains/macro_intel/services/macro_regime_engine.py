from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CORE_SERIES, MACRO_VIEW_PROJECTION_VERSION
from gmgn_twitter_intel.domains.macro_intel.services.macro_feature_engine import build_macro_features
from gmgn_twitter_intel.domains.macro_intel.services.macro_scenario_engine import build_macro_scenario

CORE_REQUIRED_SERIES = MACRO_CORE_SERIES
OPTIONAL_CONFIRMATION_SERIES = ("fred:SP500", "fred:DEXUSEU", "fred:DCOILWTICO")
PANEL_NAMES = ("liquidity", "rates", "volatility", "credit", "cross_asset")
CHAIN_NODE_NAMES = ("liquidity", "rates", "fed_corridor", "volatility", "credit", "positioning", "cross_asset")


def build_macro_view_snapshot(
    observations: Sequence[Mapping[str, Any]],
    *,
    computed_at_ms: int,
) -> dict[str, Any]:
    latest = _latest_by_series(observations)
    features = build_macro_features(observations, computed_at_ms=computed_at_ms)
    panels, indicators, triggers, panel_gaps = _build_panels(latest)
    chain = _build_chain(latest=latest, panels=panels, features=features)
    core_gaps = [f"missing:{series_key}" for series_key in CORE_REQUIRED_SERIES if series_key not in latest]
    data_gaps = _unique([*core_gaps, *panel_gaps])
    available_scores = [float(panel["score"]) for panel in panels.values() if panel.get("score") is not None]
    overall_score = round(sum(available_scores) / len(available_scores), 2) if available_scores else None
    status = _snapshot_status(latest=latest, data_gaps=data_gaps)
    asof_date = _asof_date(latest=latest, computed_at_ms=computed_at_ms)
    scenario = build_macro_scenario(
        chain=chain,
        panels=panels,
        features=features,
        triggers=triggers,
        data_gaps=data_gaps,
    )
    coverage = _source_coverage(latest)
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
        "source_coverage_json": coverage,
        "features_json": features,
        "chain_json": chain,
        "scenario_json": scenario,
        "scorecard_json": _scorecard(
            overall_score=overall_score,
            chain=chain,
            coverage=coverage,
            data_gaps=data_gaps,
        ),
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


def _build_chain(
    *,
    latest: Mapping[str, Mapping[str, Any]],
    panels: Mapping[str, Mapping[str, Any]],
    features: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        "liquidity": _liquidity_chain_node(latest=latest, panel=panels.get("liquidity", {}), features=features),
        "rates": _rates_chain_node(latest=latest, panel=panels.get("rates", {}), features=features),
        "fed_corridor": _fed_corridor_chain_node(latest=latest),
        "volatility": _volatility_chain_node(panel=panels.get("volatility", {}), features=features),
        "credit": _credit_chain_node(latest=latest, panel=panels.get("credit", {}), features=features),
        "positioning": _positioning_chain_node(latest=latest, features=features),
        "cross_asset": _cross_asset_chain_node(latest=latest, panel=panels.get("cross_asset", {}), features=features),
    }


def _liquidity_chain_node(
    *,
    latest: Mapping[str, Mapping[str, Any]],
    panel: Mapping[str, Any],
    features: Mapping[str, Any],
) -> dict[str, Any]:
    score = _panel_score(panel, default=4.0)
    evidence = _panel_strings(panel, "evidence")
    data_gaps = _panel_strings(panel, "data_gaps")

    walcl_20d = _feature_delta(features, "fred:WALCL", "20d")
    rrp_20d = _feature_delta(features, "fred:RRPONTSYD", "20d")
    tga_20d = _feature_delta(features, "treasury_fiscal:operating_cash_balance", "20d")
    if walcl_20d is not None:
        evidence.append(f"walcl_20d_delta={walcl_20d:.2f}")
        if walcl_20d <= -100_000:
            score += 0.75
    if rrp_20d is not None:
        evidence.append(f"rrp_20d_delta={rrp_20d:.2f}")
        if rrp_20d <= -100_000:
            score += 0.5
    if tga_20d is not None:
        evidence.append(f"tga_20d_delta={tga_20d:.2f}")
        if tga_20d >= 100_000:
            score += 0.75

    if not evidence:
        return _chain_node(score=None, regime="data_gap", evidence=[], data_gaps=data_gaps)
    return _chain_node(
        score=score,
        regime=_liquidity_regime(_score(score)),
        evidence=evidence,
        data_gaps=data_gaps,
    )


def _rates_chain_node(
    *,
    latest: Mapping[str, Mapping[str, Any]],
    panel: Mapping[str, Any],
    features: Mapping[str, Any],
) -> dict[str, Any]:
    score = 4.0
    evidence = _panel_strings(panel, "evidence")
    data_gaps = _panel_strings(panel, "data_gaps")
    dgs2 = _value(latest.get("fred:DGS2"))
    dgs10 = _value(latest.get("fred:DGS10"))
    curve_10y_2y = _value(latest.get("fred:T10Y2Y"))
    if curve_10y_2y is None and dgs2 is not None and dgs10 is not None:
        curve_10y_2y = dgs10 - dgs2
    curve_10y_3m = _value(latest.get("fred:T10Y3M"))
    real_10y = _value(latest.get("fred:DFII10"))
    breakeven_10y = _value(latest.get("fred:T10YIE"))
    forward_inflation = _value(latest.get("fred:T5YIFR"))
    dgs10_20d = _feature_delta(features, "fred:DGS10", "20d")
    dgs2_20d = _feature_delta(features, "fred:DGS2", "20d")

    missing_series = (
        ("fred:DGS5", _value(latest.get("fred:DGS5"))),
        ("fred:DGS30", _value(latest.get("fred:DGS30"))),
        ("fred:T10Y3M", curve_10y_3m),
        ("fred:DFII10", real_10y),
        ("fred:T10YIE", breakeven_10y),
        ("fred:T5YIFR", forward_inflation),
    )
    data_gaps.extend(f"missing:{series_key}" for series_key, value in missing_series if value is None)

    if dgs10 is not None:
        evidence.append(f"10y={dgs10:.2f}")
        if dgs10 >= 4.5:
            score += 1.5
    if curve_10y_2y is not None:
        evidence.append(f"10y_2y_curve={curve_10y_2y:.2f}")
        if curve_10y_2y <= -0.5:
            score += 1.5
        elif dgs10 is not None and dgs10 >= 4.5 and curve_10y_2y >= 0.25:
            score += 1.0
    if real_10y is not None:
        evidence.append(f"real_10y={real_10y:.2f}")
        if real_10y >= 2.0:
            score += 1.0
    if breakeven_10y is not None:
        evidence.append(f"breakeven_10y={breakeven_10y:.2f}")
        if breakeven_10y >= 2.5:
            score += 0.5
    if forward_inflation is not None:
        evidence.append(f"forward_inflation_5y5y={forward_inflation:.2f}")
        if forward_inflation >= 2.5:
            score += 0.5
    if dgs10_20d is not None:
        evidence.append(f"dgs10_20d_delta={dgs10_20d:.2f}")
        if dgs10_20d >= 0.25:
            score += 1.0
    if dgs2_20d is not None:
        evidence.append(f"dgs2_20d_delta={dgs2_20d:.2f}")
        if dgs2_20d >= 0.25:
            score += 0.5

    if not evidence:
        return _chain_node(score=None, regime="data_gap", evidence=[], data_gaps=data_gaps)
    return _chain_node(
        score=score,
        regime=_rates_chain_regime(score=_score(score), dgs10=dgs10, curve=curve_10y_2y, real_10y=real_10y),
        evidence=evidence,
        data_gaps=data_gaps,
    )


def _fed_corridor_chain_node(*, latest: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    sofr = _value(latest.get("nyfed:SOFR"))
    iorb = _value(latest.get("fred:IORB"))
    effr = _value(latest.get("fred:EFFR"))
    target_upper = _value(latest.get("fred:DFEDTARU"))
    target_lower = _value(latest.get("fred:DFEDTARL"))
    evidence: list[str] = []
    data_gaps: list[str] = []
    score = 4.0

    for series_key, value in (
        ("nyfed:SOFR", sofr),
        ("fred:IORB", iorb),
        ("fred:EFFR", effr),
        ("fred:DFEDTARU", target_upper),
        ("fred:DFEDTARL", target_lower),
    ):
        if value is None:
            data_gaps.append(f"missing:{series_key}")

    if sofr is not None and iorb is not None:
        spread_bps = (sofr - iorb) * 100.0
        evidence.append(f"sofr_iorb_spread_bps={spread_bps:.1f}")
        if spread_bps > 0:
            score += 2.0
        if spread_bps >= 10:
            score += 1.0
    if effr is not None and iorb is not None:
        spread_bps = (effr - iorb) * 100.0
        evidence.append(f"effr_iorb_spread_bps={spread_bps:.1f}")
        if spread_bps > 0:
            score += 1.0
    if target_upper is not None and target_lower is not None:
        evidence.append(f"fed_target_range={target_lower:.2f}-{target_upper:.2f}")
        if sofr is not None and sofr > target_upper:
            score += 1.5
            evidence.append("sofr_above_target_upper")
        if effr is not None and not target_lower <= effr <= target_upper:
            score += 1.0
            evidence.append("effr_outside_target_range")

    if not evidence:
        return _chain_node(score=None, regime="data_gap", evidence=[], data_gaps=data_gaps)
    return _chain_node(
        score=score,
        regime="corridor_pressure" if score >= 7.0 else "watch" if score >= 5.5 else "orderly",
        evidence=evidence,
        data_gaps=data_gaps,
    )


def _volatility_chain_node(*, panel: Mapping[str, Any], features: Mapping[str, Any]) -> dict[str, Any]:
    score = _panel_score(panel, default=0.0)
    evidence = _panel_strings(panel, "evidence")
    data_gaps = _panel_strings(panel, "data_gaps")
    vix_5d = _feature_delta(features, "fred:VIXCLS", "5d")
    vix_20d = _feature_delta(features, "fred:VIXCLS", "20d")
    if vix_5d is not None:
        evidence.append(f"vix_5d_delta={vix_5d:.2f}")
        if vix_5d >= 3.0:
            score += 0.75
    if vix_20d is not None:
        evidence.append(f"vix_20d_delta={vix_20d:.2f}")
        if vix_20d >= 5.0:
            score += 0.75

    if not evidence:
        return _chain_node(score=None, regime="data_gap", evidence=[], data_gaps=data_gaps)
    final_score = _score(score)
    return _chain_node(
        score=final_score,
        regime="panic" if final_score >= 8.5 else "near_term_stress" if final_score >= 6.0 else "carry",
        evidence=evidence,
        data_gaps=data_gaps,
    )


def _credit_chain_node(
    *,
    latest: Mapping[str, Mapping[str, Any]],
    panel: Mapping[str, Any],
    features: Mapping[str, Any],
) -> dict[str, Any]:
    score = _panel_score(panel, default=0.0)
    evidence = _panel_strings(panel, "evidence")
    data_gaps = _panel_strings(panel, "data_gaps")
    hy_oas = _value(latest.get("fred:BAMLH0A0HYM2"))
    ig_oas = _value(latest.get("fred:BAMLC0A0CM"))
    hy_5d = _feature_delta(features, "fred:BAMLH0A0HYM2", "5d")
    hy_20d = _feature_delta(features, "fred:BAMLH0A0HYM2", "20d")
    ig_20d = _feature_delta(features, "fred:BAMLC0A0CM", "20d")

    if hy_oas is not None and ig_oas is not None:
        hy_ig_spread = hy_oas - ig_oas
        evidence.append(f"hy_ig_spread={hy_ig_spread:.2f}")
        if hy_ig_spread >= 4.0:
            score += 0.75
    if hy_5d is not None:
        evidence.append(f"hy_oas_5d_delta={hy_5d:.2f}")
        if hy_5d >= 0.25:
            score += 0.75
    if hy_20d is not None:
        evidence.append(f"hy_oas_20d_delta={hy_20d:.2f}")
        if hy_20d >= 0.5:
            score += 0.75
    if ig_20d is not None:
        evidence.append(f"ig_oas_20d_delta={ig_20d:.2f}")
        if ig_20d >= 0.2:
            score += 0.5

    if not evidence:
        return _chain_node(score=None, regime="data_gap", evidence=[], data_gaps=data_gaps)
    final_score = _score(score)
    if (hy_oas is not None and hy_oas >= 7.0) or final_score >= 8.5:
        regime = "credit_led_derisking"
    elif (hy_oas is not None and hy_oas >= 5.0) or final_score >= 6.5:
        regime = "low_quality_stress"
    elif final_score <= 3.5:
        regime = "confirmed_risk_on"
    else:
        regime = "watch"
    return _chain_node(score=final_score, regime=regime, evidence=evidence, data_gaps=data_gaps)


def _positioning_chain_node(
    *,
    latest: Mapping[str, Mapping[str, Any]],
    features: Mapping[str, Any],
) -> dict[str, Any]:
    series_key = "cftc:financial_futures:sp500_net_noncommercial"
    value = _value(latest.get(series_key))
    if value is None:
        return _chain_node(
            score=None,
            regime="data_gap",
            evidence=[],
            data_gaps=[f"missing:{series_key}", "positioning_data_gap"],
        )
    evidence = [f"sp500_net_noncommercial={value:.2f}"]
    score = 5.0
    percentile = _feature_percentile(features, series_key)
    value_20d = _feature_delta(features, series_key, "20d")
    if percentile is not None:
        evidence.append(f"positioning_percentile={percentile:.2f}")
        if percentile >= 0.8:
            score += 1.5
        elif percentile <= 0.2:
            score += 1.0
    if value_20d is not None:
        evidence.append(f"positioning_20d_delta={value_20d:.2f}")
        if abs(value_20d) >= 25_000:
            score += 0.5
    if value > 0 and percentile is not None and percentile >= 0.8:
        regime = "crowded_risk_long"
    elif value < 0 and percentile is not None and percentile <= 0.2:
        regime = "defensive_short"
    else:
        regime = "neutral"
    return _chain_node(score=score, regime=regime, evidence=evidence, data_gaps=[])


def _cross_asset_chain_node(
    *,
    latest: Mapping[str, Mapping[str, Any]],
    panel: Mapping[str, Any],
    features: Mapping[str, Any],
) -> dict[str, Any]:
    score = _panel_score(panel, default=4.0)
    evidence = _panel_strings(panel, "evidence")
    data_gaps = _panel_strings(panel, "data_gaps")
    spx = _first_value(latest, ("fred:SP500", "stooq:spy.us"))
    qqq = _value(latest.get("stooq:qqq.us"))
    iwm = _value(latest.get("stooq:iwm.us"))
    hyg = _value(latest.get("stooq:hyg.us"))
    lqd = _value(latest.get("stooq:lqd.us"))
    dxy = _value(latest.get("fred:DTWEXBGS"))
    oil = _first_value(latest, ("fred:DCOILWTICO", "stooq:uso.us"))
    risk_off_votes = 0
    risk_on_votes = 0

    for label, value in (
        ("sp500", spx),
        ("qqq", qqq),
        ("iwm", iwm),
        ("hyg", hyg),
        ("lqd", lqd),
        ("dollar_index", dxy),
        ("oil", oil),
    ):
        if value is not None:
            evidence.append(f"{label}={value:.2f}")

    delta_votes = (
        ("sp500_20d_delta", _first_feature_delta(features, ("fred:SP500", "stooq:spy.us"), "20d"), -1),
        ("qqq_20d_delta", _feature_delta(features, "stooq:qqq.us", "20d"), -1),
        ("iwm_20d_delta", _feature_delta(features, "stooq:iwm.us", "20d"), -1),
        ("hyg_20d_delta", _feature_delta(features, "stooq:hyg.us", "20d"), -1),
        ("dollar_20d_delta", _feature_delta(features, "fred:DTWEXBGS", "20d"), 1),
    )
    for label, delta, risk_off_sign in delta_votes:
        if delta is None:
            continue
        evidence.append(f"{label}={delta:.2f}")
        if delta * risk_off_sign > 0:
            risk_off_votes += 1
        elif delta * risk_off_sign < 0:
            risk_on_votes += 1

    if hyg is not None and lqd is not None:
        hyg_lqd_ratio = hyg / lqd if lqd else 0.0
        evidence.append(f"hyg_lqd_ratio={hyg_lqd_ratio:.4f}")

    for series_key, value in (
        ("fred:SP500|stooq:spy.us", spx),
        ("stooq:hyg.us", hyg),
        ("stooq:lqd.us", lqd),
        ("fred:DTWEXBGS", dxy),
    ):
        if value is None:
            data_gaps.append(f"missing:{series_key}")

    if not evidence:
        return _chain_node(score=None, regime="data_gap", evidence=[], data_gaps=data_gaps)
    if risk_off_votes >= 2:
        score = max(score, 6.5 + min(2.0, risk_off_votes * 0.5))
        regime = "risk_off_confirmation"
    elif risk_on_votes >= 2:
        score = min(score, 3.0)
        regime = "risk_on_confirmation"
    else:
        regime = _panel_regime(panel, default="macro_confirmation_pending")
    return _chain_node(score=score, regime=regime, evidence=evidence, data_gaps=data_gaps)


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


def _scorecard(
    *,
    overall_score: float | None,
    chain: Mapping[str, Mapping[str, Any]],
    coverage: Mapping[str, Any],
    data_gaps: Sequence[str],
) -> dict[str, Any]:
    chain_scores = [
        float(node["score"])
        for node in chain.values()
        if node.get("regime") != "data_gap" and node.get("score") is not None
    ]
    chain_average = round(sum(chain_scores) / len(chain_scores), 2) if chain_scores else None
    return {
        "projection_version": MACRO_VIEW_PROJECTION_VERSION,
        "overall_score": overall_score,
        "chain_average": chain_average,
        "observed_series_count": int(coverage.get("observed_series_count") or 0),
        "required_series_count": int(coverage.get("required_series_count") or len(CORE_REQUIRED_SERIES)),
        "coverage_ratio": float(coverage.get("coverage_ratio") or 0.0),
        "data_gap_count": len([gap for gap in data_gaps if gap]),
        "chain_regimes": {node_key: str(node.get("regime") or "") for node_key, node in chain.items()},
    }


def _chain_node(
    *,
    score: float | None,
    regime: str,
    evidence: Sequence[str],
    data_gaps: Sequence[str],
) -> dict[str, Any]:
    return {
        "score": 0.0 if score is None else _score(score),
        "regime": regime,
        "evidence": _unique([str(item) for item in evidence]),
        "data_gaps": _unique([str(item) for item in data_gaps]),
    }


def _rates_chain_regime(
    *,
    score: float,
    dgs10: float | None,
    curve: float | None,
    real_10y: float | None,
) -> str:
    if dgs10 is not None and dgs10 >= 4.5 and score >= 6.5:
        return "term_premium_pressure"
    if real_10y is not None and real_10y >= 2.0 and score >= 6.5:
        return "term_premium_pressure"
    if curve is not None and curve <= -0.5:
        return "policy_tight_growth_scare"
    if score >= 6.5:
        return "front_end_tightening"
    if score <= 3.0:
        return "easing"
    return "neutral"


def _panel_score(panel: Mapping[str, Any], *, default: float) -> float:
    value = _float_value(panel.get("score"))
    return default if value is None else value


def _panel_strings(panel: Mapping[str, Any], key: str) -> list[str]:
    value = panel.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [str(item) for item in value if str(item)]


def _panel_regime(panel: Mapping[str, Any], *, default: str) -> str:
    value = str(panel.get("regime") or "")
    return value or default


def _feature_delta(features: Mapping[str, Any], series_key: str, horizon: str) -> float | None:
    feature = features.get(series_key)
    if not isinstance(feature, Mapping):
        return None
    delta = feature.get("delta")
    if not isinstance(delta, Mapping):
        return None
    return _float_value(delta.get(horizon))


def _first_feature_delta(features: Mapping[str, Any], series_keys: Sequence[str], horizon: str) -> float | None:
    for series_key in series_keys:
        value = _feature_delta(features, series_key, horizon)
        if value is not None:
            return value
    return None


def _feature_percentile(features: Mapping[str, Any], series_key: str) -> float | None:
    feature = features.get(series_key)
    if not isinstance(feature, Mapping):
        return None
    percentile = feature.get("percentile")
    if not isinstance(percentile, Mapping):
        return None
    return _float_value(percentile.get("value"))


def _first_value(latest: Mapping[str, Mapping[str, Any]], series_keys: Sequence[str]) -> float | None:
    for series_key in series_keys:
        value = _value(latest.get(series_key))
        if value is not None:
            return value
    return None


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
    return _float_value(value)


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
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
