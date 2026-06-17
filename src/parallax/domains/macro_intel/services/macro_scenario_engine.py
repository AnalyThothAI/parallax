from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps

CHAIN_NODE_COUNT = 7

FEATURE_CHANGE_SPECS = (
    {"concept_key": "fx:dxy", "label": "美元指数", "node": "cross_asset"},
    {"concept_key": "rates:dgs10", "label": "10Y 国债收益率", "node": "rates"},
    {"concept_key": "credit:hy_oas", "label": "高收益债 OAS", "node": "credit"},
    {"concept_key": "vol:vix", "label": "VIX", "node": "volatility"},
    {"concept_key": "asset:spx", "label": "标普500", "node": "cross_asset"},
    {"concept_key": "asset:tlt", "label": "长债 ETF", "node": "rates"},
    {"concept_key": "commodity:wti_futures", "label": "WTI 原油", "node": "cross_asset"},
    {"concept_key": "crypto:btc", "label": "比特币", "node": "cross_asset"},
)

SOURCE_LABELS = {
    "fred": "FRED",
    "yahoo": "Yahoo Finance",
}

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
    top_changes = _top_changes(triggers=triggers, features=features)
    quality_blockers = _quality_blockers(data_gaps)
    scenario_cases = _scenario_cases(current_regime)
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
        "top_changes": top_changes,
        "quality_blockers": quality_blockers,
        "scenario_cases": scenario_cases,
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
        label = _text(trigger.get("label")) or _code_label(code)
        if not label:
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
                "time_window": "24h",
                "severity": "high",
            }
        ]

    if current_regime in {"funding_stress", "tightening"}:
        watch: list[dict[str, Any]] = [
            {
                "code": "repo_pressure_persists_3d",
                "description": "SOFR remains above IORB across multiple observations.",
                "time_window": "24h",
                "severity": "high",
            },
            {
                "code": "hy_oas_widening_5d",
                "description": "HY OAS widens over five trading days.",
                "delta_5d": _feature_delta(features, "credit:hy_oas", "5d"),
                "time_window": "72h",
                "severity": "high",
            },
            {
                "code": "vix_breaks_30",
                "description": "VIX moves from stress into panic territory.",
                "time_window": "72h",
                "severity": "medium",
            },
        ]
        missing_equity_history = (
            _feature_delta(features, "asset:spx", "20d") is None
            and _feature_delta(features, "asset:spy", "20d") is None
        )
        if missing_equity_history:
            watch.append(
                {
                    "code": "risk_asset_confirmation_missing",
                    "description": "Equity proxy history is missing for risk-asset confirmation.",
                    "time_window": "72h",
                    "severity": "medium",
                }
            )
        return watch

    if current_regime == "term_premium_pressure":
        return [
            {
                "code": "real_yield_breakout",
                "description": "10Y real yield keeps rising.",
                "time_window": "24h",
                "severity": "high",
            },
            {
                "code": "breakevens_accelerate",
                "description": "Inflation compensation confirms the rates move.",
                "time_window": "72h",
                "severity": "medium",
            },
        ]
    if current_regime == "credit_stress":
        return [
            {
                "code": "hy_oas_distress",
                "description": "HY OAS crosses distress thresholds.",
                "time_window": "24h",
                "severity": "high",
            },
            {
                "code": "hyg_underperforms_lqd",
                "description": "Credit beta underperforms quality credit.",
                "time_window": "72h",
                "severity": "medium",
            },
        ]
    if current_regime == "risk_on_liquidity":
        return [
            {
                "code": "liquidity_impulse_fades",
                "description": "Net liquidity stops improving.",
                "time_window": "72h",
                "severity": "medium",
            },
            {
                "code": "vix_reprices_higher",
                "description": "VIX rises back above carry regime.",
                "time_window": "72h",
                "severity": "medium",
            },
        ]
    return [
        {
            "code": "macro_regime_breakout",
            "description": "A chain node leaves neutral regime.",
            "time_window": "72h",
            "severity": "medium",
        }
    ]


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
                "legs": _trade_legs("risk_down_credit_sensitive"),
            }
        ]
    if current_regime == "term_premium_pressure":
        return [
            {
                "expression": "duration_pressure_quality_over_growth",
                "time_window": "2w",
                "confirms_on": ["real_yield_breakout", "breakevens_accelerate"],
                "invalidates_on": ["ten_year_yield_reverses", "real_yield_recedes"],
                "legs": _trade_legs("duration_pressure_quality_over_growth"),
            }
        ]
    if current_regime == "credit_stress":
        return [
            {
                "expression": "credit_beta_underweight",
                "time_window": "1w",
                "confirms_on": ["hy_oas_distress", "hyg_underperforms_lqd"],
                "invalidates_on": ["credit_spreads_normalize"],
                "legs": _trade_legs("credit_beta_underweight"),
            }
        ]
    if current_regime == "risk_on_liquidity":
        return [
            {
                "expression": "risk_on_liquidity_beta",
                "time_window": "2w",
                "confirms_on": ["liquidity_impulse_persists"],
                "invalidates_on": ["liquidity_tightens", "vix_reprices_higher"],
                "legs": _trade_legs("risk_on_liquidity_beta"),
            }
        ]
    return []


