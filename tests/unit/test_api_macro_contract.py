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


def test_macro_research_reads_latest_persisted_publication_only() -> None:
    repository = FakeMacroResearchRepository(state="current")
    app = _app(repository)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/research",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["state"] == "current"
    assert payload["data"]["publication"]["title"] == "宏观研究：增长与实际利率的拉锯"
    assert payload["data"]["publication"]["sections"][0]["title"] == "核心机制"
    assert payload["data"]["publication"]["citations"][0]["citation_id"] == "M001"
    assert payload["data"]["publication"]["citations"][0]["available_at_ms"] == 1_774_199_000_000
    assert isinstance(repository.calls[0], date)


def test_macro_research_reads_explicit_historical_session() -> None:
    repository = FakeMacroResearchRepository(state="historical")
    app = _app(repository)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/research?session_date=2026-07-22",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["state"] == "historical"
    assert repository.calls[0] == date(2026, 7, 22)


@pytest.mark.parametrize("state", ("generating", "failed"))
def test_macro_research_exposes_persisted_run_state(state: str) -> None:
    repository = FakeMacroResearchRepository(state=state)
    app = _app(repository)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/research",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "state": state,
        "requested_session_date": response.json()["data"]["current_session_date"],
        "current_session_date": response.json()["data"]["current_session_date"],
        "publication": None,
        "run": {
            "session_date": response.json()["data"]["current_session_date"],
            "status": "running" if state == "generating" else "failed",
            "attempt_count": 1,
            "max_attempts": 3,
            "last_error": None if state == "generating" else "provider_timeout",
            "updated_at_ms": 1_774_201_900_000,
        },
    }


def test_macro_research_missing_is_explicit_and_never_builds_inline() -> None:
    repository = FakeMacroResearchRepository(state="missing")
    app = _app(repository)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/research",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["data"]["state"] == "missing"
    assert repository.calls


def test_macro_research_rejects_unknown_and_query_token_parameters() -> None:
    app = _app(FakeMacroResearchRepository(state="current"))

    with TestClient(app) as client:
        unauthenticated = client.get("/api/macro/research?token=secret")
        query_token = client.get(
            "/api/macro/research?token=secret",
            headers={"Authorization": "Bearer secret"},
        )
        unsupported = client.get(
            "/api/macro/research?window=20d",
            headers={"Authorization": "Bearer secret"},
        )

    assert unauthenticated.status_code == 401
    assert query_token.json() == {
        "ok": False,
        "error": "unsupported_query_param",
        "field": "token",
    }
    assert unsupported.json() == {
        "ok": False,
        "error": "unsupported_query_param",
        "field": "window",
    }


