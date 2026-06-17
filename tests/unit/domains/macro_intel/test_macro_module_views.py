from __future__ import annotations

import pytest

from parallax.domains.macro_intel._constants import MACRO_CORE_CONCEPTS
from parallax.domains.macro_intel.services import macro_module_views
from parallax.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps
from parallax.domains.macro_intel.services.macro_module_catalog import (
    UnsupportedMacroModuleError,
    list_macro_module_configs,
)
from parallax.domains.macro_intel.services.macro_module_views import build_macro_module_view
from parallax.domains.macro_intel.services.macro_regime_engine import build_macro_view_snapshot

NOW_MS = 1_779_000_000_000


def test_build_macro_module_view_projects_v3_display_contract() -> None:
    view = build_macro_module_view(
        "rates/yield-curve",
        snapshot=_snapshot(),
        observations=[
            _obs("rates:dgs10", "2026-05-20", 4.7, unit="percent", source_name="fred"),
            _obs("rates:dgs2", "2026-05-20", 3.9, unit="percent", source_name="fred"),
        ],
    )

    assert tuple(view) == (
        "snapshot",
        "tiles",
        "primary_chart",
        "tables",
        "module_read",
        "module_evidence",
        "transmission",
        "data_health",
        "provenance",
        "related_routes",
    )
    assert "read" not in view
    assert "evidence" not in view
    assert "data_gaps" not in view
    assert view["snapshot"] == {
        "module_id": "rates/yield-curve",
        "route_path": "/macro/rates/yield-curve",
        "title": "收益率曲线",
        "subtitle": "1M 到 30Y 的曲线形态与期限利差",
        "question": "曲线形态是在交易衰退压力，还是交易期限溢价？",
        "section": "rates",
        "projection_version": "macro_module_view_v3",
        "status": "partial",
        "status_label": "部分可用",
        "asof_date": "2026-05-20",
        "asof_label": "截至 2026-05-20",
        "computed_at_ms": NOW_MS,
        "computed_at_label": "计算于 2026-05-17 06:40 UTC",
        "source_snapshot_id": "snapshot-1",
        "source_projection_version": "macro_regime_v4",
    }
    assert view["tiles"][0] == {
        "concept_key": "rates:dgs2",
        "label": "2年期美债收益率",
        "short_label": "2Y",
        "description": "政策预期敏感的短端美债收益率",
        "value": 3.9,
        "display_value": "3.90",
        "unit": "percent",
        "unit_label": "%",
        "delta_label": "20日变化不可用",
        "source_label": "FRED",
        "observed_at": "2026-05-20",
        "observed_at_label": "观测于 2026-05-20",
        "quality": "ok",
        "quality_label": "可用",
        "score_participation": False,
        "history_points": 1,
    }
    assert view["primary_chart"]["id"] == "yield_curve"
    assert view["primary_chart"]["status"] == "partial"
    assert view["primary_chart"]["status_label"] == "部分可用"
    assert view["primary_chart"]["min_points"] == 2
    assert "rates:dgs5" in view["primary_chart"]["missing_concept_keys"]
    assert "rates:dgs30" in view["primary_chart"]["missing_concept_keys"]
    assert view["primary_chart"]["series"][0]["label"] == "2年期美债收益率"
    assert view["primary_chart"]["series"][0]["point_count"] == 1
    assert view["tables"][0]["columns"] == [
        {"key": "indicator", "label": "指标"},
        {"key": "latest", "label": "最新值"},
        {"key": "delta_20d", "label": "20日变化"},
        {"key": "quality", "label": "质量"},
        {"key": "source", "label": "来源"},
    ]
    ten_year_row = next(
        row for row in view["tables"][0]["rows"] if row["cells"]["indicator"]["display_value"] == "10年期美债收益率"
    )
    assert ten_year_row["cells"]["latest"] == {"display_value": "4.70", "sort_value": 4.7}
    assert ten_year_row["row_quality"] == "ok"
    assert ten_year_row["source_state"] == {"label": "FRED", "status": "ok"}
    assert view["module_read"] == {
        "headline": "收益率曲线：部分可用",
        "regime_label": "部分可用",
        "confidence_label": "模块覆盖 2/13",
        "data_note": "本页只展示已入库的真实观测、规则状态和可用性说明。",
        "methodology_note": "收益率曲线 使用模块配置中的 required/optional 概念生成图表和表格。",
    }
    assert view["module_evidence"]["confirmations"][0]["code"] == "module_concept_available:rates:dgs2"
    assert view["module_evidence"]["confirmations"][0]["label"] == "2年期美债收益率"
    assert isinstance(view["transmission"], list)
    assert view["transmission"][0]["kind"] == "source"
    assert view["transmission"][0]["status"] == "ok"
    assert view["transmission"][-1]["kind"] == "implication"
    assert view["data_health"]["summary_status"] == "partial"
    assert any(gap["code"] == "missing_rates_dgs5" for gap in view["data_health"]["global_gaps"])
    assert any(gap["code"] == "insufficient_history_20d" for gap in view["data_health"]["module_gaps"])
    assert "future_integration_gaps" not in view["data_health"]
    assert all(
        item["label"] not in {"rrp buffer low", "hy oas distress", "credit spreads normalize"}
        for group in view["module_evidence"].values()
        for item in group
    )
    assert view["provenance"]["rows"] == [
        {
            "row_id": "source:FRED",
            "source_label": "FRED",
            "status": "ok",
            "status_label": "可用",
            "latest_observed_at": "2026-05-20",
            "concept_count": 2,
            "notes": "",
        },
    ]
    provenance_text = str(view["provenance"])
    assert "fred" not in provenance_text
    assert "macro_import" not in provenance_text
    assert "run-1" not in provenance_text
    assert "coverage" not in view["provenance"]
    assert view["related_routes"][0] == {"href": "/macro/rates/fed-funds", "label": "联邦基金"}
    assert "section_boards" not in view


@pytest.mark.parametrize(
    "field_name",
    (
        "panels_json",
        "indicators_json",
        "triggers_json",
        "data_gaps_json",
        "source_coverage_json",
        "features_json",
        "chain_json",
        "scenario_json",
        "scorecard_json",
    ),
)
def test_build_macro_module_view_requires_formal_snapshot_json_sections(field_name: str) -> None:
    snapshot = _snapshot()
    del snapshot[field_name]

    with pytest.raises(ValueError, match=f"macro_module_view_snapshot_section_required:{field_name}"):
        build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("panels_json", []),
        ("indicators_json", []),
        ("source_coverage_json", []),
        ("features_json", []),
        ("chain_json", []),
        ("scenario_json", []),
        ("scorecard_json", []),
        ("triggers_json", {}),
        ("data_gaps_json", {}),
    ),
)
def test_build_macro_module_view_rejects_misshaped_snapshot_json_sections(
    field_name: str, invalid_value: object
) -> None:
    snapshot = _snapshot()
    snapshot[field_name] = invalid_value

    with pytest.raises(ValueError, match=f"macro_module_view_snapshot_section_invalid:{field_name}"):
        build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])


def test_module_view_provenance_exposes_fact_projection_currentness_without_run_ids() -> None:
    view = build_macro_module_view(
        "rates/yield-curve",
        snapshot=_snapshot(),
        observations=[
            _obs("rates:dgs10", "2026-05-20", 4.7, unit="percent", source_name="fred"),
        ],
        facts_max_observed_at="2026-05-22",
        projection_lag_days=2,
        projection_behind_facts=True,
    )

    assert view["provenance"]["currentness"] == {
        "facts_max_observed_at": "2026-05-22",
        "projection_lag_days": 2,
        "projection_behind_facts": True,
    }
    provenance_text = str(view["provenance"])
    assert "sync_run" not in provenance_text
    assert "import_run" not in provenance_text


def test_yield_curve_module_read_adds_curve_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["rates:dgs2"] = _feature_with_history(
        "rates:dgs2",
        [
            ("2026-02-19", 3.5),
            ("2026-04-20", 3.6),
            ("2026-05-13", 3.7),
            ("2026-05-20", 3.8),
        ],
    )
    features["rates:dgs10"] = _feature_with_history(
        "rates:dgs10",
        [
            ("2026-02-19", 3.8),
            ("2026-04-20", 3.9),
            ("2026-05-13", 4.0),
            ("2026-05-20", 4.2),
        ],
    )
    features["rates:dgs3mo"] = _feature_with_history(
        "rates:dgs3mo",
        [
            ("2026-02-19", 4.5),
            ("2026-04-20", 4.4),
            ("2026-05-13", 4.35),
            ("2026-05-20", 4.3),
        ],
    )
    features["rates:dgs5"] = _feature_with_history(
        "rates:dgs5",
        [
            ("2026-02-19", 3.7),
            ("2026-04-20", 3.8),
            ("2026-05-13", 3.9),
            ("2026-05-20", 4.0),
        ],
    )
    features["rates:dgs30"] = _feature_with_history(
        "rates:dgs30",
        [
            ("2026-02-19", 4.4),
            ("2026-04-20", 4.5),
            ("2026-05-13", 4.55),
            ("2026-05-20", 4.7),
        ],
    )
    features["rates:real_5y"] = _feature_with_history(
        "rates:real_5y",
        [
            ("2026-05-13", 1.95),
            ("2026-05-20", 2.1),
        ],
    )
    features["rates:real_10y"] = _feature_with_history(
        "rates:real_10y",
        [
            ("2026-05-13", 1.8),
            ("2026-05-20", 1.95),
        ],
    )
    features["inflation:5y_breakeven"] = _feature_with_history(
        "inflation:5y_breakeven",
        [
            ("2026-05-13", 1.95),
            ("2026-05-20", 1.9),
        ],
    )
    features["inflation:10y_breakeven"] = _feature_with_history(
        "inflation:10y_breakeven",
        [
            ("2026-05-13", 2.2),
            ("2026-05-20", 2.15),
        ],
    )

    view = build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["curve_diagnostics"]
    assert diagnostics["shape"] == "bear_steepening"
    assert diagnostics["shape_label"] == "熊陡"
    assert diagnostics["summary"] == "曲线熊陡：10Y 上行且 2s10s 走陡，期限溢价压力压制久期资产。"
    assert diagnostics["rows"] == [
        {
            "key": "2s10s",
            "label": "2s10s",
            "current_bp": 40.0,
            "change_1w_bp": 10.0,
            "change_1m_bp": 10.0,
            "change_3m_bp": 10.0,
            "status": "steepening",
            "status_label": "走陡",
        },
        {
            "key": "3m10y",
            "label": "3m10y",
            "current_bp": -10.0,
            "change_1w_bp": 25.0,
            "change_1m_bp": 40.0,
            "change_3m_bp": 60.0,
            "status": "less_inverted",
            "status_label": "倒挂缓和",
        },
        {
            "key": "5s30s",
            "label": "5s30s",
            "current_bp": 70.0,
            "change_1w_bp": 5.0,
            "change_1m_bp": 0.0,
            "change_3m_bp": 0.0,
            "status": "steepening",
            "status_label": "走陡",
        },
    ]
    assert diagnostics["implications"] == ["期限溢价压力：优先防守长久期成长、长债和高 beta。"]
    assert diagnostics["invalidations"] == ["若 10Y 回落且 2s10s 重新走平，曲线压力降级。"]
    assert diagnostics["spread_history"][0] == {
        "key": "2s10s",
        "label": "2s10s",
        "unit": "bp",
        "points": [
            {"observed_at": "2026-02-19", "value_bp": 30.0},
            {"observed_at": "2026-04-20", "value_bp": 30.0},
            {"observed_at": "2026-05-13", "value_bp": 30.0},
            {"observed_at": "2026-05-20", "value_bp": 40.0},
        ],
        "min_bp": 30.0,
        "max_bp": 40.0,
        "latest_bp": 40.0,
    }
    assert diagnostics["tenor_comparison"] == [
        {
            "key": "5y",
            "label": "5Y",
            "nominal_pct": 4.0,
            "real_pct": 2.1,
            "breakeven_pct": 1.9,
            "nominal_change_1w_bp": 10.0,
            "real_change_1w_bp": 15.0,
            "breakeven_change_1w_bp": -5.0,
            "residual_bp": 0.0,
            "driver": "real_rate",
            "driver_label": "实际利率驱动",
        },
        {
            "key": "10y",
            "label": "10Y",
            "nominal_pct": 4.2,
            "real_pct": 1.95,
            "breakeven_pct": 2.15,
            "nominal_change_1w_bp": 20.0,
            "real_change_1w_bp": 15.0,
            "breakeven_change_1w_bp": -5.0,
            "residual_bp": 10.0,
            "driver": "real_rate",
            "driver_label": "实际利率驱动",
        },
    ]


def test_yield_curve_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    features = snapshot["features_json"]
    features["rates:dgs2"] = _feature_with_history(
        "rates:dgs2",
        [
            ("2026-04-20", 3.6),
            ("2026-05-13", 3.7),
            ("2026-05-20", 3.8),
        ],
    )
    features["rates:dgs10"] = _feature_with_history(
        "rates:dgs10",
        [
            ("2026-04-20", 3.9),
            ("2026-05-13", 4.0),
            ("2026-05-20", 4.2),
        ],
    )

    view = build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])

    assert view["module_read"]["curve_diagnostics"]["rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "yield_curve_front_end_missing",
        "yield_curve_belly_missing",
        "yield_curve_long_end_missing",
        "yield_curve_real_rate_decomposition_missing",
        "yield_curve_breakeven_decomposition_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("yield_curve_")
    )
    assert "rates/auctions" not in str(view["related_routes"])
    assert "rates/expectations" not in str(view["related_routes"])


def test_fed_funds_module_read_adds_policy_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["fed:target_lower"] = _feature_with_history(
        "fed:target_lower",
        [
            ("2026-05-13", 4.25),
            ("2026-05-20", 4.25),
        ],
    )
    features["fed:target_upper"] = _feature_with_history(
        "fed:target_upper",
        [
            ("2026-05-13", 4.50),
            ("2026-05-20", 4.50),
        ],
    )
    features["fed:effr"] = _feature_with_history(
        "fed:effr",
        [
            ("2026-05-13", 4.35),
            ("2026-05-20", 4.55),
        ],
    )
    features["fed:iorb"] = _feature_with_history(
        "fed:iorb",
        [
            ("2026-05-13", 4.40),
            ("2026-05-20", 4.40),
        ],
    )
    features["liquidity:sofr"] = _feature_with_history(
        "liquidity:sofr",
        [
            ("2026-05-13", 4.36),
            ("2026-05-20", 4.62),
        ],
    )
    features["fed:sofr_30d"] = _feature_with_history(
        "fed:sofr_30d",
        [
            ("2026-05-13", 4.35),
            ("2026-05-20", 4.57),
        ],
    )
    features["fed:dff"] = _feature_with_history(
        "fed:dff",
        [
            ("2026-05-13", 4.34),
            ("2026-05-20", 4.54),
        ],
    )
    features["fed:obfr"] = _feature_with_history(
        "fed:obfr",
        [
            ("2026-05-13", 4.37),
            ("2026-05-20", 4.63),
        ],
    )
    features["fed:effr_volume"] = _feature_with_history(
        "fed:effr_volume",
        [
            ("2026-05-13", 145_000.0),
            ("2026-05-20", 102_000.0),
        ],
        unit="millions_usd",
    )
    features["fed:obfr_volume"] = _feature_with_history(
        "fed:obfr_volume",
        [
            ("2026-05-13", 210_000.0),
            ("2026-05-20", 196_000.0),
        ],
        unit="millions_usd",
    )

    view = build_macro_module_view("rates/fed-funds", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["policy_diagnostics"]
    assert diagnostics["regime"] == "corridor_pressure"
    assert diagnostics["regime_label"] == "走廊压力"
    assert diagnostics["summary"] == "政策走廊承压：EFFR 高于目标上限且 SOFR 相对 EFFR 走阔，隔夜融资压力需要降杠杆。"
    assert diagnostics["rows"] == [
        {
            "key": "target_range",
            "label": "目标区间",
            "lower_pct": 4.25,
            "upper_pct": 4.5,
            "width_bp": 25.0,
            "status": "range_defined",
            "status_label": "区间明确",
        },
        {
            "key": "effr_vs_range",
            "label": "EFFR 位置",
            "current_pct": 4.55,
            "distance_to_upper_bp": 5.0,
            "change_1w_bp": 20.0,
            "status": "above_upper",
            "status_label": "高于上限",
        },
        {
            "key": "effr_iorb_spread",
            "label": "EFFR-IORB",
            "current_bp": 15.0,
            "change_1w_bp": 20.0,
            "status": "corridor_pressure",
            "status_label": "走廊压力",
        },
        {
            "key": "sofr_effr_spread",
            "label": "SOFR-EFFR",
            "current_bp": 7.0,
            "change_1w_bp": 6.0,
            "status": "funding_pressure",
            "status_label": "融资压力",
        },
        {
            "key": "sofr_30d_effr_spread",
            "label": "SOFR 30D-EFFR",
            "current_bp": 2.0,
            "change_1w_bp": 2.0,
            "status": "stable",
            "status_label": "稳定",
        },
        {
            "key": "dff_effr_spread",
            "label": "DFF-EFFR",
            "current_bp": -1.0,
            "change_1w_bp": 0.0,
            "status": "stable",
            "status_label": "稳定",
        },
        {
            "key": "obfr_effr_spread",
            "label": "OBFR-EFFR",
            "current_bp": 8.0,
            "change_1w_bp": 6.0,
            "status": "broader_unsecured_pressure",
            "status_label": "广义无担保压力",
        },
        {
            "key": "effr_volume",
            "label": "EFFR 成交量",
            "current_bn": 102.0,
            "change_1w_bn": -43.0,
            "status": "thin_depth",
            "status_label": "成交变薄",
        },
        {
            "key": "obfr_volume",
            "label": "OBFR 成交量",
            "current_bn": 196.0,
            "change_1w_bn": -14.0,
            "status": "depth_ok",
            "status_label": "深度稳定",
        },
    ]
    assert diagnostics["implications"] == ["走廊压力：降低融资敏感资产和杠杆多头，等待 EFFR 回到目标区间内。"]
    assert diagnostics["invalidations"] == [
        "若 EFFR 回落至目标上限下方且 SOFR-EFFR 收窄至 0bp 附近，走廊压力读法降级。"
    ]


def test_fed_funds_data_health_marks_missing_implemented_corridor_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    features = snapshot["features_json"]
    for concept_key, value in (
        ("fed:target_lower", 4.25),
        ("fed:target_upper", 4.50),
        ("fed:effr", 4.35),
        ("fed:iorb", 4.40),
        ("liquidity:sofr", 4.36),
    ):
        features[concept_key] = _feature_with_history(
            concept_key,
            [
                ("2026-05-13", value),
                ("2026-05-20", value),
            ],
            unit="percent",
            source_name="fred",
        )

    view = build_macro_module_view("rates/fed-funds", snapshot=snapshot, observations=[])

    assert view["module_read"]["policy_diagnostics"]["regime"] == "stable"
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "policy_daily_fed_funds_missing",
        "policy_sofr_30d_missing",
        "policy_unsecured_funding_missing",
        "policy_volume_depth_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("policy_")
    )
    assert "rates/expectations" not in str(view["related_routes"])


