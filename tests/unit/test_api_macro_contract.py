from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

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
)
from parallax.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps


def test_macro_api_returns_latest_snapshot_without_postgres() -> None:
    data_gaps = build_macro_data_gaps(["insufficient_history:20d", "missing:asset:spx"])
    repo = FakeMacroIntelRepository(
        snapshot={
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


def test_macro_module_api_reads_precomputed_payload_without_observation_query() -> None:
    module_view = _module_view("rates/yield-curve")
    repo = FakeMacroIntelRepository(
        snapshot={"module_views_json": {"rates/yield-curve": module_view}},
    )
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/rates/yield-curve", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": module_view}
    assert repo.calls == [("module_view:rates/yield-curve", "macro_regime_v4")]
    assert repo.observations_for_concepts_call is None


def test_macro_module_api_fails_closed_when_persisted_payload_is_incomplete() -> None:
    module_view = _module_view("rates/yield-curve")
    del module_view["snapshot"]["status_label"]
    app = _app(
        FakeMacroIntelRepository(
            snapshot={"module_views_json": {"rates/yield-curve": module_view}},
        )
    )

    with TestClient(app) as client, pytest.raises(ValidationError, match="status_label"):
        client.get("/api/macro/modules/rates/yield-curve", headers={"Authorization": "Bearer secret"})


@pytest.mark.parametrize(
    ("section", "field_name"),
    (
        ("primary_chart", "series"),
        ("primary_chart", "min_points"),
        ("table", "rows"),
        ("data_health", "module_gaps"),
    ),
)
def test_macro_module_api_fails_closed_on_missing_chart_table_or_health_contract(
    section: str,
    field_name: str,
) -> None:
    module_view = _module_view("rates/yield-curve")
    _remove_module_view_field(module_view, section=section, field_name=field_name)
    app = _app(
        FakeMacroIntelRepository(
            snapshot={"module_views_json": {"rates/yield-curve": module_view}},
        )
    )

    with TestClient(app) as client, pytest.raises(ValidationError, match=field_name):
        client.get("/api/macro/modules/rates/yield-curve", headers={"Authorization": "Bearer secret"})


def test_macro_module_api_surfaces_missing_projection_without_inline_build() -> None:
    repo = FakeMacroIntelRepository(snapshot=None)
    app = _app(repo)

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/overview", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 503
    assert response.json() == {"ok": False, "error": "macro_module_projection_missing"}
    assert repo.calls == [("module_view:overview", "macro_regime_v4")]
    assert repo.observations_for_concepts_call is None


def test_macro_module_api_rejects_unsupported_module() -> None:
    app = _app(FakeMacroIntelRepository(snapshot=None))

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/not-real", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_macro_module", "field": "module_id"}


def test_macro_module_api_serves_precomputed_assets_payload_without_daily_brief_repository() -> None:
    module_view = _module_view("assets")
    app = _app(FakeMacroIntelRepository(snapshot={"module_views_json": {"assets": module_view}}))

    with TestClient(app) as client:
        response = client.get("/api/macro/modules/assets", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    assert response.json()["data"]["snapshot"]["module_id"] == "assets"
    assert response.json()["data"]["snapshot"]["route_path"] == "/macro/assets"


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
    ) -> None:
        self.snapshot = snapshot
        self.observations = observations or []
        self.publication_state = publication_state
        self.calls: list[tuple[str, str | None]] = []
        self.observations_for_concepts_call: dict[str, object] | None = None

    def latest_snapshot(self, *, projection_version: str | None = None):
        self.calls.append(("latest_snapshot", projection_version))
        return self.snapshot

    def module_view(self, *, module_id: str, projection_version: str):
        self.calls.append((f"module_view:{module_id}", projection_version))
        if self.snapshot is None:
            return None
        module_views = self.snapshot.get("module_views_json")
        if not isinstance(module_views, dict):
            return None
        return module_views.get(module_id)

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

    def macro_series_publication_state(self, projection_version: str):
        self.calls.append(("macro_series_publication_state", projection_version))
        return self.publication_state


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
    app.include_router(create_api_router(lambda _: {"ok": True}))
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
        "data_quality": "ok",
        "ingested_at_ms": 1_779_000_000_000,
    }


def _module_view(module_id: str) -> dict[str, object]:
    route_path = "/macro" if module_id == "overview" else f"/macro/{module_id}"
    payload: dict[str, object] = {
        "snapshot": {
            "module_id": module_id,
            "route_path": route_path,
            "title": module_id,
            "subtitle": "persisted macro module",
            "question": "what changed",
            "section": "rates",
            "projection_version": "macro_module_view_v3",
            "status": "ready",
            "status_label": "就绪",
            "asof_date": "2026-05-20",
            "asof_label": "截至 2026-05-20",
            "computed_at_ms": 1_779_000_000_000,
            "computed_at_label": "计算于 2026-05-20T00:00+00:00",
            "source_projection_version": "macro_regime_v4",
        },
        "tiles": [],
        "primary_chart": {
            "id": "current",
            "kind": "time_series",
            "title": "Current",
            "subtitle": "persisted observations",
            "status": "ready",
            "status_label": "就绪",
            "min_points": 2,
            "missing_concept_keys": [],
            "series": [
                {
                    "concept_key": "rates:dgs10",
                    "label": "10Y",
                    "unit_label": "%",
                    "points": [{"observed_at": "2026-05-20", "value": 4.7}],
                }
            ],
        },
        "tables": [
            {
                "id": "current_values",
                "title": "Current values",
                "status": "ready",
                "missing_concept_keys": [],
                "columns": [{"key": "label", "label": "指标"}],
                "rows": [],
            },
            {
                "id": "availability_proxy_notes",
                "title": "数据可用性 / 代理说明",
                "status": "ready",
                "rows": [],
            },
        ],
        "module_read": {},
        "module_evidence": {
            "confirmations": [],
            "contradictions": [],
            "watch_triggers": [],
            "invalidations": [],
        },
        "transmission": [],
        "data_health": {
            "summary_status": "ready",
            "summary_label": "就绪",
            "module_gaps": [],
            "chart_gaps": [],
            "global_gaps": [],
        },
        "provenance": {
            "projection_version": "macro_regime_v4",
            "currentness": {
                "facts_max_observed_at": "2026-05-20",
                "projection_lag_days": 0,
                "projection_behind_facts": False,
            },
            "rows": [],
        },
        "related_routes": [],
    }
    if module_id == "assets":
        payload["daily_brief"] = None
    return payload


def _remove_module_view_field(
    module_view: dict[str, object],
    *,
    section: str,
    field_name: str,
) -> None:
    if section == "table":
        tables = module_view["tables"]
        assert isinstance(tables, list) and isinstance(tables[0], dict)
        del tables[0][field_name]
        return
    payload = module_view[section]
    assert isinstance(payload, dict)
    del payload[field_name]


def _macro_snapshot() -> dict[str, object]:
    return {
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
