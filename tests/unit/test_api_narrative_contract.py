from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.surfaces.api import routes_radar, routes_search, routes_status
from gmgn_twitter_intel.app.surfaces.api.schemas import NarrativeBacklogHealthData

NOW_MS = 1_778_562_000_000


def test_token_case_route_hydrates_discussion_digest_and_removes_agent_brief(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    runtime = _runtime()
    monkeypatch.setattr(routes_search, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(routes_search, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(routes_search, "TokenCaseService", _token_case_service_factory)
    monkeypatch.setattr(
        routes_search,
        "NarrativeReadModel",
        lambda **kwargs: _NarrativeReadModel(calls=calls, **kwargs),
        raising=False,
    )

    response = routes_search.token_case(
        _request(),
        target_type="Asset",
        target_id="asset:solana:token:hansa",
        window="24h",
        scope="all",
        posts_limit=5,
    )

    body = _body(response)
    assert body["ok"] is True
    data = body["data"]
    assert "agent_brief" not in data
    assert data["discussion_digest"]["status"] == "ready"
    assert data["narrative_clusters"] == [{"cluster_key": "main"}]
    assert data["pulse_overlay"]["status"] == "absent"
    assert calls == [{"method": "case", "window": "24h", "scope": "all", "now_ms": NOW_MS}]


def test_target_posts_route_hydrates_per_post_semantics(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    runtime = _runtime()
    monkeypatch.setattr(routes_search, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(routes_search, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(routes_search, "TokenTargetPostsService", _target_posts_service_factory)
    monkeypatch.setattr(
        routes_search,
        "NarrativeReadModel",
        lambda **kwargs: _NarrativeReadModel(calls=calls, **kwargs),
        raising=False,
    )

    response = routes_search.target_posts(
        _request(),
        target_type="Asset",
        target_id="asset:solana:token:hansa",
        window="5m",
        scope="all",
        limit=2,
    )

    body = _body(response)
    assert body["ok"] is True
    item = body["data"]["items"][0]
    assert item["semantic"]["status"] == "labeled"
    assert item["semantic"]["trade_stance"] == "bullish"
    assert calls == [{"method": "posts", "window": "5m", "scope": "all", "now_ms": NOW_MS}]


def test_search_inspect_hydrates_token_result_but_preserves_topic_brief(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    runtime = _runtime()
    monkeypatch.setattr(routes_search, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(routes_search, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(routes_search, "SearchInspectService", _search_inspect_service_factory)
    monkeypatch.setattr(
        routes_search,
        "NarrativeReadModel",
        lambda **kwargs: _NarrativeReadModel(calls=calls, **kwargs),
        raising=False,
    )

    token_response = routes_search.search_inspect(_request(), q="$HANSA", window="24h", scope="all")
    topic_response = routes_search.search_inspect(_request(), q="narrative topic", window="24h", scope="all")

    token_data = _body(token_response)["data"]
    topic_data = _body(topic_response)["data"]
    assert "agent_brief" not in token_data["token_result"]
    assert token_data["token_result"]["discussion_digest"]["status"] == "ready"
    assert topic_data["topic_result"]["agent_brief"]["schema_version"] == "search_agent_brief_v1"
    assert calls == [{"method": "case", "window": "24h", "scope": "all", "now_ms": NOW_MS}]


def test_token_radar_route_hydrates_targets_and_attention(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    runtime = _runtime()
    monkeypatch.setattr(routes_radar, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(routes_radar, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(routes_radar, "AssetFlowService", _asset_flow_service_factory)
    monkeypatch.setattr(
        routes_radar,
        "NarrativeReadModel",
        lambda **kwargs: _NarrativeReadModel(calls=calls, **kwargs),
        raising=False,
    )

    response = routes_radar.token_radar(_request(), window="1h", scope="all", limit=5)

    data = _body(response)["data"]
    assert data["targets"][0]["discussion_digest"]["status"] == "ready"
    assert data["attention"][0]["discussion_digest"]["status"] == "ready"
    assert calls == [{"method": "radar", "window": "1h", "scope": "all", "now_ms": NOW_MS}]


def test_narrative_health_route_uses_domain_owned_query(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    runtime = _runtime()
    monkeypatch.setattr(routes_status, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(routes_status, "_now_ms", lambda: NOW_MS)
    monkeypatch.setattr(
        routes_status,
        "NarrativeBacklogHealthQuery",
        lambda conn: _NarrativeBacklogHealthQuery(conn=conn, calls=calls),
        raising=False,
    )

    response = routes_status.narrative_health(_request(), since_hours=4)

    body = _body(response)
    assert body["ok"] is True
    assert body["data"]["semantic_backlog"]["total_pending"] == 5
    assert body["data"]["semantic_backlog"]["missing_semantic_rows"] == 4
    assert body["data"]["semantic_backlog"]["current_source_rows"] == 12
    assert body["data"]["pending_digest_count"] == 2
    assert calls == [{"conn": runtime.conn, "now_ms": NOW_MS, "since_hours": 4}]


def test_narrative_health_schema_exposes_source_set_backlog_fields() -> None:
    data = NarrativeBacklogHealthData.model_validate(
        {
            "semantic_backlog": {
                "total_pending": 9,
                "current_source_rows": 12,
                "semantic_rows_for_current_sources": 8,
                "missing_semantic_rows": 4,
                "admissions_with_missing_semantics": 2,
                "pending_existing_rows": 5,
                "queued": 3,
                "retryable": 2,
                "stale": 0,
                "unavailable": 1,
                "suppressed_current_digest_count": 1,
                "stale_fingerprint_current_digest_count": 3,
            },
            "epoch": {
                "epoch_policy_version": "token-narrative-epoch-v1",
                "unsupported_window_admissions": 2,
                "last_ready_digest_count": 5,
                "updating_snapshot_count": 3,
                "material_delta_due_count": 4,
                "no_material_delta_deferred_count": 6,
                "last_ready_p50_age_ms": 120_000,
                "last_ready_p95_age_ms": 600_000,
                "delta_source_rows": 9,
                "delta_independent_authors": 3,
                "digest_refresh_due_by_window": {"1h": 2, "24h": 2},
                "digest_refresh_deferred_by_epoch_policy": {"no_material_delta": 6},
            },
        }
    )

    assert data.semantic_backlog.total_pending == 9
    assert data.semantic_backlog.missing_semantic_rows == 4
    assert data.semantic_backlog.current_source_rows == 12
    assert data.semantic_backlog.semantic_rows_for_current_sources == 8
    assert data.semantic_backlog.admissions_with_missing_semantics == 2
    assert data.semantic_backlog.pending_existing_rows == 5
    assert data.semantic_backlog.suppressed_current_digest_count == 1
    assert data.semantic_backlog.stale_fingerprint_current_digest_count == 3
    assert data.epoch.epoch_policy_version == "token-narrative-epoch-v1"
    assert data.epoch.unsupported_window_admissions == 2
    assert data.epoch.last_ready_digest_count == 5
    assert data.epoch.updating_snapshot_count == 3
    assert data.epoch.material_delta_due_count == 4
    assert data.epoch.no_material_delta_deferred_count == 6
    assert data.epoch.last_ready_p50_age_ms == 120_000
    assert data.epoch.last_ready_p95_age_ms == 600_000
    assert data.epoch.delta_source_rows == 9
    assert data.epoch.delta_independent_authors == 3
    assert data.epoch.digest_refresh_due_by_window == {"1h": 2, "24h": 2}
    assert data.epoch.digest_refresh_deferred_by_epoch_policy == {"no_material_delta": 6}


class _NarrativeReadModel:
    def __init__(self, *, calls: list[dict[str, Any]], **_kwargs: Any) -> None:
        self.calls = calls

    def hydrate_token_case(self, data: dict[str, Any], *, window: str, scope: str, now_ms: int) -> dict[str, Any]:
        assert "agent_brief" not in data
        self.calls.append({"method": "case", "window": window, "scope": scope, "now_ms": now_ms})
        return {
            **data,
            "discussion_digest": _digest(),
            "narrative_clusters": [{"cluster_key": "main"}],
            "pulse_overlay": {"status": "absent"},
        }

    def hydrate_target_posts(self, data: dict[str, Any], *, window: str, scope: str, now_ms: int) -> dict[str, Any]:
        self.calls.append({"method": "posts", "window": window, "scope": scope, "now_ms": now_ms})
        return {**data, "items": [{**item, "semantic": _semantic()} for item in data["items"]]}

    def hydrate_token_radar(self, data: dict[str, Any], *, window: str, scope: str, now_ms: int) -> dict[str, Any]:
        self.calls.append({"method": "radar", "window": window, "scope": scope, "now_ms": now_ms})
        return {
            **data,
            "targets": [{**item, "discussion_digest": _digest()} for item in data["targets"]],
            "attention": [{**item, "discussion_digest": _digest()} for item in data["attention"]],
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
                "resolver": {"selected_target": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"}},
                "token_result": _token_case_payload(),
                "topic_result": None,
                "ambiguous_result": None,
            }
        return {
            "query": {"result_kind": "topic_result"},
            "resolver": {"selected_target": None},
            "token_result": None,
            "topic_result": {"agent_brief": {"schema_version": "search_agent_brief_v1"}},
            "ambiguous_result": None,
        }

    return SimpleNamespace(inspect=inspect)


def _asset_flow_service_factory(**_kwargs: Any) -> Any:
    return SimpleNamespace(
        asset_flow=lambda **_call: {
            "targets": [{"target": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"}}],
            "attention": [{"target": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"}}],
            "projection": {},
        }
    )


def _runtime() -> SimpleNamespace:
    conn = object()
    repos = SimpleNamespace(
        conn=conn,
        token_profiles=object(),
        token_radar=object(),
        token_targets=object(),
        narratives=object(),
        pulse_read=object(),
    )
    return SimpleNamespace(
        conn=conn,
        repositories=lambda: nullcontext(repos),
        providers=SimpleNamespace(asset_market=SimpleNamespace(message_cex_market=None, dex_candle_market=None)),
        workers={},
    )


class _NarrativeBacklogHealthQuery:
    def __init__(self, *, conn: Any, calls: list[dict[str, Any]]) -> None:
        self.conn = conn
        self.calls = calls

    def health(self, *, now_ms: int, since_hours: int) -> dict[str, Any]:
        self.calls.append({"conn": self.conn, "now_ms": now_ms, "since_hours": since_hours})
        return {
            "schema_version": "narrative_intel_v1",
            "now_ms": now_ms,
            "since_hours": since_hours,
            "semantic_backlog": {
                "total_pending": 5,
                "current_source_rows": 12,
                "semantic_rows_for_current_sources": 8,
                "missing_semantic_rows": 4,
                "admissions_with_missing_semantics": 2,
                "pending_existing_rows": 5,
                "queued": 3,
                "retryable": 2,
                "stale": 0,
                "unavailable": 1,
                "suppressed_current_digest_count": 1,
                "stale_fingerprint_current_digest_count": 3,
                "oldest_due_age_ms": 4_000,
            },
            "recent_runs": {},
            "pending_digest_count": 2,
        }


def _request() -> SimpleNamespace:
    return SimpleNamespace(query_params={})


def _token_case_payload() -> dict[str, Any]:
    return {
        "target": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"},
        "profile": {"status": "pending"},
        "timeline": {"query": {"scope": "all"}},
        "posts": _posts_payload(),
        "market_live": {"status": "missing"},
    }


def _posts_payload() -> dict[str, Any]:
    return {
        "query": {"target_type": "Asset", "target_id": "asset:solana:token:hansa"},
        "items": [{"event_id": "event-1", "target_type": "Asset", "target_id": "asset:solana:token:hansa"}],
    }


def _digest() -> dict[str, Any]:
    return {"status": "ready", "semantic_coverage": 0.8, "evidence_refs": [{"ref_id": "event:event-1"}]}


def _semantic() -> dict[str, Any]:
    return {"status": "labeled", "trade_stance": "bullish", "attention_valence": "celebratory"}


def _body(response: Any) -> dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))