def test_real_rates_module_read_adds_real_rate_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["rates:real_5y"] = _feature_with_history(
        "rates:real_5y",
        [
            ("2026-02-19", 1.60),
            ("2026-04-20", 1.70),
            ("2026-05-13", 1.85),
            ("2026-05-20", 2.05),
        ],
    )
    features["rates:real_10y"] = _feature_with_history(
        "rates:real_10y",
        [
            ("2026-02-19", 1.70),
            ("2026-04-20", 1.80),
            ("2026-05-13", 1.90),
            ("2026-05-20", 2.10),
        ],
    )
    features["rates:real_30y"] = _feature_with_history(
        "rates:real_30y",
        [
            ("2026-02-19", 1.80),
            ("2026-04-20", 1.85),
            ("2026-05-13", 1.95),
            ("2026-05-20", 2.00),
        ],
    )
    features["inflation:5y_breakeven"] = _feature_with_history(
        "inflation:5y_breakeven",
        [
            ("2026-02-19", 2.00),
            ("2026-04-20", 2.05),
            ("2026-05-13", 2.00),
            ("2026-05-20", 1.90),
        ],
    )
    features["inflation:10y_breakeven"] = _feature_with_history(
        "inflation:10y_breakeven",
        [
            ("2026-02-19", 2.20),
            ("2026-04-20", 2.25),
            ("2026-05-13", 2.20),
            ("2026-05-20", 2.15),
        ],
    )
    features["inflation:5y5y_forward"] = _feature_with_history(
        "inflation:5y5y_forward",
        [
            ("2026-02-19", 2.40),
            ("2026-04-20", 2.35),
            ("2026-05-13", 2.30),
            ("2026-05-20", 2.25),
        ],
    )

    view = build_macro_module_view("rates/real-rates", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["real_rate_diagnostics"]
    assert diagnostics["regime"] == "real_rate_pressure"
    assert diagnostics["regime_label"] == "实际利率压力"
    assert (
        diagnostics["summary"] == "实际利率上行且通胀补偿未同步走阔：估值压力偏实际利率驱动，长久期与高 beta 需要降级。"
    )
    assert diagnostics["real_yield_rows"] == [
        {
            "key": "real_5y",
            "label": "5Y Real",
            "current_pct": 2.05,
            "change_1w_bp": 20.0,
            "change_1m_bp": 35.0,
            "change_3m_bp": 45.0,
            "status": "valuation_pressure",
            "status_label": "估值压力",
        },
        {
            "key": "real_10y",
            "label": "10Y Real",
            "current_pct": 2.1,
            "change_1w_bp": 20.0,
            "change_1m_bp": 30.0,
            "change_3m_bp": 40.0,
            "status": "valuation_pressure",
            "status_label": "估值压力",
        },
        {
            "key": "real_30y",
            "label": "30Y Real",
            "current_pct": 2.0,
            "change_1w_bp": 5.0,
            "change_1m_bp": 15.0,
            "change_3m_bp": 20.0,
            "status": "valuation_pressure",
            "status_label": "估值压力",
        },
    ]
    assert diagnostics["inflation_rows"] == [
        {
            "key": "breakeven_5y",
            "label": "5Y Breakeven",
            "current_pct": 1.9,
            "change_1w_bp": -10.0,
            "change_1m_bp": -15.0,
            "change_3m_bp": -10.0,
            "status": "falling",
            "status_label": "补偿回落",
        },
        {
            "key": "breakeven_10y",
            "label": "10Y Breakeven",
            "current_pct": 2.15,
            "change_1w_bp": -5.0,
            "change_1m_bp": -10.0,
            "change_3m_bp": -5.0,
            "status": "falling",
            "status_label": "补偿回落",
        },
        {
            "key": "forward_5y5y",
            "label": "5Y5Y Forward",
            "current_pct": 2.25,
            "change_1w_bp": -5.0,
            "change_1m_bp": -10.0,
            "change_3m_bp": -15.0,
            "status": "falling",
            "status_label": "补偿回落",
        },
    ]
    assert diagnostics["implications"] == ["实际利率压力：降低长久期成长、长债和高 beta 反弹置信度。"]
    assert diagnostics["invalidations"] == [
        "若 10Y 实际利率单周回落超过 15bp，且 breakeven 不再回落，实际利率压力读法降级。"
    ]


def test_real_rates_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    features = snapshot["features_json"]
    features["rates:real_10y"] = _feature_with_history(
        "rates:real_10y",
        [
            ("2026-02-19", 1.70),
            ("2026-04-20", 1.80),
            ("2026-05-13", 1.90),
            ("2026-05-20", 2.10),
        ],
    )

    view = build_macro_module_view("rates/real-rates", snapshot=snapshot, observations=[])

    assert view["module_read"]["real_rate_diagnostics"]["real_yield_rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "real_rates_tips_curve_missing",
        "real_rates_breakeven_curve_missing",
        "real_rates_forward_inflation_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("real_rates_")
    )
    assert "rates/expectations" not in str(view["related_routes"])


def test_credit_stress_module_read_adds_credit_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["credit:hy_oas"] = _feature_with_history(
        "credit:hy_oas",
        [
            ("2026-02-19", 3.5),
            ("2026-04-20", 3.7),
            ("2026-05-13", 3.9),
            ("2026-05-20", 4.2),
        ],
    )
    features["credit:ig_oas"] = _feature_with_history(
        "credit:ig_oas",
        [
            ("2026-02-19", 1.0),
            ("2026-04-20", 1.05),
            ("2026-05-13", 1.1),
            ("2026-05-20", 1.2),
        ],
    )
    features["credit:hy_ccc_oas"] = _feature_with_history(
        "credit:hy_ccc_oas",
        [
            ("2026-02-19", 7.2),
            ("2026-04-20", 8.0),
            ("2026-05-13", 8.3),
            ("2026-05-20", 9.5),
        ],
    )
    features["asset:hyg"] = _feature_with_history(
        "asset:hyg",
        [
            ("2026-02-19", 75.0),
            ("2026-04-20", 78.0),
            ("2026-05-13", 79.0),
            ("2026-05-20", 78.0),
        ],
        unit="usd",
        source_name="yahoo",
    )
    features["asset:lqd"] = _feature_with_history(
        "asset:lqd",
        [
            ("2026-02-19", 105.0),
            ("2026-04-20", 107.0),
            ("2026-05-13", 108.0),
            ("2026-05-20", 109.0),
        ],
        unit="usd",
        source_name="yahoo",
    )
    features["credit:nfci"] = _feature_with_history(
        "credit:nfci",
        [
            ("2026-02-19", -0.6),
            ("2026-04-20", -0.4),
            ("2026-05-13", -0.3),
            ("2026-05-20", -0.1),
        ],
        unit="index",
    )
    features["credit:anfci"] = _feature_with_history(
        "credit:anfci",
        [
            ("2026-02-19", -0.7),
            ("2026-04-20", -0.5),
            ("2026-05-13", -0.4),
            ("2026-05-20", -0.3),
        ],
        unit="index",
    )
    features["credit:sloos_ci_large_tightening"] = _feature_with_history(
        "credit:sloos_ci_large_tightening",
        [
            ("2026-02-19", 18.0),
            ("2026-04-20", 24.0),
            ("2026-05-13", 26.0),
            ("2026-05-20", 30.0),
        ],
    )

    view = build_macro_module_view("credit/stress", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["credit_diagnostics"]
    assert diagnostics["regime"] == "tail_widening"
    assert diagnostics["regime_label"] == "尾部走阔"
    assert diagnostics["summary"] == "信用尾部走阔：HY OAS 与 CCC-HY 尾部同时上行，高 beta 需要降级。"
    assert diagnostics["rows"] == [
        {
            "key": "hy_oas",
            "label": "HY OAS",
            "current_bp": 420.0,
            "change_1w_bp": 30.0,
            "change_1m_bp": 50.0,
            "change_3m_bp": 70.0,
            "status": "widening",
            "status_label": "走阔",
        },
        {
            "key": "ig_oas",
            "label": "IG OAS",
            "current_bp": 120.0,
            "change_1w_bp": 10.0,
            "change_1m_bp": 15.0,
            "change_3m_bp": 20.0,
            "status": "widening",
            "status_label": "走阔",
        },
        {
            "key": "ccc_hy_tail",
            "label": "CCC-HY 尾部",
            "current_bp": 530.0,
            "change_1w_bp": 90.0,
            "change_1m_bp": 100.0,
            "change_3m_bp": 160.0,
            "status": "tail_widening",
            "status_label": "尾部恶化",
        },
        {
            "key": "hyg_lqd_relative",
            "label": "HYG/LQD 信用 ETF",
            "hyg_1w_pct": -1.27,
            "lqd_1w_pct": 0.93,
            "relative_1w_pct": -2.19,
            "hyg_1m_pct": 0.0,
            "lqd_1m_pct": 1.87,
            "relative_1m_pct": -1.87,
            "status": "etf_pressure",
            "status_label": "HYG跑输",
        },
        {
            "key": "nfci",
            "label": "NFCI 金融条件",
            "current_index": -0.1,
            "change_1w_index": 0.2,
            "change_1m_index": 0.3,
            "change_3m_index": 0.5,
            "adjusted_index": -0.3,
            "status": "conditions_tightening",
            "status_label": "金融条件收紧",
        },
        {
            "key": "sloos_ci_large_tightening",
            "label": "SLOOS 大中型收紧",
            "current_pct": 30.0,
            "change_1q_pct": 12.0,
            "status": "tightening",
            "status_label": "银行收紧",
        },
    ]
    assert diagnostics["implications"] == ["信用尾部恶化：降低高 beta、盈利下修和融资敏感资产暴露。"]
    assert diagnostics["invalidations"] == ["若 HY OAS 1m 收窄且 CCC-HY 尾部回落，信用压力降级。"]


def test_credit_stress_module_read_promotes_hyg_lqd_pressure_when_spreads_lag() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["credit:hy_oas"] = _feature_with_history(
        "credit:hy_oas",
        [
            ("2026-04-20", 3.9),
            ("2026-05-13", 4.0),
            ("2026-05-20", 4.0),
        ],
    )
    features["credit:ig_oas"] = _feature_with_history(
        "credit:ig_oas",
        [
            ("2026-04-20", 1.05),
            ("2026-05-13", 1.1),
            ("2026-05-20", 1.1),
        ],
    )
    features["credit:hy_ccc_oas"] = _feature_with_history(
        "credit:hy_ccc_oas",
        [
            ("2026-04-20", 8.0),
            ("2026-05-13", 8.0),
            ("2026-05-20", 8.0),
        ],
    )
    features["asset:hyg"] = _feature_with_history(
        "asset:hyg",
        [
            ("2026-04-20", 80.0),
            ("2026-05-13", 79.5),
            ("2026-05-20", 78.0),
        ],
        unit="usd",
        source_name="yahoo",
    )
    features["asset:lqd"] = _feature_with_history(
        "asset:lqd",
        [
            ("2026-04-20", 107.0),
            ("2026-05-13", 108.0),
            ("2026-05-20", 109.0),
        ],
        unit="usd",
        source_name="yahoo",
    )

    view = build_macro_module_view("credit/stress", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["credit_diagnostics"]
    assert diagnostics["regime"] == "credit_etf_pressure"
    assert diagnostics["regime_label"] == "ETF 压力"
    assert diagnostics["summary"] == "信用 ETF 压力：HYG 跑输 LQD，现金信用尚未完全确认，先降低高收益 beta。"
    assert diagnostics["implications"] == ["信用 ETF 走弱：低配高收益信用，优先 LQD/BIL 防守。"]
    assert diagnostics["invalidations"] == ["若 HYG 相对 LQD 重新走强且 HY OAS 未走阔，ETF 压力读法降级。"]


def test_credit_stress_module_read_promotes_nfci_tightening_when_spreads_lag() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["credit:hy_oas"] = _feature_with_history(
        "credit:hy_oas",
        [
            ("2026-04-20", 3.9),
            ("2026-05-13", 4.0),
            ("2026-05-20", 4.0),
        ],
    )
    features["credit:ig_oas"] = _feature_with_history(
        "credit:ig_oas",
        [
            ("2026-04-20", 1.05),
            ("2026-05-13", 1.1),
            ("2026-05-20", 1.1),
        ],
    )
    features["credit:hy_ccc_oas"] = _feature_with_history(
        "credit:hy_ccc_oas",
        [
            ("2026-04-20", 8.0),
            ("2026-05-13", 8.0),
            ("2026-05-20", 8.0),
        ],
    )
    features["credit:nfci"] = _feature_with_history(
        "credit:nfci",
        [
            ("2026-04-20", -0.4),
            ("2026-05-13", -0.2),
            ("2026-05-20", 0.1),
        ],
        unit="index",
    )

    view = build_macro_module_view("credit/stress", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["credit_diagnostics"]
    assert diagnostics["regime"] == "financial_conditions_tightening"
    assert diagnostics["regime_label"] == "金融条件收紧"
    assert diagnostics["summary"] == "金融条件收紧：NFCI 已经升温，但信用利差尚未完全扩散，警惕滞后确认。"
    assert diagnostics["implications"] == ["金融条件收紧：降低对利差尚未反应的信用 beta 和长久期风险资产暴露。"]
    assert diagnostics["invalidations"] == ["若 NFCI 回落且 HY/IG OAS 未继续走阔，金融条件收紧读法降级。"]


def test_credit_stress_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    features = snapshot["features_json"]
    for concept_key, value in (
        ("credit:ig_oas", 1.1),
        ("credit:hy_oas", 4.0),
        ("credit:hy_ccc_oas", 8.0),
        ("vol:vix", 17.0),
    ):
        features[concept_key] = _feature_with_history(
            concept_key,
            [
                ("2026-05-13", value),
                ("2026-05-20", value),
            ],
            unit="percent" if concept_key.startswith("credit:") else "index",
            source_name="fred",
        )

    view = build_macro_module_view("credit/stress", snapshot=snapshot, observations=[])

    assert view["data_health"]["summary_status"] == "partial"
    assert view["module_read"]["credit_diagnostics"]["regime"] == "contained"
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "credit_etf_pressure_missing",
        "credit_financial_conditions_missing",
        "credit_bank_lending_missing",
        "credit_loan_quality_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("credit_")
    )
    assert "credit/cds" not in str(view["related_routes"])


def test_volatility_vix_module_read_adds_volatility_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["vol:vix"] = _feature_with_history(
        "vol:vix",
        [
            ("2026-04-20", 21.0),
            ("2026-05-13", 19.0),
            ("2026-05-20", 16.9),
        ],
        unit="index",
    )
    features["vol:vix1d"] = _feature_with_history(
        "vol:vix1d",
        [
            ("2026-04-20", 20.0),
            ("2026-05-13", 18.0),
            ("2026-05-20", 17.3),
        ],
        unit="index",
        source_name="cboe",
    )
    features["vol:vix9d"] = _feature_with_history(
        "vol:vix9d",
        [
            ("2026-04-20", 20.0),
            ("2026-05-13", 18.5),
            ("2026-05-20", 18.0),
        ],
        unit="index",
        source_name="cboe",
    )
    features["vol:vix3m"] = _feature_with_history(
        "vol:vix3m",
        [
            ("2026-04-20", 25.0),
            ("2026-05-13", 24.2),
            ("2026-05-20", 23.8),
        ],
        unit="index",
    )
    features["asset:vixy"] = _feature_with_history(
        "asset:vixy",
        [
            ("2026-04-20", 20.0),
            ("2026-05-13", 20.0),
            ("2026-05-20", 18.0),
        ],
        unit="usd",
    )
    features["asset:vixm"] = _feature_with_history(
        "asset:vixm",
        [
            ("2026-04-20", 30.0),
            ("2026-05-13", 30.0),
            ("2026-05-20", 29.0),
        ],
        unit="usd",
    )
    features["vol:move"] = _feature_with_history(
        "vol:move",
        [
            ("2026-04-20", 80.0),
            ("2026-05-13", 78.0),
            ("2026-05-20", 74.0),
        ],
        unit="index",
    )
    features["vol:vxn"] = _feature_with_history(
        "vol:vxn",
        [
            ("2026-04-20", 25.0),
            ("2026-05-13", 22.0),
            ("2026-05-20", 20.5),
        ],
        unit="index",
    )
    features["vol:vvix"] = _feature_with_history(
        "vol:vvix",
        [
            ("2026-04-20", 84.0),
            ("2026-05-13", 86.0),
            ("2026-05-20", 88.0),
        ],
        unit="index",
        source_name="cboe",
    )
    features["vol:skew"] = _feature_with_history(
        "vol:skew",
        [
            ("2026-04-20", 138.0),
            ("2026-05-13", 141.0),
            ("2026-05-20", 143.75),
        ],
        unit="index",
        source_name="cboe",
    )

    view = build_macro_module_view("volatility/vix", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["volatility_diagnostics"]
    assert diagnostics["regime"] == "carry_contango"
    assert diagnostics["regime_label"] == "期限 Contango"
    assert diagnostics["summary"] == "波动率处于 Contango：VIX 回落且远期仍有溢价，短期风险偏 carry。"
    assert diagnostics["rows"] == [
        {
            "key": "vix_spot",
            "label": "VIX 现货",
            "current_index": 16.9,
            "change_1w_index": -2.1,
            "change_1m_index": -4.1,
            "status": "normal",
            "status_label": "正常",
        },
        {
            "key": "vix1d_vix",
            "label": "VIX1D-VIX 当日溢价",
            "current_points": 0.4,
            "change_1w_points": 1.4,
            "change_1m_points": 1.4,
            "status": "normal",
            "status_label": "正常",
        },
        {
            "key": "vix9d_vix",
            "label": "VIX9D-VIX 近端溢价",
            "current_points": 1.1,
            "change_1w_points": 1.6,
            "change_1m_points": 2.1,
            "status": "normal",
            "status_label": "正常",
        },
        {
            "key": "vix3m_vix",
            "label": "VIX3M-VIX 期限溢价",
            "current_points": 6.9,
            "change_1w_points": 1.7,
            "change_1m_points": 2.9,
            "status": "contango",
            "status_label": "Contango",
        },
        {
            "key": "vvix",
            "label": "VVIX 波动率凸性",
            "current_index": 88.0,
            "change_1w_index": 2.0,
            "change_1m_index": 4.0,
            "status": "normal",
            "status_label": "正常",
        },
        {
            "key": "skew",
            "label": "SKEW 尾部风险",
            "current_index": 143.8,
            "change_1w_index": 2.8,
            "change_1m_index": 5.8,
            "status": "tail_premium",
            "status_label": "尾部溢价",
        },
        {
            "key": "move",
            "label": "MOVE 美债波动率",
            "current_index": 74.0,
            "change_1w_index": -4.0,
            "change_1m_index": -6.0,
            "status": "normal",
            "status_label": "正常",
        },
        {
            "key": "vixy_vixm",
            "label": "VIXY/VIXM 前端压力",
            "current_ratio": 0.62,
            "change_1w_pct": -6.67,
            "change_1m_pct": -6.67,
            "status": "front_relief",
            "status_label": "前端回落",
        },
        {
            "key": "vxn",
            "label": "VXN 纳指波动率",
            "current_index": 20.5,
            "change_1w_index": -1.5,
            "change_1m_index": -4.5,
            "status": "elevated",
            "status_label": "偏高",
        },
    ]
    assert diagnostics["implications"] == ["波动率 carry：风险资产可维持暴露，但不追杠杆，等待 VIX3M-VIX 收窄确认。"]
    assert diagnostics["invalidations"] == ["若 VIX3M-VIX 转负或 VIX 单周上行超过 5 点，carry 读法失效。"]
    tile_sources = {tile["concept_key"]: tile["source_label"] for tile in view["tiles"]}
    assert tile_sources["vol:vix1d"] == "Cboe"
    assert tile_sources["vol:vix9d"] == "Cboe"
    assert tile_sources["vol:vvix"] == "Cboe"
    assert tile_sources["vol:skew"] == "Cboe"
    volatility_table = next(table for table in view["tables"] if table["id"] == "vix_term_proxy_table")
    row_sources = {
        row["row_id"]: row["cells"]["source"]["display_value"]
        for row in volatility_table["rows"]
        if row["row_id"] in {"vol:vix1d", "vol:vix9d", "vol:vvix", "vol:skew"}
    }
    assert row_sources == {"vol:vix1d": "Cboe", "vol:vix9d": "Cboe", "vol:vvix": "Cboe", "vol:skew": "Cboe"}


def test_volatility_vix_module_merges_module_observation_history_for_existing_features() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["vol:vix"] = _feature("vol:vix", 16.9, unit="index", source_name="fred")
    features["vol:vix9d"] = _feature("vol:vix9d", 18.0, unit="index", source_name="cboe")

    view = build_macro_module_view(
        "volatility/vix",
        snapshot=snapshot,
        observations=[
            _obs("vol:vix", "2026-04-20", 21.0, unit="index", source_name="fred"),
            _obs("vol:vix9d", "2026-04-20", 20.0, unit="index", source_name="cboe"),
            _obs("vol:vix", "2026-05-13", 19.0, unit="index", source_name="fred"),
            _obs("vol:vix9d", "2026-05-13", 18.5, unit="index", source_name="cboe"),
            _obs("vol:vix", "2026-05-20", 16.9, unit="index", source_name="fred"),
            _obs("vol:vix9d", "2026-05-20", 18.0, unit="index", source_name="cboe"),
        ],
    )

    vix9d_tile = next(tile for tile in view["tiles"] if tile["concept_key"] == "vol:vix9d")
    assert vix9d_tile["history_points"] == 3
    assert vix9d_tile["source_label"] == "Cboe"
    vix9d_spread = next(
        row for row in view["module_read"]["volatility_diagnostics"]["rows"] if row["key"] == "vix9d_vix"
    )
    assert vix9d_spread == {
        "key": "vix9d_vix",
        "label": "VIX9D-VIX 近端溢价",
        "current_points": 1.1,
        "change_1w_points": 1.6,
        "change_1m_points": 2.1,
        "status": "normal",
        "status_label": "正常",
    }


def test_volatility_diagnostics_marks_single_point_front_etf_as_insufficient_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["vol:vix"] = _feature_with_history(
        "vol:vix",
        [("2026-04-20", 21.0), ("2026-05-13", 19.0), ("2026-05-20", 16.9)],
        unit="index",
        source_name="fred",
    )
    features["asset:vixy"] = _feature("asset:vixy", 18.6, unit="usd", source_name="yahoo")
    features["asset:vixm"] = _feature("asset:vixm", 30.0, unit="usd", source_name="yahoo")

    view = build_macro_module_view("volatility/vix", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["volatility_diagnostics"]
    rows_by_key = {row["key"]: row for row in diagnostics["rows"]}
    assert rows_by_key["vixy_vixm"]["status"] == "insufficient_history"
    assert rows_by_key["vixy_vixm"]["status_label"] == "样本不足"
    assert "待确认" not in str(diagnostics)


def test_volatility_vix_data_health_marks_missing_implemented_depth_sources() -> None:
    view = build_macro_module_view(
        "volatility/vix",
        snapshot=_snapshot(),
        observations=[
            _obs("vol:vix", "2026-05-13", 19.0, unit="index", source_name="fred"),
            _obs("vol:vix", "2026-05-20", 16.9, unit="index", source_name="fred"),
            _obs("vol:vix3m", "2026-05-13", 24.0, unit="index", source_name="fred"),
            _obs("vol:vix3m", "2026-05-20", 23.8, unit="index", source_name="fred"),
        ],
    )

    assert view["data_health"]["summary_status"] == "partial"
    assert view["module_read"]["volatility_diagnostics"]["regime"] == "carry_contango"
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "vol_event_premium_missing",
        "vol_tail_depth_missing",
        "vol_rates_vol_missing",
        "vol_futures_proxy_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("vol_")
    )
    assert "volatility/dashboard" not in str(view["related_routes"])


def test_liquidity_rrp_tga_module_read_adds_liquidity_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["liquidity:sofr"] = _feature_with_history(
        "liquidity:sofr",
        [
            ("2026-04-20", 4.36),
            ("2026-05-13", 4.41),
            ("2026-05-20", 4.47),
        ],
    )
    features["fed:iorb"] = _feature_with_history(
        "fed:iorb",
        [
            ("2026-04-20", 4.40),
            ("2026-05-13", 4.40),
            ("2026-05-20", 4.40),
        ],
    )
    features["liquidity:tgcr"] = _feature_with_history(
        "liquidity:tgcr",
        [
            ("2026-04-20", 4.35),
            ("2026-05-13", 4.37),
            ("2026-05-20", 4.38),
        ],
    )
    features["liquidity:sofr_volume"] = _feature_with_history(
        "liquidity:sofr_volume",
        [
            ("2026-04-20", 2_700_000.0),
            ("2026-05-13", 2_850_000.0),
            ("2026-05-20", 3_023_000.0),
        ],
        unit="million_usd",
    )
    features["liquidity:on_rrp"] = _feature_with_history(
        "liquidity:on_rrp",
        [
            ("2026-04-20", 900_000.0),
            ("2026-05-13", 820_000.0),
            ("2026-05-20", 760_000.0),
        ],
        unit="million_usd",
    )
    features["liquidity:tga"] = _feature_with_history(
        "liquidity:tga",
        [
            ("2026-04-20", 600_000.0),
            ("2026-05-13", 690_000.0),
            ("2026-05-20", 760_000.0),
        ],
        unit="million_usd",
    )
    features["liquidity:fed_assets"] = _feature_with_history(
        "liquidity:fed_assets",
        [
            ("2026-04-20", 7_400_000.0),
            ("2026-05-13", 7_350_000.0),
            ("2026-05-20", 7_300_000.0),
        ],
        unit="million_usd",
    )

    view = build_macro_module_view("liquidity/rrp-tga", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["liquidity_diagnostics"]
    assert diagnostics["regime"] == "corridor_drain"
    assert diagnostics["regime_label"] == "走廊抽水"
    assert diagnostics["summary"] == "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。"
    assert diagnostics["rows"] == [
        {
            "key": "sofr_iorb",
            "label": "SOFR-IORB 走廊压力",
            "current_bp": 7.0,
            "change_1w_bp": 6.0,
            "change_1m_bp": 11.0,
            "status": "corridor_pressure",
            "status_label": "走廊压力",
        },
        {
            "key": "sofr_tgcr",
            "label": "SOFR-TGCR 深度压力",
            "current_bp": 9.0,
            "change_1w_bp": 5.0,
            "change_1m_bp": 8.0,
            "status": "repo_depth_pressure",
            "status_label": "Repo 深度压力",
        },
        {
            "key": "sofr_volume",
            "label": "SOFR 成交量",
            "current_bn": 3023.0,
            "change_1w_bn": 173.0,
            "change_1m_bn": 323.0,
            "status": "volume_expansion",
            "status_label": "成交放大",
        },
        {
            "key": "on_rrp",
            "label": "RRP 缓冲",
            "current_bn": 760.0,
            "change_1w_bn": -60.0,
            "change_1m_bn": -140.0,
            "status": "buffer_drawdown",
            "status_label": "缓冲消耗",
        },
        {
            "key": "tga",
            "label": "TGA 财政现金",
            "current_bn": 760.0,
            "change_1w_bn": 70.0,
            "change_1m_bn": 160.0,
            "status": "treasury_drain",
            "status_label": "财政抽水",
        },
        {
            "key": "net_liquidity",
            "label": "净流动性",
            "current_trillion": 5.78,
            "change_1w_bn": -60.0,
            "change_1m_bn": -120.0,
            "status": "net_drain",
            "status_label": "净抽水",
        },
    ]
    assert diagnostics["implications"] == ["流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。"]
    assert diagnostics["invalidations"] == ["若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。"]


def test_liquidity_rrp_tga_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    features = snapshot["features_json"]
    features["liquidity:on_rrp"] = _feature_with_history(
        "liquidity:on_rrp",
        [
            ("2026-05-13", 760_000.0),
            ("2026-05-20", 760_000.0),
        ],
        unit="million_usd",
    )
    features["liquidity:tga"] = _feature_with_history(
        "liquidity:tga",
        [
            ("2026-05-13", 760_000.0),
            ("2026-05-20", 760_000.0),
        ],
        unit="million_usd",
    )

    view = build_macro_module_view("liquidity/rrp-tga", snapshot=snapshot, observations=[])

    assert view["module_read"]["liquidity_diagnostics"]["regime"] == "neutral"
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "liquidity_balance_sheet_missing",
        "liquidity_secured_corridor_missing",
        "liquidity_repo_depth_missing",
        "liquidity_volume_depth_missing",
        "liquidity_nyfed_operations_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("liquidity_")
    )
    assert "liquidity/subsurface" not in str(view["related_routes"])


def test_liquidity_diagnostics_marks_single_point_volume_as_insufficient_history() -> None:
    snapshot = _snapshot()
    _add_liquidity_pressure_features(snapshot["features_json"])
    snapshot["features_json"]["liquidity:sofr_volume"] = _feature(
        "liquidity:sofr_volume",
        3_023_000.0,
        unit="million_usd",
        source_name="ny_fed",
    )

    view = build_macro_module_view("liquidity/rrp-tga", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["liquidity_diagnostics"]
    rows_by_key = {row["key"]: row for row in diagnostics["rows"]}
    assert rows_by_key["sofr_volume"]["status"] == "insufficient_history"
    assert rows_by_key["sofr_volume"]["status_label"] == "样本不足"
    assert "待确认" not in str(diagnostics)


def test_liquidity_rrp_tga_module_uses_module_observations_for_repo_depth_optional_series() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["liquidity:sofr"] = _feature_with_history(
        "liquidity:sofr",
        [("2026-06-08", 3.63), ("2026-06-15", 3.69)],
    )
    features["fed:iorb"] = _feature_with_history(
        "fed:iorb",
        [("2026-06-08", 3.65), ("2026-06-15", 3.65)],
    )
    view = build_macro_module_view(
        "liquidity/rrp-tga",
        snapshot=snapshot,
        observations=[
            _obs("liquidity:on_rrp", "2026-06-15", 10_721.0, unit="millions_usd", source_name="fred"),
            _obs("liquidity:tga", "2026-06-15", 816_023.0, unit="millions_usd", source_name="treasury"),
            _obs("liquidity:fed_assets", "2026-06-15", 6_725_397.0, unit="millions_usd", source_name="fred"),
            _obs("liquidity:reserve_balances", "2026-06-15", 3_276_208.0, unit="millions_usd", source_name="fred"),
            _obs("liquidity:sofr", "2026-06-15", 3.69, unit="percent", source_name="nyfed"),
            _obs("liquidity:bgcr", "2026-06-15", 3.67, unit="percent", source_name="nyfed"),
            _obs("liquidity:tgcr", "2026-06-15", 3.67, unit="percent", source_name="nyfed"),
            _obs("liquidity:sofr_volume", "2026-06-15", 3_147_000.0, unit="millions_usd", source_name="nyfed"),
            _obs("liquidity:bgcr_volume", "2026-06-15", 1_297_000.0, unit="millions_usd", source_name="nyfed"),
            _obs("liquidity:tgcr_volume", "2026-06-15", 1_267_000.0, unit="millions_usd", source_name="nyfed"),
            _obs("fed:iorb", "2026-06-15", 3.65, unit="percent", source_name="fred"),
            _obs("liquidity:nyfed_rrp", "2026-06-15", 10_721.0, unit="millions_usd", source_name="nyfed"),
            _obs("liquidity:srf", "2026-06-15", 21.0, unit="millions_usd", source_name="nyfed"),
        ],
    )

    assert view["module_read"]["confidence_label"] == "模块覆盖 13/13"
    assert {tile["concept_key"] for tile in view["tiles"]} >= {
        "liquidity:fed_assets",
        "liquidity:reserve_balances",
        "liquidity:bgcr",
        "liquidity:tgcr",
        "liquidity:sofr_volume",
        "liquidity:bgcr_volume",
        "liquidity:tgcr_volume",
    }
    repo_rows = view["module_read"]["liquidity_diagnostics"]["rows"]
    assert {
        row["key"]: {key: value for key, value in row.items() if key in {"current_bp", "current_bn", "status"}}
        for row in repo_rows
        if row["key"] in {"sofr_tgcr", "sofr_volume"}
    } == {
        "sofr_tgcr": {"current_bp": 2.0, "status": "repo_depth_watch"},
        "sofr_volume": {"current_bn": 3147.0, "status": "insufficient_history"},
    }
    repo_table_rows = [
        row["row_id"]
        for table in view["tables"]
        for row in table["rows"]
        if row["row_id"]
        in {
            "liquidity:fed_assets",
            "liquidity:reserve_balances",
            "liquidity:bgcr",
            "liquidity:tgcr",
            "liquidity:sofr_volume",
        }
    ]
    assert repo_table_rows == [
        "liquidity:fed_assets",
        "liquidity:reserve_balances",
        "liquidity:bgcr",
        "liquidity:tgcr",
        "liquidity:sofr_volume",
    ]
    contradiction_codes = {item["code"] for item in view["module_evidence"]["contradictions"]}
    assert "module_concept_missing:liquidity:sofr_volume" not in contradiction_codes


def test_inflation_module_read_adds_inflation_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["inflation:cpi"] = _feature_with_history(
        "inflation:cpi",
        [
            ("2025-04-20", 300.0),
            ("2025-05-20", 302.0),
            ("2026-04-20", 312.0),
            ("2026-05-20", 318.0),
        ],
        unit="index",
    )
    features["inflation:core_cpi"] = _feature_with_history(
        "inflation:core_cpi",
        [
            ("2025-04-20", 300.0),
            ("2025-05-20", 301.0),
            ("2026-04-20", 313.0),
            ("2026-05-20", 318.0),
        ],
        unit="index",
    )
    features["inflation:ppi"] = _feature_with_history(
        "inflation:ppi",
        [
            ("2025-04-20", 100.0),
            ("2025-05-20", 101.0),
            ("2026-04-20", 106.0),
            ("2026-05-20", 108.0),
        ],
        unit="index",
    )
    features["inflation:10y_breakeven"] = _feature_with_history(
        "inflation:10y_breakeven",
        [
            ("2026-04-20", 2.30),
            ("2026-05-13", 2.45),
            ("2026-05-20", 2.55),
        ],
    )

    view = build_macro_module_view("economy/inflation", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["inflation_diagnostics"]
    assert diagnostics["regime"] == "reaccelerating"
    assert diagnostics["regime_label"] == "通胀再加速"
    assert diagnostics["summary"] == "通胀再加速：CPI/Core CPI 同比重新上行且通胀补偿走阔，降息交易需要降级。"
    assert diagnostics["rows"] == [
        {
            "key": "cpi_yoy",
            "label": "CPI 同比",
            "current_yoy_pct": 5.3,
            "change_1m_pct": 1.3,
            "status": "accelerating",
            "status_label": "加速",
        },
        {
            "key": "core_cpi_yoy",
            "label": "核心 CPI 同比",
            "current_yoy_pct": 5.65,
            "change_1m_pct": 1.32,
            "status": "accelerating",
            "status_label": "加速",
        },
        {
            "key": "ppi_yoy",
            "label": "PPI 同比",
            "current_yoy_pct": 6.93,
            "change_1m_pct": 0.93,
            "status": "pipeline_pressure",
            "status_label": "上游压力",
        },
        {
            "key": "breakeven_10y",
            "label": "10Y 通胀补偿",
            "current_pct": 2.55,
            "change_1w_bp": 10.0,
            "change_1m_bp": 25.0,
            "status": "expectation_pressure",
            "status_label": "预期升温",
        },
    ]
    assert diagnostics["implications"] == ["通胀再加速：降低降息受益、长久期成长和高 beta 反弹置信度。"]
    assert diagnostics["invalidations"] == ["若核心 CPI 同比回落且 10Y 通胀补偿 1m 收窄超过 10bp，再加速读法降级。"]


def test_inflation_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    features = snapshot["features_json"]
    features["inflation:cpi"] = _feature_with_history(
        "inflation:cpi",
        [
            ("2025-04-20", 300.0),
            ("2025-05-20", 302.0),
            ("2026-04-20", 312.0),
            ("2026-05-20", 318.0),
        ],
        unit="index",
    )
    features["inflation:core_cpi"] = _feature_with_history(
        "inflation:core_cpi",
        [
            ("2025-04-20", 300.0),
            ("2025-05-20", 301.0),
            ("2026-04-20", 313.0),
            ("2026-05-20", 318.0),
        ],
        unit="index",
    )
    features["inflation:ppi"] = _feature_with_history(
        "inflation:ppi",
        [
            ("2025-04-20", 100.0),
            ("2025-05-20", 101.0),
            ("2026-04-20", 106.0),
            ("2026-05-20", 108.0),
        ],
        unit="index",
    )

    view = build_macro_module_view("economy/inflation", snapshot=snapshot, observations=[])

    assert view["module_read"]["inflation_diagnostics"]["rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "inflation_pce_missing",
        "inflation_deflator_missing",
        "inflation_market_expectations_missing",
        "inflation_consumer_expectations_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("inflation_")
    )
    assert "calendar" not in str(view["related_routes"])


def test_employment_module_read_adds_employment_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["labor:unemployment"] = _feature_with_history(
        "labor:unemployment",
        [
            ("2026-03-20", 3.9),
            ("2026-04-20", 4.0),
            ("2026-05-20", 4.3),
        ],
    )
    features["labor:payrolls"] = _feature_with_history(
        "labor:payrolls",
        [
            ("2026-03-20", 158_000.0),
            ("2026-04-20", 158_220.0),
            ("2026-05-20", 158_300.0),
        ],
        unit="thousand_persons",
    )
    features["labor:initial_claims"] = _feature_with_history(
        "labor:initial_claims",
        [
            ("2026-04-20", 230_000.0),
            ("2026-05-13", 256_000.0),
            ("2026-05-20", 260_000.0),
        ],
        unit="persons",
    )
    features["labor:job_openings"] = _feature_with_history(
        "labor:job_openings",
        [
            ("2026-04-20", 8_000.0),
            ("2026-05-20", 7_400.0),
        ],
        unit="thousand_persons",
    )
    features["labor:avg_hourly_earnings"] = _feature_with_history(
        "labor:avg_hourly_earnings",
        [
            ("2025-04-20", 35.0),
            ("2025-05-20", 35.2),
            ("2026-04-20", 36.6),
            ("2026-05-20", 36.5),
        ],
        unit="usd_per_hour",
    )

    view = build_macro_module_view("economy/employment", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["employment_diagnostics"]
    assert diagnostics["regime"] == "labor_cooling"
    assert diagnostics["regime_label"] == "就业降温"
    assert diagnostics["summary"] == "就业降温：失业率与初请上行、非农动能放缓，增长风险开始压过软着陆叙事。"
    assert diagnostics["rows"] == [
        {
            "key": "unemployment_rate",
            "label": "失业率",
            "current_pct": 4.3,
            "change_1m_pct": 0.3,
            "status": "deteriorating",
            "status_label": "走弱",
        },
        {
            "key": "payroll_gain",
            "label": "非农新增",
            "current_k": 80.0,
            "change_1m_k": -140.0,
            "status": "slowing",
            "status_label": "放缓",
        },
        {
            "key": "initial_claims",
            "label": "初请失业金",
            "current_k": 260.0,
            "change_1w_k": 4.0,
            "change_1m_k": 30.0,
            "status": "claims_rising",
            "status_label": "初请上行",
        },
        {
            "key": "job_openings",
            "label": "职位空缺",
            "current_m": 7.4,
            "change_1m_m": -0.6,
            "status": "demand_cooling",
            "status_label": "需求降温",
        },
        {
            "key": "wage_yoy",
            "label": "平均时薪同比",
            "current_yoy_pct": 3.69,
            "change_1m_pct": -0.88,
            "status": "wage_cooling",
            "status_label": "工资降温",
        },
    ]
    assert diagnostics["implications"] == ["就业降温：降低盈利周期和高 beta 置信度，降息交易需等待通胀同步配合。"]
    assert diagnostics["invalidations"] == ["若非农新增重新高于 180k 且初请 1m 回落超过 20k，就业降温读法降级。"]


def test_employment_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    features = snapshot["features_json"]
    features["labor:unemployment"] = _feature_with_history(
        "labor:unemployment",
        [
            ("2026-03-20", 3.9),
            ("2026-04-20", 4.0),
            ("2026-05-20", 4.3),
        ],
    )
    features["labor:payrolls"] = _feature_with_history(
        "labor:payrolls",
        [
            ("2026-03-20", 158_000.0),
            ("2026-04-20", 158_220.0),
            ("2026-05-20", 158_300.0),
        ],
        unit="thousand_persons",
    )
    features["labor:initial_claims"] = _feature_with_history(
        "labor:initial_claims",
        [
            ("2026-04-20", 230_000.0),
            ("2026-05-13", 256_000.0),
            ("2026-05-20", 260_000.0),
        ],
        unit="persons",
    )

    view = build_macro_module_view("economy/employment", snapshot=snapshot, observations=[])

    assert view["module_read"]["employment_diagnostics"]["regime"] == "labor_cooling"
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "employment_job_openings_missing",
        "employment_wage_missing",
        "employment_participation_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("employment_")
    )
    assert "calendar" not in str(view["related_routes"])


def test_gdp_module_read_adds_growth_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["economy:gdp_real"] = _feature_with_history(
        "economy:gdp_real",
        [
            ("2025-03-31", 22_000.0),
            ("2025-06-30", 22_200.0),
            ("2026-03-31", 22_600.0),
            ("2026-06-30", 22_620.0),
        ],
        unit="billion_usd",
    )
    features["economy:gdp_nowcast"] = _feature_with_history(
        "economy:gdp_nowcast",
        [
            ("2026-05-20", 3.2),
            ("2026-06-20", 1.5),
        ],
        unit="percent_saar",
    )
    features["economy:industrial_production"] = _feature_with_history(
        "economy:industrial_production",
        [
            ("2025-04-20", 100.0),
            ("2025-05-20", 100.0),
            ("2026-04-20", 100.5),
            ("2026-05-20", 98.5),
        ],
        unit="index",
    )
    features["economy:housing_starts"] = _feature_with_history(
        "economy:housing_starts",
        [
            ("2026-04-20", 1_400.0),
            ("2026-05-20", 1_250.0),
        ],
        unit="thousand_units",
    )
    features["consumer:pce_real"] = _feature_with_history(
        "consumer:pce_real",
        [
            ("2025-04-20", 100.0),
            ("2025-05-20", 100.0),
            ("2026-04-20", 102.5),
            ("2026-05-20", 101.5),
        ],
        unit="index",
    )
    features["consumer:retail_sales"] = _feature_with_history(
        "consumer:retail_sales",
        [
            ("2025-04-20", 100.0),
            ("2025-05-20", 100.0),
            ("2026-04-20", 103.0),
            ("2026-05-20", 101.0),
        ],
        unit="index",
    )

    view = build_macro_module_view("economy/gdp", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["growth_diagnostics"]
    assert diagnostics["regime"] == "growth_cooling"
    assert diagnostics["regime_label"] == "增长降温"
    assert diagnostics["summary"] == "增长降温：实际 GDP、工业生产和消费动能同步放缓，风险资产盈利预期需要降级。"
    assert diagnostics["rows"] == [
        {
            "key": "real_gdp_yoy",
            "label": "实际 GDP 同比",
            "current_yoy_pct": 1.89,
            "change_1q_pct": -0.84,
            "status": "slowing",
            "status_label": "放缓",
        },
        {
            "key": "gdpnow_saar",
            "label": "GDPNow",
            "current_pct": 1.5,
            "change_1m_pct": -1.7,
            "status": "nowcast_cooling",
            "status_label": "Nowcast 降温",
        },
        {
            "key": "industrial_production_yoy",
            "label": "工业生产同比",
            "current_yoy_pct": -1.5,
            "change_1m_pct": -2.0,
            "status": "contracting",
            "status_label": "收缩",
        },
        {
            "key": "housing_starts",
            "label": "住房开工",
            "current_m": 1.25,
            "change_1m_k": -150.0,
            "status": "housing_drag",
            "status_label": "地产拖累",
        },
        {
            "key": "real_pce_yoy",
            "label": "实际 PCE 同比",
            "current_yoy_pct": 1.5,
            "change_1m_pct": -1.0,
            "status": "consumption_cooling",
            "status_label": "消费降温",
        },
        {
            "key": "retail_sales_yoy",
            "label": "零售销售同比",
            "current_yoy_pct": 1.0,
            "change_1m_pct": -2.0,
            "status": "demand_cooling",
            "status_label": "需求降温",
        },
    ]
    assert diagnostics["implications"] == ["增长降温：降低盈利周期和高 beta 暴露，等待就业或消费重新确认。"]
    assert diagnostics["invalidations"] == ["若实际 PCE 与工业生产同比回升且住房开工 1m 转正，增长降温读法降级。"]


def test_gdp_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    features = snapshot["features_json"]
    features["economy:gdp_real"] = _feature_with_history(
        "economy:gdp_real",
        [
            ("2025-03-31", 22_000.0),
            ("2025-06-30", 22_200.0),
            ("2026-03-31", 22_600.0),
            ("2026-06-30", 22_620.0),
        ],
        unit="billion_usd",
    )

    view = build_macro_module_view("economy/gdp", snapshot=snapshot, observations=[])

    assert view["module_read"]["growth_diagnostics"]["rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "growth_nominal_gdp_missing",
        "growth_nowcast_missing",
        "growth_production_housing_missing",
        "growth_consumption_missing",
        "growth_consumer_depth_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("growth_")
    )
    assert "economy/consumer" not in str(view["related_routes"])


def test_build_macro_module_view_returns_missing_v3_status_when_snapshot_is_absent() -> None:
    view = build_macro_module_view(
        "rates/fed-funds",
        snapshot=None,
        observations=[],
    )

    assert view["snapshot"]["status"] == "missing"
    assert view["snapshot"]["status_label"] == "缺失"
    assert view["snapshot"]["projection_version"] == "macro_module_view_v3"
    assert view["primary_chart"]["status"] == "missing"
    assert view["module_read"]["headline"] == "联邦基金与走廊：缺少快照"
    assert [gap["code"] for gap in view["data_health"]["module_gaps"]] == [
        "macro_view_snapshot_missing",
    ]


def test_build_macro_module_view_consumes_real_regime_v4_snapshot_without_crashing() -> None:
    snapshot = build_macro_view_snapshot(
        [
            _obs(concept_key, "2026-05-20", float(index + 1), unit="index", source_name="macro_import")
            for index, concept_key in enumerate(MACRO_CORE_CONCEPTS)
        ],
        computed_at_ms=NOW_MS,
    )

    view = build_macro_module_view(
        "assets/equities",
        snapshot=snapshot,
        observations=[],
    )

    assert view["snapshot"]["projection_version"] == "macro_module_view_v3"
    assert view["snapshot"]["source_projection_version"] == "macro_regime_v4"
    assert view["data_health"]["module_gaps"]
    assert all(isinstance(gap, dict) for gap in view["data_health"]["module_gaps"])
    assert view["primary_chart"]["status"] == "insufficient_history"
    assert "asset:spy" not in view["tiles"][0]["label"]


def test_assets_landing_module_view_includes_daily_brief_without_redirecting_to_equities() -> None:
    brief = {
        "brief_key": "assets_today",
        "projection_version": "macro_daily_brief_v1",
        "brief_date": "2026-05-20",
        "asof_date": "2026-05-20",
        "status": "partial",
        "headline": "今日判断：风险资产偏震荡",
        "blocks": [
            {"id": "cross_correlation", "title": "跨资产相关性", "stance": "neutral", "body": "股债相关性偏高。"}
        ],
    }

    view = build_macro_module_view("assets", snapshot=_snapshot(), observations=[], daily_brief=brief)

    assert view["snapshot"]["module_id"] == "assets"
    assert view["snapshot"]["route_path"] == "/macro/assets"
    assert view["snapshot"]["title"] == "大类资产"
    assert view["daily_brief"] == brief
    assert view["primary_chart"]["id"] == "asset_cross_market_snapshot"
    assert view["tables"][0]["id"] == "asset_group_snapshot"


def test_assets_landing_module_read_adds_cross_asset_diagnostics_from_history() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["asset:spx"] = _feature_with_history(
        "asset:spx",
        [
            ("2026-04-20", 100.0),
            ("2026-05-13", 98.0),
            ("2026-05-20", 95.0),
        ],
        unit="index",
        source_name="yahoo",
    )
    features["asset:tlt"] = _feature_with_history(
        "asset:tlt",
        [
            ("2026-04-20", 100.0),
            ("2026-05-13", 99.0),
            ("2026-05-20", 97.0),
        ],
        unit="usd",
        source_name="yahoo",
    )
    features["fx:dxy"] = _feature_with_history(
        "fx:dxy",
        [
            ("2026-04-20", 100.0),
            ("2026-05-13", 102.0),
            ("2026-05-20", 103.0),
        ],
        unit="index",
        source_name="yahoo",
    )
    features["commodity:wti_futures"] = _feature_with_history(
        "commodity:wti_futures",
        [
            ("2026-04-20", 80.0),
            ("2026-05-13", 82.0),
            ("2026-05-20", 88.0),
        ],
        unit="usd_per_barrel",
        source_name="yahoo",
    )
    features["crypto:btc"] = _feature_with_history(
        "crypto:btc",
        [
            ("2026-04-20", 100_000.0),
            ("2026-05-13", 95_000.0),
            ("2026-05-20", 92_000.0),
        ],
        unit="usd",
        source_name="yahoo",
    )
    features["vol:vix"] = _feature_with_history(
        "vol:vix",
        [
            ("2026-04-20", 16.0),
            ("2026-05-13", 18.0),
            ("2026-05-20", 22.0),
        ],
        unit="index",
    )
    features["credit:hy_oas"] = _feature_with_history(
        "credit:hy_oas",
        [
            ("2026-04-20", 3.0),
            ("2026-05-13", 3.1),
            ("2026-05-20", 3.4),
        ],
    )

    view = build_macro_module_view("assets", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["asset_diagnostics"]
    assert diagnostics["regime"] == "stagflation_shock"
    assert diagnostics["regime_label"] == "滞胀冲击"
    assert diagnostics["summary"] == "跨资产主线偏滞胀冲击：股债双杀、美元与能源走强，风险资产需要降档。"
    assert diagnostics["rows"] == [
        {
            "key": "spx",
            "label": "SPX",
            "change_1w_pct": -3.06,
            "change_1m_pct": -5.0,
            "status": "risk_off",
            "status_label": "风险降温",
        },
        {
            "key": "tlt",
            "label": "TLT",
            "change_1w_pct": -2.02,
            "change_1m_pct": -3.0,
            "status": "duration_pressure",
            "status_label": "久期承压",
        },
        {
            "key": "dxy",
            "label": "DXY",
            "change_1w_pct": 0.98,
            "change_1m_pct": 3.0,
            "status": "dollar_up",
            "status_label": "美元走强",
        },
        {
            "key": "wti",
            "label": "WTI",
            "change_1w_pct": 7.32,
            "change_1m_pct": 10.0,
            "status": "energy_up",
            "status_label": "能源上行",
        },
        {
            "key": "btc",
            "label": "BTC",
            "change_1w_pct": -3.16,
            "change_1m_pct": -8.0,
            "status": "crypto_beta_down",
            "status_label": "加密降温",
        },
        {
            "key": "vix",
            "label": "VIX",
            "current_index": 22.0,
            "change_1w_index": 4.0,
            "change_1m_index": 6.0,
            "status": "vol_up",
            "status_label": "波动升温",
        },
        {
            "key": "hy_oas",
            "label": "HY OAS",
            "current_bp": 340.0,
            "change_1w_bp": 30.0,
            "change_1m_bp": 40.0,
            "status": "credit_widening",
            "status_label": "信用走阔",
        },
    ]
    assert diagnostics["implications"] == ["滞胀冲击：降低权益/加密 beta，保留美元、能源或现金防守表达。"]
    assert diagnostics["invalidations"] == ["若 SPX/BTC 修复且 DXY、WTI、VIX 同步回落，滞胀冲击读法降级。"]


def test_asset_diagnostics_marks_single_point_rows_as_insufficient_history() -> None:
    snapshot = _snapshot()
    snapshot["features_json"]["asset:spx"] = _feature_with_history(
        "asset:spx",
        [("2026-04-20", 100.0), ("2026-05-13", 104.0), ("2026-05-20", 100.0)],
        unit="index",
        source_name="yahoo",
    )

    view = build_macro_module_view("assets", snapshot=snapshot, observations=[])

    diagnostics = view["module_read"]["asset_diagnostics"]
    rows_by_key = {row["key"]: row for row in diagnostics["rows"]}
    assert rows_by_key["tlt"]["status"] == "insufficient_history"
    assert rows_by_key["tlt"]["status_label"] == "样本不足"
    assert rows_by_key["btc"]["status"] == "insufficient_history"
    assert rows_by_key["btc"]["status_label"] == "样本不足"
    assert "待确认" not in str(diagnostics)


def test_assets_landing_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    view = build_macro_module_view(
        "assets",
        snapshot=snapshot,
        observations=[
            _obs("asset:spx", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:spx", "2026-05-20", 104.0, unit="usd", source_name="yahoo"),
            _obs("rates:dgs10", "2026-05-13", 4.4, unit="percent", source_name="fred"),
            _obs("rates:dgs10", "2026-05-20", 4.5, unit="percent", source_name="fred"),
            _obs("fx:dxy", "2026-05-13", 100.0, unit="index", source_name="fred"),
            _obs("fx:dxy", "2026-05-20", 101.0, unit="index", source_name="fred"),
            _obs("commodity:wti_futures", "2026-05-13", 80.0, unit="usd", source_name="yahoo"),
            _obs("commodity:wti_futures", "2026-05-20", 84.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-20", 106.0, unit="usd", source_name="yahoo"),
        ],
    )

    assert view["module_read"]["asset_diagnostics"]["rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "asset_risk_breadth_missing",
        "asset_duration_proxy_missing",
        "asset_credit_stress_missing",
        "asset_volatility_missing",
        "asset_commodity_depth_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("asset_")
    )
    assert "assets/crypto-derivatives" not in str(view["related_routes"])


def test_equities_module_read_adds_asset_class_diagnostics_from_module_history() -> None:
    view = build_macro_module_view(
        "assets/equities",
        snapshot=_snapshot(),
        observations=[
            _obs("asset:spx", "2026-04-20", 100.0, unit="index", source_name="yahoo"),
            _obs("asset:spx", "2026-05-13", 104.0, unit="index", source_name="yahoo"),
            _obs("asset:spx", "2026-05-20", 100.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-04-20", 100.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-13", 110.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-20", 105.0, unit="index", source_name="yahoo"),
            _obs("asset:rut", "2026-04-20", 100.0, unit="index", source_name="yahoo"),
            _obs("asset:rut", "2026-05-13", 94.0, unit="index", source_name="yahoo"),
            _obs("asset:rut", "2026-05-20", 88.0, unit="index", source_name="yahoo"),
            _obs("asset:qqq", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:qqq", "2026-05-13", 109.0, unit="usd", source_name="yahoo"),
            _obs("asset:qqq", "2026-05-20", 104.0, unit="usd", source_name="yahoo"),
            _obs("asset:iwm", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:iwm", "2026-05-13", 95.0, unit="usd", source_name="yahoo"),
            _obs("asset:iwm", "2026-05-20", 88.0, unit="usd", source_name="yahoo"),
            _obs(
                "positioning:sp500_net_noncommercial",
                "2026-04-20",
                -20_000.0,
                unit="contracts",
                source_name="cftc",
            ),
            _obs(
                "positioning:sp500_net_noncommercial",
                "2026-05-13",
                -60_000.0,
                unit="contracts",
                source_name="cftc",
            ),
            _obs(
                "positioning:sp500_net_noncommercial",
                "2026-05-20",
                -120_000.0,
                unit="contracts",
                source_name="cftc",
            ),
        ],
    )

    diagnostics = view["module_read"]["asset_class_diagnostics"]
    assert diagnostics["regime"] == "equity_risk_off"
    assert diagnostics["regime_label"] == "美股降温"
    assert diagnostics["summary"] == "美股风险偏好走弱：大盘和成长承压，小盘/高 beta 未确认，风险资产需要降档。"
    assert diagnostics["rows"] == [
        {
            "key": "spx",
            "label": "SPX",
            "change_1w_pct": -3.85,
            "change_1m_pct": 0.0,
            "status": "risk_off",
            "status_label": "风险降温",
        },
        {
            "key": "ndx",
            "label": "NDX",
            "change_1w_pct": -4.55,
            "change_1m_pct": 5.0,
            "status": "risk_off",
            "status_label": "风险降温",
        },
        {
            "key": "rut",
            "label": "RUT",
            "change_1w_pct": -6.38,
            "change_1m_pct": -12.0,
            "status": "risk_off",
            "status_label": "风险降温",
        },
        {
            "key": "qqq",
            "label": "QQQ",
            "change_1w_pct": -4.59,
            "change_1m_pct": 4.0,
            "status": "risk_off",
            "status_label": "风险降温",
        },
        {
            "key": "iwm",
            "label": "IWM",
            "change_1w_pct": -7.37,
            "change_1m_pct": -12.0,
            "status": "risk_off",
            "status_label": "风险降温",
        },
        {
            "key": "sp500_positioning",
            "label": "CFTC S&P 净投机",
            "current_k": -120.0,
            "change_1w_k": -60.0,
            "change_1m_k": -100.0,
            "status": "positioning_defensive",
            "status_label": "仓位防守",
        },
    ]
    assert diagnostics["implications"] == ["美股降温：降低股票、加密 beta 和高收益信用暴露，等待小盘和成长股修复。"]
    assert diagnostics["invalidations"] == ["若 SPX/NDX 1w 转正且 RUT/IWM 不再跑输，美股降温读法降级。"]


def test_equities_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    view = build_macro_module_view(
        "assets/equities",
        snapshot=snapshot,
        observations=[
            _obs("asset:spx", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:spx", "2026-05-20", 104.0, unit="usd", source_name="yahoo"),
        ],
    )

    assert view["module_read"]["asset_class_diagnostics"]["rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "equity_growth_leadership_missing",
        "equity_small_caps_missing",
        "equity_global_sector_missing",
        "equity_positioning_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("equity_")
    )
    assert "options" not in str(view["related_routes"]).lower()


def test_bonds_module_read_adds_asset_class_diagnostics_from_module_history() -> None:
    view = build_macro_module_view(
        "assets/bonds",
        snapshot=_snapshot(),
        observations=[
            _obs("asset:tlt", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-13", 102.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-20", 96.0, unit="usd", source_name="yahoo"),
            _obs("asset:ief", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:ief", "2026-05-13", 101.0, unit="usd", source_name="yahoo"),
            _obs("asset:ief", "2026-05-20", 99.0, unit="usd", source_name="yahoo"),
            _obs("asset:lqd", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:lqd", "2026-05-13", 101.0, unit="usd", source_name="yahoo"),
            _obs("asset:lqd", "2026-05-20", 98.0, unit="usd", source_name="yahoo"),
            _obs("asset:hyg", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:hyg", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:hyg", "2026-05-20", 95.0, unit="usd", source_name="yahoo"),
            _obs("credit:hy_oas", "2026-04-20", 3.0, unit="percent", source_name="fred"),
            _obs("credit:hy_oas", "2026-05-13", 3.1, unit="percent", source_name="fred"),
            _obs("credit:hy_oas", "2026-05-20", 3.4, unit="percent", source_name="fred"),
            _obs("credit:ig_oas", "2026-04-20", 1.1, unit="percent", source_name="fred"),
            _obs("credit:ig_oas", "2026-05-13", 1.12, unit="percent", source_name="fred"),
            _obs("credit:ig_oas", "2026-05-20", 1.22, unit="percent", source_name="fred"),
        ],
    )

    diagnostics = view["module_read"]["asset_class_diagnostics"]
    assert diagnostics["regime"] == "bond_credit_pressure"
    assert diagnostics["regime_label"] == "信用久期双压"
    assert diagnostics["summary"] == "债券横截面偏防守：长久期回撤且 HYG 跑输 LQD，信用利差同步走阔。"
    assert diagnostics["rows"] == [
        {
            "key": "tlt",
            "label": "TLT",
            "change_1w_pct": -5.88,
            "change_1m_pct": -4.0,
            "status": "duration_pressure",
            "status_label": "久期承压",
        },
        {
            "key": "ief",
            "label": "IEF",
            "change_1w_pct": -1.98,
            "change_1m_pct": -1.0,
            "status": "duration_pressure",
            "status_label": "久期承压",
        },
        {
            "key": "lqd",
            "label": "LQD",
            "change_1w_pct": -2.97,
            "change_1m_pct": -2.0,
            "status": "credit_beta_down",
            "status_label": "信用承压",
        },
        {
            "key": "hyg",
            "label": "HYG",
            "change_1w_pct": -5.0,
            "change_1m_pct": -5.0,
            "status": "credit_beta_down",
            "status_label": "信用承压",
        },
        {
            "key": "hy_oas",
            "label": "HY OAS",
            "current_bp": 340.0,
            "change_1w_bp": 30.0,
            "change_1m_bp": 40.0,
            "status": "credit_widening",
            "status_label": "信用走阔",
        },
        {
            "key": "ig_oas",
            "label": "IG OAS",
            "current_bp": 122.0,
            "change_1w_bp": 10.0,
            "change_1m_bp": 12.0,
            "status": "credit_widening",
            "status_label": "信用走阔",
        },
    ]
    assert diagnostics["implications"] == ["信用久期双压：降低 HYG/JNK 和长久期暴露，优先现金、短债或高质量信用。"]
    assert diagnostics["invalidations"] == ["若 TLT/IEF 1w 转正且 HYG 不再跑输 LQD，信用久期双压读法降级。"]


def test_bonds_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    view = build_macro_module_view(
        "assets/bonds",
        snapshot=snapshot,
        observations=[
            _obs("asset:tlt", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-20", 96.0, unit="usd", source_name="yahoo"),
        ],
    )

    assert view["module_read"]["asset_class_diagnostics"]["rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "bond_intermediate_duration_missing",
        "bond_inflation_protection_missing",
        "bond_credit_beta_missing",
        "bond_credit_spreads_missing",
        "bond_aggregate_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("bond_")
    )
    assert "credit/cds" not in str(view["related_routes"])


def test_commodities_module_read_adds_asset_class_diagnostics_from_module_history() -> None:
    view = build_macro_module_view(
        "assets/commodities",
        snapshot=_snapshot(),
        observations=[
            _obs("commodity:wti_futures", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("commodity:wti_futures", "2026-05-13", 95.0, unit="usd", source_name="yahoo"),
            _obs("commodity:wti_futures", "2026-05-20", 110.0, unit="usd", source_name="yahoo"),
            _obs("commodity:brent", "2026-04-20", 100.0, unit="usd_per_barrel", source_name="fred"),
            _obs("commodity:brent", "2026-05-13", 97.0, unit="usd_per_barrel", source_name="fred"),
            _obs("commodity:brent", "2026-05-20", 111.0, unit="usd_per_barrel", source_name="fred"),
            _obs("commodity:natgas_futures", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("commodity:natgas_futures", "2026-05-13", 85.0, unit="usd", source_name="yahoo"),
            _obs("commodity:natgas_futures", "2026-05-20", 130.0, unit="usd", source_name="yahoo"),
            _obs("commodity:gold_futures", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("commodity:gold_futures", "2026-05-13", 103.0, unit="usd", source_name="yahoo"),
            _obs("commodity:gold_futures", "2026-05-20", 98.0, unit="usd", source_name="yahoo"),
            _obs("commodity:copper_futures", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("commodity:copper_futures", "2026-05-13", 102.0, unit="usd", source_name="yahoo"),
            _obs("commodity:copper_futures", "2026-05-20", 108.0, unit="usd", source_name="yahoo"),
        ],
    )

    diagnostics = view["module_read"]["asset_class_diagnostics"]
    assert diagnostics["regime"] == "energy_inflation_shock"
    assert diagnostics["regime_label"] == "能源通胀冲击"
    assert diagnostics["summary"] == "商品主线偏能源通胀冲击：原油和天然气同步上行，铜确认需求，贵金属未给防守确认。"
    assert diagnostics["rows"] == [
        {
            "key": "wti",
            "label": "WTI",
            "change_1w_pct": 15.79,
            "change_1m_pct": 10.0,
            "status": "energy_up",
            "status_label": "能源上行",
        },
        {
            "key": "brent",
            "label": "Brent",
            "change_1w_pct": 14.43,
            "change_1m_pct": 11.0,
            "status": "energy_up",
            "status_label": "能源上行",
        },
        {
            "key": "natgas",
            "label": "NatGas",
            "change_1w_pct": 52.94,
            "change_1m_pct": 30.0,
            "status": "energy_up",
            "status_label": "能源上行",
        },
        {
            "key": "gold",
            "label": "Gold",
            "change_1w_pct": -4.85,
            "change_1m_pct": -2.0,
            "status": "precious_down",
            "status_label": "贵金属回落",
        },
        {
            "key": "copper",
            "label": "Copper",
            "change_1w_pct": 5.88,
            "change_1m_pct": 8.0,
            "status": "industrial_bid",
            "status_label": "工业金属走强",
        },
    ]
    assert diagnostics["implications"] == ["能源通胀冲击：保留能源/美元受益表达，降低长久期和高估值风险资产。"]
    assert diagnostics["invalidations"] == ["若 WTI/Brent 1w 转负且 NatGas 回落，能源通胀冲击读法降级。"]


def test_commodities_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    view = build_macro_module_view(
        "assets/commodities",
        snapshot=snapshot,
        observations=[
            _obs("commodity:wti_futures", "2026-05-13", 95.0, unit="usd", source_name="yahoo"),
            _obs("commodity:wti_futures", "2026-05-20", 110.0, unit="usd", source_name="yahoo"),
        ],
    )

    assert view["module_read"]["asset_class_diagnostics"]["rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "commodity_brent_missing",
        "commodity_natural_gas_missing",
        "commodity_precious_metals_missing",
        "commodity_copper_missing",
        "commodity_etf_proxy_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("commodity_")
    )
    assert "options" not in str(view["related_routes"]).lower()


def test_fx_module_read_adds_asset_class_diagnostics_from_module_history() -> None:
    view = build_macro_module_view(
        "assets/fx",
        snapshot=_snapshot(),
        observations=[
            _obs("fx:dxy", "2026-04-20", 100.0, unit="index", source_name="fred"),
            _obs("fx:dxy", "2026-05-13", 101.0, unit="index", source_name="fred"),
            _obs("fx:dxy", "2026-05-20", 103.0, unit="index", source_name="fred"),
            _obs("fx:broad_dollar", "2026-04-20", 100.0, unit="index", source_name="fred"),
            _obs("fx:broad_dollar", "2026-05-13", 100.5, unit="index", source_name="fred"),
            _obs("fx:broad_dollar", "2026-05-20", 102.0, unit="index", source_name="fred"),
            _obs("fx:eurusd", "2026-04-20", 100.0, unit="rate", source_name="yahoo"),
            _obs("fx:eurusd", "2026-05-13", 99.0, unit="rate", source_name="yahoo"),
            _obs("fx:eurusd", "2026-05-20", 96.0, unit="rate", source_name="yahoo"),
            _obs("fx:usdjpy", "2026-04-20", 100.0, unit="rate", source_name="yahoo"),
            _obs("fx:usdjpy", "2026-05-13", 103.0, unit="rate", source_name="yahoo"),
            _obs("fx:usdjpy", "2026-05-20", 106.0, unit="rate", source_name="yahoo"),
            _obs("fx:usdcny", "2026-04-20", 100.0, unit="rate", source_name="yahoo"),
            _obs("fx:usdcny", "2026-05-13", 101.0, unit="rate", source_name="yahoo"),
            _obs("fx:usdcny", "2026-05-20", 103.0, unit="rate", source_name="yahoo"),
            _obs("asset:uup", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:uup", "2026-05-13", 101.5, unit="usd", source_name="yahoo"),
            _obs("asset:uup", "2026-05-20", 103.0, unit="usd", source_name="yahoo"),
        ],
    )

    diagnostics = view["module_read"]["asset_class_diagnostics"]
    assert diagnostics["regime"] == "dollar_squeeze"
    assert diagnostics["regime_label"] == "美元挤压"
    assert diagnostics["summary"] == "美元压力偏紧：DXY 和广义美元走强，欧元、日元与人民币同步确认离岸美元需求。"
    assert diagnostics["rows"] == [
        {
            "key": "dxy",
            "label": "DXY",
            "change_1w_pct": 1.98,
            "change_1m_pct": 3.0,
            "status": "dollar_up",
            "status_label": "美元走强",
        },
        {
            "key": "broad_dollar",
            "label": "Broad USD",
            "change_1w_pct": 1.49,
            "change_1m_pct": 2.0,
            "status": "dollar_up",
            "status_label": "美元走强",
        },
        {
            "key": "eurusd",
            "label": "EURUSD",
            "change_1w_pct": -3.03,
            "change_1m_pct": -4.0,
            "status": "usd_up",
            "status_label": "美元走强",
        },
        {
            "key": "usdjpy",
            "label": "USDJPY",
            "change_1w_pct": 2.91,
            "change_1m_pct": 6.0,
            "status": "usd_up",
            "status_label": "美元走强",
        },
        {
            "key": "usdcny",
            "label": "USDCNY",
            "change_1w_pct": 1.98,
            "change_1m_pct": 3.0,
            "status": "usd_up",
            "status_label": "美元走强",
        },
        {
            "key": "uup",
            "label": "UUP",
            "change_1w_pct": 1.48,
            "change_1m_pct": 3.0,
            "status": "dollar_up",
            "status_label": "美元走强",
        },
    ]
    assert diagnostics["implications"] == [
        "美元挤压：降低新兴市场、商品进口国和高 beta 风险资产，保留美元现金或 UUP 防守。"
    ]
    assert diagnostics["invalidations"] == ["若 DXY/Broad USD 1w 转负且 EURUSD 修复，美元挤压读法降级。"]


def test_fx_data_health_marks_missing_implemented_depth_sources() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = []
    snapshot["features_json"] = {}
    view = build_macro_module_view(
        "assets/fx",
        snapshot=snapshot,
        observations=[
            _obs("fx:dxy", "2026-05-13", 100.0, unit="index", source_name="fred"),
            _obs("fx:dxy", "2026-05-20", 103.0, unit="index", source_name="fred"),
        ],
    )

    assert view["module_read"]["asset_class_diagnostics"]["rows"]
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "fx_broad_dollar_missing",
        "fx_g10_pairs_missing",
        "fx_asia_pairs_missing",
        "fx_etf_proxy_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("fx_")
    )
    assert "global-dollar" not in str(view["related_routes"])


def test_crypto_module_read_adds_asset_class_diagnostics_from_module_history() -> None:
    view = build_macro_module_view(
        "assets/crypto",
        snapshot=_snapshot(),
        observations=[
            _obs("crypto:btc", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-13", 94.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-20", 90.0, unit="usd", source_name="yahoo"),
            _obs("crypto:eth", "2026-04-20", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:eth", "2026-05-13", 88.0, unit="usd", source_name="yahoo"),
            _obs("crypto:eth", "2026-05-20", 82.0, unit="usd", source_name="yahoo"),
        ],
    )

    diagnostics = view["module_read"]["asset_class_diagnostics"]
    assert diagnostics["regime"] == "crypto_beta_unwind"
    assert diagnostics["regime_label"] == "加密 beta 降温"
    assert diagnostics["summary"] == "加密资产同步降温：BTC 和 ETH 单周回撤，ETH 跑输 BTC，宏观 risk-on 需要降档。"
    assert diagnostics["rows"] == [
        {
            "key": "btc",
            "label": "BTC",
            "change_1w_pct": -4.26,
            "change_1m_pct": -10.0,
            "status": "crypto_beta_down",
            "status_label": "加密降温",
        },
        {
            "key": "eth",
            "label": "ETH",
            "change_1w_pct": -6.82,
            "change_1m_pct": -18.0,
            "status": "crypto_beta_down",
            "status_label": "加密降温",
        },
    ]
    assert diagnostics["implications"] == [
        "加密 beta 降温：降低 BTC/ETH 和高 beta 风险资产暴露，等待 BTC 稳定与 ETH 不再跑输。"
    ]
    assert diagnostics["invalidations"] == ["若 BTC/ETH 1w 转正且 ETH 不再跑输 BTC，加密降温读法降级。"]


def test_crypto_module_read_adds_derivatives_diagnostics_without_restoring_page() -> None:
    view = build_macro_module_view(
        "assets/crypto",
        snapshot=_snapshot(),
        observations=[
            _obs("crypto:btc", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-20", 104.0, unit="usd", source_name="yahoo"),
            _obs("crypto:eth", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:eth", "2026-05-20", 105.0, unit="usd", source_name="yahoo"),
            _obs(
                "crypto_derivatives:okx_btc_oi_usd",
                "2026-05-13",
                10_000_000_000.0,
                unit="usd",
                source_name="okx",
            ),
            _obs(
                "crypto_derivatives:okx_btc_oi_usd",
                "2026-05-20",
                11_000_000_000.0,
                unit="usd",
                source_name="okx",
            ),
            _obs(
                "crypto_derivatives:deribit_btc_oi_usd",
                "2026-05-13",
                5_000_000_000.0,
                unit="usd",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:deribit_btc_oi_usd",
                "2026-05-20",
                5_500_000_000.0,
                unit="usd",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:okx_eth_oi_usd",
                "2026-05-13",
                8_000_000_000.0,
                unit="usd",
                source_name="okx",
            ),
            _obs(
                "crypto_derivatives:okx_eth_oi_usd",
                "2026-05-20",
                8_800_000_000.0,
                unit="usd",
                source_name="okx",
            ),
            _obs(
                "crypto_derivatives:deribit_eth_oi_usd",
                "2026-05-13",
                2_000_000_000.0,
                unit="usd",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:deribit_eth_oi_usd",
                "2026-05-20",
                2_200_000_000.0,
                unit="usd",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:okx_btc_funding",
                "2026-05-20",
                0.0008,
                unit="rate",
                source_name="okx",
            ),
            _obs(
                "crypto_derivatives:deribit_btc_funding_8h",
                "2026-05-20",
                0.0006,
                unit="rate",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:okx_eth_funding",
                "2026-05-20",
                0.0005,
                unit="rate",
                source_name="okx",
            ),
            _obs(
                "crypto_derivatives:deribit_eth_funding_8h",
                "2026-05-20",
                0.0005,
                unit="rate",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:okx_btc_basis",
                "2026-05-20",
                1.2,
                unit="percent",
                source_name="okx",
            ),
            _obs(
                "crypto_derivatives:deribit_btc_basis",
                "2026-05-20",
                1.0,
                unit="percent",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:okx_eth_basis",
                "2026-05-20",
                0.8,
                unit="percent",
                source_name="okx",
            ),
            _obs(
                "crypto_derivatives:deribit_eth_basis",
                "2026-05-20",
                0.9,
                unit="percent",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:deribit_btc_vol_index",
                "2026-05-13",
                52.0,
                unit="index",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:deribit_btc_vol_index",
                "2026-05-20",
                66.0,
                unit="index",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:deribit_eth_vol_index",
                "2026-05-13",
                58.0,
                unit="index",
                source_name="deribit",
            ),
            _obs(
                "crypto_derivatives:deribit_eth_vol_index",
                "2026-05-20",
                72.0,
                unit="index",
                source_name="deribit",
            ),
        ],
    )

    diagnostics = view["module_read"]["asset_class_diagnostics"]
    assert diagnostics["regime"] == "crypto_leverage_chase"
    assert diagnostics["regime_label"] == "加密杠杆追涨"
    assert diagnostics["summary"] == (
        "加密价格、OI、资金费率和基差同步走热，DVOL 升温，当前更像杠杆追涨而不是干净 beta。"
    )
    assert "assets/crypto-derivatives" not in str(view["related_routes"])
    derivative_rows = {row["key"]: row for row in diagnostics["rows"]}
    assert derivative_rows["btc_perp_oi"] == {
        "key": "btc_perp_oi",
        "label": "BTC 永续 OI",
        "current_bn": 16.5,
        "change_1w_pct": 10.0,
        "status": "leverage_expanding",
        "status_label": "杠杆扩张",
    }
    assert derivative_rows["btc_funding"] == {
        "key": "btc_funding",
        "label": "BTC 资金费率",
        "current_bp": 7.0,
        "status": "funding_hot",
        "status_label": "多头拥挤",
    }
    assert derivative_rows["btc_basis"] == {
        "key": "btc_basis",
        "label": "BTC 基差",
        "current_bp": 110.0,
        "status": "basis_rich",
        "status_label": "正基差",
    }
    assert derivative_rows["btc_dvol"] == {
        "key": "btc_dvol",
        "label": "BTC DVOL",
        "current_index": 66.0,
        "change_1w_index": 14.0,
        "status": "vol_hot",
        "status_label": "波动升温",
    }
    assert diagnostics["implications"] == [
        "杠杆追涨：保留 BTC/ETH beta 要降低杠杆和追价，优先等待 funding、basis 或 DVOL 降温后再加仓。"
    ]
    assert diagnostics["invalidations"] == ["若 OI 收缩且 funding/basis 回落，加密杠杆追涨读法降级。"]


def test_crypto_module_data_health_marks_missing_derivatives_as_reference_gap() -> None:
    view = build_macro_module_view(
        "assets/crypto",
        snapshot=_snapshot(),
        observations=[
            _obs("crypto:btc", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-20", 104.0, unit="usd", source_name="yahoo"),
            _obs("crypto:eth", "2026-05-13", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:eth", "2026-05-20", 105.0, unit="usd", source_name="yahoo"),
        ],
    )

    assert view["data_health"]["summary_status"] == "partial"
    assert view["module_read"]["headline"] == "加密资产：部分可用"
    assert view["module_read"]["asset_class_diagnostics"]["regime"] == "crypto_beta_risk_on"
    gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert {
        "crypto_derivatives_oi_missing",
        "crypto_derivatives_funding_missing",
        "crypto_derivatives_basis_missing",
        "crypto_derivatives_dvol_missing",
    }.issubset(gap_codes)
    assert all(
        gap["scope"] == "module_reference"
        for gap in view["data_health"]["module_gaps"]
        if str(gap["code"]).startswith("crypto_derivatives_")
    )
    assert "assets/crypto-derivatives" not in str(view["related_routes"])


def test_assets_landing_prefers_fresh_wti_futures_over_stale_fred_spot() -> None:
    snapshot = _snapshot()
    snapshot["features_json"]["commodity:wti"] = {
        **_feature("commodity:wti", 95.96, unit="usd_per_barrel", source_name="fred"),
        "latest": {"value": 95.96, "observed_at": "2026-06-01", "unit": "usd_per_barrel"},
        "freshness_days": 8,
        "stale_after_days": 7,
        "data_gaps": [
            {
                "code": "stale_latest_8d",
                "label": "最新观测滞后：8 天",
                "severity": "warning",
                "score_participation": False,
                "remediation_hint": "检查 FRED WTI 现货导入与最新观测。",
            }
        ],
    }
    snapshot["features_json"]["commodity:wti_futures"] = _feature(
        "commodity:wti_futures",
        91.3,
        unit="usd",
        source_name="yahoo",
    )

    view = build_macro_module_view("assets", snapshot=snapshot, observations=[])

    chart_keys = [series["concept_key"] for series in view["primary_chart"]["series"]]
    assert "commodity:wti_futures" in chart_keys
    assert "commodity:wti" not in chart_keys
    table_row_ids = [row["row_id"] for row in view["tables"][0]["rows"]]
    assert "commodity:wti_futures" in table_row_ids
    assert "commodity:wti" not in table_row_ids
    module_gap_codes = {gap["code"] for gap in view["data_health"]["module_gaps"]}
    assert "stale_latest_8d" not in module_gap_codes


def test_optional_concept_error_gap_degrades_module_without_marking_page_missing() -> None:
    snapshot = _snapshot()
    snapshot["features_json"]["commodity:wti_futures"] = _feature(
        "commodity:wti_futures",
        80.75,
        unit="usd",
        source_name="yahoo",
    )
    snapshot["features_json"]["commodity:wti"] = {
        **_feature("commodity:wti", 95.96, unit="usd_per_barrel", source_name="fred"),
        "latest": {"value": 95.96, "observed_at": "2026-06-08", "unit": "usd_per_barrel"},
        "freshness_days": 8,
        "stale_after_days": 7,
        "data_gaps": [
            {
                "code": "stale_latest_8d",
                "label": "最新观测已过期：8 天未更新",
                "severity": "error",
                "score_participation": False,
                "remediation_hint": "检查 FRED WTI 现货导入与最新观测。",
            }
        ],
    }

    view = build_macro_module_view("assets/commodities", snapshot=snapshot, observations=[])

    assert view["data_health"]["summary_status"] == "partial"
    assert view["module_read"]["headline"] == "商品冲击：部分可用"
    stale_gap = next(gap for gap in view["data_health"]["module_gaps"] if gap["code"] == "stale_latest_8d")
    assert stale_gap["scope"] == "module_reference"
    assert stale_gap["concept_key"] == "commodity:wti"


def test_required_concept_error_gap_keeps_module_missing() -> None:
    snapshot = _snapshot()
    snapshot["features_json"]["commodity:wti_futures"] = {
        **_feature("commodity:wti_futures", 80.75, unit="usd", source_name="yahoo"),
        "latest": {"value": 80.75, "observed_at": "2026-06-08", "unit": "usd"},
        "freshness_days": 8,
        "stale_after_days": 7,
        "data_gaps": [
            {
                "code": "stale_latest_8d",
                "label": "最新观测已过期：8 天未更新",
                "severity": "error",
                "score_participation": False,
                "remediation_hint": "检查 Yahoo WTI 期货导入与最新观测。",
            }
        ],
    }

    view = build_macro_module_view("assets/commodities", snapshot=snapshot, observations=[])

    assert view["data_health"]["summary_status"] == "missing"
    assert view["module_read"]["headline"] == "商品冲击：缺失"
    stale_gap = next(gap for gap in view["data_health"]["module_gaps"] if gap["code"] == "stale_latest_8d")
    assert stale_gap["scope"] == "module_blocker"
    assert stale_gap["concept_key"] == "commodity:wti_futures"


def test_module_view_uses_semantic_chart_table_titles_for_every_catalog_spec() -> None:
    snapshot = _snapshot()
    for config in list_macro_module_configs():
        view = build_macro_module_view(config.module_id, snapshot=snapshot, observations=[])

        chart = view["primary_chart"]
        assert chart["title"]
        assert chart["title"] != chart["id"]
        assert "_" not in chart["title"]
        for table in view["tables"]:
            assert table["title"]
            assert table["title"] != table["id"]
            assert "_" not in table["title"]


def test_gap_payloads_do_not_preserve_labels_for_retired_source_backlog_codes() -> None:
    retired_source_backlog_codes = [
        "move_index_missing",
        "basis_missing",
        "vix_term_structure_missing",
        "fed_calendar_missing",
        "fed_speeches_missing",
        "fed_statement_text_missing",
        "crypto_options_missing",
        "etf_flows_missing",
        "equity_breadth_missing",
        "equity_options_gex_missing",
        "options_iv_rv_missing",
    ]

    gaps = build_macro_data_gaps(retired_source_backlog_codes)

    assert {gap["code"] for gap in gaps} == set(retired_source_backlog_codes)
    assert {gap["code"]: gap["label"] for gap in gaps} == {
        "move_index_missing": "MOVE 指数缺失",
        "basis_missing": "基差缺失",
        "vix_term_structure_missing": "VIX 期限结构缺失",
        "fed_calendar_missing": "Fed 日历缺失",
        "fed_speeches_missing": "Fed 讲话缺失",
        "fed_statement_text_missing": "Fed 声明文本缺失",
        "crypto_options_missing": "加密期权缺失",
        "etf_flows_missing": "ETF 资金流缺失",
        "equity_breadth_missing": "股票广度缺失",
        "equity_options_gex_missing": "股票期权 GEX 缺失",
        "options_iv_rv_missing": "期权 IV/RV 缺失",
    }
    assert {gap["remediation_hint"] for gap in gaps} == {"补齐数据源后重新投影。"}


def test_gap_payloads_do_not_preserve_labels_for_implemented_source_gaps() -> None:
    implemented_gap_codes = [
        "sloos_missing",
        "loan_quality_missing",
        "jolts_missing",
        "average_hourly_earnings_missing",
        "personal_spending_missing",
    ]

    gaps = build_macro_data_gaps(implemented_gap_codes)

    assert {gap["code"] for gap in gaps} == set(implemented_gap_codes)
    assert {gap["code"]: gap["label"] for gap in gaps} == {
        "sloos_missing": "SLOOS 缺失",
        "loan_quality_missing": "贷款质量缺失",
        "jolts_missing": "JOLTS 缺失",
        "average_hourly_earnings_missing": "平均时薪缺失",
        "personal_spending_missing": "个人消费支出缺失",
    }
    assert all(gap["remediation_hint"] == "补齐数据源后重新投影。" for gap in gaps)


def test_gap_payloads_do_not_emit_unnamed_indicator_for_unmapped_missing_codes() -> None:
    gaps = build_macro_data_gaps(["missing:rates:unmapped"])

    assert gaps == [
        {
            "code": "missing_rates_unmapped",
            "label": "数据质量缺口：missing_rates_unmapped",
            "severity": "error",
            "score_participation": False,
            "remediation_hint": "检查对应 provider 导入与最新观测。",
        }
    ]
    assert "未命名指标" not in str(gaps)


def test_feature_label_and_unit_fallback_use_metadata_not_raw_keys_or_units() -> None:
    snapshot = _snapshot()
    feature = snapshot["features_json"]["rates:dgs2"]
    for key in ("label", "short_label", "description", "unit_label"):
        feature.pop(key)

    view = build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])

    tile = view["tiles"][0]
    assert tile["label"] == "2年期美债收益率"
    assert tile["short_label"] == "2Y"
    assert tile["unit_label"] == "%"
    assert tile["label"] != "rates:dgs2"
    assert tile["unit_label"] != "percent"


def test_feature_unit_label_requires_feature_or_metadata_unit(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _snapshot()
    feature = snapshot["features_json"]["rates:dgs2"]
    feature.pop("unit_label")
    metadata = dict(macro_module_views.MACRO_CONCEPT_METADATA["rates:dgs2"])
    metadata.pop("unit_label")
    monkeypatch.setitem(macro_module_views.MACRO_CONCEPT_METADATA, "rates:dgs2", metadata)

    with pytest.raises(ValueError, match="Missing macro concept unit metadata: rates:dgs2"):
        build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])


def test_availability_rows_require_catalog_concept_label_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = dict(macro_module_views.MACRO_CONCEPT_METADATA["rates:dgs5"])
    metadata.pop("label")
    monkeypatch.setitem(macro_module_views.MACRO_CONCEPT_METADATA, "rates:dgs5", metadata)

    with pytest.raises(ValueError, match="Missing macro concept label metadata: rates:dgs5"):
        build_macro_module_view("rates/yield-curve", snapshot=_snapshot(), observations=[])


def test_observation_supplements_require_catalog_unit_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _snapshot()
    metadata = dict(macro_module_views.MACRO_CONCEPT_METADATA["rates:dgs5"])
    metadata.pop("unit_label")
    monkeypatch.setitem(macro_module_views.MACRO_CONCEPT_METADATA, "rates:dgs5", metadata)

    with pytest.raises(ValueError, match="Missing macro concept unit metadata: rates:dgs5"):
        build_macro_module_view(
            "rates/yield-curve",
            snapshot=snapshot,
            observations=[
                _obs("rates:dgs5", "2026-05-19", 4.0, unit="percent", source_name="fred"),
                _obs("rates:dgs5", "2026-05-20", 4.1, unit="percent", source_name="fred"),
            ],
        )


def test_module_view_provenance_requires_public_provider_metadata() -> None:
    with pytest.raises(ValueError, match="Missing macro provider label metadata: internal_feed"):
        build_macro_module_view(
            "rates/yield-curve",
            snapshot=_snapshot(),
            observations=[
                _obs(
                    "rates:dgs10",
                    "2026-05-20",
                    4.7,
                    unit="percent",
                    source_name="internal_feed",
                )
                | {"data_quality": "ok"},
            ],
        )


def test_module_view_requires_known_snapshot_status_metadata() -> None:
    snapshot = _snapshot()
    snapshot["status"] = "provider_not_configured"

    with pytest.raises(ValueError, match="Missing macro status label metadata: provider_not_configured"):
        build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])


def test_module_view_requires_known_feature_quality_metadata() -> None:
    snapshot = _snapshot()
    snapshot["features_json"]["rates:dgs2"]["data_quality"] = "provider_not_configured"

    with pytest.raises(ValueError, match="Missing macro quality label metadata: provider_not_configured"):
        build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])


def test_module_view_requires_labeled_data_gap_severity_metadata() -> None:
    snapshot = _snapshot()
    snapshot["data_gaps_json"] = [
        {
            "code": "missing_rates_dgs5",
            "label": "缺少当前数据：5Y",
        }
    ]

    with pytest.raises(ValueError, match="Missing macro data gap severity metadata: missing_rates_dgs5"):
        build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])


def test_module_view_requires_data_gap_remediation_metadata() -> None:
    snapshot = _snapshot()
    snapshot["data_gaps_json"] = [
        {
            "code": "missing_rates_dgs5",
            "label": "缺少当前数据：5Y",
            "severity": "error",
        }
    ]

    with pytest.raises(ValueError, match="Missing macro data gap remediation_hint metadata: missing_rates_dgs5"):
        build_macro_module_view("rates/yield-curve", snapshot=snapshot, observations=[])


def test_overview_transmission_requires_known_regime_metadata() -> None:
    snapshot = _snapshot()
    snapshot["chain_json"] = {"liquidity": {"regime": "shadow_liquidity"}}

    with pytest.raises(ValueError, match="Missing macro regime label metadata: shadow_liquidity"):
        build_macro_module_view("overview", snapshot=snapshot, observations=[])


def test_decision_console_requires_labeled_quality_blockers() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "quality_blockers": [{"description": "Provider contract is incomplete."}],
    }

    with pytest.raises(ValueError, match="Missing macro quality blocker label metadata"):
        build_macro_module_view("overview", snapshot=snapshot, observations=[])


def test_decision_console_requires_labeled_quality_blocker_severity() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "quality_blockers": [
            {
                "code": "missing_liquidity_srf",
                "label": "缺少 SRF",
                "description": "缺少 SRF",
            }
        ],
    }

    with pytest.raises(ValueError, match="Missing macro quality blocker severity metadata: missing_liquidity_srf"):
        build_macro_module_view("overview", snapshot=snapshot, observations=[])


def test_decision_console_requires_known_top_change_section_metadata() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "top_changes": [
            {
                "code": "higher_real_rates",
                "label": "实际利率上行",
                "description": "10Y real yield broke higher",
                "node": "shadow_macro",
                "kind": "trigger",
            }
        ],
    }

    with pytest.raises(ValueError, match="Missing macro section label metadata: shadow_macro"):
        build_macro_module_view("overview", snapshot=snapshot, observations=[])


def test_decision_console_requires_top_change_section_metadata() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "top_changes": [
            {
                "code": "higher_real_rates",
                "label": "实际利率上行",
                "description": "10Y real yield broke higher",
                "kind": "trigger",
            }
        ],
    }

    with pytest.raises(ValueError, match="Missing macro section label metadata: <missing>"):
        build_macro_module_view("overview", snapshot=snapshot, observations=[])


def test_decision_console_requires_known_watchlist_severity_metadata() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "watch_triggers": [
            {
                "code": "real_yield_breakout",
                "description": "10Y real yield keeps rising.",
                "time_window": "24h",
                "severity": "urgent",
            }
        ],
    }

    with pytest.raises(ValueError, match="Missing macro severity label metadata: urgent"):
        build_macro_module_view("overview", snapshot=snapshot, observations=[])


def test_decision_console_requires_known_liquidity_pressure_regime_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()

    monkeypatch.setattr(
        macro_module_views,
        "_liquidity_diagnostics",
        lambda _feature_map: {
            "regime": "shadow_liquidity",
            "regime_label": "",
            "summary": "Malformed liquidity diagnostics.",
            "rows": [],
        },
    )

    with pytest.raises(ValueError, match="Missing macro liquidity pressure regime metadata: shadow_liquidity"):
        build_macro_module_view("overview", snapshot=snapshot, observations=[])


def test_non_overview_module_view_does_not_reuse_global_scenario_or_blockers() -> None:
    view = build_macro_module_view(
        "assets/equities",
        snapshot=_snapshot_with_global_scenario(),
        observations=[],
    )

    assert view["snapshot"]["projection_version"] == "macro_module_view_v3"
    assert "module_read" in view
    assert "module_evidence" in view
    assert "transmission" in view
    assert "data_health" in view
    assert "section_boards" not in view
    assert "read" not in view
    assert "evidence" not in view
    assert "data_gaps" not in view
    assert "期限溢价压力" not in view["module_read"]["headline"]
    assert all(item.get("code") != "global_term_premium" for item in view["module_evidence"]["confirmations"])
    assert all(gap.get("code") != "missing_liquidity_srf" for gap in view["data_health"]["module_gaps"])
    assert any(gap.get("code") == "missing_liquidity_srf" for gap in view["data_health"]["global_gaps"])
    assert all(gap.get("scope") == "global_reference" for gap in view["data_health"]["global_gaps"])


def test_overview_module_view_surfaces_global_scenario_and_data_health() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot_with_global_scenario(),
        observations=[],
    )

    assert view["module_read"]["headline"] == "宏观总览：期限溢价压力"
    assert view["module_evidence"]["confirmations"][0]["code"] == "global_term_premium"
    assert view["module_read"]["decision_console"] == {
        "top_changes": [
            {
                "code": "higher_real_rates",
                "label": "实际利率上行",
                "description": "10Y real yield broke higher",
                "node": "利率定价",
                "kind": "trigger",
            },
            {
                "code": "rrp_buffer_low",
                "label": "RRP 缓冲偏低",
                "description": "ON RRP buffer is below 300bn USD",
                "node": "资金面",
                "kind": "trigger",
            },
        ],
        "quality_blockers": [
            {
                "code": "missing_liquidity_srf",
                "label": "缺少 SRF",
                "description": "缺少 SRF",
                "severity": "error",
            }
        ],
        "trade_map": [{"expression": "duration_pressure_quality_over_growth"}],
        "watchlist_alerts": {
            "key": "watchlist_alerts",
            "label": "Watchlist 与触发提醒",
            "assets": [],
            "rules": [
                {
                    "key": "quality:missing_liquidity_srf",
                    "label": "缺少 SRF",
                    "description": "缺少 SRF",
                    "kind": "quality",
                    "kind_label": "质量",
                    "severity": "error",
                    "severity_label": "阻断",
                }
            ],
        },
        "scenario_cases": [
            {
                "case": "base",
                "label": "基准情景",
                "probability": 0.5,
                "probability_label": "50%",
                "time_window": "未来 2 周",
                "thesis": "长端利率维持压力。",
                "trade": "低配 TLT。",
                "entry_condition": "10Y 继续上行。",
                "stop": "10Y 回落。",
                "invalidation": "实际利率压力消退。",
            }
        ],
    }
    assert any(gap.get("code") == "missing_liquidity_srf" for gap in view["data_health"]["global_gaps"])
    assert view["data_health"]["summary_status"] == "missing"


def test_overview_module_view_omits_unmapped_signal_and_trade_placeholder_copy() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        "current_regime": "",
        "confirmations": [{"code": "unmapped_confirmation", "description": "Unknown confirmation."}],
        "contradictions": [{"code": "unmapped_contradiction", "description": "Unknown contradiction."}],
        "watch_triggers": [
            {
                "code": "unmapped_watch_trigger",
                "description": "Unknown watch trigger.",
                "time_window": "24h",
                "severity": "high",
            }
        ],
        "invalidations": [{"code": "unmapped_invalidation", "description": "Unknown invalidation."}],
        "top_changes": [
            {
                "code": "unmapped_top_change",
                "description": "Unknown top change.",
                "node": "macro",
                "kind": "trigger",
            }
        ],
        "trade_map": [{"expression": "unmapped_trade_expression"}],
        "scenario_cases": [
            {
                "case": "base",
                "label": "基准情景",
                "thesis": "资金压力维持。",
                "trade": "降低高 beta 暴露。",
                "entry_condition": "SOFR-IORB 仍为正。",
                "stop": "SOFR 回到 IORB 附近。",
                "invalidation": "信用利差收窄。",
            }
        ],
    }

    view = build_macro_module_view("overview", snapshot=snapshot, observations=[])

    assert view["module_evidence"]["confirmations"] == []
    assert view["module_evidence"]["contradictions"] == []
    assert view["module_evidence"]["watch_triggers"] == []
    assert view["module_evidence"]["invalidations"] == []
    decision_console = view["module_read"]["decision_console"]
    assert decision_console["top_changes"] == []
    assert "future_catalysts" not in decision_console
    watchlist_rules = decision_console.get("watchlist_alerts", {}).get("rules", [])
    assert all("unmapped_" not in str(rule) for rule in watchlist_rules)
    assert "待确认信号" not in str(view)
    assert "待确认交易映射" not in str(view)
    assert "待确认" not in str(view["module_read"].get("structured_analysis", ""))


def test_backend_status_fallbacks_use_specific_insufficient_history_labels() -> None:
    assert macro_module_views._structured_regime_label({}) == "样本不足"
    assert macro_module_views._liquidity_net_status(None) == ("insufficient_history", "样本不足")
    assert macro_module_views._volatility_term_status(None) == ("insufficient_history", "样本不足")
    assert macro_module_views._volatility_front_premium_status(
        current_points=None,
        change_1w_points=None,
    ) == ("insufficient_history", "样本不足")
    assert macro_module_views._judgement_review_window({"horizon": "1d", "label": "1D"}) == {
        "horizon": "1d",
        "label": "1D",
        "status": "insufficient_history",
        "status_label": "样本不足",
        "sample_count": 0,
        "hit_count": 0,
        "win_rate_label": "0/0",
        "pnl_usd": 0.0,
        "average_signed_return_pct": 0.0,
    }


def test_overview_decision_console_adds_liquidity_pressure_from_retained_rrp_tga_diagnostics() -> None:
    snapshot = _snapshot()
    _add_liquidity_pressure_features(snapshot["features_json"])

    view = build_macro_module_view("overview", snapshot=snapshot, observations=[])

    assert view["module_read"]["decision_console"]["liquidity_pressure"] == {
        "key": "liquidity_pressure",
        "label": "流动性压力",
        "score": 7.0,
        "score_label": "7.0/10",
        "regime": "corridor_drain",
        "regime_label": "走廊抽水",
        "summary": "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
        "drivers": [
            {
                "key": "sofr_iorb",
                "label": "SOFR-IORB 走廊压力",
                "current_bp": 7.0,
                "change_1w_bp": 6.0,
                "change_1m_bp": 11.0,
                "status": "corridor_pressure",
                "status_label": "走廊压力",
            },
            {
                "key": "net_liquidity",
                "label": "净流动性",
                "current_trillion": 5.78,
                "change_1w_bn": -60.0,
                "change_1m_bn": -120.0,
                "status": "net_drain",
                "status_label": "净抽水",
            },
            {
                "key": "tga",
                "label": "TGA 财政现金",
                "current_bn": 760.0,
                "change_1w_bn": 70.0,
                "change_1m_bn": 160.0,
                "status": "treasury_drain",
                "status_label": "财政抽水",
            },
        ],
        "implication": "流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。",
        "invalidation": "若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。",
    }
    assert "liquidity/rrp-tga" not in str(view["module_read"]["decision_console"]["liquidity_pressure"])


def test_overview_decision_console_adds_data_credibility_layer_from_core_features() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["fx:dxy"] = _feature("fx:dxy", 104.2, unit="index", source_name="fred")
    features["commodity:wti_futures"] = _feature(
        "commodity:wti_futures",
        72.4,
        unit="usd",
        source_name="yahoo",
    )
    features["liquidity:on_rrp"] = _feature(
        "liquidity:on_rrp",
        127.0,
        unit="millions_usd",
        source_name="fred",
    )
    features["credit:hy_oas"] = {
        **features["credit:hy_oas"],
        "data_quality": "stale",
        "latest": {"value": 2.8, "observed_at": "2026-05-17", "unit": "percent"},
    }
    features["liquidity:on_rrp"] = {
        **features["liquidity:on_rrp"],
        "data_quality": "degraded",
    }

    view = build_macro_module_view("overview", snapshot=snapshot, observations=[])

    assert view["module_read"]["decision_console"]["data_credibility"] == {
        "label": "数据可信度层",
        "issue_count": 2,
        "issue_label": "2 issue(s)",
        "rows": [
            {
                "concept_key": "asset:spx",
                "label": "SPX",
                "display_value": "5312.40",
                "unit_label": "点",
                "observed_at": "2026-05-20",
                "observed_at_label": "观测于 2026-05-20",
                "source_label": "FRED",
                "quality": "ok",
                "quality_label": "可用",
            },
            {
                "concept_key": "fx:dxy",
                "label": "DXY",
                "display_value": "104.20",
                "unit_label": "点",
                "observed_at": "2026-05-20",
                "observed_at_label": "观测于 2026-05-20",
                "source_label": "FRED",
                "quality": "ok",
                "quality_label": "可用",
            },
            {
                "concept_key": "crypto:btc",
                "label": "BTC",
                "display_value": "110000.00",
                "unit_label": "美元",
                "observed_at": "2026-05-20",
                "observed_at_label": "观测于 2026-05-20",
                "source_label": "Yahoo",
                "quality": "ok",
                "quality_label": "可用",
            },
            {
                "concept_key": "commodity:wti_futures",
                "label": "CL=F",
                "display_value": "72.40",
                "unit_label": "美元",
                "observed_at": "2026-05-20",
                "observed_at_label": "观测于 2026-05-20",
                "source_label": "Yahoo",
                "quality": "ok",
                "quality_label": "可用",
            },
            {
                "concept_key": "rates:dgs10",
                "label": "10Y",
                "display_value": "4.70",
                "unit_label": "%",
                "observed_at": "2026-05-20",
                "observed_at_label": "观测于 2026-05-20",
                "source_label": "FRED",
                "quality": "ok",
                "quality_label": "可用",
            },
            {
                "concept_key": "vol:vix",
                "label": "VIX",
                "display_value": "17.20",
                "unit_label": "点",
                "observed_at": "2026-05-20",
                "observed_at_label": "观测于 2026-05-20",
                "source_label": "FRED",
                "quality": "ok",
                "quality_label": "可用",
            },
            {
                "concept_key": "credit:hy_oas",
                "label": "HY OAS",
                "display_value": "2.80",
                "unit_label": "%",
                "observed_at": "2026-05-17",
                "observed_at_label": "观测于 2026-05-17",
                "source_label": "FRED",
                "quality": "stale",
                "quality_label": "过期",
            },
            {
                "concept_key": "liquidity:on_rrp",
                "label": "ON RRP",
                "display_value": "127.00",
                "unit_label": "百万美元",
                "observed_at": "2026-05-20",
                "observed_at_label": "观测于 2026-05-20",
                "source_label": "FRED",
                "quality": "degraded",
                "quality_label": "降级",
            },
        ],
    }


def test_overview_module_read_adds_structured_analysis_from_domain_diagnostics() -> None:
    snapshot = _snapshot()
    features = snapshot["features_json"]
    features["asset:spx"] = _feature_with_history(
        "asset:spx",
        [("2026-04-20", 5400.0), ("2026-05-13", 5350.0), ("2026-05-20", 5200.0)],
        unit="index",
    )
    features["asset:tlt"] = _feature_with_history(
        "asset:tlt",
        [("2026-04-20", 90.0), ("2026-05-13", 88.0), ("2026-05-20", 84.0)],
        unit="usd",
    )
    features["fx:dxy"] = _feature_with_history(
        "fx:dxy",
        [("2026-04-20", 101.0), ("2026-05-13", 103.0), ("2026-05-20", 104.5)],
        unit="index",
    )
    features["commodity:wti_futures"] = _feature_with_history(
        "commodity:wti_futures",
        [("2026-04-20", 70.0), ("2026-05-13", 73.0), ("2026-05-20", 76.0)],
        unit="usd",
    )
    features["crypto:btc"] = _feature_with_history(
        "crypto:btc",
        [("2026-04-20", 110_000.0), ("2026-05-13", 105_000.0), ("2026-05-20", 100_000.0)],
        unit="usd",
    )
    features["rates:dgs2"] = _feature_with_history(
        "rates:dgs2",
        [("2026-04-20", 3.8), ("2026-05-13", 3.9), ("2026-05-20", 4.1)],
    )
    features["rates:dgs10"] = _feature_with_history(
        "rates:dgs10",
        [("2026-04-20", 4.0), ("2026-05-13", 4.2), ("2026-05-20", 4.6)],
    )
    features["rates:dgs3mo"] = _feature_with_history(
        "rates:dgs3mo",
        [("2026-04-20", 4.5), ("2026-05-13", 4.55), ("2026-05-20", 4.6)],
    )
    features["rates:dgs5"] = _feature_with_history(
        "rates:dgs5",
        [("2026-04-20", 3.9), ("2026-05-13", 4.05), ("2026-05-20", 4.3)],
    )
    features["rates:dgs30"] = _feature_with_history(
        "rates:dgs30",
        [("2026-04-20", 4.3), ("2026-05-13", 4.45), ("2026-05-20", 4.8)],
    )
    _add_liquidity_pressure_features(features)
    features["credit:hy_oas"] = _feature_with_history(
        "credit:hy_oas",
        [("2026-04-20", 3.5), ("2026-05-13", 4.0), ("2026-05-20", 4.4)],
    )
    features["credit:ig_oas"] = _feature_with_history(
        "credit:ig_oas",
        [("2026-04-20", 1.0), ("2026-05-13", 1.1), ("2026-05-20", 1.25)],
    )
    features["credit:hy_ccc_oas"] = _feature_with_history(
        "credit:hy_ccc_oas",
        [("2026-04-20", 7.0), ("2026-05-13", 8.0), ("2026-05-20", 9.5)],
    )
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "current_regime": "term_premium_pressure",
        "top_changes": [
            {
                "code": "higher_real_rates",
                "label": "实际利率上行",
                "description": "10Y real yield broke higher",
                "node": "rates",
                "kind": "trigger",
            },
            {
                "code": "rrp_buffer_low",
                "label": "RRP 缓冲偏低",
                "description": "ON RRP buffer is below 300bn USD",
                "node": "funding",
                "kind": "trigger",
            },
        ],
        "trade_map": [{"expression": "duration_pressure_quality_over_growth"}],
        "scenario_cases": [
            {
                "case": "base",
                "label": "基准情景",
                "probability": 0.5,
                "probability_label": "50%",
                "time_window": "未来 2 周",
                "thesis": "长端利率维持压力。",
                "trade": "低配 TLT。",
                "entry_condition": "10Y 继续上行。",
                "stop": "10Y 回落。",
                "invalidation": "实际利率压力消退。",
            }
        ],
    }

    view = build_macro_module_view("overview", snapshot=snapshot, observations=[])

    assert view["module_read"]["structured_analysis"] == {
        "key": "structured_analysis",
        "label": "跨域判断链",
        "rows": [
            {
                "key": "market_thesis",
                "label": "市场主线",
                "regime_label": "期限溢价压力",
                "fact": "市场主线：长端利率维持压力。",
                "evidence": [
                    "实际利率上行 · 10Y real yield broke higher",
                    "RRP 缓冲偏低 · ON RRP buffer is below 300bn USD",
                    "Trade Map · 久期承压 / 质量优于成长",
                ],
                "trade": "低配 TLT。",
                "invalidation": "实际利率压力消退。",
            },
            {
                "key": "assets",
                "label": "大类资产",
                "regime_label": "滞胀冲击",
                "fact": "跨资产主线偏滞胀冲击：股债双杀、美元与能源走强，风险资产需要降档。",
                "evidence": [
                    "SPX · 1w -2.8% · 1m -3.7% · 风险降温",
                    "TLT · 1w -4.5% · 1m -6.7% · 久期承压",
                    "DXY · 1w +1.5% · 1m +3.5% · 美元走强",
                ],
                "trade": "滞胀冲击：降低权益/加密 beta，保留美元、能源或现金防守表达。",
                "invalidation": "若 SPX/BTC 修复且 DXY、WTI、VIX 同步回落，滞胀冲击读法降级。",
            },
            {
                "key": "rates",
                "label": "利率曲线",
                "regime_label": "熊陡",
                "fact": "曲线熊陡：10Y 上行且 2s10s 走陡，期限溢价压力压制久期资产。",
                "evidence": [
                    "2s10s · 50bp · 走陡",
                    "3m10y · 0bp · 走陡",
                    "5s30s · 50bp · 走陡",
                ],
                "trade": "期限溢价压力：优先防守长久期成长、长债和高 beta。",
                "invalidation": "若 10Y 回落且 2s10s 重新走平，曲线压力降级。",
            },
            {
                "key": "liquidity",
                "label": "流动性",
                "regime_label": "走廊抽水",
                "fact": "流动性走廊抽水：SOFR 高于 IORB 且净流动性回落，高 beta 需要降杠杆。",
                "evidence": [
                    "SOFR-IORB 走廊压力 · 7bp · 走廊压力",
                    "SOFR-TGCR 深度压力 · 9bp · Repo 深度压力",
                    "SOFR 成交量 · $3023B · 成交放大",
                ],
                "trade": "流动性抽水：降低高 beta、杠杆多头和融资敏感资产暴露。",
                "invalidation": "若 SOFR-IORB 回落至 0bp 附近且净流动性 1w 转正，抽水读法降级。",
            },
            {
                "key": "credit",
                "label": "信用市场",
                "regime_label": "尾部走阔",
                "fact": "信用尾部走阔：HY OAS 与 CCC-HY 尾部同时上行，高 beta 需要降级。",
                "evidence": [
                    "HY OAS · 440bp · 走阔",
                    "IG OAS · 125bp · 走阔",
                    "CCC-HY 尾部 · 510bp · 尾部恶化",
                ],
                "trade": "信用尾部恶化：降低高 beta、盈利下修和融资敏感资产暴露。",
                "invalidation": "若 HY OAS 1m 收窄且 CCC-HY 尾部回落，信用压力降级。",
            },
        ],
    }


def test_overview_structured_analysis_adds_fed_communication_from_official_text() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot_with_global_scenario(),
        observations=[
            _event_obs(
                "event:fed_speech",
                "official_fed_text:speech_latest#abc123",
                "2026-06-16",
                None,
                provider="official_fed_text",
                raw_payload={
                    "series_key": "official_fed_text:speech_latest",
                    "provider": "official_fed_text",
                    "observed_at": "2026-06-16T18:30:00Z",
                    "value": "Waller, Update On Federal Reserve Bank Operations",
                    "unit": "document",
                    "frequency": "event",
                    "source_ts": "2026-06-16T18:30:00Z",
                    "provenance": [
                        {
                            "document_type": "speech",
                            "document_title": "Waller, Update On Federal Reserve Bank Operations",
                            "published_at": "2026-06-16T18:30:00Z",
                            "source_url": "https://www.federalreserve.gov/newsevents/speech/waller20260616a.htm",
                        }
                    ],
                },
            )
        ],
    )

    rows = view["module_read"]["structured_analysis"]["rows"]
    assert rows[1] == {
        "key": "fed_communication",
        "label": "美联储沟通",
        "regime_label": "讲话",
        "fact": "Fed 沟通：2026-06-16 · Waller, Update On Federal Reserve Bank Operations",
        "evidence": [
            "Fed 官员讲话 · Federal Reserve · Waller",
            "Fed 沟通 · 跟踪措辞、投票分歧和政策路径信号。",
        ],
        "trade": "利率路径和流动性定价需跟随 Fed 沟通重新校准。",
        "invalidation": "若后续 FOMC 声明、纪要或讲话与当前政策路径反向，Fed 沟通读法降级。",
    }


def test_overview_structured_analysis_keeps_all_retained_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    def row(key: str, label: str) -> dict[str, object]:
        return {
            "key": key,
            "label": label,
            "regime_label": "可用",
            "fact": f"{label} fact",
            "evidence": [f"{label} evidence"],
            "trade": f"{label} trade",
            "invalidation": f"{label} invalidation",
        }

    monkeypatch.setattr(
        macro_module_views,
        "_structured_market_thesis_row",
        lambda _scenario: row("market_thesis", "市场主线"),
    )
    monkeypatch.setattr(
        macro_module_views,
        "_structured_fed_communication_row",
        lambda _observations: row("fed_communication", "美联储沟通"),
    )
    monkeypatch.setattr(
        macro_module_views,
        "_structured_analysis_row",
        lambda *, key, label, diagnostics: row(key, label),
    )

    structured = macro_module_views._structured_analysis({}, scenario={}, observations=[])

    assert structured is not None
    assert [item["key"] for item in structured["rows"]] == [
        "market_thesis",
        "fed_communication",
        "assets",
        "rates",
        "policy",
        "liquidity",
        "growth",
        "employment",
        "inflation",
        "volatility",
        "credit",
    ]


def test_overview_ready_snapshot_treats_global_gaps_as_reference_quality_not_missing_page() -> None:
    snapshot = _snapshot_with_global_scenario()
    snapshot["status"] = "ready"
    snapshot["data_gaps_json"] = [
        {
            "code": "stale_latest_8d",
            "label": "最新观测已过期：8 天未更新",
            "severity": "error",
            "score_participation": False,
            "remediation_hint": "检查宏观核心源最新观测后重新投影。",
        }
    ]

    view = build_macro_module_view("overview", snapshot=snapshot, observations=[])

    assert view["data_health"]["summary_status"] == "partial"
    assert view["module_read"]["headline"] == "宏观总览：期限溢价压力"
    assert view["data_health"]["global_gaps"] == [
        {
            "code": "stale_latest_8d",
            "label": "最新观测已过期：8 天未更新",
            "severity": "error",
            "remediation_hint": "检查宏观核心源最新观测后重新投影。",
            "score_participation": False,
            "owner": "macro_intel",
            "score_impact": "excluded",
            "scope": "global_reference",
        }
    ]


def test_overview_transmission_uses_display_labels_for_chain_nodes_and_regimes() -> None:
    snapshot = _snapshot()
    snapshot["chain_json"] = {
        "liquidity": {"regime": "tightening"},
        "fed_corridor": {"regime": "corridor_pressure"},
        "volatility": {"regime": "carry"},
        "credit": {"regime": "confirmed_risk_on"},
        "cross_asset": {"regime": "equity_context_available"},
        "positioning": {"regime": "crowded_risk_long"},
    }

    view = build_macro_module_view("overview", snapshot=snapshot, observations=[])

    transmission_text = "\n".join(f"{node.get('label')} {node.get('value')}" for node in view["transmission"])
    assert "fed_corridor" not in transmission_text
    assert "cross_asset" not in transmission_text
    assert "positioning" not in transmission_text
    assert "未知宏观状态" not in transmission_text
    assert "政策走廊 走廊压力" in transmission_text
    assert "波动率 波动率 carry" in transmission_text
    assert "信用压力 风险偏好确认" in transmission_text
    assert "跨资产确认 风险资产参考可用" in transmission_text
    assert "仓位拥挤度 风险多头拥挤" in transmission_text


def test_overview_module_view_adds_official_events_to_market_event_flow() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot(),
        observations=[
            _event_obs(
                "event:fomc_decision_next",
                "official_calendar:fomc_decision_next",
                "2026-06-17",
                1,
                provider="official_calendar",
                raw_payload={
                    "series_key": "official_calendar:fomc_decision_next",
                    "provider": "official_calendar",
                    "observed_at": "2026-06-17",
                    "value": 1,
                    "unit": "days",
                    "frequency": "event",
                    "provenance": [
                        {
                            "event_title": "FOMC decision",
                            "event_time": "14:00 ET",
                            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                        }
                    ],
                },
            ),
            _event_obs(
                "event:treasury_auction_10y_bid_to_cover",
                "treasury_auction:10y_bid_to_cover",
                "2026-06-10",
                2.52,
                provider="treasury_auction",
                raw_payload={
                    "series_key": "treasury_auction:10y_bid_to_cover",
                    "provider": "treasury_auction",
                    "observed_at": "2026-06-10",
                    "value": 2.52,
                    "unit": "ratio",
                    "frequency": "event",
                    "provenance": [
                        {
                            "security_term": "10-Year",
                            "cusip": "91282CQQ9",
                            "source_url": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
                        }
                    ],
                },
            ),
            _event_obs(
                "event:treasury_auction_10y_next",
                "treasury_auction:10y_next_auction_days",
                "2026-07-08",
                22,
                provider="treasury_auction",
                raw_payload={
                    "series_key": "treasury_auction:10y_next_auction_days",
                    "provider": "treasury_auction",
                    "observed_at": "2026-07-08",
                    "value": 22,
                    "unit": "days_until",
                    "frequency": "event",
                    "source_ts": "2026-06-16",
                    "provenance": [
                        {
                            "security_type": "NOTE",
                            "security_term": "10-Year",
                            "announcement_date": "2026-07-02",
                            "auction_date": "2026-07-08",
                            "settlement_date": "2026-07-15",
                            "reopening": True,
                            "tips": False,
                            "floating_rate": False,
                            "source_url": "https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml",
                        }
                    ],
                },
            ),
            _event_obs(
                "event:fed_speech",
                "official_fed_text:speech_latest#abc123",
                "2026-05-08",
                None,
                provider="official_fed_text",
                raw_payload={
                    "series_key": "official_fed_text:speech_latest",
                    "provider": "official_fed_text",
                    "observed_at": "2026-05-08T23:30:01Z",
                    "value": "Waller, Update On Federal Reserve Bank Operations",
                    "unit": "document",
                    "frequency": "event",
                    "source_ts": "2026-05-08T23:30:00Z",
                    "provenance": [
                        {
                            "document_type": "speech",
                            "document_title": "Waller, Update On Federal Reserve Bank Operations",
                            "published_at": "2026-05-08T23:30:00Z",
                            "source_url": "https://www.federalreserve.gov/newsevents/speech/waller20260508a.htm",
                        }
                    ],
                },
            ),
        ],
    )

    assert "event_catalysts" not in view["module_read"]["decision_console"]
    assert "event_heatmap" not in view["module_read"]["decision_console"]
    assert view["module_read"]["market_event_flow"] == {
        "key": "market_event_flow",
        "label": "市场事件流",
        "rows": [
            {
                "key": "official_calendar:fomc_decision_next",
                "label": "FOMC 决议",
                "date": "2026-06-17",
                "detail": "2026-06-17 · 还有 1 天 · 14:00 ET",
                "source": "官方日历",
                "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                "kind": "calendar",
                "window": "0-3d",
                "severity": "high",
                "severity_label": "高",
                "category": "policy",
                "category_label": "政策",
                "impact": "policy_path",
                "impact_label": "政策路径",
                "watch": "利率路径和流动性定价。",
            },
            {
                "key": "treasury_auction:10y_next_auction_days",
                "label": "10Y 国债拍卖日历",
                "date": "2026-07-08",
                "detail": "2026-07-08 · 还有 22 天 · 2026-07-02 公告 · 2026-07-15 交割 · Reopen",
                "source": "US Treasury",
                "source_url": "https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml",
                "kind": "auction_calendar",
                "window": "15-30d",
                "severity": "low",
                "severity_label": "低",
                "category": "treasury_supply",
                "category_label": "国债供给",
                "impact": "settlement_watch",
                "impact_label": "拍卖/交割",
                "watch": "关注拍卖需求、公告规模和交割日资金占用。",
            },
            {
                "key": "treasury_auction:10y_bid_to_cover",
                "label": "10Y 国债拍卖 Bid/Cover",
                "date": "2026-06-10",
                "detail": "2026-06-10 · 2.52 · CUSIP 91282CQQ9",
                "source": "US Treasury",
                "source_url": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
                "kind": "auction_result",
                "window": "recent",
                "severity": "medium",
                "severity_label": "中",
                "category": "treasury_supply",
                "category_label": "国债供给",
                "impact": "auction_result",
                "impact_label": "拍卖结果",
                "watch": "拍卖结果作为国债需求和期限溢价压力证据。",
            },
            {
                "key": "official_fed_text:speech_latest",
                "label": "Fed 官员讲话",
                "date": "2026-05-08",
                "detail": "2026-05-08 · Waller, Update On Federal Reserve Bank Operations",
                "source": "Federal Reserve",
                "source_url": "https://www.federalreserve.gov/newsevents/speech/waller20260508a.htm",
                "kind": "fed_text",
                "window": "recent",
                "severity": "medium",
                "severity_label": "中",
                "category": "policy",
                "category_label": "政策",
                "impact": "fed_communication",
                "impact_label": "Fed 沟通",
                "watch": "跟踪措辞、投票分歧和政策路径信号。",
            },
        ],
    }


def test_overview_event_flow_show_bls_release_time_and_reference_period() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot(),
        observations=[
            _event_obs(
                "event:bls_cpi_next",
                "official_calendar:bls_cpi_next",
                "2026-07-14",
                28,
                provider="official_calendar",
                raw_payload={
                    "series_key": "official_calendar:bls_cpi_next",
                    "provider": "official_calendar",
                    "observed_at": "2026-07-14",
                    "value": 28,
                    "unit": "days_until",
                    "frequency": "event",
                    "provenance": [
                        {
                            "event_title": "Consumer Price Index",
                            "event_time_et": "08:30 AM",
                            "reference_period": "June 2026",
                            "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
                        }
                    ],
                },
            ),
        ],
    )

    assert view["module_read"]["market_event_flow"]["rows"] == [
        {
            "key": "official_calendar:bls_cpi_next",
            "label": "CPI 发布",
            "date": "2026-07-14",
            "detail": "2026-07-14 · 还有 28 天 · 08:30 AM · June 2026",
            "source": "官方日历",
            "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
            "kind": "calendar",
            "window": "15-30d",
            "severity": "low",
            "severity_label": "低",
            "category": "economic_data",
            "category_label": "经济数据",
            "impact": "release_revision",
            "impact_label": "实际/修正",
            "watch": "跟踪官方实际值、前值修正和数据口径变化。",
        },
    ]


def test_overview_event_flow_prioritizes_near_upcoming_treasury_auction_calendar() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot(),
        observations=[
            _event_obs("event:bea_gdp_next", "official_calendar:bea_gdp_next", "2026-07-30", 44),
            _event_obs("event:bls_cpi_next", "official_calendar:bls_cpi_next", "2026-07-14", 28),
            _event_obs("event:bls_employment_next", "official_calendar:bls_employment_next", "2026-07-02", 16),
            _event_obs("event:bls_ppi_next", "official_calendar:bls_ppi_next", "2026-07-15", 29),
            _event_obs("event:fomc_decision_next", "official_calendar:fomc_decision_next", "2026-06-17", 1),
            _event_obs(
                "event:treasury_auction_2y_next",
                "treasury_auction:2y_next_auction_days",
                "2026-07-27",
                41,
                provider="treasury_auction",
                raw_payload=_auction_calendar_payload("2-Year", "2026-07-23", "2026-07-27", "2026-07-31"),
            ),
            _event_obs(
                "event:treasury_auction_2y_next",
                "treasury_auction:2y_next_auction_days",
                "2026-06-23",
                7,
                provider="treasury_auction",
                raw_payload=_auction_calendar_payload("2-Year", "2026-06-18", "2026-06-23", "2026-06-30"),
            ),
            _event_obs(
                "event:treasury_auction_10y_next",
                "treasury_auction:10y_next_auction_days",
                "2026-07-08",
                22,
                provider="treasury_auction",
                raw_payload=_auction_calendar_payload("10-Year", "2026-07-02", "2026-07-08", "2026-07-15"),
            ),
            _event_obs(
                "event:treasury_auction_30y_next",
                "treasury_auction:30y_next_auction_days",
                "2026-07-09",
                23,
                provider="treasury_auction",
                raw_payload=_auction_calendar_payload("30-Year", "2026-07-02", "2026-07-09", "2026-07-15"),
            ),
        ],
    )

    rows = view["module_read"]["market_event_flow"]["rows"]
    assert [item["key"] for item in rows] == [
        "official_calendar:fomc_decision_next",
        "treasury_auction:2y_next_auction_days",
        "official_calendar:bls_employment_next",
        "treasury_auction:10y_next_auction_days",
        "treasury_auction:30y_next_auction_days",
        "official_calendar:bls_cpi_next",
        "official_calendar:bls_ppi_next",
        "official_calendar:bea_gdp_next",
    ]
    assert rows[1]["date"] == "2026-06-23"
    assert rows[1]["detail"] == "2026-06-23 · 还有 7 天 · 2026-06-18 公告 · 2026-06-30 交割"


def test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot(),
        observations=[
            _event_obs(
                "event:fomc_decision_next",
                "official_calendar:fomc_decision_next",
                "2026-06-17",
                1,
                provider="official_calendar",
                raw_payload={
                    "series_key": "official_calendar:fomc_decision_next",
                    "provider": "official_calendar",
                    "observed_at": "2026-06-17",
                    "value": 1,
                    "unit": "days_until",
                    "frequency": "event",
                    "provenance": [
                        {
                            "event_title": "FOMC decision",
                            "event_time": "14:00 ET",
                            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                        }
                    ],
                },
            ),
            _event_obs(
                "event:treasury_auction_2y_next",
                "treasury_auction:2y_next_auction_days",
                "2026-06-23",
                7,
                provider="treasury_auction",
                raw_payload=_auction_calendar_payload("2-Year", "2026-06-18", "2026-06-23", "2026-06-30"),
            ),
            _event_obs("event:bls_employment_next", "official_calendar:bls_employment_next", "2026-07-02", 16),
            _event_obs(
                "event:treasury_auction_10y_bid_to_cover",
                "treasury_auction:10y_bid_to_cover",
                "2026-06-10",
                2.52,
                provider="treasury_auction",
            ),
            _event_obs(
                "event:fed_speech",
                "official_fed_text:speech_latest#abc123",
                "2026-06-16",
                None,
                provider="official_fed_text",
                raw_payload={
                    "series_key": "official_fed_text:speech_latest",
                    "provider": "official_fed_text",
                    "observed_at": "2026-06-16T18:30:00Z",
                    "value": "Waller, Update On Federal Reserve Bank Operations",
                    "unit": "document",
                    "frequency": "event",
                    "source_ts": "2026-06-16T18:30:00Z",
                    "provenance": [
                        {
                            "document_type": "speech",
                            "document_title": "Waller, Update On Federal Reserve Bank Operations",
                            "published_at": "2026-06-16T18:30:00Z",
                            "source_url": "https://www.federalreserve.gov/newsevents/speech/waller20260616a.htm",
                        }
                    ],
                },
            ),
        ],
    )

    assert view["module_read"]["market_event_flow"]["rows"] == [
        {
            "key": "official_calendar:fomc_decision_next",
            "label": "FOMC 决议",
            "date": "2026-06-17",
            "detail": "2026-06-17 · 还有 1 天 · 14:00 ET",
            "source": "官方日历",
            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "kind": "calendar",
            "window": "0-3d",
            "severity": "high",
            "severity_label": "高",
            "category": "policy",
            "category_label": "政策",
            "impact": "policy_path",
            "impact_label": "政策路径",
            "watch": "利率路径和流动性定价。",
        },
        {
            "key": "treasury_auction:2y_next_auction_days",
            "label": "2Y 国债拍卖日历",
            "date": "2026-06-23",
            "detail": "2026-06-23 · 还有 7 天 · 2026-06-18 公告 · 2026-06-30 交割",
            "source": "US Treasury",
            "source_url": "https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml",
            "kind": "auction_calendar",
            "window": "4-7d",
            "severity": "medium",
            "severity_label": "中",
            "category": "treasury_supply",
            "category_label": "国债供给",
            "impact": "settlement_watch",
            "impact_label": "拍卖/交割",
            "watch": "关注拍卖需求、公告规模和交割日资金占用。",
        },
        {
            "key": "official_calendar:bls_employment_next",
            "label": "就业报告发布",
            "date": "2026-07-02",
            "detail": "2026-07-02 · 还有 16 天",
            "source": "官方日历",
            "source_url": None,
            "kind": "calendar",
            "window": "15-30d",
            "severity": "low",
            "severity_label": "低",
            "category": "economic_data",
            "category_label": "经济数据",
            "impact": "release_revision",
            "impact_label": "实际/修正",
            "watch": "跟踪官方实际值、前值修正和数据口径变化。",
        },
        {
            "key": "official_fed_text:speech_latest",
            "label": "Fed 官员讲话",
            "date": "2026-06-16",
            "detail": "2026-06-16 · Waller, Update On Federal Reserve Bank Operations",
            "source": "Federal Reserve",
            "source_url": "https://www.federalreserve.gov/newsevents/speech/waller20260616a.htm",
            "kind": "fed_text",
            "window": "recent",
            "severity": "medium",
            "severity_label": "中",
            "category": "policy",
            "category_label": "政策",
            "impact": "fed_communication",
            "impact_label": "Fed 沟通",
            "watch": "跟踪措辞、投票分歧和政策路径信号。",
        },
        {
            "key": "treasury_auction:10y_bid_to_cover",
            "label": "10Y 国债拍卖 Bid/Cover",
            "date": "2026-06-10",
            "detail": "2026-06-10 · 2.52",
            "source": "US Treasury",
            "source_url": None,
            "kind": "auction_result",
            "window": "recent",
            "severity": "medium",
            "severity_label": "中",
            "category": "treasury_supply",
            "category_label": "国债供给",
            "impact": "auction_result",
            "impact_label": "拍卖结果",
            "watch": "拍卖结果作为国债需求和期限溢价压力证据。",
        },
    ]


def test_overview_market_event_flow_uses_untruncated_event_candidates() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot(),
        observations=[
            _event_obs("event:fomc_decision_next", "official_calendar:fomc_decision_next", "2026-06-17", 1),
            _event_obs("event:bea_gdp_next", "official_calendar:bea_gdp_next", "2026-06-18", 2),
            _event_obs("event:bea_pce_next", "official_calendar:bea_pce_next", "2026-06-19", 3),
            _event_obs("event:bls_cpi_next", "official_calendar:bls_cpi_next", "2026-06-20", 4),
            _event_obs(
                "event:bls_employment_next",
                "official_calendar:bls_employment_next",
                "2026-06-21",
                5,
            ),
            _event_obs("event:bls_ppi_next", "official_calendar:bls_ppi_next", "2026-06-22", 6),
            _event_obs(
                "event:treasury_auction_2y_next",
                "treasury_auction:2y_next_auction_days",
                "2026-06-23",
                7,
                provider="treasury_auction",
                raw_payload=_auction_calendar_payload("2-Year", "2026-06-18", "2026-06-23", "2026-06-30"),
            ),
            _event_obs(
                "event:treasury_auction_10y_next",
                "treasury_auction:10y_next_auction_days",
                "2026-06-24",
                8,
                provider="treasury_auction",
                raw_payload=_auction_calendar_payload("10-Year", "2026-06-18", "2026-06-24", "2026-07-01"),
            ),
        ],
    )

    assert "event_catalysts" not in view["module_read"]["decision_console"]
    assert "event_heatmap" not in view["module_read"]["decision_console"]
    assert [item["key"] for item in view["module_read"]["market_event_flow"]["rows"]] == [
        "official_calendar:fomc_decision_next",
        "official_calendar:bea_gdp_next",
        "official_calendar:bea_pce_next",
        "official_calendar:bls_cpi_next",
        "official_calendar:bls_employment_next",
        "official_calendar:bls_ppi_next",
        "treasury_auction:2y_next_auction_days",
        "treasury_auction:10y_next_auction_days",
    ]


def test_overview_market_event_flow_adds_source_backed_news_events() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot(),
        observations=[],
        news_rows=[
            {
                "row_id": "news-row-1",
                "news_item_id": "news-1",
                "headline": "中东震荡下，日本追加预算预期升温",
                "summary": "油价与美元走强，风险资产低开。",
                "source_domain": "bloomberg.com",
                "canonical_url": "https://news.google.com/articles/macro-1",
                "latest_at_ms": 1_781_049_600_000,
                "token_lanes": [{"symbol": "SPX"}, {"symbol": "美元"}],
                "market_scope": {
                    "primary": "macro_policy",
                    "scope": ["macro_policy", "equities", "fx"],
                    "status": "classified",
                },
                "signal": {
                    "agent_signal": {
                        "status": "ready",
                        "decision_class": "context",
                        "direction": "neutral",
                    },
                    "display_signal": {
                        "status": "ready",
                        "direction": "neutral",
                        "label_zh": "中性",
                    },
                    "alert_eligibility": {"in_app_eligible": False, "decision_class": "context"},
                },
            }
        ],
    )

    assert "event_catalysts" not in view["module_read"]["decision_console"]
    assert "event_heatmap" not in view["module_read"]["decision_console"]
    assert view["module_read"]["market_event_flow"] == {
        "key": "market_event_flow",
        "label": "市场事件流",
        "rows": [
            {
                "key": "news:news-row-1",
                "label": "中东震荡下，日本追加预算预期升温",
                "date": "2026-06-10",
                "detail": "油价与美元走强，风险资产低开。",
                "source": "bloomberg.com",
                "source_url": "https://news.google.com/articles/macro-1",
                "kind": "news",
                "window": "recent",
                "severity": "low",
                "severity_label": "低",
                "category": "macro_policy",
                "category_label": "美联储",
                "impact": "mainline_context",
                "impact_label": "不改主线",
                "watch": "SPX · 美元 · 美联储",
            }
        ],
    }


def test_overview_decision_console_adds_future_24_72h_catalysts() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "watch_triggers": [
            {
                "code": "real_yield_breakout",
                "description": "10Y real yield keeps rising.",
                "time_window": "24h",
                "severity": "high",
            },
            {
                "code": "hy_oas_distress",
                "description": "HY OAS crosses distress thresholds.",
                "time_window": "72h",
                "severity": "medium",
            },
        ],
    }
    view = build_macro_module_view(
        "overview",
        snapshot=snapshot,
        observations=[
            _event_obs(
                "event:fomc_decision_next",
                "official_calendar:fomc_decision_next",
                "2026-06-17",
                1,
                provider="official_calendar",
                raw_payload={
                    "series_key": "official_calendar:fomc_decision_next",
                    "provider": "official_calendar",
                    "observed_at": "2026-06-17",
                    "value": 1,
                    "unit": "days_until",
                    "frequency": "event",
                    "provenance": [
                        {
                            "event_title": "FOMC decision",
                            "event_time": "14:00 ET",
                            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                        }
                    ],
                },
            ),
            _event_obs(
                "event:treasury_auction_2y_next",
                "treasury_auction:2y_next_auction_days",
                "2026-06-19",
                3,
                provider="treasury_auction",
                raw_payload=_auction_calendar_payload("2-Year", "2026-06-18", "2026-06-19", "2026-06-30"),
            ),
            _event_obs("event:bls_cpi_next", "official_calendar:bls_cpi_next", "2026-06-20", 4),
            _event_obs(
                "event:treasury_auction_10y_bid_to_cover",
                "treasury_auction:10y_bid_to_cover",
                "2026-06-10",
                2.52,
                provider="treasury_auction",
            ),
        ],
    )

    assert view["module_read"]["decision_console"]["future_catalysts"] == {
        "label": "未来 24/72h 催化剂",
        "rows": [
            {
                "key": "watch:real_yield_breakout",
                "label": "实际利率突破",
                "description": "10Y real yield keeps rising.",
                "window": "24h",
                "window_label": "24h",
                "severity": "high",
                "severity_label": "高",
                "source": "情景触发",
                "kind": "watch_trigger",
            },
            {
                "key": "event:official_calendar:fomc_decision_next",
                "label": "FOMC 决议",
                "description": "2026-06-17 · 还有 1 天 · 14:00 ET",
                "window": "24h",
                "window_label": "24h",
                "severity": "high",
                "severity_label": "高",
                "source": "官方日历",
                "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                "kind": "calendar",
            },
            {
                "key": "watch:hy_oas_distress",
                "label": "高收益债利差进入困境区",
                "description": "HY OAS crosses distress thresholds.",
                "window": "72h",
                "window_label": "72h",
                "severity": "medium",
                "severity_label": "中",
                "source": "情景触发",
                "kind": "watch_trigger",
            },
            {
                "key": "event:treasury_auction:2y_next_auction_days",
                "label": "2Y 国债拍卖日历",
                "description": "2026-06-19 · 还有 3 天 · 2026-06-18 公告 · 2026-06-30 交割",
                "window": "72h",
                "window_label": "72h",
                "severity": "medium",
                "severity_label": "中",
                "source": "US Treasury",
                "source_url": "https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml",
                "kind": "auction_calendar",
            },
        ],
    }
    assert "official_calendar:bls_cpi_next" not in str(view["module_read"]["decision_console"]["future_catalysts"])
    assert "treasury_auction:10y_bid_to_cover" not in str(view["module_read"]["decision_console"]["future_catalysts"])


def test_overview_decision_console_adds_watchlist_alerts_from_trade_map_and_rules() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "watch_triggers": [
            {
                "code": "real_yield_breakout",
                "description": "10Y real yield keeps rising.",
                "time_window": "24h",
                "severity": "high",
            }
        ],
        "invalidations": [{"code": "ten_year_yield_reverses", "description": "10Y yield loses pressure."}],
        "quality_blockers": [
            {
                "code": "missing_asset_spy",
                "label": "缺少当前数据：SPY",
                "description": "检查对应 provider 导入与最新观测。",
                "severity": "error",
            }
        ],
        "trade_map": [
            {
                "expression": "risk_down_credit_sensitive",
                "time_window": "1w",
                "confirms_on": ["hy_oas_widening_5d"],
                "invalidates_on": ["vix_returns_to_carry"],
                "legs": [
                    {"symbol": "BIL", "label": "现金/短债", "action": "做多/防守"},
                    {"symbol": "QQQ", "label": "纳斯达克", "action": "回避/做空代理"},
                    {"symbol": "HYG", "label": "高收益信用", "action": "低配"},
                ],
            }
        ],
    }

    view = build_macro_module_view("overview", snapshot=snapshot, observations=[])

    assert view["module_read"]["decision_console"]["watchlist_alerts"] == {
        "key": "watchlist_alerts",
        "label": "Watchlist 与触发提醒",
        "assets": [
            {"key": "BIL", "symbol": "BIL", "label": "现金/短债", "action": "做多/防守"},
            {"key": "QQQ", "symbol": "QQQ", "label": "纳斯达克", "action": "回避/做空代理"},
            {"key": "HYG", "symbol": "HYG", "label": "高收益信用", "action": "低配"},
        ],
        "rules": [
            {
                "key": "watch:real_yield_breakout",
                "label": "实际利率突破",
                "description": "10Y real yield keeps rising.",
                "kind": "watch",
                "kind_label": "触发",
                "window": "24h",
                "severity": "high",
                "severity_label": "高",
            },
            {
                "key": "invalidation:ten_year_yield_reverses",
                "label": "10年期收益率回落",
                "description": "10Y yield loses pressure.",
                "kind": "invalidation",
                "kind_label": "失效",
            },
            {
                "key": "quality:missing_asset_spy",
                "label": "缺少当前数据：SPY",
                "description": "检查对应 provider 导入与最新观测。",
                "kind": "quality",
                "kind_label": "质量",
                "severity": "error",
                "severity_label": "阻断",
            },
        ],
    }


