from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import (
    TokenRadarProjection,
    _claim_requires_source_rebuild,
)


def _claim(*, source_dirty: bool, market_dirty: bool, repair_dirty: bool) -> dict[str, Any]:
    return {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "claim-hash",
        "lease_owner": "projection-worker",
        "attempt_count": 1,
        "source_dirty": source_dirty,
        "market_dirty": market_dirty,
        "repair_dirty": repair_dirty,
    }


def test_claim_requires_source_rebuild_classifies_dirty_kind_flags() -> None:
    assert (
        _claim_requires_source_rebuild(
            {
                "source_dirty": False,
                "market_dirty": True,
                "repair_dirty": True,
            }
        )
        is True
    )
    assert (
        _claim_requires_source_rebuild(
            {
                "source_dirty": True,
                "market_dirty": True,
                "repair_dirty": False,
            }
        )
        is True
    )
    assert _claim_requires_source_rebuild({"target_type_key": "Asset", "identity_id": "asset-1"}) is True
    assert (
        _claim_requires_source_rebuild(
            {
                "source_dirty": False,
                "market_dirty": True,
                "repair_dirty": False,
            }
        )
        is False
    )


def test_rebuild_dirty_targets_market_only_loads_existing_rows_without_populating_edges(monkeypatch) -> None:
    now_ms = 1_777_800_060_000
    existing_source_row = {"event_id": "event-existing", "received_at_ms": now_ms - 60_000}
    claim = _claim(source_dirty=False, market_dirty=True, repair_dirty=False)
    rank_sources = FakeRankSources(rows_by_request={"*": [existing_source_row]})
    dirty_targets = FakeDirtyTargets([claim])
    repos = _repos(dirty_targets=dirty_targets, rank_sources=rank_sources)
    score_calls: list[dict[str, Any]] = []
    refresh_calls: list[dict[str, Any]] = []

    def score(self, **kwargs):
        score_calls.append(kwargs)
        return {
            "source_rows": len(kwargs["source_rows"]),
            "status": "updated",
            "rank_set_changed": True,
        }

    def refresh(self, **kwargs):
        refresh_calls.append(kwargs)
        return {"rows_written": 1, "source_rows": 1, "status": "ready"}

    monkeypatch.setattr(TokenRadarProjection, "_project_source_request", score)
    monkeypatch.setattr(TokenRadarProjection, "refresh_rank_set", refresh)

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
        rank_limit=7,
    )

    assert result["status"] == "ready"
    assert rank_sources.populate_calls == []
    assert len(rank_sources.load_calls) == 1
    loaded_requests = [
        (request.window, request.scope, request.target_type_key, request.identity_id)
        for request in rank_sources.load_calls[0]
    ]
    assert loaded_requests == [
        ("5m", "all", "Asset", "asset-1")
    ]
    assert len(score_calls) == 1
    assert score_calls[0]["source_rows"] == [existing_source_row]
    assert refresh_calls == [
        {"window": "5m", "scope": "all", "now_ms": now_ms, "limit": 7},
    ]
    assert dirty_targets.done[0]["identity_id"] == "asset-1"
    assert dirty_targets.errors == []


@pytest.mark.parametrize(
    "claim",
    [
        _claim(source_dirty=True, market_dirty=False, repair_dirty=False),
        _claim(source_dirty=False, market_dirty=True, repair_dirty=True),
    ],
)
def test_rebuild_dirty_targets_source_or_repair_claim_populates_edges(monkeypatch, claim) -> None:
    now_ms = 1_777_800_060_000
    rank_sources = FakeRankSources(rows_by_request={"*": [{"event_id": "event-existing"}]})
    dirty_targets = FakeDirtyTargets([claim])
    repos = _repos(dirty_targets=dirty_targets, rank_sources=rank_sources)

    monkeypatch.setattr(
        TokenRadarProjection,
        "_project_source_request",
        lambda self, **kwargs: {"source_rows": 1, "status": "updated", "rank_set_changed": False},
    )
    monkeypatch.setattr(
        TokenRadarProjection,
        "refresh_rank_set",
        lambda self, **kwargs: {"rows_written": 1, "source_rows": 1, "status": "ready"},
    )

    result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=now_ms,
        limit=20,
    )

    assert result["status"] == "ready"
    assert len(rank_sources.populate_calls) == 1
    populated_requests = [
        (request.window, request.scope, request.target_type_key, request.identity_id)
        for request in rank_sources.populate_calls[0]["requests"]
    ]
    assert populated_requests == [
        ("5m", "all", "Asset", "asset-1")
    ]
    assert rank_sources.populate_calls[0]["projected_at_ms"] == now_ms
    assert rank_sources.populate_calls[0]["commit"] is False
    assert len(rank_sources.load_calls) == 1
    assert dirty_targets.done[0]["identity_id"] == "asset-1"
    assert dirty_targets.errors == []


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


class FakeRankSources:
    def __init__(self, *, rows_by_request: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_request = rows_by_request
        self.load_calls: list[list[Any]] = []
        self.populate_calls: list[dict[str, Any]] = []

    def load_rows_for_requests(self, requests):
        request_list = list(requests)
        self.load_calls.append(request_list)
        return {
            request.request_key: list(self.rows_by_request.get(request.request_key, self.rows_by_request.get("*", [])))
            for request in request_list
        }

    def populate_edges_for_requests(self, requests, *, projected_at_ms, commit):
        self.populate_calls.append(
            {
                "requests": list(requests),
                "projected_at_ms": projected_at_ms,
                "commit": commit,
            }
        )
        return len(self.populate_calls[-1]["requests"])


def _repos(*, dirty_targets: FakeDirtyTargets, rank_sources: FakeRankSources) -> Any:
    return SimpleNamespace(
        token_radar_dirty_targets=dirty_targets,
        token_radar_rank_sources=rank_sources,
    )
