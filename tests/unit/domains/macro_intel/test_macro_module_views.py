from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CORE_CONCEPTS
from gmgn_twitter_intel.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps
from gmgn_twitter_intel.domains.macro_intel.services.macro_module_catalog import (
    UnsupportedMacroModuleError,
    list_macro_module_configs,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_module_views import build_macro_module_view
from gmgn_twitter_intel.domains.macro_intel.services.macro_regime_engine import build_macro_view_snapshot

NOW_MS = 1_779_000_000_000


def test_build_macro_module_view_projects_v3_display_contract() -> None:
    view = build_macro_module_view(
        "rates",
        snapshot=_snapshot(),
        observations=[
            _obs("rates:dgs10", "2026-05-20", 4.7, unit="percent", source_name="fred"),
            _obs("rates:dgs2", "2026-05-20", 3.9, unit="percent", source_name="fred"),
        ],
        latest_import_run={"run_id": "run-1", "status": "partial", "reason_codes_json": ["missing_api_key"]},
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
        "section_boards",
    )
    assert "read" not in view
    assert "evidence" not in view
    assert "data_gaps" not in view
    assert view["snapshot"] == {
        "module_id": "rates",
        "route_path": "/macro/rates",
        "title": "利率定价",
        "subtitle": "曲线、实际利率与估值压力",
        "question": "利率曲线是在释放风险偏好，还是继续压制估值？",
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
    assert view["primary_chart"]["id"] == "rates_curve"
    assert view["primary_chart"]["status"] == "partial"
    assert view["primary_chart"]["status_label"] == "部分可用"
    assert view["primary_chart"]["min_points"] == 2
    assert view["primary_chart"]["missing_concept_keys"] == ["rates:dgs3mo", "rates:dgs5", "rates:dgs30"]
    assert view["primary_chart"]["series"][0]["label"] == "2年期美债收益率"
    assert view["primary_chart"]["series"][0]["point_count"] == 1
    assert view["tables"][0]["columns"] == [
        {"key": "indicator", "label": "指标"},
        {"key": "latest", "label": "最新值"},
        {"key": "delta_20d", "label": "20日变化"},
        {"key": "quality", "label": "质量"},
        {"key": "source", "label": "来源"},
    ]
    first_row = view["tables"][0]["rows"][0]
    assert first_row["cells"]["indicator"]["display_value"] == "2年期美债收益率"
    assert first_row["cells"]["latest"] == {"display_value": "3.90", "sort_value": 3.9}
    assert first_row["row_quality"] == "ok"
    assert first_row["source_state"] == {"label": "FRED", "status": "ok"}
    assert view["module_read"] == {
        "headline": "利率定价：部分可用",
        "regime_label": "部分可用",
        "confidence_label": "模块覆盖 2/8",
        "data_note": "本页只展示已入库的真实观测、规则状态和可用性说明。",
        "methodology_note": "利率定价 使用模块配置中的 required/optional 概念生成图表和表格。",
    }
    assert view["module_evidence"]["confirmations"][0]["code"] == "module_concept_available:rates:dgs2"
    assert view["module_evidence"]["confirmations"][0]["label"] == "2年期美债收益率"
    assert any(item["code"] == "module_gap:move_index_missing" for item in view["module_evidence"]["watch_triggers"])
    assert isinstance(view["transmission"], list)
    assert view["transmission"][0]["kind"] == "source"
    assert view["transmission"][0]["status"] == "ok"
    assert view["transmission"][-1]["kind"] == "implication"
    assert view["data_health"]["summary_status"] == "partial"
    assert any(gap["code"] == "missing_rates_dgs5" for gap in view["data_health"]["global_gaps"])
    assert any(gap["code"] == "insufficient_history_20d" for gap in view["data_health"]["module_gaps"])
    assert any(gap["code"] == "move_index_missing" for gap in view["data_health"]["future_integration_gaps"])
    assert all(
        item["label"] not in {"rrp buffer low", "hy oas distress", "credit spreads normalize"}
        for group in view["module_evidence"].values()
        for item in group
    )
    assert view["provenance"]["rows"] == [
        {
            "source": "FRED",
            "status": "ok",
            "status_label": "可用",
            "latest_observed_at": "2026-05-20",
            "concept_count": 2,
            "notes": "",
        },
        {
            "source": "宏观导入",
            "status": "partial",
            "status_label": "部分可用",
            "latest_observed_at": None,
            "concept_count": None,
            "notes": "导入配置缺失",
        },
    ]
    provenance_text = str(view["provenance"])
    assert "fred" not in provenance_text
    assert "macro_import" not in provenance_text
    assert "run-1" not in provenance_text
    assert "coverage" not in view["provenance"]
    assert view["related_routes"][0] == {"href": "/macro/rates/fed-funds", "label": "联邦基金"}
    assert view["section_boards"] == []


def test_build_macro_module_view_returns_missing_v3_status_when_snapshot_is_absent() -> None:
    view = build_macro_module_view(
        "fed",
        snapshot=None,
        observations=[],
        latest_import_run=None,
    )

    assert view["snapshot"]["status"] == "missing"
    assert view["snapshot"]["status_label"] == "缺失"
    assert view["snapshot"]["projection_version"] == "macro_module_view_v3"
    assert view["primary_chart"]["status"] == "missing"
    assert view["module_read"]["headline"] == "美联储走廊：缺少快照"
    assert [gap["code"] for gap in view["data_health"]["module_gaps"]] == [
        "macro_view_snapshot_missing",
        "fed_calendar_missing",
        "fed_speeches_missing",
        "fed_statement_text_missing",
    ]


def test_crypto_derivatives_missing_snapshot_keeps_cex_table_shape() -> None:
    view = build_macro_module_view(
        "assets/crypto-derivatives",
        snapshot=None,
        observations=[],
        latest_import_run=None,
    )

    cex_table = next(table for table in view["tables"] if table["id"] == "cex_perp_board")
    assert cex_table["columns"] == [
        {"key": "symbol", "label": "合约"},
        {"key": "open_interest", "label": "未平仓"},
        {"key": "funding", "label": "资金费率"},
        {"key": "volume_24h", "label": "24h 成交"},
        {"key": "score", "label": "分数"},
    ]
    assert cex_table["rows"][0]["row_id"] == "cex_board_missing"
    assert cex_table["rows"][0]["cells"]["symbol"]["display_value"] == "CEX 数据不可用"


def test_crypto_derivatives_missing_snapshot_still_renders_available_cex_board() -> None:
    view = build_macro_module_view(
        "assets/crypto-derivatives",
        snapshot=None,
        observations=[],
        latest_import_run=None,
        cex_board={
            "status": "success",
            "rows": [
                {
                    "native_market_id": "SOLUSDT",
                    "base_symbol": "SOL",
                    "open_interest_usd": 1_250_000_000,
                    "funding_rate": 0.0002,
                    "volume_24h_usd": 4_500_000_000,
                    "score": 77.5,
                }
            ],
        },
    )

    cex_table = next(table for table in view["tables"] if table["id"] == "cex_perp_board")
    assert cex_table["status"] == "ok"
    assert cex_table["columns"] == [
        {"key": "symbol", "label": "合约"},
        {"key": "open_interest", "label": "未平仓"},
        {"key": "funding", "label": "资金费率"},
        {"key": "volume_24h", "label": "24h 成交"},
        {"key": "score", "label": "分数"},
    ]
    assert cex_table["rows"][0]["row_id"] == "SOLUSDT"
    assert cex_table["rows"][0]["cells"]["open_interest"] == {
        "display_value": "1.25B",
        "sort_value": 1_250_000_000.0,
    }
    assert view["provenance"]["rows"][-1] == {
        "source": "CEX OI Radar",
        "status": "ok",
        "status_label": "可用",
        "latest_observed_at": None,
        "concept_count": 1,
        "notes": "",
    }


def test_build_macro_module_view_consumes_real_regime_v4_snapshot_without_crashing() -> None:
    snapshot = build_macro_view_snapshot(
        [
            _obs(concept_key, "2026-05-20", float(index + 1), unit="index", source_name="fixture")
            for index, concept_key in enumerate(MACRO_CORE_CONCEPTS)
        ],
        computed_at_ms=NOW_MS,
    )

    view = build_macro_module_view(
        "assets",
        snapshot=snapshot,
        observations=[],
        latest_import_run={"run_id": "run-1", "status": "ok", "reason_codes": []},
    )

    assert view["snapshot"]["projection_version"] == "macro_module_view_v3"
    assert view["snapshot"]["source_projection_version"] == "macro_regime_v4"
    assert view["data_health"]["module_gaps"]
    assert all(isinstance(gap, dict) for gap in view["data_health"]["module_gaps"])
    assert view["primary_chart"]["status"] == "insufficient_history"
    assert "asset:spy" not in view["tiles"][0]["label"]


def test_module_view_uses_semantic_chart_table_titles_for_every_catalog_spec() -> None:
    snapshot = _snapshot()
    for config in list_macro_module_configs():
        view = build_macro_module_view(config.module_id, snapshot=snapshot, observations=[], latest_import_run=None)

        chart = view["primary_chart"]
        assert chart["title"]
        assert chart["title"] != chart["id"]
        assert "_" not in chart["title"]
        for table in view["tables"]:
            assert table["title"]
            assert table["title"] != table["id"]
            assert "_" not in table["title"]


def test_gap_payloads_localize_catalog_gap_codes_without_raw_label_fallback() -> None:
    raw_codes = [
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
        "cex_board_missing",
        "cex_board_empty",
    ]

    gaps = build_macro_data_gaps(raw_codes)

    assert {gap["code"] for gap in gaps} == set(raw_codes)
    for gap in gaps:
        assert gap["label"]
        assert gap["label"] != f"数据缺口：{gap['code']}"
        assert gap["code"] not in gap["label"]
        assert gap["remediation_hint"]


def test_feature_label_and_unit_fallback_use_metadata_not_raw_keys_or_units() -> None:
    snapshot = _snapshot()
    feature = snapshot["features_json"]["rates:dgs2"]
    for key in ("label", "short_label", "description", "unit_label"):
        feature.pop(key)

    view = build_macro_module_view("rates", snapshot=snapshot, observations=[], latest_import_run=None)

    tile = view["tiles"][0]
    assert tile["label"] == "2年期美债收益率"
    assert tile["short_label"] == "2Y"
    assert tile["unit_label"] == "%"
    assert tile["label"] != "rates:dgs2"
    assert tile["unit_label"] != "percent"


def test_crypto_derivatives_view_includes_typed_cex_board() -> None:
    view = build_macro_module_view(
        "assets/crypto-derivatives",
        snapshot=_snapshot(),
        observations=[_obs("crypto:btc", "2026-05-20", 110_000, unit="usd", source_name="yahoo")],
        latest_import_run={"run_id": "run-1", "status": "ok", "reason_codes": []},
        cex_board={
            "status": "partial",
            "degraded_reasons": ["coinglass_partial"],
            "observed_at_ms": NOW_MS,
            "rows": [
                {
                    "row_id": "cex-oi-radar-row:internal",
                    "run_id": "cex-oi-radar:run",
                    "rank": 1,
                    "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                    "native_market_id": "BTCUSDT",
                    "base_symbol": "BTC",
                    "quote_symbol": "USDT",
                    "open_interest_usd": 12_500_000_000,
                    "open_interest_change_pct_1h": 3.4,
                    "funding_rate": 0.0001,
                    "volume_24h_usd": 31_000_000_000,
                    "mark_price": 110_100.0,
                    "score": 91.2,
                    "score_components_json": {"oi": 50},
                    "computed_at_ms": 1_779_000_100_000,
                }
            ],
        },
    )

    cex_table = next(table for table in view["tables"] if table["id"] == "cex_perp_board")
    assert cex_table["status"] == "partial"
    assert cex_table["columns"][0] == {"key": "symbol", "label": "合约"}
    assert cex_table["rows"][0]["row_id"] == "BTCUSDT"
    assert cex_table["rows"][0]["cells"]["open_interest"]["display_value"] == "12.50B"
    assert cex_table["rows"][0]["cells"]["funding"]["sort_value"] == 0.0001
    assert cex_table["rows"][0]["row_quality"] == "partial"
    assert cex_table["rows"][0]["source_state"] == {"label": "CEX OI Radar", "status": "partial"}
    row_text = str(cex_table["rows"][0])
    assert "pricefeed_id" not in row_text
    assert "score_components_json" not in row_text
    assert view["provenance"]["rows"][-1]["source"] == "CEX OI Radar"
    assert view["provenance"]["rows"][-1]["status"] == "partial"
    assert view["provenance"]["rows"][-1]["notes"] == "Coinglass 数据不完整"


def test_module_view_provenance_never_exposes_unknown_provider_or_status_codes() -> None:
    view = build_macro_module_view(
        "rates",
        snapshot=_snapshot(),
        observations=[
            _obs(
                "rates:dgs10",
                "2026-05-20",
                4.7,
                unit="percent",
                source_name="internal_feed",
            )
            | {"data_quality": "provider_not_configured"},
        ],
        latest_import_run={"run_id": "run-1", "status": "provider_not_configured", "reason_codes": ["run-1"]},
    )

    assert view["provenance"]["rows"] == [
        {
            "source": "未知来源",
            "status": "unknown",
            "status_label": "未知",
            "latest_observed_at": "2026-05-20",
            "concept_count": 1,
            "notes": "",
        },
        {
            "source": "宏观导入",
            "status": "unknown",
            "status_label": "未知",
            "latest_observed_at": None,
            "concept_count": None,
            "notes": "数据源降级",
        },
    ]
    provenance_text = str(view["provenance"])
    assert "internal_feed" not in provenance_text
    assert "provider_not_configured" not in provenance_text
    assert "run-1" not in provenance_text


def test_crypto_derivatives_view_preserves_zero_values_and_normalizes_success_status() -> None:
    view = build_macro_module_view(
        "assets/crypto-derivatives",
        snapshot=_snapshot(),
        observations=[],
        latest_import_run=None,
        cex_board={
            "status": "success",
            "rows": [
                {
                    "native_market_id": "ETHUSDT",
                    "base_symbol": "ETH",
                    "open_interest_usd": 0,
                    "funding_rate": 0,
                    "volume_24h_usd": 0,
                    "score": 0,
                }
            ],
        },
    )

    cex_table = next(table for table in view["tables"] if table["id"] == "cex_perp_board")
    row = cex_table["rows"][0]
    assert cex_table["status"] == "ok"
    assert cex_table["status_label"] == "可用"
    assert row["row_id"] == "ETHUSDT"
    assert row["row_quality"] == "ok"
    assert row["source_state"] == {"label": "CEX OI Radar", "status": "ok"}
    assert row["cells"]["open_interest"] == {"display_value": "0.00", "sort_value": 0.0}
    assert row["cells"]["funding"] == {"display_value": "0.0000%", "sort_value": 0.0}
    assert row["cells"]["volume_24h"] == {"display_value": "0.00", "sort_value": 0.0}
    assert row["cells"]["score"] == {"display_value": "0.00", "sort_value": 0.0}


def test_crypto_derivatives_view_marks_absent_or_empty_cex_board_as_degraded_row() -> None:
    missing_view = build_macro_module_view(
        "assets/crypto-derivatives",
        snapshot=_snapshot(),
        observations=[],
        latest_import_run=None,
        cex_board=None,
    )
    empty_view = build_macro_module_view(
        "assets/crypto-derivatives",
        snapshot=_snapshot(),
        observations=[],
        latest_import_run=None,
        cex_board={"status": "ok", "rows": []},
    )

    for view, expected_code in ((missing_view, "cex_board_missing"), (empty_view, "cex_board_empty")):
        cex_table = next(table for table in view["tables"] if table["id"] == "cex_perp_board")
        assert cex_table["status"] == "missing"
        assert cex_table["rows"] == [
            {
                "row_id": expected_code,
                "row_quality": "missing",
                "source_state": {"label": "CEX OI Radar", "status": "missing"},
                "cells": {
                    "symbol": {"display_value": "CEX 数据不可用", "sort_value": None},
                    "open_interest": {"display_value": "缺失", "sort_value": None},
                    "funding": {"display_value": "缺失", "sort_value": None},
                    "volume_24h": {"display_value": "缺失", "sort_value": None},
                    "score": {"display_value": "缺失", "sort_value": None},
                },
            }
        ]
        assert any(gap["code"] == expected_code for gap in view["data_health"]["module_gaps"])


def test_non_overview_module_view_does_not_reuse_global_scenario_or_blockers() -> None:
    view = build_macro_module_view(
        "assets/equities",
        snapshot=_snapshot_with_global_scenario(),
        observations=[],
        latest_import_run=None,
    )

    assert view["snapshot"]["projection_version"] == "macro_module_view_v3"
    assert "module_read" in view
    assert "module_evidence" in view
    assert "transmission" in view
    assert "data_health" in view
    assert "section_boards" in view
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
        latest_import_run=None,
    )

    assert view["module_read"]["headline"] == "宏观总览：期限溢价压力"
    assert view["module_evidence"]["confirmations"][0]["code"] == "global_term_premium"
    assert any(gap.get("code") == "missing_liquidity_srf" for gap in view["data_health"]["global_gaps"])
    assert view["data_health"]["summary_status"] == "missing"


def test_assets_index_view_returns_section_boards() -> None:
    view = build_macro_module_view(
        "assets",
        snapshot=_snapshot(),
        observations=[],
        latest_import_run=None,
    )

    assert [board["id"] for board in view["section_boards"]] == [
        "equities",
        "bonds",
        "commodities",
        "fx",
        "crypto",
        "crypto_derivatives",
    ]
    equities = view["section_boards"][0]
    assert equities["title"] == "美股"
    assert equities["href"] == "/macro/assets/equities"
    assert equities["status"] == "partial"
    assert equities["status_label"] == "部分可用"
    assert "board_id" not in equities
    assert "route_path" not in equities
    assert [row["concept_key"] for row in equities["rows"]] == ["asset:spx", "asset:spy", "asset:qqq", "asset:iwm"]


def test_assets_index_section_board_status_is_missing_when_all_rows_are_missing() -> None:
    snapshot = _snapshot()
    snapshot["features_json"] = {}

    view = build_macro_module_view(
        "assets",
        snapshot=snapshot,
        observations=[],
        latest_import_run=None,
    )

    equities = view["section_boards"][0]
    assert equities["id"] == "equities"
    assert equities["status"] == "missing"
    assert equities["status_label"] == "缺失"
    assert all(row["status"] == "missing" for row in equities["rows"])


def test_build_macro_module_view_rejects_unknown_module_id() -> None:
    with pytest.raises(UnsupportedMacroModuleError) as exc_info:
        build_macro_module_view("not-real", snapshot=None, observations=[], latest_import_run=None)

    assert exc_info.value.code == "unsupported_macro_module"


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
                {"code": "real_yield_breakout", "description": "10Y real yield keeps rising."},
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
        "data_gaps_json": [
            {
                "code": "missing_rates_dgs5",
                "label": "缺少当前数据：5Y",
                "severity": "error",
                "score_participation": False,
            }
        ],
        "source_coverage_json": {"latest_coverage_ratio": 0.5, "history_coverage_ratio": 0.25},
    }