def test_overview_trade_map_adds_five_asset_historical_review() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "trade_map": [
            {
                "expression": "risk_down_credit_sensitive",
                "time_window": "1w",
                "confirms_on": ["hy_oas_widening_5d"],
                "invalidates_on": ["vix_returns_to_carry"],
                "legs": [],
            }
        ],
    }

    view = build_macro_module_view(
        "overview",
        snapshot=snapshot,
        observations=[
            _obs("asset:ndx", "2026-05-01", 100.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-02", 99.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-06", 96.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-20", 94.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-21", 94.0, unit="index", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-01", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-02", 98.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-06", 94.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-20", 90.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-21", 90.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-01", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-02", 101.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-06", 102.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-20", 104.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-21", 104.0, unit="usd", source_name="yahoo"),
            _obs("asset:spx", "2026-05-01", 100.0, unit="index", source_name="fred"),
            _obs("asset:spx", "2026-05-02", 99.5, unit="index", source_name="fred"),
            _obs("asset:spx", "2026-05-06", 99.0, unit="index", source_name="fred"),
            _obs("asset:spx", "2026-05-20", 98.0, unit="index", source_name="fred"),
            _obs("asset:spx", "2026-05-21", 98.0, unit="index", source_name="fred"),
            _obs("asset:tlt", "2026-05-01", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-02", 100.5, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-06", 98.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-10", 96.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-20", 101.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-21", 101.0, unit="usd", source_name="yahoo"),
        ],
    )

    trade = view["module_read"]["decision_console"]["trade_map"][0]
    review = trade["historical_review"]
    assert review == {
        "label": "五资产 60日验证",
        "window": "60d",
        "sample_count": 5,
        "hit_count": 5,
        "win_rate": 1.0,
        "win_rate_label": "5/5",
        "average_return_pct": -2.6,
        "max_adverse_excursion_pct": -4.0,
        "rows": [
            {
                "asset": "NDX",
                "label": "纳斯达克",
                "concept_key": "asset:ndx",
                "expected_direction": "down",
                "action": "回避",
                "return_pct": -6.0,
                "mfe_pct": 6.0,
                "mae_pct": 0.0,
                "outcome": "hit",
            },
            {
                "asset": "BTC",
                "label": "比特币",
                "concept_key": "crypto:btc",
                "expected_direction": "down",
                "action": "回避",
                "return_pct": -10.0,
                "mfe_pct": 10.0,
                "mae_pct": 0.0,
                "outcome": "hit",
            },
            {
                "asset": "GOLD",
                "label": "黄金",
                "concept_key": "asset:gld",
                "expected_direction": "up",
                "action": "防守",
                "return_pct": 4.0,
                "mfe_pct": 4.0,
                "mae_pct": 0.0,
                "outcome": "hit",
            },
            {
                "asset": "SPX",
                "label": "标普500",
                "concept_key": "asset:spx",
                "expected_direction": "down",
                "action": "回避",
                "return_pct": -2.0,
                "mfe_pct": 2.0,
                "mae_pct": 0.0,
                "outcome": "hit",
            },
            {
                "asset": "TLT",
                "label": "长债",
                "concept_key": "asset:tlt",
                "expected_direction": "up",
                "action": "防守",
                "return_pct": 1.0,
                "mfe_pct": 1.0,
                "mae_pct": -4.0,
                "outcome": "hit",
            },
        ],
    }
    assert trade["portfolio_review"] == {
        "label": "$10K 纸面映射",
        "notional_usd": 10000,
        "deployed_usd": 10000,
        "pnl_usd": 460.0,
        "pnl_pct": 4.6,
        "max_adverse_usd": -80.0,
        "risk_temperature": "低",
        "summary": "$10,000 · P&L +$460 · 胜率 5/5",
    }
    assert trade["action_checklist"] == [
        {
            "kind": "confirm",
            "label": "HY OAS 5日走阔",
            "description": "观察 HY OAS 5日走阔 是否继续确认。",
        },
        {
            "kind": "invalidate",
            "label": "VIX 回到 carry 区间",
            "description": "若 VIX 回到 carry 区间，则撤销该映射。",
        },
        {
            "kind": "position_review",
            "label": "纸面仓位复盘",
            "description": "$10,000 · P&L +$460 · 胜率 5/5",
        },
    ]
    assert trade["historical_trust"] == {
        "label": "历史可信度",
        "score_pct": 93.3,
        "quality": "高",
        "sample_count": 15,
        "hit_count": 14,
        "summary": "历史可信度 93.3% · 高 · 15 个样本",
    }
    assert trade["holding_period_review"] == {
        "label": "持有期复盘",
        "rows": [
            {
                "horizon": "1d",
                "label": "1D",
                "status": "complete",
                "status_label": "已完成",
                "sample_count": 5,
                "hit_count": 5,
                "win_rate": 1.0,
                "win_rate_label": "5/5",
                "pnl_usd": 100.0,
                "average_signed_return_pct": 1.0,
            },
            {
                "horizon": "5d",
                "label": "5D",
                "status": "complete",
                "status_label": "已完成",
                "sample_count": 5,
                "hit_count": 4,
                "win_rate": 0.8,
                "win_rate_label": "4/5",
                "pnl_usd": 220.0,
                "average_signed_return_pct": 2.2,
            },
            {
                "horizon": "20d",
                "label": "20D",
                "status": "complete",
                "status_label": "已完成",
                "sample_count": 5,
                "hit_count": 5,
                "win_rate": 1.0,
                "win_rate_label": "5/5",
                "pnl_usd": 460.0,
                "average_signed_return_pct": 4.6,
            },
        ],
    }


def test_overview_decision_console_summarizes_judgement_review_across_holding_windows() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "trade_map": [
            {
                "expression": "risk_down_credit_sensitive",
                "time_window": "1w",
                "confirms_on": ["hy_oas_widening_5d"],
                "invalidates_on": ["vix_returns_to_carry"],
                "legs": [],
            }
        ],
    }

    view = build_macro_module_view(
        "overview",
        snapshot=snapshot,
        observations=[
            _obs("asset:ndx", "2026-05-01", 100.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-02", 99.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-06", 96.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-20", 94.0, unit="index", source_name="yahoo"),
            _obs("asset:ndx", "2026-05-21", 94.0, unit="index", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-01", 100.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-02", 98.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-06", 94.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-20", 90.0, unit="usd", source_name="yahoo"),
            _obs("crypto:btc", "2026-05-21", 90.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-01", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-02", 101.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-06", 102.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-20", 104.0, unit="usd", source_name="yahoo"),
            _obs("asset:gld", "2026-05-21", 104.0, unit="usd", source_name="yahoo"),
            _obs("asset:spx", "2026-05-01", 100.0, unit="index", source_name="fred"),
            _obs("asset:spx", "2026-05-02", 99.5, unit="index", source_name="fred"),
            _obs("asset:spx", "2026-05-06", 99.0, unit="index", source_name="fred"),
            _obs("asset:spx", "2026-05-20", 98.0, unit="index", source_name="fred"),
            _obs("asset:spx", "2026-05-21", 98.0, unit="index", source_name="fred"),
            _obs("asset:tlt", "2026-05-01", 100.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-02", 100.5, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-06", 98.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-10", 96.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-20", 101.0, unit="usd", source_name="yahoo"),
            _obs("asset:tlt", "2026-05-21", 101.0, unit="usd", source_name="yahoo"),
        ],
    )

    assert view["module_read"]["decision_console"]["judgement_review"] == {
        "label": "昨日判断复盘",
        "item_count": 1,
        "item_count_label": "1 条",
        "rows": [
            {
                "key": "risk_down_credit_sensitive:holding_periods",
                "expression": "risk_down_credit_sensitive",
                "label": "风险降档 / 信用敏感",
                "reliability_summary": "历史可信度 93.3% · 高 · 15 个样本",
                "windows": [
                    {
                        "horizon": "1d",
                        "label": "1D",
                        "status": "complete",
                        "status_label": "已完成",
                        "sample_count": 5,
                        "hit_count": 5,
                        "win_rate_label": "5/5",
                        "pnl_usd": 100.0,
                        "average_signed_return_pct": 1.0,
                    },
                    {
                        "horizon": "5d",
                        "label": "5D",
                        "status": "complete",
                        "status_label": "已完成",
                        "sample_count": 5,
                        "hit_count": 4,
                        "win_rate_label": "4/5",
                        "pnl_usd": 220.0,
                        "average_signed_return_pct": 2.2,
                    },
                    {
                        "horizon": "20d",
                        "label": "20D",
                        "status": "complete",
                        "status_label": "已完成",
                        "sample_count": 5,
                        "hit_count": 5,
                        "win_rate_label": "5/5",
                        "pnl_usd": 460.0,
                        "average_signed_return_pct": 4.6,
                    },
                ],
            }
        ],
    }


def test_overview_module_view_preserves_watch_trigger_horizon_and_priority() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot(),
        observations=[],
    )

    assert view["module_evidence"]["watch_triggers"][0] == {
        "code": "real_yield_breakout",
        "label": "实际利率突破",
        "description": "10Y real yield keeps rising.",
        "time_window": "24h",
        "severity": "high",
    }


