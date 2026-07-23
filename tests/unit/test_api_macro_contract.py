from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router
from parallax.domains.macro_intel.services.macro_evidence_snapshot import build_macro_evidence_snapshot

_PAGE_ROUTES = {
    "/api/macro/overview": "overview",
    "/api/macro/cross-asset": "cross_asset",
    "/api/macro/rates-inflation": "rates_inflation",
    "/api/macro/growth-labor": "growth_labor",
    "/api/macro/liquidity-funding": "liquidity_funding",
    "/api/macro/credit": "credit",
}


def test_six_macro_pages_read_only_the_persisted_page_projection() -> None:
    snapshot = build_macro_evidence_snapshot([], computed_at_ms=1_779_000_000_000)
    repo = FakeMacroIntelRepository(pages={page_id: snapshot[page_id] for page_id in _PAGE_ROUTES.values()})
    app = _app(repo)

    with TestClient(app) as client:
        responses = {path: client.get(path, headers={"Authorization": "Bearer secret"}) for path in _PAGE_ROUTES}

    assert all(response.status_code == 200 for response in responses.values())
    assert [call for call in repo.calls] == list(_PAGE_ROUTES.values())
    assert repo.observations_for_concepts_call is None
    for path, page_id in _PAGE_ROUTES.items():
        payload = responses[path].json()
        assert payload["ok"] is True
        assert payload["data"]["page_id"] == page_id
        assert payload["data"]["snapshot"]["projection_version"] == "macro_decision_v2"


