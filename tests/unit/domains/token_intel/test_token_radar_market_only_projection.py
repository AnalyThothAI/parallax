from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from parallax.domains.token_intel.services.token_radar_projection import TokenRadarProjection


def _target_claim(*, market_dirty: bool = True, repair_dirty: bool = False) -> dict[str, Any]:
    return {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "target-claim-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
        "market_dirty": market_dirty,
        "repair_dirty": repair_dirty,
    }


def _source_claim() -> dict[str, Any]:
    return {
        "projection_version": "token-radar-v13-social-attention",
        "source_event_id": "event-claim",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "source-claim-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
    }


def test_rebuild_dirty_targets_market_only_loads_existing_edges_without_populating(monkeypatch) -> None:
    now_ms = 1_777_800_060_000
    existing_source_row = {
        "event_id": "event-existing",
        "received_at_ms": now_ms - 60_000,
        "target_type": "Asset",
        "target_id": "asset-1",
        "latest_price_tick_id": "stale-tick",
    }
    latest_market_context = {
        ("Asset", "asset-1"): {
            "latest_price_tick_id": "fresh-tick",
            "latest_price_provider": "fresh-provider",
            "latest_price_observed_at_ms": now_ms - 10_000,
            "latest_price_usd": 2.5,
        }
    }
    claim = _target_claim(market_dirty=True)
    rank_sources = FakeRankSources(
        rows_by_request={"*": [existing_source_row]},
        latest_market_context=latest_market_context,
    )
    dirty_targets = FakeDirtyTargets([claim])
    source_dirty = FakeSourceDirtyEvents([])
    repos = _repos(dirty_targets=dirty_targets, source_dirty=source_dirty, rank_sources=rank_sources)
    score_calls: list[dict[str, Any]] = []
    refresh_calls: list[dict[str, Any]] = []

    def score(self, **kwargs):
        score_calls.append(kwargs)
        return {"source_rows": len(kwargs["source_rows"]), "status": "updated", "rank_set_changed": True}

    def refresh(self, **kwargs):
        refresh_calls.append(kwargs)
        return {"rows_written": 1, "source_rows": 1, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", score)
    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        venues=("bsc",),
        now_ms=now_ms,
        limit=20,
        rank_limit=7,
    )

    assert result["status"] == "ready"
    assert rank_sources.populate_calls == []
    assert rank_sources.latest_market_calls == [[claim]]
    loaded_requests = [
        (request.window, request.scope, request.venue, request.target_type_key, request.identity_id)
        for request in rank_sources.load_calls[0]
    ]
    assert loaded_requests == [("5m", "all", "bsc", "Asset", "asset-1")]
    scored_source = score_calls[0]["source_rows"][0]
    assert scored_source["latest_price_tick_id"] == "fresh-tick"
    assert scored_source["latest_price_usd"] == 2.5
    assert refresh_calls == [
        {"window": "5m", "scope": "all", "venue": "all", "now_ms": now_ms, "limit": 7},
        {"window": "5m", "scope": "all", "venue": "bsc", "now_ms": now_ms, "limit": 7},
    ]
    assert dirty_targets.done[0]["identity_id"] == "asset-1"
    assert source_dirty.done == []
    assert dirty_targets.errors == []


def test_rebuild_dirty_targets_source_event_claim_populates_narrow_edges(monkeypatch) -> None:
    now_ms = 1_777_800_060_000
    claim = _source_claim()
    rank_sources = FakeRankSources(rows_by_request={"*": [{"event_id": "event-existing"}]})
    dirty_targets = FakeDirtyTargets([])
    source_dirty = FakeSourceDirtyEvents([claim])
    repos = _repos(dirty_targets=dirty_targets, source_dirty=source_dirty, rank_sources=rank_sources)

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated", "rank_set_changed": False},
    )

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "ready"
    assert len(rank_sources.populate_calls) == 1
    populated = rank_sources.populate_calls[0]["requests"]
    assert [request.source_event_id for request in populated] == ["event-claim"]
    assert rank_sources.populate_calls[0]["projected_at_ms"] == now_ms
    assert rank_sources.populate_calls[0]["commit"] is False
    assert len(rank_sources.load_calls) == 1
    assert rank_sources.latest_market_calls == []
    assert source_dirty.done[0]["source_event_id"] == "event-claim"
    assert dirty_targets.done == []


class FakeDirtyTargets:
    def __init__(self, claims: list[dict[str, Any]]) -> None:
        self.claims = claims
        self.claim_due_calls: list[dict[str, Any]] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def claim_due(self, **kwargs):
        self.claim_due_calls.append(kwargs)
        return list(self.claims)

    def mark_done(self, keys, **kwargs):
        self.done.extend(dict(key) for key in keys)
        return len(self.done)

    def mark_error(self, keys, *, error, **kwargs):
        for key in keys:
            self.errors.append({**dict(key), "error": error})
        return len(self.errors)


class FakeSourceDirtyEvents(FakeDirtyTargets):
    pass


class FakeRankSources:
    def __init__(
        self,
        *,
        rows_by_request: dict[str, list[dict[str, Any]]],
        latest_market_context: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.rows_by_request = rows_by_request
        self.latest_market_context = latest_market_context or {}
        self.load_calls: list[list[Any]] = []
        self.populate_calls: list[dict[str, Any]] = []
        self.affected_calls: list[list[Any]] = []
        self.latest_market_calls: list[list[dict[str, Any]]] = []

    def load_rows_for_requests(self, requests):
        request_list = list(requests)
        self.load_calls.append(request_list)
        return {
            request.request_key: list(self.rows_by_request.get(request.request_key, self.rows_by_request.get("*", [])))
            for request in request_list
        }

    def populate_edges_for_event_ids(self, requests, *, projected_at_ms, commit):
        self.populate_calls.append({"requests": list(requests), "projected_at_ms": projected_at_ms, "commit": commit})
        return len(self.populate_calls[-1]["requests"])

    def populate_edges_for_targets(self, targets, *, projected_at_ms, analysis_since_ms, commit):
        self.populate_calls.append(
            {
                "targets": list(targets),
                "projected_at_ms": projected_at_ms,
                "analysis_since_ms": analysis_since_ms,
                "commit": commit,
            }
        )
        return len(self.populate_calls[-1]["targets"])

    def affected_targets_for_event_ids(self, requests):
        self.affected_calls.append(list(requests))
        return [{"target_type_key": "Asset", "identity_id": "asset-1"}]

    def latest_market_context_for_targets(self, targets):
        self.latest_market_calls.append([dict(target) for target in targets])
        return dict(self.latest_market_context)


def _repos(
    *,
    dirty_targets: FakeDirtyTargets,
    source_dirty: FakeSourceDirtyEvents,
    rank_sources: FakeRankSources,
) -> Any:
    return SimpleNamespace(
        token_radar_dirty_targets=dirty_targets,
        token_radar_source_dirty_events=source_dirty,
        token_radar_rank_sources=rank_sources,
    )
