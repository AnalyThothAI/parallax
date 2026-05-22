from __future__ import annotations

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


def test_macro_api_returns_latest_snapshot_without_postgres() -> None:
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "macro-view:macro_regime_v3:1",
            "projection_version": "macro_regime_v3",
            "asof_date": "2026-05-20",
            "status": "partial",
            "regime": "funding_stress",
            "overall_score": 7.2,
            "panels_json": {"liquidity": {"score": 8.0, "regime": "funding_stress"}},
            "indicators_json": {"sofr_iorb_spread_bps": {"value": 15.0}},
            "triggers_json": [{"code": "sofr_above_iorb"}],
            "data_gaps_json": ["missing:asset:spx"],
            "source_coverage_json": {"observed_concept_count": 10},
            "features_json": {
                "rates:dgs10": {
                    "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
                    "delta": {"5d": 0.1, "20d": 0.35, "60d": None},
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
                "projection_version": "macro_regime_v3",
                "chain_average": 7.8,
                "observed_concept_count": 10,
            },
            "computed_at_ms": 1_779_000_000_000,
        }
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert repo.calls == [("latest_snapshot", "macro_regime_v3")]
    assert response.json() == {
        "ok": True,
        "data": {
            "snapshot": {
                "snapshot_id": "macro-view:macro_regime_v3:1",
                "projection_version": "macro_regime_v3",
                "asof_date": "2026-05-20",
                "status": "partial",
                "regime": "funding_stress",
                "overall_score": 7.2,
                "computed_at_ms": 1_779_000_000_000,
            },
            "panels": {"liquidity": {"score": 8.0, "regime": "funding_stress"}},
            "indicators": {"sofr_iorb_spread_bps": {"value": 15.0}},
            "triggers": [{"code": "sofr_above_iorb"}],
            "data_gaps": ["missing:asset:spx"],
            "source_coverage": {"observed_concept_count": 10},
            "features": {
                "rates:dgs10": {
                    "latest": {"value": 4.7, "observed_at": "2026-05-20", "unit": "percent"},
                    "delta": {"5d": 0.1, "20d": 0.35, "60d": None},
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
                "projection_version": "macro_regime_v3",
                "chain_average": 7.8,
                "observed_concept_count": 10,
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
        "panels": {},
        "indicators": {},
        "triggers": [],
        "data_gaps": ["macro_view_snapshot_missing"],
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
            },
            "chain_json": {"rates": {"regime": "tightening"}},
            "scenario_json": {"current_regime": "tightening", "watch_triggers": [{"code": "higher_real_rates"}]},
            "source_coverage_json": {"coverage_ratio": 0.5},
            "data_gaps_json": [],
        },
        observations=[_macro_observation("rates:dgs10", "2026-05-20", 4.7)],
        import_run={"run_id": "macro-import-1", "status": "partial", "reason_codes_json": ["fred_key_missing"]},
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/rates", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert repo.calls == [("latest_snapshot", "macro_regime_v3"), ("latest_import_run", None)]
    assert repo.latest_observations_call == {
        "concept_keys": (
            "rates:dgs2",
            "rates:dgs10",
            "rates:dgs5",
            "rates:dgs30",
            "rates:10y2y",
            "rates:10y3m",
        ),
        "limit": 250,
    }
    assert repo.observations_for_concepts_call is None
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["snapshot"]["module_id"] == "rates"
    assert payload["data"]["charts"][0]["status"] == "partial"
    assert payload["data"]["provenance"]["latest_import_run"]["run_id"] == "macro-import-1"


def test_macro_module_api_rejects_unsupported_module() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/not-real", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_macro_module", "field": "module_id"}


def test_macro_module_api_compacts_crypto_derivatives_cex_rows() -> None:
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "snapshot-1",
            "projection_version": "macro_regime_v3",
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
            "source_coverage_json": {"coverage_ratio": 0.5},
            "data_gaps_json": [],
        },
        observations=[],
        import_run=None,
    )
    cex_repo = FakeCexOiRadarRepository(
        board={
            "run": {
                "run_id": "cex-run-1",
                "status": "partial",
                "finished_at_ms": 1_779_000_200_000,
                "notes_json": {"degraded_reasons": ["coinglass_partial"]},
            },
            "rows": [
                {
                    "row_id": "cex-row-internal",
                    "run_id": "cex-run-1",
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
    cex_table = next(
        table for table in response.json()["data"]["tables"] if table["table_id"] == "cex_perp_board"
    )
    row = cex_table["rows"][0]
    assert row == {
        "rank": 1,
        "symbol": "BTC",
        "native_market_id": "BTCUSDT",
        "quote_symbol": "USDT",
        "open_interest_usd": 12_500_000_000,
        "funding_rate": 0.0001,
        "volume_24h_usd": 31_000_000_000,
        "mark_price": 110_100.0,
        "score": 91.2,
        "observed_at_ms": 1_779_000_100_000,
        "computed_at_ms": 1_779_000_150_000,
        "degraded_reasons": ["coinglass_partial"],
    }
    assert "row_id" not in row
    assert "run_id" not in row
    assert "target_id" not in row
    assert "pricefeed_id" not in row
    assert "score_components_json" not in row


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
        import_run: dict[str, object] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.observations = observations or []
        self.import_run = import_run
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

    def latest_import_run(self):
        self.calls.append(("latest_import_run", None))
        return self.import_run


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