def test_overview_module_view_labels_hy_oas_watch_and_invalidation_codes() -> None:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        **snapshot["scenario_json"],
        "watch_triggers": [{"code": "hy_oas_widening", "description": "HY OAS widens over five trading days."}],
        "invalidations": [
            {"code": "hy_oas_tightens", "description": "HY OAS tightens enough to reject credit stress."}
        ],
    }

    view = build_macro_module_view("overview", snapshot=snapshot, observations=[])

    assert view["module_evidence"]["watch_triggers"][0]["label"] == "HY OAS 走阔"
    assert view["module_evidence"]["invalidations"][0]["label"] == "HY OAS 收窄"


def test_build_macro_module_view_rejects_unknown_module_id() -> None:
    with pytest.raises(UnsupportedMacroModuleError) as exc_info:
        build_macro_module_view("not-real", snapshot=None, observations=[])

    assert exc_info.value.code == "unsupported_macro_module"


@pytest.mark.parametrize(
    "module_id",
    ("rates", "fed", "liquidity", "economy", "volatility", "credit"),
)
def test_build_macro_module_view_rejects_parent_category_ids(module_id: str) -> None:
    with pytest.raises(UnsupportedMacroModuleError):
        build_macro_module_view(module_id, snapshot=None, observations=[])


def _snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "snapshot-1",
        "projection_version": "macro_regime_v4",
        "asof_date": "2026-05-20",
        "status": "partial",
        "regime": "tightening",
        "computed_at_ms": NOW_MS,
        "features_json": {
            "rates:dgs2": _feature("rates:dgs2", 3.9, unit="percent", source_name="fred"),
            "rates:dgs10": _feature("rates:dgs10", 4.7, unit="percent", source_name="fred"),
            "asset:spx": _feature("asset:spx", 5312.4, unit="index", source_name="fred"),
            "asset:spy": _feature("asset:spy", 523.1, unit="usd", source_name="yahoo"),
            "asset:qqq": _feature("asset:qqq", 454.2, unit="usd", source_name="yahoo"),
            "asset:tlt": _feature("asset:tlt", 88.4, unit="usd", source_name="yahoo"),
            "vol:vix": _feature("vol:vix", 17.2, unit="index", source_name="fred"),
            "credit:hy_oas": _feature("credit:hy_oas", 2.8, unit="percent", source_name="fred"),
            "crypto:btc": _feature("crypto:btc", 110_000, unit="usd", source_name="yahoo"),
        },
        "chain_json": {
            "rates": {"regime": "tightening", "score": 7.1, "evidence": ["10y=4.70"], "data_gaps": []},
        },
        "scenario_json": {
            "current_regime": "tightening",
            "confidence": 0.64,
            "confirmations": [
                {"code": "term_premium_pressure", "description": "10Y yield pressure"},
                {"code": "rrp_buffer_low", "description": "RRP buffer is low"},
            ],
            "contradictions": [],
            "watch_triggers": [
                {
                    "code": "real_yield_breakout",
                    "description": "10Y real yield keeps rising.",
                    "time_window": "24h",
                    "severity": "high",
                },
                {"code": "hy_oas_distress", "description": "HY OAS crosses distress thresholds."},
            ],
            "invalidations": [
                {"code": "ten_year_yield_reverses", "description": "10Y yield loses pressure."},
                {"code": "credit_spreads_normalize", "description": "HY and IG OAS tighten together."},
            ],
            "trade_map": [{"expression": "duration_pressure_quality_over_growth"}],
        },
        "panels_json": {"rates": {"regime": "term_premium_pressure", "score": 7.1}},
        "indicators_json": {"rates:dgs10": {"value": 4.7, "unit": "percent"}},
        "triggers_json": [{"code": "real_yield_breakout", "description": "10Y real yield keeps rising."}],
        "data_gaps_json": [
            {
                "code": "missing_rates_dgs5",
                "label": "缺少当前数据：5Y",
                "severity": "error",
                "score_participation": False,
                "remediation_hint": "检查 FRED 5Y 国债收益率导入与最新观测。",
            }
        ],
        "source_coverage_json": {"latest_coverage_ratio": 0.5, "history_coverage_ratio": 0.25},
        "scorecard_json": {"projection_version": "macro_regime_v4", "chain_average": 7.1},
    }