@pytest.mark.parametrize(
    "path",
    (
        "/api/macro/overview",
        "/api/macro/cross-asset",
        "/api/macro/rates-inflation",
        "/api/macro/growth-labor",
        "/api/macro/liquidity-funding",
        "/api/macro/credit",
        "/api/macro/series?concept_keys=rates:dgs10",
        "/api/macro/daily-judgment",
    ),
)
def test_retired_macro_endpoints_are_ordinary_not_found(path: str) -> None:
    app = _app(FakeMacroResearchRepository(state="current"))

    with TestClient(app) as client:
        response = client.get(path, headers={"Authorization": "Bearer secret"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_macro_research_contract_rejects_unknown_fields() -> None:
    publication = _publication(date(2026, 7, 23))
    api_schemas.MacroResearchPublicationData.model_validate(publication)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        api_schemas.MacroResearchPublicationData.model_validate({**publication, "risk_lanes": []})


def test_macro_live_dashboard_reads_persisted_facts_only() -> None:
    macro_intel = FakeMacroIntelRepository(
        rows=[
            {
                "observation_id": "rates:dgs10:2026-07-23",
                "concept_key": "rates:dgs10",
                "source_name": "fred",
                "series_key": "fred:DGS10",
                "source_priority": 100,
                "observed_at": date(2026, 7, 23),
                "value_numeric": 4.22,
                "unit": "percent",
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": "2026-07-23T16:00:00-04:00",
                "raw_payload_json": {},
                "ingested_at_ms": 1_774_199_500_000,
            },
            {
                "observation_id": "macro:new_fact:2026-07-23",
                "concept_key": "macro:new_fact",
                "source_name": "fixture",
                "series_key": "fixture:new",
                "source_priority": 1,
                "observed_at": date(2026, 7, 23),
                "value_numeric": 7.0,
                "unit": "index",
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": "2026-07-23",
                "raw_payload_json": {},
                "ingested_at_ms": 1_774_199_600_000,
            },
        ]
    )
    app = _app(FakeMacroResearchRepository(state="current"), macro_intel=macro_intel)

    with TestClient(app) as client:
        response = client.get(
            "/api/macro/evidence/dashboard?window=90d",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "macro_live_evidence_v1"
    assert data["view_id"] == "dashboard"
    assert [view["view_id"] for view in data["views"]] == [
        "overview",
        "rates-inflation",
        "growth-labor",
        "liquidity-funding",
        "credit",
        "cross-asset",
    ]
    assert data["unclassified"][0]["concept_key"] == "macro:new_fact"
    assert data["research"]["title"] == "宏观研究：增长与实际利率的拉锯"
    assert macro_intel.live_calls
    assert macro_intel.uncatalogued_calls == [50]


@pytest.mark.parametrize(
    "path",
    (
        "/api/macro/evidence/unknown",
        "/api/macro/evidence/credit?window=20d",
        "/api/macro/evidence/credit?token=secret",
        "/api/macro/evidence/credit?extra=1",
    ),
)
def test_macro_live_evidence_rejects_unknown_views_and_parameters(path: str) -> None:
    app = _app(
        FakeMacroResearchRepository(state="current"),
        macro_intel=FakeMacroIntelRepository(rows=[]),
    )

    with TestClient(app) as client:
        response = client.get(path, headers={"Authorization": "Bearer secret"})

    assert response.status_code in {400, 422}
    assert response.json()["ok"] is False


def test_macro_live_contract_rejects_retired_semantic_fields() -> None:
    metric = {
        "concept_key": "rates:dgs10",
        "page_id": "rates-inflation",
        "section_id": "nominal-curve",
        "section_label": "名义收益率曲线",
        "display_label": "美国 10 年期国债收益率",
        "display_order": 1,
        "summary": True,
        "kind": "material",
        "availability": "available",
        "value_numeric": 4.22,
        "unit": "percent",
        "frequency": "daily",
        "observed_at": "2026-07-23",
        "source_timestamp": "2026-07-23",
        "received_at_ms": 1_774_199_500_000,
        "source_name": "fred",
        "series_key": "fred:DGS10",
        "source_priority": 100,
        "data_quality": "ok",
        "source_url": None,
        "history": [],
        "calculation": None,
    }
    api_schemas.MacroLiveMetricData.model_validate(metric)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        api_schemas.MacroLiveMetricData.model_validate({**metric, "direction": "headwind"})


class FakeMacroResearchRepository:
    def __init__(self, *, state: str) -> None:
        self.state = state
        self.calls: list[date] = []

    def research_state(self, session_date: date | None) -> dict[str, Any] | None:
        assert session_date is not None
        self.calls.append(session_date)
        target = session_date
        if self.state in {"current", "historical"}:
            publication = _publication(target)
            return {
                **_run_row(target, status="published"),
                "artifact_json": _artifact(publication),
                "report_markdown": "# internal derived export",
                "audit_json": publication["audit"],
                "published_at_ms": 1_774_202_000_000,
            }
        if self.state in {"generating", "failed"}:
            return _run_row(
                target,
                status="running" if self.state == "generating" else "failed",
                last_error=None if self.state == "generating" else "provider_timeout",
            )
        return None


class FakeMacroIntelRepository:
    def __init__(self, *, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.live_calls: list[dict[str, Any]] = []
        self.uncatalogued_calls: list[int] = []

    def live_observations(
        self,
        *,
        concept_keys: tuple[str, ...],
        start_date: date,
        max_rows_per_series: int,
    ) -> list[dict[str, Any]]:
        self.live_calls.append(
            {
                "concept_keys": concept_keys,
                "start_date": start_date,
                "max_rows_per_series": max_rows_per_series,
            }
        )
        selected = set(concept_keys)
        return [row for row in self.rows if row["concept_key"] in selected]

    def latest_uncatalogued_observations(
        self,
        *,
        catalog_concept_keys: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, Any]]:
        self.uncatalogued_calls.append(limit)
        selected = set(catalog_concept_keys)
        return [row for row in self.rows if row["concept_key"] not in selected][:limit]


def _publication(session_date: date) -> dict[str, Any]:
    return {
        "schema_version": "macro_research_artifact_v2",
        "session_date": session_date,
        "market_cutoff_ms": 1_774_200_000_000,
        "title": "宏观研究：增长与实际利率的拉锯",
        "executive_summary": "增长放缓与实际利率高位并存，风险资产缺少单边确认。",
        "sections": [
            {
                "section_id": "mechanism",
                "title": "核心机制",
                "body_markdown": "实际利率维持高位，信用尚未确认系统性收紧。",
                "citation_ids": ["M001"],
            }
        ],
        "evidence_gaps": [
            {
                "gap_id": "term-premium-history",
                "summary": "期限溢价历史窗口不足",
                "details": "无法可靠区分供给冲击与增长预期。",
                "citation_ids": [],
            }
        ],
        "citations": [
            {
                "citation_id": "M001",
                "source_type": "macro_observation",
                "source_ref": "macro:rates:dgs10:2026-07-23",
                "source_label": "U.S. Treasury 10Y",
                "observed_at": "2026-07-23",
                "published_at_ms": None,
                "available_at_ms": 1_774_199_000_000,
                "source_url": "https://fred.stlouisfed.org/series/DGS10",
                "lineage": {"concept_key": "rates:dgs10"},
            }
        ],
        "reviewer_notes": ["反证已覆盖，但期限溢价仍应标为缺口。"],
        "audit": {
            "model": "provider-model",
            "planning_used": True,
            "subagents_used": ["skeptic"],
        },
        "published_at_ms": 1_774_202_000_000,
    }


def _artifact(publication: dict[str, Any]) -> dict[str, Any]:
    citations = [
        {
            **{key: value for key, value in citation.items() if key != "source_url"},
            "url": citation["source_url"],
        }
        for citation in publication["citations"]
    ]
    return {
        key: value
        for key, value in publication.items()
        if key not in {"audit", "evidence_gaps", "published_at_ms", "citations"}
    } | {
        "gaps": publication["evidence_gaps"],
        "citations": citations,
    }


def _run_row(
    session_date: date,
    *,
    status: str,
    last_error: str | None = None,
) -> dict[str, Any]:
    return {
        "session_date": session_date,
        "market_cutoff_ms": 1_774_200_000_000,
        "run_status": status,
        "sealed_at_ms": 1_774_199_000_000,
        "attempt_count": 1,
        "max_attempts": 3,
        "due_at_ms": 1_774_199_100_000,
        "leased_until_ms": None,
        "last_error_code": last_error,
        "last_error_message": None,
        "created_at_ms": 1_774_199_000_000,
        "updated_at_ms": 1_774_201_900_000,
        "artifact_json": None,
        "report_markdown": None,
        "audit_json": None,
        "model_name": None,
        "prompt_version": None,
        "workflow_version": None,
        "artifact_hash": None,
        "published_at_ms": None,
    }


class FakeRepositoryContext:
    def __init__(
        self,
        macro_research: FakeMacroResearchRepository,
        macro_intel: FakeMacroIntelRepository,
    ) -> None:
        self.macro_research = macro_research
        self.macro_intel = macro_intel

    def __enter__(self) -> FakeRepositoryContext:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakeRuntime:
    def __init__(
        self,
        macro_research: FakeMacroResearchRepository,
        macro_intel: FakeMacroIntelRepository,
    ) -> None:
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.macro_research = macro_research
        self.macro_intel = macro_intel

    def repositories(self) -> FakeRepositoryContext:
        return FakeRepositoryContext(self.macro_research, self.macro_intel)


def _app(
    macro_research: FakeMacroResearchRepository,
    *,
    macro_intel: FakeMacroIntelRepository | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: {"ok": True}))
    app.state.service = FakeRuntime(
        macro_research,
        macro_intel or FakeMacroIntelRepository(rows=[]),
    )
    return app
