from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router
from parallax.app.surfaces.api.routes_macro import _public_macro
from parallax.domains.macro_intel._constants import (
    MACRO_CORE_CONCEPTS,
    MACRO_VIEW_HISTORY_LIMIT_PER_SERIES,
    MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
)
from parallax.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps


def test_macro_api_returns_latest_snapshot_without_postgres() -> None:
    data_gaps = build_macro_data_gaps(["insufficient_history:20d", "missing:asset:spx"])
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "macro-view:macro_regime_v4:1",
            "projection_version": "macro_regime_v4",
            "asof_date": "2026-05-20",
            "status": "partial",
            "regime": "funding_stress",
            "overall_score": 7.2,
            "panels_json": {"liquidity": {"score": 8.0, "regime": "funding_stress"}},
            "indicators_json": {"sofr_iorb_spread_bps": {"value": 15.0}},
            "triggers_json": [{"code": "sofr_above_iorb"}],
            "data_gaps_json": data_gaps,
            "source_coverage_json": {
                "latest_coverage_ratio": 1.0,
                "history_coverage_ratio": 0.0,
                "required_concept_count": len(MACRO_CORE_CONCEPTS),
                "observed_concept_count": len(MACRO_CORE_CONCEPTS),
                "required_history_concept_count": len(MACRO_CORE_CONCEPTS),
                "history_ready_concept_count": 0,
                "concepts_below_min_history": ["rates:dgs10"],
                "latest_observed_at": "2026-05-20",
            },
            "features_json": {
                "rates:dgs10": {
                    "concept_key": "rates:dgs10",
                    "label": "10年期美债收益率",
                    "short_label": "10Y",
                    "description": "美国长期无风险利率基准",
                    "unit": "percent",
                    "unit_label": "%",
                    "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
                    "freshness_days": 0,
                    "history_points": 1,
                    "history_windows": {
                        "20d": {"point_count": 1, "status": "insufficient_history"},
                        "60d": {"point_count": 1, "status": "insufficient_history"},
                        "252d": {"point_count": 1, "status": "insufficient_history"},
                    },
                    "delta": {"5d": 0.1, "20d": 0.35, "60d": None},
                    "zscore": None,
                    "percentile": None,
                    "score_participation": False,
                    "data_quality": "ok",
                    "data_gaps": build_macro_data_gaps(["insufficient_history:20d"]),
                    "source": {"name": "fred", "series_key": "fred:DGS10"},
                }
            },
            "chain_json": {
                "liquidity": {
                    "score": 8.0,
                    "regime": "funding_stress",
                    "evidence": ["sofr_iorb_spread_bps=15.0"],
                    "data_gaps": [],
                }
            },
            "scenario_json": {
                "current_regime": "funding_stress",
                "confidence": 0.72,
                "time_window": "1w",
                "confirmations": [{"code": "sofr_above_iorb"}],
                "contradictions": [],
                "watch_triggers": [{"code": "vix_breaks_30"}],
                "invalidations": [{"code": "sofr_iorb_normalizes"}],
                "trade_map": [
                    {
                        "expression": "risk_down_credit_sensitive",
                        "label": "风险降档 / 信用敏感",
                        "time_window": "1w",
                    }
                ],
                "top_changes": [
                    {
                        "code": "sofr_above_iorb",
                        "label": "SOFR 高于 IORB",
                        "description": "SOFR is above IORB",
                        "node": "funding",
                        "kind": "trigger",
                    }
                ],
                "quality_blockers": [
                    {
                        "code": "missing_asset_spx",
                        "label": "缺少当前数据：SPX",
                        "description": "检查对应 provider 导入与最新观测。",
                        "severity": "error",
                    }
                ],
                "scenario_cases": [
                    {
                        "case": "base",
                        "label": "基准情景",
                        "thesis": "风险降档延续。",
                        "trade": "降低信用敏感 beta。",
                        "invalidation": "美元与信用压力同步回落。",
                    }
                ],
            },
            "scorecard_json": {
                "projection_version": "macro_regime_v4",
                "chain_average": 7.8,
                "observed_concept_count": 10,
                "history_coverage_ratio": 0.0,
            },
            "computed_at_ms": 1_779_000_000_000,
        }
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert repo.calls == [
        ("latest_snapshot", "macro_regime_v4"),
        ("macro_series_publication_state", "macro_regime_v4"),
    ]
    assert response.json() == {
        "ok": True,
        "data": {
            "snapshot": {
                "snapshot_id": "macro-view:macro_regime_v4:1",
                "projection_version": "macro_regime_v4",
                "asof_date": "2026-05-20",
                "status": "partial",
                "regime": "funding_stress",
                "overall_score": 7.2,
                "computed_at_ms": 1_779_000_000_000,
            },
            "currentness": {
                "publication_status": None,
                "publication_row_count": None,
                "publication_finished_at_ms": None,
                "facts_max_observed_at": "2026-05-20",
                "projection_lag_days": 0,
                "projection_behind_facts": False,
            },
            "panels": {"liquidity": {"score": 8.0, "regime": "funding_stress"}},
            "indicators": {"sofr_iorb_spread_bps": {"value": 15.0}},
            "triggers": [{"code": "sofr_above_iorb"}],
            "data_gaps": data_gaps,
            "source_coverage": {
                "latest_coverage_ratio": 1.0,
                "history_coverage_ratio": 0.0,
                "required_concept_count": len(MACRO_CORE_CONCEPTS),
                "observed_concept_count": len(MACRO_CORE_CONCEPTS),
                "required_history_concept_count": len(MACRO_CORE_CONCEPTS),
                "history_ready_concept_count": 0,
                "concepts_below_min_history": ["rates:dgs10"],
                "latest_observed_at": "2026-05-20",
            },
            "features": {
                "rates:dgs10": {
                    "concept_key": "rates:dgs10",
                    "label": "10年期美债收益率",
                    "short_label": "10Y",
                    "description": "美国长期无风险利率基准",
                    "unit": "percent",
                    "unit_label": "%",
                    "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
                    "freshness_days": 0,
                    "history_points": 1,
                    "history_windows": {
                        "20d": {"point_count": 1, "status": "insufficient_history"},
                        "60d": {"point_count": 1, "status": "insufficient_history"},
                        "252d": {"point_count": 1, "status": "insufficient_history"},
                    },
                    "delta": {"5d": 0.1, "20d": 0.35, "60d": None},
                    "zscore": None,
                    "percentile": None,
                    "score_participation": False,
                    "data_quality": "ok",
                    "data_gaps": build_macro_data_gaps(["insufficient_history:20d"]),
                    "source": {"name": "fred", "series_key": "fred:DGS10"},
                }
            },
            "chain": {
                "liquidity": {
                    "score": 8.0,
                    "regime": "funding_stress",
                    "evidence": ["sofr_iorb_spread_bps=15.0"],
                    "data_gaps": [],
                }
            },
            "scenario": {
                "current_regime": "funding_stress",
                "confidence": 0.72,
                "time_window": "1w",
                "confirmations": [{"code": "sofr_above_iorb"}],
                "contradictions": [],
                "watch_triggers": [{"code": "vix_breaks_30"}],
                "invalidations": [{"code": "sofr_iorb_normalizes"}],
                "trade_map": [
                    {
                        "expression": "risk_down_credit_sensitive",
                        "label": "风险降档 / 信用敏感",
                        "time_window": "1w",
                    }
                ],
                "top_changes": [
                    {
                        "code": "sofr_above_iorb",
                        "label": "SOFR 高于 IORB",
                        "description": "SOFR is above IORB",
                        "node": "funding",
                        "kind": "trigger",
                    }
                ],
                "quality_blockers": [
                    {
                        "code": "missing_asset_spx",
                        "label": "缺少当前数据：SPX",
                        "description": "检查对应 provider 导入与最新观测。",
                        "severity": "error",
                    }
                ],
                "scenario_cases": [
                    {
                        "case": "base",
                        "label": "基准情景",
                        "thesis": "风险降档延续。",
                        "trade": "降低信用敏感 beta。",
                        "invalidation": "美元与信用压力同步回落。",
                    }
                ],
            },
            "scorecard": {
                "projection_version": "macro_regime_v4",
                "chain_average": 7.8,
                "observed_concept_count": 10,
                "history_coverage_ratio": 0.0,
            },
        },
    }