def _snapshot_with_global_scenario() -> dict[str, object]:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        "current_regime": "term_premium_pressure",
        "confidence": 0.79,
        "confirmations": [{"code": "global_term_premium", "description": "global only"}],
        "top_changes": [
            {
                "code": "higher_real_rates",
                "label": "实际利率上行",
                "description": "10Y real yield broke higher",
                "node": "rates",
                "kind": "trigger",
            },
            {
                "code": "rrp_buffer_low",
                "label": "RRP 缓冲偏低",
                "description": "ON RRP buffer is below 300bn USD",
                "node": "funding",
                "kind": "trigger",
            },
        ],
        "quality_blockers": [
            {
                "code": "missing_liquidity_srf",
                "label": "缺少 SRF",
                "description": "缺少 SRF",
                "severity": "error",
                "remediation_hint": "同步 macro-core 流动性深度源后重新投影。",
            }
        ],
        "trade_map": [{"expression": "duration_pressure_quality_over_growth"}],
        "scenario_cases": [
            {
                "case": "base",
                "label": "基准情景",
                "probability": 0.5,
                "probability_label": "50%",
                "time_window": "未来 2 周",
                "thesis": "长端利率维持压力。",
                "trade": "低配 TLT。",
                "entry_condition": "10Y 继续上行。",
                "stop": "10Y 回落。",
                "invalidation": "实际利率压力消退。",
            }
        ],
    }
    snapshot["data_gaps_json"] = [
        {
            "code": "missing_liquidity_srf",
            "label": "缺少 SRF",
            "severity": "error",
            "remediation_hint": "同步 macro-core 流动性深度源后重新投影。",
        }
    ]
    return snapshot