def _trade_legs(expression: str) -> list[dict[str, str]]:
    legs = {
        "risk_down_credit_sensitive": [
            ("cash_short_bills", "现金/短债", "BIL", "做多/防守"),
            ("nasdaq", "纳斯达克", "QQQ", "回避/做空代理"),
            ("high_yield_credit", "高收益信用", "HYG", "低配"),
        ],
        "duration_pressure_quality_over_growth": [
            ("cash_short_bills", "现金/短债", "BIL", "做多/防守"),
            ("long_duration", "长久期美债", "TLT", "低配"),
            ("growth_equity", "成长股", "QQQ", "回避"),
        ],
        "credit_beta_underweight": [
            ("cash_short_bills", "现金/短债", "BIL", "做多/防守"),
            ("high_yield_credit", "高收益信用", "HYG", "低配"),
            ("quality_credit", "高质量信用", "LQD", "相对防守"),
        ],
        "risk_on_liquidity_beta": [
            ("equity_beta", "标普500", "SPY", "做多"),
            ("growth_equity", "纳斯达克", "QQQ", "做多"),
            ("bitcoin", "比特币", "BTC", "观察/顺势"),
        ],
    }.get(expression, [])
    return [
        {"asset": asset, "label": label, "symbol": symbol, "action": action} for asset, label, symbol, action in legs
    ]