def test_macro_api_returns_data_gap_when_snapshot_missing() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get("/api/macro", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json()["data"] == {
        "snapshot": None,
        "currentness": {
            "publication_status": None,
            "publication_row_count": None,
            "publication_finished_at_ms": None,
            "facts_max_observed_at": None,
            "projection_lag_days": None,
            "projection_behind_facts": False,
        },
        "panels": {},
        "indicators": {},
        "triggers": [],
        "data_gaps": build_macro_data_gaps(["macro_view_snapshot_missing"]),
        "source_coverage": {
            "observed_concept_count": 0,
            "required_concept_count": len(MACRO_CORE_CONCEPTS),
            "coverage_ratio": 0.0,
        },
        "features": {},
        "chain": {},
        "scenario": {},
        "scorecard": {},
    }


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
def test_macro_public_payload_requires_snapshot_json_sections(field_name: str) -> None:
    snapshot = _macro_snapshot()
    del snapshot[field_name]

    with pytest.raises(ValueError, match=f"macro_view_snapshot_section_required:{field_name}"):
        _public_macro(snapshot, currentness=_macro_currentness())


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
def test_macro_public_payload_rejects_misshaped_snapshot_json_sections(field_name: str, invalid_value: object) -> None:
    snapshot = _macro_snapshot()
    snapshot[field_name] = invalid_value

    with pytest.raises(ValueError, match=f"macro_view_snapshot_section_invalid:{field_name}"):
        _public_macro(snapshot, currentness=_macro_currentness())


def test_macro_api_rejects_timestamp_text_for_currentness_dates() -> None:
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "macro-view:macro_regime_v4:timestamp",
            "projection_version": "macro_regime_v4",
            "asof_date": "2026-05-27",
            "status": "ready",
            "regime": "risk_on",
            "overall_score": 6.8,
            "panels_json": {},
            "indicators_json": {},
            "triggers_json": [],
            "data_gaps_json": [],
            "source_coverage_json": {
                "latest_observed_at": "2026-05-28 00:00:00+00:00",
            },
            "features_json": {},
            "chain_json": {},
            "scenario_json": {},
            "scorecard_json": {},
            "computed_at_ms": 1_779_000_000_000,
        }
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json()["data"]["currentness"] == {
        "publication_status": None,
        "publication_row_count": None,
        "publication_finished_at_ms": None,
        "facts_max_observed_at": None,
        "projection_lag_days": None,
        "projection_behind_facts": False,
    }


