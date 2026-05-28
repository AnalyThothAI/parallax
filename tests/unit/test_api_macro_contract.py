from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gmgn_twitter_intel.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from gmgn_twitter_intel.app.surfaces.api.http import create_api_router
from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CORE_CONCEPTS
from gmgn_twitter_intel.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps


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
                "trade_map": [{"expression": "risk_down_credit_sensitive", "time_window": "1w"}],
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
                "trade_map": [{"expression": "risk_down_credit_sensitive", "time_window": "1w"}],
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


def test_macro_api_rejects_timestamp_text_for_currentness_dates() -> None:
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "macro-view:macro_regime_v4:timestamp",
            "projection_version": "macro_regime_v4",
            "asof_date": "2026-05-27",
            "status": "ready",
            "regime": "risk_on",
            "overall_score": 6.8,
            "computed_at_ms": 1_779_000_000_000,
            "source_coverage_json": {
                "latest_observed_at": "2026-05-28 00:00:00+00:00",
            },
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
            "features_json": {
                "rates:dgs2": {
                    "label": "2年期美债收益率",
                    "short_label": "2Y",
                    "latest": {"value": 3.9, "observed_at": "2026-05-20", "unit": "percent"},
                    "freshness_days": 1,
                    "history_points": 1,
                    "data_gaps": build_macro_data_gaps(["insufficient_history:20d"]),
                    "source": {"name": "fred"},
                },
                "rates:dgs10": {
                    "label": "10年期美债收益率",
                    "short_label": "10Y",
                    "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
                    "freshness_days": 1,
                    "history_points": 1,
                    "data_gaps": build_macro_data_gaps(["insufficient_history:20d"]),
                    "source": {"name": "fred"},
                },
            },
            "chain_json": {"rates": {"regime": "tightening"}},
            "scenario_json": {"current_regime": "tightening", "watch_triggers": [{"code": "higher_real_rates"}]},
            "source_coverage_json": {"latest_coverage_ratio": 1.0, "history_coverage_ratio": 0.0},
            "data_gaps_json": build_macro_data_gaps(["insufficient_history:20d"]),
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
    assert repo.latest_observations_call == {
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
        "limit": 250,
    }
    assert repo.observations_for_concepts_call is None
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
        "source": "Yahoo",
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


def test_macro_module_api_rejects_unsupported_module() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/not-real", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_macro_module", "field": "module_id"}


@pytest.mark.parametrize("module_id", ("assets", "rates", "fed", "liquidity", "economy", "volatility", "credit"))
def test_macro_module_api_rejects_parent_categories(module_id: str) -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get(f"/api/macro/modules/{module_id}", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_macro_module", "field": "module_id"}


def test_macro_module_api_compacts_crypto_derivatives_cex_rows() -> None:
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "snapshot-1",
            "projection_version": "macro_regime_v4",
            "asof_date": "2026-05-20",
            "status": "partial",
            "regime": "tightening",
            "computed_at_ms": 1_779_000_000_000,
            "features_json": {
                "crypto:btc": {
                    "latest": {"value": 110_000, "observed_at": "2026-05-20", "unit": "usd"},
                    "freshness_days": 1,
                    "data_gaps": [],
                },
            },
            "chain_json": {"assets": {"regime": "risk_on"}},
            "scenario_json": {"current_regime": "risk_on", "watch_triggers": []},
            "source_coverage_json": {"latest_coverage_ratio": 0.5, "history_coverage_ratio": 0.0},
            "data_gaps_json": [],
        },
        observations=[],
    )
    cex_repo = FakeCexOiRadarRepository(
        board={
            "publication": {
                "status": "partial",
                "published_at_ms": 1_779_000_200_000,
            },
            "rows": [
                {
                    "row_id": "cex-row-internal",
                    "rank": 1,
                    "target_id": "cex-token:btc",
                    "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                    "native_market_id": "BTCUSDT",
                    "base_symbol": "BTC",
                    "quote_symbol": "USDT",
                    "open_interest_usd": 12_500_000_000,
                    "funding_rate": 0.0001,
                    "volume_24h_usd": 31_000_000_000,
                    "mark_price": 110_100.0,
                    "score": 91.2,
                    "score_components_json": {"oi": 50},
                    "observed_at_ms": 1_779_000_100_000,
                    "computed_at_ms": 1_779_000_150_000,
                }
            ],
        }
    )
    app = _app(repo, cex_oi_radar=cex_repo)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/modules/assets/crypto-derivatives",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert cex_repo.latest_board_call == {"limit": 20}
    cex_table = next(table for table in response.json()["data"]["tables"] if table["id"] == "cex_perp_board")
    row = cex_table["rows"][0]
    assert row == {
        "row_id": "BTCUSDT",
        "row_quality": "partial",
        "source_state": {"label": "CEX OI Radar", "status": "partial"},
        "cells": {
            "symbol": {"display_value": "BTC", "sort_value": "BTC"},
            "open_interest": {"display_value": "12.50B", "sort_value": 12_500_000_000.0},
            "funding": {"display_value": "0.0100%", "sort_value": 0.0001},
            "volume_24h": {"display_value": "31.00B", "sort_value": 31_000_000_000.0},
            "score": {"display_value": "91.20", "sort_value": 91.2},
        },
    }
    assert "run_id" not in row
    assert "target_id" not in row
    assert "pricefeed_id" not in row
    assert "score_components_json" not in row
    assert "rank" not in row
    assert "native_market_id" not in row
    assert "mark_price" not in row


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


