from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.token_intel._constants import (
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_VERSION,
)
from parallax.domains.token_intel.queries.token_radar_rank_source_query import TokenRadarFeatureSourceRequest
from parallax.domains.token_intel.scoring.factor_snapshot import build_token_factor_snapshot
from parallax.domains.token_intel.services.token_radar_projector import (
    PROJECTION_VERSION,
    TokenRadarProjectionWindowError,
    TokenRadarProjector,
    prune_token_radar_private_cache,
    token_radar_venue_for_rank_input,
)


def test_projector_uses_the_canonical_projection_version() -> None:
    assert PROJECTION_VERSION == TOKEN_RADAR_PROJECTION_VERSION


def test_rank_compact_inputs_orders_public_candidates_by_rank_then_tiebreakers() -> None:
    rows = [
        _rank_input("older", score=42, watched=1, mentions=3, latest_ms=100),
        _rank_input("newer", score=42, watched=1, mentions=3, latest_ms=200),
        _rank_input("stronger", score=80, watched=0, mentions=1, latest_ms=50),
    ]

    ranked = TokenRadarProjector.rank_compact_inputs(rows)

    assert [row["identity_id"] for row in ranked] == ["stronger", "newer", "older"]
    assert all(set(row["factor_ranks"]) == set(TOKEN_RADAR_FACTOR_FAMILIES) for row in ranked)


@pytest.mark.parametrize(
    "field",
    ["raw_composite_score", "gates_max_decision", "social_heat_mentions_1h"],
)
def test_rank_compact_inputs_rejects_incomplete_rank_contract(field: str) -> None:
    row = _rank_input("invalid", score=42, watched=1, mentions=3, latest_ms=100)
    row.pop(field)

    with pytest.raises(RuntimeError, match=field):
        TokenRadarProjector.rank_compact_inputs([row])


def test_rank_compact_inputs_preserves_zero_mentions_1h_without_window_fallback() -> None:
    recent = _rank_input("recent", score=42, watched=1, mentions=1, latest_ms=100)
    quiet = _rank_input("quiet", score=42, watched=1, mentions=0, latest_ms=100)
    quiet["social_propagation_mentions"] = 99

    ranked = TokenRadarProjector.rank_compact_inputs([quiet, recent])

    assert [row["identity_id"] for row in ranked] == ["recent", "quiet"]


def test_empty_source_request_removes_both_private_feature_lanes() -> None:
    token_radar = FakeTokenRadar()
    projector = TokenRadarProjector(repos=SimpleNamespace(token_radar=token_radar))
    request = TokenRadarFeatureSourceRequest(
        request_key="target-0:test",
        target_type_key="Asset",
        identity_id="asset-1",
        window="5m",
        scope="all",
        analysis_since_ms=1,
        score_since_ms=2,
        now_ms=3,
    )

    result = projector.project_source_request(
        request=request,
        target={"target_type_key": "Asset", "identity_id": "asset-1"},
        source_rows=[],
        now_ms=3,
    )

    assert result["status"] == "deleted"
    assert result["rank_set_changed"] is True
    assert [call["lane"] for call in token_radar.delete_calls] == ["resolved", "attention"]


def test_empty_source_request_still_touches_the_targets_real_venue() -> None:
    token_radar = FakeTokenRadar()
    projector = TokenRadarProjector(repos=SimpleNamespace(token_radar=token_radar))
    identity_id = "asset:solana:spl:mint-1"
    request = TokenRadarFeatureSourceRequest(
        request_key="target-0:test",
        target_type_key="Asset",
        identity_id=identity_id,
        window="5m",
        scope="all",
        analysis_since_ms=1,
        score_since_ms=2,
        now_ms=3,
    )

    result = projector.project_source_request(
        request=request,
        target={"target_type_key": "Asset", "identity_id": identity_id},
        source_rows=[],
        now_ms=3,
    )

    assert result["target_venue"] == "sol"


def test_edge_refresh_failure_is_returned_per_claim_without_touching_private_features() -> None:
    rank_sources = FakeRankSources(error=RuntimeError("edge refresh failed"))
    projector = TokenRadarProjector(repos=SimpleNamespace(token_radar_rank_sources=rank_sources))
    claims = (
        {"target_type_key": "Asset", "identity_id": "asset-1"},
        {"target_type_key": "Asset", "identity_id": "asset-2"},
    )

    projected = projector.project_claims(
        claimed_targets=claims,
        work_items=(("5m", "all"),),
        now_ms=1_777_800_000_000,
    )

    assert [item.error for item in projected] == ["edge refresh failed", "edge refresh failed"]
    assert rank_sources.load_calls == []


def test_build_empty_rank_set_filters_by_window_without_writing_serving_rows() -> None:
    token_radar = FakeTokenRadar()
    projector = TokenRadarProjector(repos=SimpleNamespace(token_radar=token_radar))

    projected = projector.build_rank_set(window="5m", scope="all", venue="all", now_ms=500_000, limit=20)

    assert projected.rows == ()
    assert projected.source_rows == 0
    assert token_radar.rank_input_calls[0]["min_latest_event_received_at_ms"] == 200_000