def test_macro_asset_correlation_api_returns_backend_computed_concept_matrix() -> None:
    repo = FakeMacroIntelRepository(
        snapshot=None,
        observations=[
            _macro_observation("asset:spy", "2026-05-17", 100.0),
            _macro_observation("asset:spy", "2026-05-18", 102.0),
            _macro_observation("asset:spy", "2026-05-19", 101.0),
            _macro_observation("asset:spy", "2026-05-20", 104.0),
            _macro_observation("asset:qqq", "2026-05-17", 200.0),
            _macro_observation("asset:qqq", "2026-05-18", 204.0),
            _macro_observation("asset:qqq", "2026-05-19", 202.0),
            _macro_observation("asset:qqq", "2026-05-20", 208.0),
        ],
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/assets/correlation?window=20d&assets=asset:spy,asset:qqq",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert repo.observations_for_concepts_call is not None
    assert repo.observations_for_concepts_call["concept_keys"] == ("asset:spy", "asset:qqq")
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["window"] == "20d"
    assert payload["data"]["assets"][0]["concept_key"] == "asset:spy"
    assert payload["data"]["matrix"][0]["concept_key"] == "asset:spy"
    assert payload["data"]["pairs"][0]["left"] == "asset:spy"
    assert payload["data"]["pairs"][0]["right"] == "asset:qqq"
    assert payload["data"]["asof_date"] == "2026-05-20"


def test_macro_asset_correlation_api_rejects_provider_series_keys() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/assets/correlation?assets=yahoo:SPY",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_asset", "field": "assets"}