def test_macro_series_api_accepts_query_token_auth() -> None:
    repo = FakeMacroIntelRepository(
        snapshot=None,
        observations=[_macro_observation("rates:dgs10", "2026-05-20", 4.7)],
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro/series?concept_keys=rates:dgs10&window=60d&token=secret")

    assert response.status_code == 200
    assert repo.observations_for_concepts_call == {
        "concept_keys": ("rates:dgs10",),
        "lookback_days": 90,
        "limit_per_series": 90,
    }
    payload = response.json()
    assert payload["data"]["series"]["rates:dgs10"]["status"] == "insufficient_history"
    assert payload["data"]["series"]["rates:dgs10"]["data_gaps"] == [
        {
            "code": "insufficient_history_2_points",
            "label": "历史样本不足：至少需要 2 个点才能绘图",
            "severity": "warning",
            "score_participation": False,
            "concept_key": "rates:dgs10",
        }
    ]
    assert payload["data"]["data_gaps"] == payload["data"]["series"]["rates:dgs10"]["data_gaps"]


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
    ) -> None:
        self.snapshot = snapshot
        self.observations = observations or []
        self.publication_state = publication_state
        self.calls: list[tuple[str, str | None]] = []
        self.observations_for_concepts_call: dict[str, object] | None = None
        self.latest_observations_call: dict[str, object] | None = None

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


class FakeCexOiRadarRepository:
    def __init__(self, *, board: dict[str, object]) -> None:
        self.board = board
        self.latest_board_call: dict[str, object] | None = None

    def latest_board(self, *, limit: int):
        self.latest_board_call = {"limit": limit}
        return self.board


class FakeRepositoryContext:
    def __init__(
        self,
        macro_intel: FakeMacroIntelRepository,
        cex_oi_radar: FakeCexOiRadarRepository | None = None,
    ) -> None:
        self.macro_intel = macro_intel
        self.cex_oi_radar = cex_oi_radar

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(
        self,
        macro_intel: FakeMacroIntelRepository,
        cex_oi_radar: FakeCexOiRadarRepository | None = None,
    ) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.macro_intel = macro_intel
        self.cex_oi_radar = cex_oi_radar

    def repositories(self):
        return FakeRepositoryContext(self.macro_intel, cex_oi_radar=self.cex_oi_radar)


def _app(
    macro_intel: FakeMacroIntelRepository,
    *,
    cex_oi_radar: FakeCexOiRadarRepository | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(macro_intel, cex_oi_radar=cex_oi_radar)
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
        "ingested_at_ms": 1_779_000_000_000,
    }