def _snapshot_with_global_scenario() -> dict[str, object]:
    snapshot = _snapshot()
    snapshot["scenario_json"] = {
        "current_regime": "term_premium_pressure",
        "confidence": 0.79,
        "confirmations": [{"code": "global_term_premium", "description": "global only"}],
    }
    snapshot["data_gaps_json"] = [{"code": "missing_liquidity_srf", "label": "缺少 SRF", "severity": "error"}]
    return snapshot


def _feature(concept_key: str, value: float, *, unit: str, source_name: str) -> dict[str, object]:
    labels = {
        "rates:dgs2": ("2年期美债收益率", "2Y", "政策预期敏感的短端美债收益率", "%"),
        "rates:dgs10": ("10年期美债收益率", "10Y", "美国长期无风险利率基准", "%"),
        "asset:spx": ("标普500", "SPX", "美国大盘股风险偏好基准", "点"),
        "asset:spy": ("标普500 ETF", "SPY", "美国大盘股可交易风险偏好代理", "美元"),
        "asset:qqq": ("纳指100 ETF", "QQQ", "美国成长股风险偏好代理", "美元"),
        "asset:tlt": ("长期美债 ETF", "TLT", "长久期利率敏感资产代理", "美元"),
        "vol:vix": ("VIX", "VIX", "标普500 隐含波动率压力", "点"),
        "credit:hy_oas": ("高收益债 OAS", "HY OAS", "美国高收益债信用利差压力", "%"),
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
            }
        ],
    }


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