def _feature(concept_key: str, value: float, *, unit: str, source_name: str) -> dict[str, object]:
    labels = {
        "rates:dgs3mo": ("3个月期美债收益率", "3M", "美国短端国库券收益率", "%"),
        "rates:dgs2": ("2年期美债收益率", "2Y", "政策预期敏感的短端美债收益率", "%"),
        "rates:dgs5": ("5年期美债收益率", "5Y", "美国中端美债收益率", "%"),
        "rates:dgs10": ("10年期美债收益率", "10Y", "美国长期无风险利率基准", "%"),
        "rates:dgs30": ("30年期美债收益率", "30Y", "美国超长端美债收益率", "%"),
        "asset:spx": ("标普500", "SPX", "美国大盘股风险偏好基准", "点"),
        "asset:spy": ("标普500 ETF", "SPY", "美国大盘股可交易风险偏好代理", "美元"),
        "asset:qqq": ("纳指100 ETF", "QQQ", "美国成长股风险偏好代理", "美元"),
        "asset:tlt": ("长期美债 ETF", "TLT", "长久期利率敏感资产代理", "美元"),
        "fx:dxy": ("DXY 美元指数", "DXY", "美元指数风险偏好和流动性代理", "点"),
        "commodity:wti": ("WTI 原油现货", "WTI Spot", "FRED 原油现货宏观参考", "美元/桶"),
        "commodity:wti_futures": ("WTI 原油期货", "CL=F", "WTI 原油可交易期货代理", "美元"),
        "vol:vix": ("VIX", "VIX", "标普500 隐含波动率压力", "点"),
        "vol:move": ("MOVE 美债波动率", "MOVE", "Yahoo Finance 上的 ICE BofA MOVE 美债隐含波动率代理", "点"),
        "credit:ig_oas": ("投资级 OAS", "IG OAS", "美国投资级债信用利差", "%"),
        "credit:hy_oas": ("高收益债 OAS", "HY OAS", "美国高收益债信用利差压力", "%"),
        "credit:hy_ccc_oas": ("CCC 高收益债 OAS", "CCC OAS", "高收益债尾部信用压力", "%"),
        "asset:hyg": ("高收益债 ETF", "HYG", "高收益信用 ETF 代理", "美元"),
        "asset:lqd": ("投资级债 ETF", "LQD", "投资级信用 ETF 代理", "美元"),
        "credit:nfci": ("NFCI", "NFCI", "芝加哥联储金融条件指数", "指数"),
        "credit:anfci": ("调整后 NFCI", "ANFCI", "芝加哥联储调整后金融条件指数", "指数"),
        "credit:sloos_ci_large_tightening": (
            "SLOOS 大中型企业贷款标准收紧",
            "SLOOS Lg Tight",
            "银行对大中型企业贷款标准净收紧比例",
            "%",
        ),
        "vol:vix3m": ("VIX3M", "VIX3M", "3个月标普500隐含波动率", "点"),
        "vol:vix1d": ("VIX1D 当日波动率", "VIX1D", "Cboe 1-Day Volatility Index", "点"),
        "vol:vix9d": ("VIX9D 近端波动率", "VIX9D", "Cboe 9-Day Volatility Index", "点"),
        "vol:vvix": ("VVIX 波动率凸性", "VVIX", "Cboe VIX of VIX 指数", "点"),
        "vol:skew": ("SKEW 尾部风险", "SKEW", "Cboe SKEW 指数", "点"),
        "vol:vxn": ("VXN 纳指波动率", "VXN", "纳斯达克100隐含波动率", "点"),
        "asset:vixy": ("VIXY 短期期货 ETF", "VIXY", "短端 VIX 期货 ETF 代理", "美元"),
        "asset:vixm": ("VIXM 中期期货 ETF", "VIXM", "中端 VIX 期货 ETF 代理", "美元"),
        "fed:dff": ("每日有效联邦基金利率", "DFF", "FRED 每日有效联邦基金利率", "%"),
        "fed:effr": ("有效联邦基金利率", "EFFR", "纽约联储有效联邦基金利率", "%"),
        "fed:effr_volume": ("EFFR 成交量", "EFFR Vol", "EFFR 底层联邦基金成交量", "百万美元"),
        "fed:iorb": ("准备金余额利率", "IORB", "美联储管理利率走廊上沿锚", "%"),
        "fed:obfr": ("隔夜银行融资利率", "OBFR", "NY Fed 广义无担保隔夜银行融资利率", "%"),
        "fed:obfr_volume": ("OBFR 成交量", "OBFR Vol", "OBFR 底层银行融资成交量", "百万美元"),
        "fed:sofr_30d": ("SOFR 30D", "SOFR 30D", "30日平均 SOFR", "%"),
        "fed:target_lower": ("联邦基金目标下限", "Target Lower", "FOMC 联邦基金目标区间下限", "%"),
        "fed:target_upper": ("联邦基金目标上限", "Target Upper", "FOMC 联邦基金目标区间上限", "%"),
        "rates:real_5y": ("5年期实际利率", "5Y Real", "5年期 TIPS 实际利率", "%"),
        "rates:real_10y": ("10年期实际利率", "10Y Real", "10年期 TIPS 实际利率", "%"),
        "rates:real_30y": ("30年期实际利率", "30Y Real", "30年期 TIPS 实际利率", "%"),
        "inflation:5y_breakeven": ("5年期通胀补偿", "5Y BEI", "5年期市场隐含通胀补偿", "%"),
        "inflation:10y_breakeven": ("10年期通胀补偿", "10Y BEI", "10年期市场隐含通胀补偿", "%"),
        "inflation:5y5y_forward": ("5年5年远期通胀", "5Y5Y", "5年5年远期通胀补偿", "%"),
        "inflation:core_cpi": ("核心 CPI", "Core CPI", "剔除食品和能源后的 CPI", "指数"),
        "inflation:cpi": ("CPI", "CPI", "美国消费者价格指数", "指数"),
        "inflation:ppi": ("PPI", "PPI", "生产者价格指数", "指数"),
        "liquidity:fed_assets": ("美联储总资产", "Fed 资产", "美联储资产负债表规模", "百万美元"),
        "liquidity:bgcr": ("BGCR", "BGCR", "NY Fed 广义一般抵押品回购利率", "%"),
        "liquidity:on_rrp": ("隔夜逆回购", "ON RRP", "隔夜逆回购工具使用量", "百万美元"),
        "liquidity:bgcr_volume": ("BGCR 成交量", "BGCR Vol", "BGCR 底层交易成交量", "百万美元"),
        "liquidity:sofr": ("SOFR", "SOFR", "有担保隔夜融资利率", "%"),
        "liquidity:sofr_volume": ("SOFR 成交量", "SOFR Vol", "SOFR 底层交易成交量", "百万美元"),
        "liquidity:tga": ("财政部现金账户", "TGA", "美国财政部在美联储现金余额", "百万美元"),
        "liquidity:tgcr": ("TGCR", "TGCR", "NY Fed 三方一般抵押品回购利率", "%"),
        "liquidity:tgcr_volume": ("TGCR 成交量", "TGCR Vol", "TGCR 底层交易成交量", "百万美元"),
        "consumer:pce_real": ("实际 PCE", "Real PCE", "通胀调整后的个人消费支出", "指数"),
        "consumer:retail_sales": ("零售销售", "Retail", "美国零售销售", "指数"),
        "economy:gdp_real": ("实际 GDP", "Real GDP", "美国实际国内生产总值", "十亿美元"),
        "economy:gdp_nowcast": ("GDPNow", "GDPNow", "Atlanta Fed GDPNow 实时 GDP 增长估计", "% SAAR"),
        "economy:housing_starts": ("住房开工", "Housing", "美国新屋开工年化", "千套"),
        "economy:industrial_production": ("工业生产", "IP", "美国工业生产指数", "指数"),
        "labor:avg_hourly_earnings": ("平均时薪", "AHE", "美国私营部门平均时薪", "美元/小时"),
        "labor:initial_claims": ("初请失业金", "Claims", "美国首次申请失业救济人数", "人"),
        "labor:job_openings": ("职位空缺", "JOLTS", "JOLTS 职位空缺", "千人"),
        "labor:payrolls": ("非农就业", "NFP", "美国非农就业总人数", "千人"),
        "labor:unemployment": ("失业率", "U-3", "美国失业率", "%"),
        "crypto:btc": ("比特币", "BTC", "加密资产宏观风险偏好代理", "美元"),
    }
    label, short_label, description, unit_label = labels[concept_key]
    return {
        "concept_key": concept_key,
        "label": label,
        "short_label": short_label,
        "description": description,
        "unit_label": unit_label,
        "latest": {"value": value, "observed_at": "2026-05-20", "unit": unit},
        "freshness_days": 1,
        "delta": {"20d": None},
        "history_points": 1,
        "history_windows": {"20d": {"points": 1, "required_points": 21, "ready": False}},
        "score_participation": False,
        "data_quality": "ok",
        "source": {"name": source_name, "series_key": f"{source_name}:{concept_key}"},
        "data_gaps": [
            {
                "code": "insufficient_history_20d",
                "label": "历史样本不足：无法计算 20 日变化",
                "severity": "warning",
                "score_participation": False,
                "remediation_hint": "回填历史后重新生成宏观投影。",
            }
        ],
    }