def _scenario_cases(current_regime: str) -> list[dict[str, Any]]:
    if current_regime == "data_gap":
        return []
    if current_regime in {"funding_stress", "tightening"}:
        return _scenario_case_set(
            base={
                "thesis": "资金压力维持，信用 beta 继续承压，风险资产反弹先按减仓处理。",
                "trade": "防守：做多/持有 BIL，低配 QQQ 与 HYG。",
                "entry_condition": "SOFR-IORB 仍为正且 HY OAS 5日继续走阔。",
                "stop": "SOFR 回到 IORB 附近且 HY OAS 明显收窄。",
                "invalidation": "若 VIX 回到 carry 区且信用利差同步收窄，资金压力情景降级。",
            },
            upside={
                "thesis": "流动性压力快速缓和，信用没有继续恶化，风险资产获得技术性修复窗口。",
                "trade": "仅在确认后回补 SPY/QQQ beta，避免提前抢跑。",
                "entry_condition": "SOFR-IORB 正常化、HY OAS 收窄且 VIX 低于 20。",
                "stop": "任一资金或信用确认重新转弱。",
                "invalidation": "若 repo 压力延续 3 日或 HY OAS 重新走阔，乐观情景失效。",
            },
            downside={
                "thesis": "资金压力传导到信用与波动率，风险资产进入去杠杆。",
                "trade": "提高现金/短债，继续低配 HYG 与 QQQ，可用 VIX 上行作为保护确认。",
                "entry_condition": "HY OAS 进入困境区或 VIX 突破 30。",
                "stop": "信用利差收窄且 VIX 回落到 20 以下。",
                "invalidation": "若净流动性转正且信用利差未扩张，悲观情景降级。",
            },
        )
    if current_regime == "term_premium_pressure":
        return _scenario_case_set(
            base={
                "thesis": "长端利率与实际利率维持压力，久期和成长估值继续受约束。",
                "trade": "低配 TLT 与高估值成长，保留现金/短债防守。",
                "entry_condition": "10Y 收益率或实际利率继续上行，通胀补偿没有回落。",
                "stop": "10Y 收益率回落且实际利率压力消退。",
                "invalidation": "若流动性转松且长端利率下行，期限溢价压力情景降级。",
            },
            upside={
                "thesis": "利率压力回落，风险资产获得估值修复窗口。",
                "trade": "仅在收益率回落确认后逐步回补 QQQ/TLT。",
                "entry_condition": "10Y 收益率回落、实际利率下行且信用不恶化。",
                "stop": "长端利率重新上行。",
                "invalidation": "若通胀补偿再加速，乐观情景失效。",
            },
            downside={
                "thesis": "熊陡或实际利率上行继续压估值，风险资产与长久期债同时承压。",
                "trade": "继续低配 TLT/QQQ，等待信用或波动率确认再加防守。",
                "entry_condition": "10Y 收益率突破近期高位或 2s10s 熊陡。",
                "stop": "收益率回落且曲线重新走平。",
                "invalidation": "若长端下行并伴随信用稳定，悲观情景降级。",
            },
        )
    if current_regime == "credit_stress":
        return _scenario_case_set(
            base={
                "thesis": "信用压力主导风险偏好，高收益 beta 继续跑输。",
                "trade": "低配 HYG，优先 LQD/BIL 防守。",
                "entry_condition": "HY OAS 维持高位或 HYG 跑输 LQD。",
                "stop": "HY 与 IG OAS 同步收窄。",
                "invalidation": "若信用利差连续收窄且波动率不升，信用压力情景降级。",
            },
            upside={
                "thesis": "信用压力缓和，风险资产获得修复。",
                "trade": "信用利差收窄确认后再回补 HYG/SPY。",
                "entry_condition": "HY OAS 收窄且 HYG 相对 LQD 企稳。",
                "stop": "HY OAS 重新走阔。",
                "invalidation": "若低质量信用再次扩散，乐观情景失效。",
            },
            downside={
                "thesis": "信用压力外溢到股票与流动性，去风险进入加速段。",
                "trade": "提高现金/短债，低配高收益债和小盘/高 beta 股票。",
                "entry_condition": "HY OAS 进入困境区或 VIX 同步上行。",
                "stop": "信用利差收窄且 VIX 回落。",
                "invalidation": "若信用压力不再扩散，悲观情景降级。",
            },
        )
    if current_regime == "risk_on_liquidity":
        return _scenario_case_set(
            base={
                "thesis": "流动性改善支持风险资产，但需确认信用与波动率未背离。",
                "trade": "顺势持有 SPY/QQQ beta，保留触发式风控。",
                "entry_condition": "净流动性继续改善且 VIX 未重新定价。",
                "stop": "流动性转紧或 VIX 重新上行。",
                "invalidation": "若信用压力出现，风险偏好情景降级。",
            },
            upside={
                "thesis": "流动性脉冲强化，风险资产进入扩散上涨。",
                "trade": "在确认后增加 SPY/QQQ，BTC 作为顺势观察。",
                "entry_condition": "流动性改善延续且信用稳定。",
                "stop": "风险资产涨幅失去信用确认。",
                "invalidation": "若 VIX 快速上行，乐观情景失效。",
            },
            downside={
                "thesis": "流动性改善停止，风险资产反弹变成假突破。",
                "trade": "降低高 beta，回到 BIL/质量资产防守。",
                "entry_condition": "净流动性改善停止或 VIX 重新定价。",
                "stop": "流动性重新改善。",
                "invalidation": "若净流动性继续扩张且信用稳定，悲观情景降级。",
            },
        )
    return _scenario_case_set(
        base={
            "thesis": "宏观链条缺少单一主导方向，等待利率、信用、流动性给出确认。",
            "trade": "保持中性仓位，避免把单点波动外推成趋势。",
            "entry_condition": "至少两个链条节点同步离开中性区。",
            "stop": "确认信号消失或数据质量恶化。",
            "invalidation": "若核心链条重新分歧，中性情景延续。",
        },
        upside={
            "thesis": "流动性或风险偏好改善并获得信用确认。",
            "trade": "确认后小幅增加 SPY/QQQ beta。",
            "entry_condition": "流动性转松且 VIX/信用稳定。",
            "stop": "信用或波动率转弱。",
            "invalidation": "若确认不足，乐观情景失效。",
        },
        downside={
            "thesis": "利率、信用或资金压力重新成为主导风险。",
            "trade": "提高现金/短债，降低高 beta。",
            "entry_condition": "信用走阔、VIX 上行或 SOFR-IORB 压力出现。",
            "stop": "压力信号回落。",
            "invalidation": "若风险压力未扩散，悲观情景降级。",
        },
    )


