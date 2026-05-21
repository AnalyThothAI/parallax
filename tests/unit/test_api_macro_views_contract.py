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


def test_macro_views_api_returns_latest_snapshot_without_postgres() -> None:
    repo = FakeMacroIntelRepository(
        snapshot={
            "snapshot_id": "macro-view:macro_regime_v1:1",
            "projection_version": "macro_regime_v1",
            "asof_date": "2026-05-20",
            "status": "partial",
            "regime": "funding_stress",
            "overall_score": 7.2,
            "panels_json": {"liquidity": {"score": 8.0, "regime": "funding_stress"}},
            "indicators_json": {"sofr_iorb_spread_bps": {"value": 15.0}},
            "triggers_json": [{"code": "sofr_above_iorb"}],
            "data_gaps_json": ["missing:fred:SP500"],
            "source_coverage_json": {"observed_series_count": 10},
            "computed_at_ms": 1_779_000_000_000,
        }
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/views/macro", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert repo.calls == ["latest_snapshot"]
    assert response.json() == {
        "ok": True,
        "data": {
            "snapshot": {
                "snapshot_id": "macro-view:macro_regime_v1:1",
                "projection_version": "macro_regime_v1",
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
        },
    }


def test_macro_views_api_returns_data_gap_when_snapshot_missing() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get("/api/views/macro", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json()["data"] == {
        "snapshot": None,
        "panels": {},
        "indicators": {},
        "triggers": [],
        "data_gaps": ["macro_view_snapshot_missing"],
        "source_coverage": {"observed_series_count": 0},
    }


class FakeMacroIntelRepository:
    def __init__(self, *, snapshot: dict[str, object] | None) -> None:
        self.snapshot = snapshot
        self.calls: list[str] = []

    def latest_snapshot(self):
        self.calls.append("latest_snapshot")
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