def _feature_with_history(
    concept_key: str,
    points: list[tuple[str, float]],
    *,
    unit: str = "percent",
    source_name: str = "fred",
) -> dict[str, object]:
    latest_observed_at, latest_value = points[-1]
    feature = _feature(concept_key, latest_value, unit=unit, source_name=source_name)
    feature["latest"] = {"value": latest_value, "observed_at": latest_observed_at, "unit": unit}
    feature["history"] = [{"observed_at": observed_at, "value": value} for observed_at, value in points]
    feature["history_points"] = len(points)
    feature["history_windows"] = {"20d": {"points": len(points), "required_points": 2, "ready": True}}
    feature["data_gaps"] = []
    return feature


def _add_liquidity_pressure_features(features: dict[str, object]) -> None:
    features["liquidity:sofr"] = _feature_with_history(
        "liquidity:sofr",
        [
            ("2026-04-20", 4.36),
            ("2026-05-13", 4.41),
            ("2026-05-20", 4.47),
        ],
    )
    features["fed:iorb"] = _feature_with_history(
        "fed:iorb",
        [
            ("2026-04-20", 4.40),
            ("2026-05-13", 4.40),
            ("2026-05-20", 4.40),
        ],
    )
    features["liquidity:tgcr"] = _feature_with_history(
        "liquidity:tgcr",
        [
            ("2026-04-20", 4.35),
            ("2026-05-13", 4.37),
            ("2026-05-20", 4.38),
        ],
    )
    features["liquidity:sofr_volume"] = _feature_with_history(
        "liquidity:sofr_volume",
        [
            ("2026-04-20", 2_700_000.0),
            ("2026-05-13", 2_850_000.0),
            ("2026-05-20", 3_023_000.0),
        ],
        unit="million_usd",
    )
    features["liquidity:on_rrp"] = _feature_with_history(
        "liquidity:on_rrp",
        [
            ("2026-04-20", 900_000.0),
            ("2026-05-13", 820_000.0),
            ("2026-05-20", 760_000.0),
        ],
        unit="million_usd",
    )
    features["liquidity:tga"] = _feature_with_history(
        "liquidity:tga",
        [
            ("2026-04-20", 600_000.0),
            ("2026-05-13", 690_000.0),
            ("2026-05-20", 760_000.0),
        ],
        unit="million_usd",
    )
    features["liquidity:fed_assets"] = _feature_with_history(
        "liquidity:fed_assets",
        [
            ("2026-04-20", 7_400_000.0),
            ("2026-05-13", 7_350_000.0),
            ("2026-05-20", 7_300_000.0),
        ],
        unit="million_usd",
    )


