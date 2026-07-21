from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

from parallax.app.surfaces.api import routes_search
from parallax.app.surfaces.api.schemas import TokenCaseData, TokenRadarData


def test_token_case_route_passes_token_radar_repository_to_read_model(monkeypatch) -> None:
    runtime = _runtime()
    factory_kwargs: list[dict[str, Any]] = []

    def service_factory(**kwargs: Any) -> Any:
        factory_kwargs.append(kwargs)
        return SimpleNamespace(dossier=lambda **_call: _token_case_payload())

    monkeypatch.setattr(routes_search, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(routes_search, "_now_ms", lambda: 1_778_562_000_000)
    monkeypatch.setattr(routes_search, "TokenCaseService", service_factory)

    response = routes_search.token_case(
        SimpleNamespace(query_params={}),
        target_type="Asset",
        target_id="asset-1",
        window="1h",
        scope="all",
        posts_limit=5,
    )

    assert _body(response)["data"]["narrative_admission"] == _admission()
    assert factory_kwargs[0]["token_radar"] is runtime.repo.token_radar


def test_public_narrative_schema_remains_admission_only() -> None:
    case = TokenCaseData.model_validate(_token_case_payload())
    radar = TokenRadarData.model_validate(
        {
            "window": "1h",
            "scope": "all",
            "venue": "all",
            "targets": [{"narrative_admission": _admission(), "target": {"target_id": "asset-1"}}],
            "attention": [],
        }
    )

    assert case.narrative_admission.status == "admitted"
    assert case.narrative_admission.coverage.independent_authors == 4
    assert radar.targets[0].narrative_admission is not None
    assert radar.targets[0].narrative_admission.currentness.display_status == "current"
    serialized = radar.model_dump()
    assert "narrative_delta" not in serialized["targets"][0]
    assert "narrative_clusters" not in serialized["targets"][0]


def _runtime() -> SimpleNamespace:
    repo = SimpleNamespace(
        token_profiles=object(),
        token_radar=object(),
        token_targets=object(),
    )
    return SimpleNamespace(repo=repo, repositories=lambda: nullcontext(repo))


def _token_case_payload() -> dict[str, Any]:
    return {
        "target": {"target_type": "Asset", "target_id": "asset-1"},
        "profile": {"status": "pending"},
        "timeline": {"query": {"scope": "all"}},
        "posts": {"query": {"scope": "all"}, "items": []},
        "narrative_admission": _admission(),
        "market_live": {"status": "missing"},
    }


def _admission() -> dict[str, Any]:
    return {
        "status": "admitted",
        "reason": "hot_rank",
        "is_current": True,
        "computed_at_ms": 1_778_562_000_000,
        "currentness": {"display_status": "current", "reason": "hot_rank"},
        "coverage": {"source_mentions": 10, "independent_authors": 4},
        "data_gaps": [],
    }


def _body(response: Any) -> dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))