def test_macro_module_api_returns_backend_module_view() -> None:
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "snapshot-1",
            "projection_version": "macro_regime_v4",
            "asof_date": "2026-05-20",
            "status": "partial",
            "regime": "tightening",
            "computed_at_ms": 1_779_000_000_000,
            "panels_json": {"rates": {"regime": "tightening"}},
            "indicators_json": {"rates:dgs2": {"value": 3.9}, "rates:dgs10": {"value": 4.7}},
            "triggers_json": [{"code": "higher_real_rates"}],
            "features_json": {
                "rates:dgs2": {
                    "label": "2年期美债收益率",
                    "short_label": "2Y",
                    "description": "政策预期敏感的短端美债收益率",
                    "unit_label": "%",
                    "latest": {"value": 3.9, "observed_at": "2026-05-20", "unit": "percent"},
                    "freshness_days": 1,
                    "history_points": 1,
                    "data_gaps": build_macro_data_gaps(["insufficient_history:20d"]),
                    "data_quality": "ok",
                    "source": {"name": "fred"},
                },
                "rates:dgs10": {
                    "label": "10年期美债收益率",
                    "short_label": "10Y",
                    "description": "美国长期无风险利率基准",
                    "unit_label": "%",
                    "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
                    "freshness_days": 1,
                    "history_points": 1,
                    "data_gaps": build_macro_data_gaps(["insufficient_history:20d"]),
                    "data_quality": "ok",
                    "source": {"name": "fred"},
                },
            },
            "chain_json": {"rates": {"regime": "tightening"}},
            "scenario_json": {
                "current_regime": "tightening",
                "confidence": 0.64,
                "watch_triggers": [{"code": "higher_real_rates"}],
            },
            "source_coverage_json": {"latest_coverage_ratio": 1.0, "history_coverage_ratio": 0.0},
            "data_gaps_json": build_macro_data_gaps(["insufficient_history:20d"]),
            "scorecard_json": {"projection_version": "macro_regime_v4", "chain_average": 7.1},
        },
        observations=[_macro_observation("rates:dgs10", "2026-05-20", 4.7)],
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/rates/yield-curve", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert repo.calls == [
        ("latest_snapshot", "macro_regime_v4"),
        ("macro_series_publication_state", "macro_regime_v4"),
    ]
    assert repo.latest_observations_call is None
    assert repo.observations_for_concepts_call == {
        "concept_keys": (
            "rates:dgs2",
            "rates:dgs10",
            "rates:dgs1mo",
            "rates:dgs3mo",
            "rates:dgs6mo",
            "rates:dgs1",
            "rates:dgs3",
            "rates:dgs5",
            "rates:dgs7",
            "rates:dgs20",
            "rates:dgs30",
            "rates:10y2y",
            "rates:10y3m",
        ),
        "lookback_days": MACRO_VIEW_HISTORY_LOOKBACK_DAYS,
        "limit_per_series": MACRO_VIEW_HISTORY_LIMIT_PER_SERIES,
    }
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["snapshot"]["module_id"] == "rates/yield-curve"
    assert payload["data"]["snapshot"]["projection_version"] == "macro_module_view_v3"
    assert payload["data"]["snapshot"]["source_projection_version"] == "macro_regime_v4"
    assert "module_read" in payload["data"]
    assert "module_evidence" in payload["data"]
    assert "transmission" in payload["data"]
    assert "data_health" in payload["data"]
    assert "section_boards" not in payload["data"]
    assert "read" not in payload["data"]
    assert "evidence" not in payload["data"]
    assert "data_gaps" not in payload["data"]
    assert payload["data"]["primary_chart"]["status"] == "partial"
    assert payload["data"]["primary_chart"]["series"][0]["status"] == "insufficient_history"
    assert payload["data"]["provenance"]["rows"][-1] == {
        "row_id": "source:Yahoo",
        "source_label": "Yahoo",
        "status": "ok",
        "status_label": "可用",
        "latest_observed_at": "2026-05-20",
        "concept_count": 1,
        "notes": "",
    }
    assert "macro_import" not in str(payload["data"]["provenance"])
    assert "macro-import-1" not in str(payload["data"]["provenance"])
    assert "charts" not in payload["data"]
    assert "current_read" not in payload["data"]
    assert "signals" not in payload["data"]
    assert "latest_import_run" not in payload["data"]["provenance"]
    assert all(isinstance(gap, dict) for gap in payload["data"]["data_health"]["module_gaps"])