def _obs(concept_key: str, observed_at: str, value: float, *, unit: str, source_name: str) -> dict[str, object]:
    return {
        "concept_key": concept_key,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": unit,
        "source_name": source_name,
        "series_key": f"{source_name}:{concept_key}",
        "data_quality": "ok",
    }


def _event_obs(
    concept_key: str,
    series_key: str,
    observed_at: str,
    value: float | None,
    *,
    provider: str = "official_calendar",
    raw_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = raw_payload or {
        "series_key": series_key,
        "provider": provider,
        "observed_at": observed_at,
        "value": value,
        "unit": "days_until",
        "frequency": "event",
        "provenance": [],
    }
    return {
        "concept_key": concept_key,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": payload.get("unit"),
        "source_name": provider,
        "source_priority": 80,
        "series_key": series_key,
        "frequency": "event",
        "source_ts": payload.get("source_ts") or observed_at,
        "data_quality": "ok",
        "raw_payload_json": payload,
    }


def _auction_calendar_payload(
    security_term: str,
    announcement_date: str,
    auction_date: str,
    settlement_date: str,
) -> dict[str, object]:
    prefix = {"2-Year": "2y", "10-Year": "10y", "30-Year": "30y"}[security_term]
    return {
        "series_key": f"treasury_auction:{prefix}_next_auction_days",
        "provider": "treasury_auction",
        "observed_at": auction_date,
        "value": None,
        "unit": "days_until",
        "frequency": "event",
        "provenance": [
            {
                "security_term": security_term,
                "announcement_date": announcement_date,
                "auction_date": auction_date,
                "settlement_date": settlement_date,
                "reopening": False,
                "source_url": "https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml",
            }
        ],
    }