def test_build_rank_sets_loads_each_window_scope_cohort_once_for_all_venues() -> None:
    token_radar = FakeTokenRadar()
    projector = TokenRadarProjector(repos=SimpleNamespace(token_radar=token_radar))

    projected = projector.build_rank_sets(
        window="5m",
        scope="all",
        venues=("all", "sol", "eth", "base", "bsc", "cex"),
        now_ms=500_000,
        limit=20,
    )

    assert set(projected) == {"all", "sol", "eth", "base", "bsc", "cex"}
    assert len(token_radar.rank_input_calls) == 1


def test_build_rank_set_rejects_unknown_window() -> None:
    projector = TokenRadarProjector(repos=SimpleNamespace(token_radar=FakeTokenRadar()))

    with pytest.raises(TokenRadarProjectionWindowError):
        projector.build_rank_set(window="unknown", scope="all", venue="all", now_ms=500_000, limit=20)


def test_private_cache_pruning_uses_one_explicit_transaction_and_shared_budget() -> None:
    transaction = TransactionRecorder()
    token_radar = FakeTokenRadar(pruned_features=2)
    rank_sources = FakeRankSources(pruned_edges=3)
    repos = SimpleNamespace(
        transaction=transaction.transaction,
        token_radar=token_radar,
        token_radar_rank_sources=rank_sources,
    )

    result = prune_token_radar_private_cache(
        repos=repos,
        windows=("5m",),
        scopes=("all",),
        now_ms=1_000_000,
        retention_ms=100_000,
        limit=10,
    )

    assert transaction.entries == 1
    assert result == {
        "status": "ready",
        "cutoff_ms": 900_000,
        "target_features_deleted": 2,
        "rank_source_edges_deleted": 3,
        "limit": 10,
    }
    assert rank_sources.prune_calls[0]["limit"] == 8


def _factor_snapshot(chain: str) -> dict[str, Any]:
    return build_token_factor_snapshot(
        target={
            "target_type": "Asset",
            "target_id": f"asset:{chain}:address",
            "symbol": "TOKEN",
            "chain": chain,
            "address": "address",
            "pricefeed_id": None,
        },
        attention={},
        social_quality={},
        social_semantics={},
        market={
            "event_anchor": None,
            "decision_latest": None,
            "readiness": {
                "anchor_status": "missing",
                "latest_status": "missing",
                "dex_floor_status": "missing_fields",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        timing={},
        source_event_ids=["event-1"],
        computed_at_ms=1,
    )


@pytest.mark.parametrize(
    ("row", "venue"),
    [
        ({"target_type": "CexToken"}, "cex"),
        ({"target_type": "Asset", "factor_snapshot_json": _factor_snapshot("eip155:56")}, "bsc"),
        ({"target_type": "Asset", "factor_snapshot_json": _factor_snapshot("base")}, "base"),
    ],
)
def test_rank_input_venue_is_derived_from_formal_identity(row: dict[str, Any], venue: str) -> None:
    assert token_radar_venue_for_rank_input(row) == venue


class TransactionRecorder:
    def __init__(self) -> None:
        self.entries = 0

    @contextmanager
    def transaction(self):
        self.entries += 1
        yield


class FakeTokenRadar:
    def __init__(self, *, pruned_features: int = 0) -> None:
        self.pruned_features = pruned_features
        self.delete_calls: list[dict[str, Any]] = []
        self.rank_input_calls: list[dict[str, Any]] = []
        self.prune_calls: list[dict[str, Any]] = []

    def delete_target_feature(self, **kwargs):
        self.delete_calls.append(kwargs)
        return 1 if len(self.delete_calls) == 1 else 0

    def list_rank_inputs_for_rank_set(self, **kwargs):
        self.rank_input_calls.append(kwargs)
        return []

    def prune_target_features(self, **kwargs):
        self.prune_calls.append(kwargs)
        return self.pruned_features


class FakeRankSources:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        pruned_edges: int = 0,
    ) -> None:
        self.error = error
        self.pruned_edges = pruned_edges
        self.load_calls: list[list[Any]] = []
        self.prune_calls: list[dict[str, Any]] = []

    def populate_edges_for_targets(self, targets, **kwargs):
        if self.error is not None:
            raise self.error

    def load_rows_for_requests(self, requests):
        self.load_calls.append(list(requests))
        return {}

    def prune_edges(self, **kwargs):
        self.prune_calls.append(kwargs)
        return self.pruned_edges


def _rank_input(
    identity_id: str,
    *,
    score: float,
    watched: int,
    mentions: int,
    latest_ms: int,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "target_id": f"asset:{identity_id}",
        "target_type_key": "Asset",
        "identity_id": identity_id,
        "raw_composite_score": score,
        "gates_max_decision": "high_alert",
        "cohort_high_confidence_mentions": 0,
        "cohort_kol_mentions": 0,
        "cohort_public_followup_authors": 0,
        "cohort_first_seen_global_24h": False,
        "cohort_symbol": identity_id.upper(),
        "social_heat_watched_mentions": watched,
        "social_heat_mentions_1h": mentions,
        "social_propagation_mentions": mentions,
        "social_heat_latest_seen_ms": latest_ms,
    }
    for family in TOKEN_RADAR_FACTOR_FAMILIES:
        row[f"{family}_raw_score"] = score
        row[f"{family}_weight"] = 1.0
    return row