def test_macro_overview_module_api_loads_event_concepts_for_market_event_flow() -> None:
    snapshot = _macro_snapshot()
    snapshot["scenario_json"] = {
        "current_regime": "funding_stress",
        "confidence": 0.72,
        "confirmations": [],
        "contradictions": [],
        "watch_triggers": [],
        "invalidations": [],
        "top_changes": [],
        "quality_blockers": [],
        "trade_map": [
            {
                "expression": "risk_down_credit_sensitive",
                "label": "风险降档 / 信用敏感",
                "time_window": "1w",
            }
        ],
        "scenario_cases": [
            {
                "case": "base",
                "label": "基准情景",
                "thesis": "风险降档延续。",
                "trade": "降低信用敏感 beta。",
                "invalidation": "美元与信用压力同步回落。",
            }
        ],
    }
    repo = FakeMacroIntelRepository(
        snapshot=snapshot,
        observations=[
            _macro_observation("asset:ndx", "2026-05-01", 100.0),
            _macro_observation("asset:ndx", "2026-05-20", 94.0),
            _macro_observation("crypto:btc", "2026-05-01", 100.0),
            _macro_observation("crypto:btc", "2026-05-20", 90.0),
            _macro_observation("asset:gld", "2026-05-01", 100.0),
            _macro_observation("asset:gld", "2026-05-20", 104.0),
            _macro_observation("asset:spx", "2026-05-01", 100.0),
            _macro_observation("asset:spx", "2026-05-20", 98.0),
            _macro_observation("asset:tlt", "2026-05-01", 100.0),
            _macro_observation("asset:tlt", "2026-05-20", 101.0),
            {
                **_macro_observation("event:fomc_decision_next", "2026-06-17", 1),
                "series_key": "official_calendar:fomc_decision_next",
                "source_name": "official_calendar",
                "unit": "days",
                "frequency": "event",
                "raw_payload_json": {
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
            },
        ],
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/overview", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert repo.latest_observations_call is None
    assert repo.observations_for_concepts_call is not None
    assert repo.observations_for_concepts_call["lookback_days"] == 60
    assert "event:fomc_decision_next" in repo.observations_for_concepts_call["concept_keys"]
    assert "event:fed_speech" in repo.observations_for_concepts_call["concept_keys"]
    assert "event:bea_gdp_next" in repo.observations_for_concepts_call["concept_keys"]
    assert "event:treasury_auction_10y_bid_to_cover" in repo.observations_for_concepts_call["concept_keys"]
    assert "asset:ndx" in repo.observations_for_concepts_call["concept_keys"]
    assert "crypto:btc" in repo.observations_for_concepts_call["concept_keys"]
    assert "asset:gld" in repo.observations_for_concepts_call["concept_keys"]
    assert "asset:spx" in repo.observations_for_concepts_call["concept_keys"]
    assert "asset:tlt" in repo.observations_for_concepts_call["concept_keys"]
    payload = response.json()
    assert "event_catalysts" not in payload["data"]["module_read"]["decision_console"]
    assert "event_heatmap" not in payload["data"]["module_read"]["decision_console"]
    assert payload["data"]["module_read"]["market_event_flow"]["rows"] == [
        {
            "key": "official_calendar:fomc_decision_next",
            "label": "FOMC 决议",
            "date": "2026-06-17",
            "detail": "2026-06-17 · 还有 1 天 · 14:00 ET",
            "source": "官方日历",
            "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "kind": "calendar",
            "window": "0-3d",
            "window_label": "0-3天",
            "severity": "high",
            "severity_label": "高",
            "category": "policy",
            "category_label": "政策",
            "impact": "policy_path",
            "impact_label": "政策路径",
            "watch": "利率路径和流动性定价。",
        }
    ]
    assert (
        payload["data"]["module_read"]["decision_console"]["trade_map"][0]["historical_review"]["win_rate_label"]
        == "5/5"
    )


def test_macro_overview_module_api_loads_news_rows_for_market_event_flow() -> None:
    macro_intel = FakeMacroIntelRepository(snapshot=_macro_snapshot(), observations=[])
    news = FakeNewsRepository(
        rows=[
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
                "macro_event_flow": {
                    "window": "recent",
                    "window_label": "近期",
                    "severity": "low",
                    "severity_label": "低",
                    "category": "macro_policy",
                    "category_label": "美联储",
                    "impact": "mainline_context",
                    "impact_label": "不改主线",
                    "watch": "SPX · 美元 · 美联储",
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
        ]
    )
    app = _app(macro_intel, news=news)

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/overview", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert news.calls == [
        {
            "cursor": None,
            "limit": 7,
            "macro_event_flow": True,
            "q": None,
            "signal": None,
            "status": None,
        }
    ]
    payload = response.json()
    assert payload["data"]["module_read"]["market_event_flow"]["rows"] == [
        {
            "key": "news:news-row-1",
            "label": "中东震荡下，日本追加预算预期升温",
            "date": "2026-06-10",
            "detail": "油价与美元走强，风险资产低开。",
            "source": "bloomberg.com",
            "source_url": "https://news.google.com/articles/macro-1",
            "kind": "news",
            "window": "recent",
            "window_label": "近期",
            "severity": "low",
            "severity_label": "低",
            "category": "macro_policy",
            "category_label": "美联储",
            "impact": "mainline_context",
            "impact_label": "不改主线",
            "watch": "SPX · 美元 · 美联储",
        }
    ]


def test_macro_module_api_rejects_unsupported_module() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/not-real", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_macro_module", "field": "module_id"}


def test_macro_module_api_serves_assets_landing_module() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/assets", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json()["data"]["snapshot"]["module_id"] == "assets"
    assert response.json()["data"]["snapshot"]["route_path"] == "/macro/assets"


def test_macro_assets_module_requires_daily_brief_repository_contract() -> None:
    app = _app(MissingDailyBriefMacroIntelRepository(snapshot=None))

    with pytest.raises(AttributeError, match="latest_macro_daily_brief"), TestClient(app) as client:
        client.get("/api/macro/modules/assets", headers={"Authorization": "Bearer secret"})


@pytest.mark.parametrize("module_id", ("rates", "fed", "liquidity", "economy", "volatility", "credit"))
def test_macro_module_api_rejects_parent_categories(module_id: str) -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get(f"/api/macro/modules/{module_id}", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_macro_module", "field": "module_id"}


def test_macro_series_api_returns_bounded_concept_series() -> None:
    repo = FakeMacroIntelRepository(
        snapshot=None,
        observations=[
            _macro_observation("rates:dgs10", "2026-05-19", 4.6),
            _macro_observation("rates:dgs10", "2026-05-20", 4.7),
        ],
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/series?concept_keys=rates:dgs10&window=60d",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert repo.observations_for_concepts_call == {
        "concept_keys": ("rates:dgs10",),
        "lookback_days": 90,
        "limit_per_series": 90,
    }
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["series"]["rates:dgs10"]["status"] == "ok"
    assert payload["data"]["series"]["rates:dgs10"]["data_gaps"] == []
    assert payload["data"]["series"]["rates:dgs10"]["points"] == [
        {"observed_at": "2026-05-19", "value": 4.6, "source_name": "yahoo", "data_quality": "ok"},
        {"observed_at": "2026-05-20", "value": 4.7, "source_name": "yahoo", "data_quality": "ok"},
    ]


def test_macro_series_api_rejects_query_token_auth() -> None:
    repo = FakeMacroIntelRepository(
        snapshot=None,
        observations=[_macro_observation("rates:dgs10", "2026-05-20", 4.7)],
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro/series?concept_keys=rates:dgs10&window=60d&token=secret")

    assert response.status_code == 401
    assert response.json() == {"ok": False, "error": "unauthorized"}
    assert repo.observations_for_concepts_call is None


def test_macro_series_api_rejects_token_query_param_even_with_bearer_auth() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/series?concept_keys=rates:dgs10&window=60d&token=secret",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_query_param", "field": "token"}


def test_macro_series_api_rejects_provider_series_keys() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/series?concept_keys=fred:DGS10&window=60d",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_macro_concept", "field": "concept_keys"}


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        snapshot: dict[str, object] | None,
        observations: list[dict[str, object]] | None = None,
        publication_state: dict[str, object] | None = None,
        daily_brief: dict[str, object] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.observations = observations or []
        self.publication_state = publication_state
        self.daily_brief = daily_brief
        self.calls: list[tuple[str, str | None]] = []
        self.observations_for_concepts_call: dict[str, object] | None = None
        self.latest_observations_call: dict[str, object] | None = None
        self.latest_macro_daily_brief_call: dict[str, object] | None = None

    def latest_snapshot(self, *, projection_version: str | None = None):
        self.calls.append(("latest_snapshot", projection_version))
        return self.snapshot

    def observations_for_concepts(
        self,
        *,
        concept_keys: tuple[str, ...],
        lookback_days: int,
        limit_per_series: int,
    ):
        self.observations_for_concepts_call = {
            "concept_keys": concept_keys,
            "lookback_days": lookback_days,
            "limit_per_series": limit_per_series,
        }
        return self.observations

    def latest_observations(self, *, limit: int = 250, concept_keys: tuple[str, ...] | None = None):
        self.latest_observations_call = {
            "concept_keys": concept_keys,
            "limit": limit,
        }
        return self.observations

    def macro_series_publication_state(self, projection_version: str):
        self.calls.append(("macro_series_publication_state", projection_version))
        return self.publication_state

    def latest_macro_daily_brief(self, *, brief_key: str = "assets_today"):
        self.latest_macro_daily_brief_call = {"brief_key": brief_key}
        return self.daily_brief


class MissingDailyBriefMacroIntelRepository(FakeMacroIntelRepository):
    def __getattribute__(self, name: str):
        if name == "latest_macro_daily_brief":
            raise AttributeError(name)
        return super().__getattribute__(name)


class FakeNewsRepository:
    def __init__(self, *, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[dict[str, object]] = []

    def list_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        signal: str | None = None,
        macro_event_flow: bool = False,
        q: str | None = None,
    ):
        self.calls.append(
            {
                "cursor": cursor,
                "limit": limit,
                "macro_event_flow": macro_event_flow,
                "q": q,
                "signal": signal,
                "status": status,
            }
        )
        return self.rows[:limit]


class FakeRepositoryContext:
    def __init__(self, macro_intel: FakeMacroIntelRepository, news: FakeNewsRepository) -> None:
        self.macro_intel = macro_intel
        self.news = news

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(self, macro_intel: FakeMacroIntelRepository, news: FakeNewsRepository | None = None) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.macro_intel = macro_intel
        self.news = news or FakeNewsRepository()

    def repositories(self):
        return FakeRepositoryContext(self.macro_intel, self.news)


def _app(macro_intel: FakeMacroIntelRepository, *, news: FakeNewsRepository | None = None) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(macro_intel, news)
    return app


def _macro_observation(concept_key: str, observed_at: str, value: float) -> dict[str, object]:
    return {
        "concept_key": concept_key,
        "series_key": f"series:{concept_key}",
        "source_name": "yahoo",
        "source_priority": 100,
        "observed_at": observed_at,
        "value_numeric": value,
        "unit": "price",
        "data_quality": "ok",
        "ingested_at_ms": 1_779_000_000_000,
    }


def _macro_snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "macro-view:macro_regime_v4:current",
        "projection_version": "macro_regime_v4",
        "asof_date": "2026-05-20",
        "status": "ready",
        "regime": "risk_on",
        "overall_score": 7.2,
        "panels_json": {"liquidity": {"score": 8.0}},
        "indicators_json": {"sofr_iorb_spread_bps": {"value": 15.0}},
        "triggers_json": [{"code": "sofr_above_iorb"}],
        "data_gaps_json": [],
        "source_coverage_json": {"latest_coverage_ratio": 1.0},
        "features_json": {
            "rates:dgs10": {
                "concept_key": "rates:dgs10",
                "label": "10年期美债收益率",
                "short_label": "10Y",
                "description": "美国长期无风险利率基准",
                "unit": "percent",
                "unit_label": "%",
                "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
                "history_points": 252,
                "data_quality": "ok",
                "source": {"name": "fred", "series_key": "fred:DGS10"},
            }
        },
        "chain_json": {"liquidity": {"regime": "supportive"}},
        "scenario_json": {
            "current_regime": "risk_on",
            "confidence": 0.68,
            "confirmations": [],
            "contradictions": [],
            "watch_triggers": [],
            "invalidations": [],
            "top_changes": [
                {
                    "code": "liquidity_supports_risk",
                    "label": "流动性支持风险偏好",
                    "evidence_label": "SOFR-IORB pressure remains contained",
                    "node": "liquidity",
                    "kind": "confirmation",
                }
            ],
            "quality_blockers": [],
            "trade_map": [],
            "scenario_cases": [
                {
                    "case": "base",
                    "label": "基准情景",
                    "thesis": "风险偏好维持。",
                    "trade": "维持风险资产观察仓位。",
                    "invalidation": "流动性压力重新抬头。",
                }
            ],
        },
        "scorecard_json": {"projection_version": "macro_regime_v4"},
        "computed_at_ms": 1_779_000_000_000,
    }


def _macro_currentness() -> dict[str, object]:
    return {
        "publication_status": "published",
        "publication_row_count": 1,
        "publication_finished_at_ms": 1_779_000_000_000,
        "facts_max_observed_at": "2026-05-20",
        "projection_lag_days": 0,
        "projection_behind_facts": False,
    }
