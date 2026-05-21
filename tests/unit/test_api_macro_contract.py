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


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        snapshot: dict[str, object] | None,
        observations: list[dict[str, object]] | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.observations = observations or []
        self.calls: list[tuple[str, str | None]] = []
        self.observations_for_concepts_call: dict[str, object] | None = None

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


class FakeRepositoryContext:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.macro_intel = macro_intel

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(self, macro_intel: FakeMacroIntelRepository) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.macro_intel = macro_intel

    def repositories(self):
        return FakeRepositoryContext(self.macro_intel)


def _app(macro_intel: FakeMacroIntelRepository) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(macro_intel)
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
