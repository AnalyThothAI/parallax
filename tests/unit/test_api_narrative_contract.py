from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

from parallax.app.surfaces.api import routes_radar, routes_search
from parallax.app.surfaces.api.schemas import TokenCaseData, TokenRadarData

NOW_MS = 1_778_562_000_000


def test_token_case_route_hydrates_admission_coverage(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(routes_search, "_authenticated_runtime", lambda _request: _runtime())
    monkeypatch.setattr(routes_search, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(routes_search, "TokenCaseService", _token_case_service_factory)
    monkeypatch.setattr(routes_search, "NarrativeReadModel", lambda **kwargs: _NarrativeReadModel(calls, **kwargs))

    response = routes_search.token_case(
        _request(),
        target_type="Asset",
        target_id="asset:solana:token:hansa",
        window="24h",
        scope="all",
        posts_limit=5,
    )

    data = _body(response)["data"]
    assert "agent_brief" not in data
    assert data["narrative_admission"] == _admission()
    assert "narrative_delta" not in data
    assert "narrative_clusters" not in data
    assert calls == [{"method": "case", "window": "24h", "scope": "all"}]


def test_target_posts_route_returns_posts_without_semantic_hydration(monkeypatch) -> None:
    monkeypatch.setattr(routes_search, "_authenticated_runtime", lambda _request: _runtime())
    monkeypatch.setattr(routes_search, "TokenTargetPostsService", _target_posts_service_factory)
    monkeypatch.setattr(
        routes_search,
        "NarrativeReadModel",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("target posts must not hydrate narratives")),
    )

    response = routes_search.target_posts(
        _request(),
        target_type="Asset",
        target_id="asset:solana:token:hansa",
        window="5m",
        scope="all",
        limit=2,
    )

    item = _body(response)["data"]["items"][0]
    assert item["event_id"] == "event-1"
    assert "semantic" not in item


def test_search_inspect_hydrates_only_token_result(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(routes_search, "_authenticated_runtime", lambda _request: _runtime())
    monkeypatch.setattr(routes_search, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(routes_search, "SearchInspectService", _search_inspect_service_factory)
    monkeypatch.setattr(routes_search, "NarrativeReadModel", lambda **kwargs: _NarrativeReadModel(calls, **kwargs))

    token_data = _body(routes_search.search_inspect(_request(), q="$HANSA", window="24h", scope="all"))["data"]
    topic_data = _body(routes_search.search_inspect(_request(), q="narrative topic", window="24h", scope="all"))["data"]

    assert token_data["token_result"]["narrative_admission"] == _admission()
    assert topic_data["topic_result"]["agent_brief"]["schema_version"] == "search_agent_brief_v1"
    assert calls == [{"method": "case", "window": "24h", "scope": "all"}]


def test_token_radar_route_hydrates_admission_coverage(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(routes_radar, "_authenticated_runtime", lambda _request: _runtime())
    monkeypatch.setattr(routes_radar, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(routes_radar, "AssetFlowService", _asset_flow_service_factory)
    monkeypatch.setattr(routes_radar, "NarrativeReadModel", lambda **kwargs: _NarrativeReadModel(calls, **kwargs))

    data = _body(routes_radar.token_radar(_request(), window="1h", scope="all", limit=5))["data"]

    assert data["targets"][0]["narrative_admission"] == _admission()
    assert data["attention"][0]["narrative_admission"] == _admission()
    assert calls == [{"method": "radar", "window": "1h", "scope": "all"}]


def test_public_narrative_schema_is_admission_only() -> None:
    case = TokenCaseData.model_validate(
        {
            "target": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"},
            "timeline": {},
            "posts": {},
            "market_live": {},
            "narrative_admission": _admission(),
        }
    )
    radar = TokenRadarData.model_validate(
        {
            "window": "5m",
            "scope": "all",
            "venue": "all",
            "targets": [{"narrative_admission": _unsupported_admission()}],
            "attention": [],
        }
    )

    assert case.narrative_admission.currentness.display_status == "current"
    assert case.narrative_admission.coverage.source_mentions == 10
    assert radar.targets[0].narrative_admission is not None
    assert radar.targets[0].narrative_admission.currentness.display_status == "unsupported_window"


class _NarrativeReadModel:
    def __init__(self, calls: list[dict[str, Any]], **_kwargs: Any) -> None:
        self.calls = calls

    def hydrate_token_case(self, data: dict[str, Any], *, window: str, scope: str) -> dict[str, Any]:
        assert "agent_brief" not in data
        self.calls.append({"method": "case", "window": window, "scope": scope})
        return {**data, "narrative_admission": _admission()}

    def hydrate_token_radar(self, data: dict[str, Any], *, window: str, scope: str) -> dict[str, Any]:
        self.calls.append({"method": "radar", "window": window, "scope": scope})
        return {
            **data,
            "targets": [{**item, "narrative_admission": _admission()} for item in data["targets"]],
            "attention": [{**item, "narrative_admission": _admission()} for item in data["attention"]],
        }


def _token_case_service_factory(**_kwargs: Any) -> Any:
    return SimpleNamespace(dossier=lambda **_call: _token_case_payload())


def _target_posts_service_factory(**_kwargs: Any) -> Any:
    return SimpleNamespace(target_posts=lambda **_call: _posts_payload())


def _search_inspect_service_factory(**_kwargs: Any) -> Any:
    def inspect(q: str, **_call: Any) -> dict[str, Any]:
        if q.startswith("$"):
            return {
                "query": {"result_kind": "token_result"},
                "resolver": {},
                "token_result": _token_case_payload(),
                "topic_result": None,
                "ambiguous_result": None,
            }
        return {
            "query": {"result_kind": "topic_result"},
            "resolver": {},
            "token_result": None,
            "topic_result": {"agent_brief": {"schema_version": "search_agent_brief_v1"}},
            "ambiguous_result": None,
        }

    return SimpleNamespace(inspect=inspect)


def _asset_flow_service_factory(**_kwargs: Any) -> Any:
    row = {"target": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"}}
    return SimpleNamespace(asset_flow=lambda **_call: {"targets": [row], "attention": [row], "projection": {}})


def _runtime() -> SimpleNamespace:
    repos = SimpleNamespace(
        conn=object(),
        token_profiles=object(),
        token_radar=object(),
        token_targets=object(),
        narratives=object(),
        cex_detail_snapshots=object(),
    )
    return SimpleNamespace(repositories=lambda: nullcontext(repos), workers={})


def _request() -> SimpleNamespace:
    return SimpleNamespace(query_params={})


def _token_case_payload() -> dict[str, Any]:
    return {
        "target": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"},
        "profile": {"status": "pending"},
        "timeline": {"query": {"scope": "all"}},
        "posts": _posts_payload(),
        "market_live": {"status": "missing"},
        "agent_brief": {"legacy": True},
    }


def _posts_payload() -> dict[str, Any]:
    return {
        "query": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"},
        "items": [{"event_id": "event-1", "target_type": "Asset", "target_id": "asset:solana:token:hansa"}],
    }


def _admission() -> dict[str, Any]:
    return {
        "status": "admitted",
        "is_current": True,
        "reason": "admitted",
        "computed_at_ms": NOW_MS,
        "currentness": {"display_status": "current", "reason": "admitted"},
        "coverage": {"source_mentions": 10, "independent_authors": 4},
        "data_gaps": [],
    }


def _unsupported_admission() -> dict[str, Any]:
    return {
        "status": "missing",
        "is_current": False,
        "reason": "narrative_not_supported_for_window",
        "currentness": {
            "display_status": "unsupported_window",
            "reason": "narrative_not_supported_for_window",
        },
        "coverage": {"source_mentions": 0, "independent_authors": 0},
        "data_gaps": [{"reason": "narrative_not_supported_for_window"}],
    }


def _body(response: Any) -> dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))
