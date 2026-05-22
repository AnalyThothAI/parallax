from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.macro_intel.services.macro_module_catalog import UnsupportedMacroModuleError
from gmgn_twitter_intel.domains.macro_intel.services.macro_module_views import build_macro_module_view


def test_build_macro_module_view_projects_snapshot_fields_deterministically() -> None:
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
        "charts",
        "tables",
        "current_read",
        "signals",
        "provenance",
        "data_gaps",
        "related_routes",
    )
    assert view["snapshot"] == {
        "module_id": "rates",
        "route_path": "/macro/rates",
        "title": "Rates",
        "section": "rates",
        "projection_version": "macro_module_view_v1",
        "status": "partial",
        "asof_date": "2026-05-20",
        "source_snapshot_id": "snapshot-1",
        "source_projection_version": "macro_regime_v3",
        "computed_at_ms": 1_779_000_000_000,
    }
    assert view["tiles"] == [
        {"concept_key": "rates:dgs2", "label": "rates:dgs2", "latest": 3.9, "unit": "percent", "freshness_days": 1},
        {"concept_key": "rates:dgs10", "label": "rates:dgs10", "latest": 4.7, "unit": "percent", "freshness_days": 1},
    ]
    assert view["charts"][0]["chart_id"] == "rates_curve"
    assert view["charts"][0]["status"] == "partial"
    assert view["charts"][0]["missing_concept_keys"] == ["rates:dgs5", "rates:dgs30"]
    assert view["charts"][0]["series"][0]["concept_key"] == "rates:dgs2"
    assert view["tables"][0]["status"] == "partial"
    assert view["tables"][0]["missing_concept_keys"] == ["rates:10y2y"]
    assert view["tables"][0]["rows"][0]["concept_key"] == "rates:dgs2"
    assert view["current_read"] == {
        "regime": "tightening",
        "current_regime": "tightening",
        "summary": "Rates are pressuring risk assets",
        "trade_map": {"risk": "reduce_duration"},
    }
    assert view["signals"] == [
        {"code": "higher_real_rates", "severity": "watch", "description": "10y real rates above 2%"}
    ]
    assert view["provenance"] == {
        "latest_import_run": {"run_id": "run-1", "status": "partial", "reason_codes": ["missing_api_key"]},
        "source_coverage": {"coverage_ratio": 0.5},
        "observation_sources": ["fred"],
        "degradation": {"status": "partial", "reason_codes": ["missing_api_key"]},
    }
    assert view["data_gaps"] == ["missing:rates:dgs5", "move_index_missing"]
    assert view["related_routes"] == ["/macro/rates/yield-curve", "/macro/rates/real-rates", "/macro/fed"]


def test_build_macro_module_view_returns_missing_status_when_snapshot_is_absent() -> None:
    view = build_macro_module_view(
        "fed",
        snapshot=None,
        observations=[],
        latest_import_run=None,
    )

    assert view["snapshot"]["status"] == "missing"
    assert view["snapshot"]["projection_version"] == "macro_module_view_v1"
    assert view["data_gaps"] == [
        "macro_view_snapshot_missing",
        "fed_calendar_missing",
        "fed_speeches_missing",
        "fed_statement_text_missing",
    ]
    assert view["tiles"] == []
    assert view["charts"][0]["status"] == "missing"
    assert view["provenance"]["degradation"]["reason_codes"] == ["macro_view_snapshot_missing"]


def test_build_macro_module_view_projects_overview_concepts_into_chart_and_table() -> None:
    view = build_macro_module_view(
        "overview",
        snapshot=_snapshot(),
        observations=[],
        latest_import_run=None,
    )

    assert view["charts"][0]["chart_id"] == "macro_regime"
    assert view["charts"][0]["status"] == "ok"
    assert view["charts"][0]["missing_concept_keys"] == []
    assert [series["concept_key"] for series in view["charts"][0]["series"]] == [
        "asset:spx",
        "rates:dgs10",
        "vol:vix",
        "credit:hy_oas",
    ]
    assert view["tables"][0]["table_id"] == "panel_scorecard"
    assert view["tables"][0]["status"] == "ok"
    assert view["tables"][0]["missing_concept_keys"] == []
    assert [row["concept_key"] for row in view["tables"][0]["rows"]] == [
        "asset:spx",
        "rates:dgs10",
        "vol:vix",
        "credit:hy_oas",
    ]


def test_build_macro_module_view_marks_missing_specs_without_available_concepts() -> None:
    snapshot = _snapshot()
    snapshot["features_json"] = {
        key: value for key, value in snapshot["features_json"].items() if key != "vol:vix"
    }
    view = build_macro_module_view(
        "volatility",
        snapshot=snapshot,
        observations=[],
        latest_import_run=None,
    )

    assert view["charts"][0]["status"] == "missing"
    assert view["charts"][0]["missing_concept_keys"] == ["vol:vix"]
    assert view["tables"][0]["status"] == "missing"
    assert view["tables"][0]["missing_concept_keys"] == ["vol:vix"]