@pytest.mark.parametrize(
    "path",
    (
        "/api/macro",
        "/api/macro/assets/correlation",
        "/api/macro/modules/overview",
        "/api/macro/modules/rates/yield-curve",
    ),
)
def test_retired_macro_endpoints_are_ordinary_not_found(path: str) -> None:
    app = _app(FakeMacroIntelRepository())

    with TestClient(app) as client:
        response = client.get(path, headers={"Authorization": "Bearer secret"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_macro_page_missing_projection_fails_closed_without_inline_build() -> None:
    repo = FakeMacroIntelRepository()
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/overview",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 503
    assert response.json() == {"ok": False, "error": "macro_projection_missing"}
    assert repo.calls == ["overview"]
    assert repo.observations_for_concepts_call is None


def test_macro_pages_have_exact_typed_contracts() -> None:
    snapshot = build_macro_evidence_snapshot([], computed_at_ms=1_779_000_000_000)
    models = {
        "overview": api_schemas.MacroOverviewData,
        "cross_asset": api_schemas.MacroCrossAssetData,
        "rates_inflation": api_schemas.MacroRatesInflationData,
        "growth_labor": api_schemas.MacroGrowthLaborData,
        "liquidity_funding": api_schemas.MacroLiquidityFundingData,
        "credit": api_schemas.MacroCreditData,
    }

    for page_id, model in models.items():
        model.model_validate(snapshot[page_id])
        with pytest.raises(ValidationError, match="extra_forbidden"):
            model.model_validate({**snapshot[page_id], "legacy_score": 100})

    evidence = dict(snapshot["credit"]["evidence"][0])
    with pytest.raises(ValidationError, match="extra_forbidden"):
        api_schemas.MacroEvidenceData.model_validate({**evidence, "percentile": 0.9})


def test_macro_series_api_returns_strict_bounded_series() -> None:
    repo = FakeMacroIntelRepository(
        observations=[
            {
                "concept_key": "rates:dgs10",
                "observed_at": "2026-05-20",
                "value_numeric": 4.7,
                "source_name": "fred",
                "series_key": "fred:DGS10",
                "unit": "percent",
                "frequency": "daily",
                "data_quality": "ok",
                "event_metadata_json": {},
            },
            {
                "concept_key": "rates:dgs10",
                "observed_at": "2026-05-21",
                "value_numeric": 4.8,
                "source_name": "fred",
                "series_key": "fred:DGS10",
                "unit": "percent",
                "frequency": "daily",
                "data_quality": "ok",
                "event_metadata_json": {},
            },
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
    point = response.json()["data"]["series"]["rates:dgs10"]["points"][0]
    assert point == {
        "observed_at": "2026-05-20",
        "value": 4.7,
        "source_name": "fred",
        "series_key": "fred:DGS10",
        "unit": "percent",
        "frequency": "daily",
        "data_quality": "ok",
        "event_metadata": {},
    }


def test_macro_series_rejects_query_token_and_provider_series_keys() -> None:
    app = _app(FakeMacroIntelRepository())

    with TestClient(app) as client:
        query_token = client.get("/api/macro/series?concept_keys=rates:dgs10&token=secret")
        bearer_token_query = client.get(
            "/api/macro/series?concept_keys=rates:dgs10&token=secret",
            headers={"Authorization": "Bearer secret"},
        )
        provider_key = client.get(
            "/api/macro/series?concept_keys=fred:DGS10",
            headers={"Authorization": "Bearer secret"},
        )

    assert query_token.status_code == 401
    assert bearer_token_query.json() == {
        "ok": False,
        "error": "unsupported_query_param",
        "field": "token",
    }
    assert provider_key.json() == {
        "ok": False,
        "error": "unsupported_macro_concept",
        "field": "concept_keys",
    }


def test_daily_macro_judgment_reads_typed_persisted_job_state_without_model_calls() -> None:
    daily = FakeDailyMacroJudgmentRepository(
        jobs={
            date(2026, 7, 22): {
                "session_date": date(2026, 7, 22),
                "market_cutoff_ms": 1_774_200_000_000,
                "status": "blocked",
                "attempt_count": 1,
                "max_attempts": 3,
                "due_at_ms": 1_774_201_800_000,
                "reviewer_disposition": "block",
                "last_error": "daily_macro_judgment_reviewer_block",
                "updated_at_ms": 1_774_201_900_000,
            }
        }
    )
    app = _app(FakeMacroIntelRepository(), daily_macro_judgments=daily)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/daily-judgment?session_date=2026-07-22",
            headers={"Authorization": "Bearer secret"},
        )
        unsupported = client.get(
            "/api/macro/daily-judgment?session_date=2026-07-22&window=20d",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data": {
            "target_session_date": "2026-07-22",
            "state": "blocked",
            "is_current": False,
            "publication": None,
            "target_job": {
                "session_date": "2026-07-22",
                "market_cutoff_ms": 1_774_200_000_000,
                "status": "blocked",
                "attempt_count": 1,
                "max_attempts": 3,
                "due_at_ms": 1_774_201_800_000,
                "reviewer_disposition": "block",
                "last_error": "daily_macro_judgment_reviewer_block",
                "updated_at_ms": 1_774_201_900_000,
            },
        },
    }
    assert daily.calls == [
        ("publication", date(2026, 7, 22)),
        ("job", date(2026, 7, 22)),
    ]
    assert unsupported.json() == {
        "ok": False,
        "error": "unsupported_query_param",
        "field": "window",
    }


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        pages: dict[str, dict[str, Any]] | None = None,
        observations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.pages = pages or {}
        self.observations = observations or []
        self.calls: list[str] = []
        self.observations_for_concepts_call: dict[str, object] | None = None

    def snapshot_page(self, page_id: str) -> dict[str, Any] | None:
        self.calls.append(page_id)
        return self.pages.get(page_id)

    def observations_for_concepts(
        self,
        *,
        concept_keys: tuple[str, ...],
        lookback_days: int,
        limit_per_series: int,
    ) -> list[dict[str, Any]]:
        self.observations_for_concepts_call = {
            "concept_keys": concept_keys,
            "lookback_days": lookback_days,
            "limit_per_series": limit_per_series,
        }
        return self.observations


class FakeDailyMacroJudgmentRepository:
    def __init__(
        self,
        *,
        jobs: dict[date, dict[str, Any]] | None = None,
    ) -> None:
        self.jobs = jobs or {}
        self.calls: list[tuple[str, date]] = []

    def publication_record(self, session_date: date) -> None:
        self.calls.append(("publication", session_date))

    def latest_publication_record(self) -> None:
        return None

    def job_record(self, session_date: date) -> dict[str, Any] | None:
        self.calls.append(("job", session_date))
        return self.jobs.get(session_date)

    def outcomes_for_session(self, session_date: date) -> list[dict[str, Any]]:
        raise AssertionError(f"unexpected outcome read for {session_date}")


class FakeRepositoryContext:
    def __init__(
        self,
        macro_intel: FakeMacroIntelRepository,
        daily_macro_judgments: FakeDailyMacroJudgmentRepository,
    ) -> None:
        self.macro_intel = macro_intel
        self.daily_macro_judgments = daily_macro_judgments

    def __enter__(self) -> FakeRepositoryContext:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakeRuntime:
    def __init__(
        self,
        macro_intel: FakeMacroIntelRepository,
        daily_macro_judgments: FakeDailyMacroJudgmentRepository,
    ) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.macro_intel = macro_intel
        self.daily_macro_judgments = daily_macro_judgments

    def repositories(self) -> FakeRepositoryContext:
        return FakeRepositoryContext(self.macro_intel, self.daily_macro_judgments)


def _app(
    macro_intel: FakeMacroIntelRepository,
    *,
    daily_macro_judgments: FakeDailyMacroJudgmentRepository | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: {"ok": True}))
    app.state.service = FakeRuntime(
        macro_intel,
        daily_macro_judgments or FakeDailyMacroJudgmentRepository(),
    )
    return app
