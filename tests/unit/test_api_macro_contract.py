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


def test_macro_api_returns_latest_snapshot_without_postgres() -> None:
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "macro-view:macro_regime_v2:1",
            "projection_version": "macro_regime_v2",
            "asof_date": "2026-05-20",
            "status": "partial",
            "regime": "funding_stress",
            "overall_score": 7.2,
            "panels_json": {"liquidity": {"score": 8.0, "regime": "funding_stress"}},
            "indicators_json": {"sofr_iorb_spread_bps": {"value": 15.0}},
            "triggers_json": [{"code": "sofr_above_iorb"}],
            "data_gaps_json": ["missing:fred:SP500"],
            "source_coverage_json": {"observed_series_count": 10},
            "features_json": {
                "fred:DGS10": {
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
                "projection_version": "macro_regime_v2",
                "chain_average": 7.8,
                "observed_series_count": 10,
            },
            "computed_at_ms": 1_779_000_000_000,
        }
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert repo.calls == [("latest_snapshot", "macro_regime_v2")]
    assert response.json() == {
        "ok": True,
        "data": {
            "snapshot": {
                "snapshot_id": "macro-view:macro_regime_v2:1",
                "projection_version": "macro_regime_v2",
                "asof_date": "2026-05-20",
                "status": "partial",
                "regime": "funding_stress",
                "overall_score": 7.2,
                "computed_at_ms": 1_779_000_000_000,
            },
            "panels": {"liquidity": {"score": 8.0, "regime": "funding_stress"}},
            "indicators": {"sofr_iorb_spread_bps": {"value": 15.0}},
            "triggers": [{"code": "sofr_above_iorb"}],
            "data_gaps": ["missing:fred:SP500"],
            "source_coverage": {"observed_series_count": 10},
            "features": {
                "fred:DGS10": {
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
                "projection_version": "macro_regime_v2",
                "chain_average": 7.8,
                "observed_series_count": 10,
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
        "source_coverage": {"observed_series_count": 0},
        "features": {},
        "chain": {},
        "scenario": {},
        "scorecard": {},
    }


class FakeMacroIntelRepository:
    def __init__(self, *, snapshot: dict[str, object] | None) -> None:
        self.snapshot = snapshot
        self.calls: list[tuple[str, str | None]] = []

    def latest_snapshot(self, *, projection_version: str | None = None):
        self.calls.append(("latest_snapshot", projection_version))
        return self.snapshot


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