def _scenario_case_set(
    *,
    base: Mapping[str, str],
    upside: Mapping[str, str],
    downside: Mapping[str, str],
) -> list[dict[str, Any]]:
    return [
        _scenario_case("base", "基准情景", 0.5, base),
        _scenario_case("upside", "乐观情景", 0.25, upside),
        _scenario_case("downside", "悲观情景", 0.25, downside),
    ]


def _scenario_case(case: str, label: str, probability: float, body: Mapping[str, str]) -> dict[str, Any]:
    return {
        "case": case,
        "label": label,
        "probability": probability,
        "probability_label": f"{probability:.0%}",
        "time_window": "未来 2 周",
        "thesis": body["thesis"],
        "trade": body["trade"],
        "entry_condition": body["entry_condition"],
        "stop": body["stop"],
        "invalidation": body["invalidation"],
    }


def _top_changes(
    *,
    triggers: Sequence[Mapping[str, Any]],
    features: Mapping[str, Any],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for trigger in triggers:
        code = _text(trigger.get("code"))
        if not code:
            continue
        label = _text(trigger.get("label")) or _code_label(code)
        if not label:
            continue
        changes.append(
            {
                "code": code,
                "label": label,
                "description": _text(trigger.get("description")),
                "node": _trigger_node(code),
                "kind": "trigger",
            }
        )
    changes.extend(_feature_top_changes(features))
    return _unique_items(changes, key_name="code")[:3]


def _feature_top_changes(features: Mapping[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for spec in FEATURE_CHANGE_SPECS:
        concept_key = str(spec["concept_key"])
        feature = features.get(concept_key)
        if not isinstance(feature, Mapping):
            continue
        horizon, delta = _feature_change_delta(feature)
        if horizon is None or delta is None:
            continue
        latest = _mapping(feature.get("latest"))
        source_label = _source_label(_mapping(feature.get("source")))
        change_label = _feature_change_label(horizon=horizon, delta=delta, unit=_text(latest.get("unit")))
        value_label = _feature_latest_label(latest)
        observed_at = _text(latest.get("observed_at"))
        severity = _feature_change_severity(delta=delta, unit=_text(latest.get("unit")))
        changes.append(
            {
                "code": f"feature_change:{concept_key}:{horizon}",
                "label": str(spec["label"]),
                "description": _feature_change_description(
                    horizon=horizon,
                    delta=delta,
                    latest=latest,
                    source=_mapping(feature.get("source")),
                ),
                "change_label": change_label,
                "value_label": value_label,
                "observed_at": observed_at,
                "source_label": source_label,
                "severity": severity,
                "severity_label": _severity_label(severity),
                "evidence_label": _feature_change_evidence_label(
                    change_label=change_label,
                    value_label=value_label,
                    source_label=source_label,
                    observed_at=observed_at,
                ),
                "node": str(spec["node"]),
                "kind": "feature_change",
            }
        )
    return changes


def _feature_change_delta(feature: Mapping[str, Any]) -> tuple[str | None, float | None]:
    deltas = feature.get("delta")
    if not isinstance(deltas, Mapping):
        return None, None
    for horizon in ("20d", "5d"):
        delta = _number(deltas.get(horizon))
        if delta is not None:
            return horizon, delta
    return None, None


def _feature_change_description(
    *,
    horizon: str,
    delta: float,
    latest: Mapping[str, Any],
    source: Mapping[str, Any],
) -> str:
    value = _number(latest.get("value"))
    unit = _text(latest.get("unit"))
    observed_at = _text(latest.get("observed_at"))
    source_name = _source_label(source)
    parts = [f"{horizon.replace('d', '日')}变化 {_format_delta(delta, unit)}"]
    if value is not None:
        parts.append(f"最新 {_format_latest(value, unit)}")
    if observed_at:
        parts.append(f"as-of {observed_at}")
    if source_name:
        parts.append(f"source={source_name}")
    return "，".join(parts)


def _feature_change_label(*, horizon: str, delta: float, unit: str) -> str:
    return f"{horizon.replace('d', '日')}变化 {_format_delta(delta, unit)}"


def _feature_latest_label(latest: Mapping[str, Any]) -> str:
    value = _number(latest.get("value"))
    if value is None:
        return ""
    return f"最新 {_format_latest(value, _text(latest.get('unit')))}"


def _feature_change_evidence_label(
    *,
    change_label: str,
    value_label: str,
    source_label: str,
    observed_at: str,
) -> str:
    parts = [
        change_label,
        value_label,
        f"source={source_label}" if source_label else "",
        f"as-of={observed_at}" if observed_at else "",
    ]
    return " · ".join(part for part in parts if part)


def _feature_change_severity(*, delta: float, unit: str) -> str:
    magnitude = abs(delta * 100.0) if unit == "percent" else abs(delta)
    high_threshold = 25.0 if unit == "percent" else 2.0
    medium_threshold = 5.0 if unit == "percent" else 1.0
    if magnitude >= high_threshold:
        return "high"
    if magnitude >= medium_threshold:
        return "medium"
    return "low"


def _severity_label(severity: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(severity, "中")


def _format_delta(value: float, unit: str) -> str:
    if unit == "percent":
        return f"{value * 100:+.1f}bp"
    suffix = f" {unit}" if unit else ""
    return f"{value:+.2f}{suffix}"


def _format_latest(value: float, unit: str) -> str:
    if unit == "percent":
        return f"{value:.2f} %"
    suffix = f" {unit}" if unit else ""
    return f"{value:.2f}{suffix}"


def _source_label(source: Mapping[str, Any]) -> str:
    source_name = _text(source.get("source_name") or source.get("source"))
    if not source_name:
        return ""
    return SOURCE_LABELS.get(source_name, source_name)


def _quality_blockers(data_gaps: Sequence[str]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for gap in build_macro_data_gaps(data_gaps):
        code = _text(gap.get("code"))
        if not code:
            continue
        blockers.append(
            {
                "code": code,
                "label": _text(gap.get("label")),
                "description": _text(gap.get("remediation_hint")),
                "severity": _text(gap.get("severity") or "warning"),
            }
        )
    return _unique_items(blockers, key_name="code")[:5]


def _trigger_node(code: str) -> str:
    if code.startswith(("sofr_", "repo_", "rrp_", "tga_")):
        return "funding"
    if code.startswith(("hy_", "credit_", "hyg_", "loan_")):
        return "credit"
    if code.startswith(("vix", "volatility", "options")):
        return "volatility"
    if code.startswith(("real_yield", "ten_year", "term_", "deep_curve", "breakevens")):
        return "rates"
    if code.startswith(("risk_", "cross_asset")):
        return "cross_asset"
    return "macro"


def _contains_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


def _code_label(code: str) -> str | None:
    if not code:
        return None
    if _contains_cjk(code):
        return code
    return {
        "breakevens_accelerate": "通胀补偿加速",
        "credit_stress": "信用压力",
        "deep_curve_inversion": "曲线深度倒挂",
        "fed_corridor_pressure": "政策走廊压力",
        "higher_real_rates": "实际利率上行",
        "hyg_underperforms_lqd": "HYG 跑输 LQD",
        "hy_oas_distress": "高收益债利差进入困境区",
        "hy_oas_stress": "高收益债利差压力",
        "liquidity_tightening": "流动性收紧",
        "repo_corridor_pressure": "回购走廊压力",
        "rrp_buffer_low": "RRP 缓冲偏低",
        "sofr_above_iorb": "SOFR 高于 IORB",
        "term_premium_pressure": "期限溢价压力",
        "tga_high": "TGA 偏高",
        "vix_elevated": "VIX 偏高",
        "volatility_stress": "波动率压力",
    }.get(code)


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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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
