from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.token_intel.services.token_radar_projector import TokenRadarProjector


def test_market_only_claim_reuses_edges_and_overlays_latest_market_context(monkeypatch) -> None:
    now_ms = 1_777_800_060_000
    claim = {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "dirty_reason": "market_tick_current_changed",
        "market_dirty": True,
        "repair_dirty": False,
    }
    rank_sources = FakeRankSources(
        source_rows=[
            {
                "event_id": "event-existing",
                "received_at_ms": now_ms - 60_000,
                "target_type": "Asset",
                "target_id": "asset-1",
                "latest_price_tick_id": "stale-tick",
            }
        ],
        latest_market_context={
            ("Asset", "asset-1"): {
                "latest_price_tick_id": "fresh-tick",
                "latest_price_provider": "fresh-provider",
                "latest_price_observed_at_ms": now_ms - 10_000,
                "latest_price_usd": 2.5,
            }
        },
    )
    projector = TokenRadarProjector(repos=SimpleNamespace(token_radar_rank_sources=rank_sources))
    score_calls: list[dict[str, Any]] = []

    def score(self, **kwargs):
        score_calls.append(kwargs)
        return {
            "source_rows": len(kwargs["source_rows"]),
            "status": "updated",
            "rank_set_changed": True,
            "target_venue": "bsc",
        }

    monkeypatch.setattr(TokenRadarProjector, "project_source_request", score)

    projected = projector.project_claims(
        claimed_targets=(claim,),
        work_items=(
            ("5m", "all", "all"),
            ("5m", "all", "sol"),
            ("5m", "all", "eth"),
            ("5m", "all", "base"),
            ("5m", "all", "bsc"),
            ("5m", "all", "cex"),
        ),
        now_ms=now_ms,
    )

    assert rank_sources.populate_calls == []
    assert rank_sources.latest_market_calls == [[claim]]
    assert len(rank_sources.load_calls[0]) == 1
    request = rank_sources.load_calls[0][0]
    assert (request.window, request.scope, request.target_type_key, request.identity_id) == (
        "5m",
        "all",
        "Asset",
        "asset-1",
    )
    scored_source = score_calls[0]["source_rows"][0]
    assert scored_source["latest_price_tick_id"] == "fresh-tick"
    assert scored_source["latest_price_usd"] == 2.5
    assert projected[0].error is None
    assert projected[0].rank_sets == frozenset({("5m", "all", "all"), ("5m", "all", "bsc")})


@pytest.mark.parametrize(
    "claim",
    [
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "dirty_reason": "mixed",
            "market_dirty": True,
            "repair_dirty": False,
        },
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "dirty_reason": "ops_market_current_repair",
            "market_dirty": True,
            "repair_dirty": True,
        },
    ],
    ids=("mixed-social-and-market", "explicit-repair"),
)
def test_mixed_or_repair_market_claim_refreshes_edges_and_overlays_market(
    monkeypatch,
    claim: dict[str, Any],
) -> None:
    now_ms = 1_777_800_060_000
    rank_sources = FakeRankSources(
        source_rows=[
            {
                "event_id": "event-existing",
                "received_at_ms": now_ms - 60_000,
                "target_type": "Asset",
                "target_id": "asset-1",
            }
        ],
        latest_market_context={
            ("Asset", "asset-1"): {
                "latest_price_tick_id": "fresh-tick",
                "latest_price_observed_at_ms": now_ms - 10_000,
            }
        },
    )
    projector = TokenRadarProjector(repos=SimpleNamespace(token_radar_rank_sources=rank_sources))

    monkeypatch.setattr(
        TokenRadarProjector,
        "project_source_request",
        lambda self, **kwargs: {
            "source_rows": len(kwargs["source_rows"]),
            "status": "updated",
            "rank_set_changed": False,
            "target_venue": "all",
        },
    )

    projected = projector.project_claims(
        claimed_targets=(claim,),
        work_items=(("5m", "all", "all"),),
        now_ms=now_ms,
    )

    assert len(rank_sources.populate_calls) == 1
    assert rank_sources.populate_calls[0]["targets"] == [claim]
    assert rank_sources.populate_calls[0]["projected_at_ms"] == now_ms
    assert rank_sources.latest_market_calls == [[claim]]
    assert projected[0].error is None


class FakeRankSources:
    def __init__(
        self,
        *,
        source_rows: list[dict[str, Any]],
        latest_market_context: dict[tuple[str, str], dict[str, Any]],
    ) -> None:
        self.source_rows = source_rows
        self.latest_market_context = latest_market_context
        self.load_calls: list[list[Any]] = []
        self.populate_calls: list[dict[str, Any]] = []
        self.latest_market_calls: list[list[dict[str, Any]]] = []

    def load_rows_for_requests(self, requests):
        request_list = list(requests)
        self.load_calls.append(request_list)
        return {request.request_key: list(self.source_rows) for request in request_list}

    def populate_edges_for_targets(self, targets, *, projected_at_ms, analysis_since_ms):
        self.populate_calls.append(
            {
                "targets": list(targets),
                "projected_at_ms": projected_at_ms,
                "analysis_since_ms": analysis_since_ms,
            }
        )

    def latest_market_context_for_targets(self, targets):
        self.latest_market_calls.append([dict(target) for target in targets])
        return dict(self.latest_market_context)
