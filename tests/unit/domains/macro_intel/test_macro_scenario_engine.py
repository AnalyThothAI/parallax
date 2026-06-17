from __future__ import annotations

from parallax.domains.macro_intel.services.macro_scenario_engine import (
    build_macro_scenario,
)


def test_build_macro_scenario_emits_funding_stress_trade_map() -> None:
    scenario = build_macro_scenario(
        chain={
            "liquidity": {
                "score": 9.0,
                "regime": "funding_stress",
                "evidence": ["sofr_iorb_spread_bps=15.0"],
                "data_gaps": [],
            },
            "fed_corridor": {
                "score": 8.0,
                "regime": "corridor_pressure",
                "evidence": ["sofr_above_iorb"],
                "data_gaps": [],
            },
            "volatility": {
                "score": 7.0,
                "regime": "near_term_stress",
                "evidence": ["vix=24.0"],
                "data_gaps": [],
            },
        },
        panels={"credit": {"regime": "low_quality_stress", "score": 7.0}},
        features={"credit:hy_oas": {"delta": {"5d": 0.35}}},
        triggers=[
            {"code": "sofr_above_iorb", "description": "SOFR is above IORB", "value": 15.0},
            {"code": "hy_oas_stress", "description": "HY OAS is above 5%", "value": 5.8},
        ],
        data_gaps=["missing:asset:spy"],
    )

    assert scenario["current_regime"] == "funding_stress"
    assert scenario["confidence"] > 0
    assert scenario["time_window"] == "1w"
    assert {item["code"] for item in scenario["confirmations"]} >= {"sofr_above_iorb", "hy_oas_stress"}
    assert scenario["watch_triggers"][:3] == [
        {
            "code": "repo_pressure_persists_3d",
            "description": "SOFR remains above IORB across multiple observations.",
            "time_window": "24h",
            "severity": "high",
        },
        {
            "code": "hy_oas_widening_5d",
            "description": "HY OAS widens over five trading days.",
            "delta_5d": 0.35,
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
    assert scenario["invalidations"]
    assert scenario["trade_map"][0]["expression"] == "risk_down_credit_sensitive"
    assert scenario["trade_map"][0]["legs"] == [
        {
            "asset": "cash_short_bills",
            "label": "现金/短债",
            "symbol": "BIL",
            "action": "做多/防守",
        },
        {
            "asset": "nasdaq",
            "label": "纳斯达克",
            "symbol": "QQQ",
            "action": "回避/做空代理",
        },
        {
            "asset": "high_yield_credit",
            "label": "高收益信用",
            "symbol": "HYG",
            "action": "低配",
        },
    ]
    assert scenario["top_changes"][:2] == [
        {
            "code": "sofr_above_iorb",
            "label": "SOFR 高于 IORB",
            "description": "SOFR is above IORB",
            "node": "funding",
            "kind": "trigger",
        },
        {
            "code": "hy_oas_stress",
            "label": "高收益债利差压力",
            "description": "HY OAS is above 5%",
            "node": "credit",
            "kind": "trigger",
        },
    ]
    assert scenario["quality_blockers"] == [
        {
            "code": "missing_asset_spy",
            "label": "缺少当前数据：SPY",
            "description": "检查对应 provider 导入与最新观测。",
            "severity": "error",
        }
    ]


def test_build_macro_scenario_emits_three_case_trade_plan() -> None:
    scenario = build_macro_scenario(
        chain={
            "liquidity": {
                "score": 9.0,
                "regime": "funding_stress",
                "evidence": ["sofr_iorb_spread_bps=15.0"],
                "data_gaps": [],
            },
            "fed_corridor": {
                "score": 8.0,
                "regime": "corridor_pressure",
                "evidence": ["sofr_above_iorb"],
                "data_gaps": [],
            },
            "volatility": {
                "score": 7.0,
                "regime": "near_term_stress",
                "evidence": ["vix=24.0"],
                "data_gaps": [],
            },
        },
        panels={"credit": {"regime": "low_quality_stress", "score": 7.0}},
        features={"credit:hy_oas": {"delta": {"5d": 0.35}}},
        triggers=[
            {"code": "sofr_above_iorb", "description": "SOFR is above IORB", "value": 15.0},
            {"code": "hy_oas_stress", "description": "HY OAS is above 5%", "value": 5.8},
        ],
        data_gaps=[],
    )

    assert scenario["scenario_cases"] == [
        {
            "case": "base",
            "label": "基准情景",
            "probability": 0.5,
            "probability_label": "50%",
            "time_window": "未来 2 周",
            "thesis": "资金压力维持，信用 beta 继续承压，风险资产反弹先按减仓处理。",
            "trade": "防守：做多/持有 BIL，低配 QQQ 与 HYG。",
            "entry_condition": "SOFR-IORB 仍为正且 HY OAS 5日继续走阔。",
            "stop": "SOFR 回到 IORB 附近且 HY OAS 明显收窄。",
            "invalidation": "若 VIX 回到 carry 区且信用利差同步收窄，资金压力情景降级。",
        },
        {
            "case": "upside",
            "label": "乐观情景",
            "probability": 0.25,
            "probability_label": "25%",
            "time_window": "未来 2 周",
            "thesis": "流动性压力快速缓和，信用没有继续恶化，风险资产获得技术性修复窗口。",
            "trade": "仅在确认后回补 SPY/QQQ beta，避免提前抢跑。",
            "entry_condition": "SOFR-IORB 正常化、HY OAS 收窄且 VIX 低于 20。",
            "stop": "任一资金或信用确认重新转弱。",
            "invalidation": "若 repo 压力延续 3 日或 HY OAS 重新走阔，乐观情景失效。",
        },
        {
            "case": "downside",
            "label": "悲观情景",
            "probability": 0.25,
            "probability_label": "25%",
            "time_window": "未来 2 周",
            "thesis": "资金压力传导到信用与波动率，风险资产进入去杠杆。",
            "trade": "提高现金/短债，继续低配 HYG 与 QQQ，可用 VIX 上行作为保护确认。",
            "entry_condition": "HY OAS 进入困境区或 VIX 突破 30。",
            "stop": "信用利差收窄且 VIX 回落到 20 以下。",
            "invalidation": "若净流动性转正且信用利差未扩张，悲观情景降级。",
        },
    ]


def test_build_macro_scenario_reports_data_gap_without_chain_evidence() -> None:
    scenario = build_macro_scenario(
        chain={
            "liquidity": {
                "score": 0.0,
                "regime": "data_gap",
                "evidence": [],
                "data_gaps": ["missing:liquidity:fed_assets"],
            },
            "rates": {"score": 0.0, "regime": "data_gap", "evidence": [], "data_gaps": ["missing:rates:dgs10"]},
        },
        panels={},
        features={},
        triggers=[],
        data_gaps=["missing:liquidity:fed_assets", "missing:rates:dgs10"],
    )

    assert scenario["current_regime"] == "data_gap"
    assert scenario["confidence"] == 0.0
    assert scenario["confirmations"] == []
    assert scenario["watch_triggers"]
    assert scenario["trade_map"] == []
    assert scenario["top_changes"] == []
    assert [item["code"] for item in scenario["quality_blockers"]] == [
        "missing_liquidity_fed_assets",
        "missing_rates_dgs10",
    ]


def test_build_macro_scenario_derives_top_changes_from_feature_deltas_without_triggers() -> None:
    scenario = build_macro_scenario(
        chain={
            "rates": {"score": 7.0, "regime": "term_premium_pressure", "evidence": [], "data_gaps": []},
            "credit": {"score": 4.0, "regime": "confirmed_risk_on", "evidence": [], "data_gaps": []},
            "cross_asset": {"score": 6.0, "regime": "risk_off_confirmation", "evidence": [], "data_gaps": []},
        },
        panels={},
        features={
            "fx:dxy": {
                "latest": {"value": 104.2, "unit": "index", "observed_at": "2026-05-20"},
                "delta": {"5d": 0.6, "20d": 1.4},
                "source": {"source_name": "yahoo"},
            },
            "rates:dgs10": {
                "latest": {"value": 4.59, "unit": "percent", "observed_at": "2026-05-20"},
                "delta": {"5d": 0.12, "20d": 0.28},
                "source": {"source_name": "fred"},
            },
            "credit:hy_oas": {
                "latest": {"value": 2.76, "unit": "percent", "observed_at": "2026-05-19"},
                "delta": {"5d": -0.06, "20d": -0.18},
                "source": {"source_name": "fred"},
            },
            "asset:spx": {
                "latest": {"value": 7408.5, "unit": "index", "observed_at": "2026-05-20"},
                "delta": {"5d": -0.4, "20d": -1.2},
                "source": {"source_name": "yahoo"},
            },
        },
        triggers=[],
        data_gaps=[],
    )

    assert scenario["top_changes"] == [
        {
            "code": "feature_change:fx:dxy:20d",
            "label": "美元指数",
            "description": "20日变化 +1.40 index，最新 104.20 index，as-of 2026-05-20，source=Yahoo Finance",
            "change_label": "20日变化 +1.40 index",
            "value_label": "最新 104.20 index",
            "observed_at": "2026-05-20",
            "source_label": "Yahoo Finance",
            "severity": "medium",
            "severity_label": "中",
            "evidence_label": "20日变化 +1.40 index · 最新 104.20 index · source=Yahoo Finance · as-of=2026-05-20",
            "node": "cross_asset",
            "kind": "feature_change",
        },
        {
            "code": "feature_change:rates:dgs10:20d",
            "label": "10Y 国债收益率",
            "description": "20日变化 +28.0bp，最新 4.59 %，as-of 2026-05-20，source=FRED",
            "change_label": "20日变化 +28.0bp",
            "value_label": "最新 4.59 %",
            "observed_at": "2026-05-20",
            "source_label": "FRED",
            "severity": "high",
            "severity_label": "高",
            "evidence_label": "20日变化 +28.0bp · 最新 4.59 % · source=FRED · as-of=2026-05-20",
            "node": "rates",
            "kind": "feature_change",
        },
        {
            "code": "feature_change:credit:hy_oas:20d",
            "label": "高收益债 OAS",
            "description": "20日变化 -18.0bp，最新 2.76 %，as-of 2026-05-19，source=FRED",
            "change_label": "20日变化 -18.0bp",
            "value_label": "最新 2.76 %",
            "observed_at": "2026-05-19",
            "source_label": "FRED",
            "severity": "medium",
            "severity_label": "中",
            "evidence_label": "20日变化 -18.0bp · 最新 2.76 % · source=FRED · as-of=2026-05-19",
            "node": "credit",
            "kind": "feature_change",
        },
    ]


def test_build_macro_scenario_omits_unmapped_trigger_placeholder_labels() -> None:
    scenario = build_macro_scenario(
        chain={},
        panels={},
        features={},
        triggers=[{"code": "unmapped_trigger_code", "description": "Unknown trigger"}],
        data_gaps=[],
    )

    assert scenario["confirmations"] == []
    assert scenario["top_changes"] == []
    assert "待确认信号" not in str(scenario)