def test_crypto_derivatives_view_includes_cex_board_and_missing_derivative_gaps() -> None:
    view = build_macro_module_view(
        "assets/crypto-derivatives",
        snapshot=_snapshot(),
        observations=[_obs("crypto:btc", "2026-05-20", 110_000, unit="usd", source_name="yahoo")],
        latest_import_run={"run_id": "run-1", "status": "ok", "reason_codes": []},
        cex_board={
            "status": "degraded",
            "degraded_reasons": ["coinglass_partial"],
            "observed_at_ms": 1_779_000_000_000,
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

    cex_table = next(table for table in view["tables"] if table["table_id"] == "cex_perp_board")
    assert cex_table["status"] == "ok"
    assert cex_table["missing_concept_keys"] == []
    assert cex_table["source"] == {
        "name": "cex_market_intel",
        "status": "degraded",
        "degraded_reasons": ["coinglass_partial"],
        "observed_at_ms": 1_779_000_000_000,
    }
    assert cex_table["rows"] == [
        {
            "rank": 1,
            "symbol": "BTC",
            "native_market_id": "BTCUSDT",
            "quote_symbol": "USDT",
            "open_interest_usd": 12_500_000_000,
            "open_interest_change_pct_1h": 3.4,
            "funding_rate": 0.0001,
            "volume_24h_usd": 31_000_000_000,
            "mark_price": 110_100.0,
            "score": 91.2,
            "observed_at_ms": 1_779_000_000_000,
            "computed_at_ms": 1_779_000_100_000,
            "degraded_reasons": ["coinglass_partial"],
        }
    ]
    row = cex_table["rows"][0]
    assert "row_id" not in row
    assert "run_id" not in row
    assert "pricefeed_id" not in row
    assert "score_components_json" not in row
    assert "crypto_options_missing" in view["data_gaps"]
    assert "basis_missing" in view["data_gaps"]
    assert "etf_flows_missing" in view["data_gaps"]
    assert view["provenance"]["cex_board"]["status"] == "degraded"


def test_crypto_derivatives_view_marks_missing_empty_cex_board_table() -> None:
    view = build_macro_module_view(
        "assets/crypto-derivatives",
        snapshot=_snapshot(),
        observations=[],
        latest_import_run=None,
        cex_board={"status": "ok", "rows": []},
    )

    cex_table = next(table for table in view["tables"] if table["table_id"] == "cex_perp_board")
    assert cex_table["status"] == "missing"
    assert cex_table["missing_concept_keys"] == []
    assert cex_table["source"]["status"] == "ok"
    assert cex_table["source"]["degraded_reasons"] == ["cex_board_empty"]


def test_build_macro_module_view_rejects_unknown_module_id() -> None:
    with pytest.raises(UnsupportedMacroModuleError) as exc_info:
        build_macro_module_view("not-real", snapshot=None, observations=[], latest_import_run=None)

    assert exc_info.value.code == "unsupported_macro_module"


def _snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "snapshot-1",
        "projection_version": "macro_regime_v3",
        "asof_date": "2026-05-20",
        "status": "partial",
        "regime": "tightening",
        "computed_at_ms": 1_779_000_000_000,
        "features_json": {
            "rates:dgs2": {
                "latest": {"value": 3.9, "observed_at": "2026-05-20", "unit": "percent"},
                "freshness_days": 1,
                "data_gaps": [],
            },
            "rates:dgs10": {
                "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
                "freshness_days": 1,
                "data_gaps": [],
            },
            "asset:spx": {
                "latest": {"value": 5312.4, "observed_at": "2026-05-20", "unit": "index"},
                "freshness_days": 1,
                "data_gaps": [],
            },
            "vol:vix": {
                "latest": {"value": 17.2, "observed_at": "2026-05-20", "unit": "index"},
                "freshness_days": 1,
                "data_gaps": [],
            },
            "credit:hy_oas": {
                "latest": {"value": 2.8, "observed_at": "2026-05-20", "unit": "percent"},
                "freshness_days": 1,
                "data_gaps": [],
            },
            "crypto:btc": {
                "latest": {"value": 110_000, "observed_at": "2026-05-20", "unit": "usd"},
                "freshness_days": 1,
                "data_gaps": [],
            },
        },
        "chain_json": {
            "rates": {"regime": "tightening", "score": 7.1, "evidence": ["10y=4.70"], "data_gaps": []},
        },
        "scenario_json": {
            "current_regime": "tightening",
            "summary": "Rates are pressuring risk assets",
            "trade_map": {"risk": "reduce_duration"},
            "watch_triggers": [
                {"code": "higher_real_rates", "severity": "watch", "description": "10y real rates above 2%"}
            ],
        },
        "panels_json": {"rates": {"regime": "term_premium_pressure", "score": 7.1}},
        "indicators_json": {"rates:dgs10": {"value": 4.7, "unit": "percent"}},
        "data_gaps_json": ["missing:rates:dgs5"],
        "source_coverage_json": {"coverage_ratio": 0.5},
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
