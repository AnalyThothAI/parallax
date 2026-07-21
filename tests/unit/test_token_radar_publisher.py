from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from parallax.domains.token_intel.services.token_radar_projector import (
    ProjectedClaim,
    RankSetProjection,
)
from parallax.domains.token_intel.services.token_radar_publisher import TokenRadarPublisher


def test_publish_rank_set_maps_unchanged_to_zero_serving_writes() -> None:
    repos = FakeRepos(publication_status="unchanged", rows_written=0)
    publisher = TokenRadarPublisher(repos=repos, projector=FakeProjector(rows=[_current_row()]))

    result = publisher.publish_rank_set(window="5m", scope="all", venue="all", now_ms=1_000, limit=20)

    assert result["status"] == "unchanged"
    assert result["rows_written"] == 0
    assert repos.token_radar.publish_calls[0]["rows"][0]["identity_id"] == "asset-1"
    assert repos.token_radar.failed_calls == []


def test_publish_rank_set_records_failed_publication_state() -> None:
    repos = FakeRepos(publication_error=RuntimeError("publish failed"))
    publisher = TokenRadarPublisher(repos=repos, projector=FakeProjector(rows=[_current_row()]))

    with pytest.raises(RuntimeError, match="publish failed"):
        publisher.publish_rank_set(window="5m", scope="all", venue="all", now_ms=1_000, limit=20)

    assert repos.token_radar.failed_calls[0]["error"] == "publish failed"
    assert repos.token_radar.failed_calls[0]["generation_id"].endswith(":5m:all:all:1000")


def test_publish_transaction_enqueues_profile_downstreams_from_current_change() -> None:
    repos = FakeRepos(invoke_change_callback=True)
    publisher = TokenRadarPublisher(repos=repos, projector=FakeProjector(rows=[_current_row()]))

    result = publisher.publish_rank_set(window="5m", scope="all", venue="all", now_ms=1_000, limit=20)

    assert result["status"] == "ready"
    assert repos.token_profile_current_dirty_targets.targets[0]["target_id"] == "asset-1"
    assert {item["provider"] for item in repos.asset_profile_refresh_targets.targets} == {
        "gmgn_dex_profile",
        "binance_web3_profile",
    }


def test_non_default_venue_does_not_enqueue_default_product_downstreams() -> None:
    repos = FakeRepos(invoke_change_callback=True)
    publisher = TokenRadarPublisher(repos=repos, projector=FakeProjector(rows=[_current_row()]))

    publisher.publish_rank_set(window="5m", scope="all", venue="bsc", now_ms=1_000, limit=20)

    assert repos.token_profile_current_dirty_targets.targets == []
    assert repos.asset_profile_refresh_targets.targets == []


def test_successful_claim_is_acknowledged_after_its_rank_set_publishes(monkeypatch) -> None:
    claim = _claim()
    projected = ProjectedClaim(
        claim=claim,
        rank_sets=frozenset({("5m", "all", "all")}),
        source_rows=4,
    )
    repos = FakeRepos(claims=[claim])
    publisher = TokenRadarPublisher(repos=repos, projector=FakeProjector(projected_claims=[projected]))
    publish_calls: list[dict[str, Any]] = []

    def publish_rank_sets(**kwargs):
        publish_calls.append(kwargs)
        return {venue: {"status": "ready", "rows_written": 1, "source_rows": 1} for venue in kwargs["venues"]}

    monkeypatch.setattr(publisher, "publish_rank_sets", publish_rank_sets)

    result = publisher.rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=1_000,
        limit=20,
        rank_limit=7,
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        lease_owner="worker-1",
    )

    assert result["status"] == "ready"
    assert result["source_rows"] == 4
    assert publish_calls == [{"window": "5m", "scope": "all", "venues": ("all",), "now_ms": 1_000, "limit": 7}]
    assert repos.token_radar_dirty_targets.done[0]["identity_id"] == "asset-1"
    assert repos.token_radar_dirty_targets.errors == []


def test_failed_rank_publication_retries_only_claims_that_touched_that_rank_set(monkeypatch) -> None:
    changed = _claim(identity_id="asset-changed")
    untouched = _claim(identity_id="asset-untouched")
    projector = FakeProjector(
        projected_claims=[
            ProjectedClaim(
                claim=changed,
                rank_sets=frozenset({("5m", "all", "all")}),
                source_rows=1,
            ),
            ProjectedClaim(claim=untouched, rank_sets=frozenset(), source_rows=0),
        ]
    )
    repos = FakeRepos(claims=[changed, untouched])
    publisher = TokenRadarPublisher(repos=repos, projector=projector)

    def fail_publish(**kwargs):
        return {
            venue: {
                "status": "failed",
                "rows_written": 0,
                "source_rows": 0,
                "error": "rank publish failed",
            }
            for venue in kwargs["venues"]
        }

    monkeypatch.setattr(publisher, "publish_rank_sets", fail_publish)

    result = publisher.rebuild_dirty_targets(
        windows=("5m",),
        scopes=("all",),
        now_ms=1_000,
        limit=20,
        rank_limit=20,
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        lease_owner="worker-1",
    )

    assert result["status"] == "failed"
    assert [item["identity_id"] for item in repos.token_radar_dirty_targets.done] == ["asset-untouched"]
    assert [item["identity_id"] for item in repos.token_radar_dirty_targets.errors] == ["asset-changed"]


def test_due_publication_runs_without_claims_for_durable_interval_catch_up(monkeypatch) -> None:
    repos = FakeRepos(claims=[])
    publisher = TokenRadarPublisher(repos=repos, projector=FakeProjector())
    publish_calls: list[dict[str, Any]] = []

    def publish_rank_sets(**kwargs):
        publish_calls.append(kwargs)
        return {venue: {"status": "unchanged", "rows_written": 0, "source_rows": 0} for venue in kwargs["venues"]}

    monkeypatch.setattr(publisher, "publish_rank_sets", publish_rank_sets)

    result = publisher.rebuild_dirty_targets(
        work_items=(("1h", "all"),),
        now_ms=1_000,
        limit=20,
        rank_limit=20,
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        lease_owner="worker-1",
    )

    assert result["status"] == "ready"
    assert result["claimed"] == 0
    assert publish_calls[0]["window"] == "1h"


def test_due_venues_publish_from_one_window_scope_projection_batch() -> None:
    venues = ("all", "sol", "eth", "base", "bsc", "cex")
    projector = FakeProjector()
    repos = FakeRepos(claims=[])
    publisher = TokenRadarPublisher(repos=repos, projector=projector)

    result = publisher.rebuild_dirty_targets(
        work_items=tuple(("1h", "all", venue) for venue in venues),
        now_ms=1_000,
        limit=20,
        rank_limit=20,
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        lease_owner="worker-1",
    )

    assert result["status"] == "ready"
    assert len(projector.rank_batch_calls) == 1
    assert set(projector.rank_batch_calls[0]["venues"]) == set(venues)
    assert len(repos.token_radar.publish_calls) == len(venues)


def test_publisher_collapses_venue_score_work_to_one_window_scope_request() -> None:
    claim = _claim()
    projector = FakeProjector(projected_claims=[ProjectedClaim(claim=claim, rank_sets=frozenset(), source_rows=1)])
    repos = FakeRepos(claims=[claim])
    publisher = TokenRadarPublisher(repos=repos, projector=projector)

    result = publisher.rebuild_dirty_targets(
        score_work_items=tuple(("5m", "all", venue) for venue in ("all", "sol", "eth", "base", "bsc", "cex")),
        now_ms=1_000,
        limit=20,
        rank_limit=20,
        lease_ms=120_000,
        retry_ms=30_000,
        max_attempts=3,
        lease_owner="worker-1",
    )

    assert result["status"] == "ready"
    assert projector.project_calls[0]["work_items"] == (("5m", "all"),)


class FakeProjector:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        projected_claims: list[ProjectedClaim] | None = None,
    ) -> None:
        self.rows = rows or []
        self.projected_claims = projected_claims or []
        self.project_calls: list[dict[str, Any]] = []
        self.rank_batch_calls: list[dict[str, Any]] = []

    def build_rank_set(self, **kwargs):
        return RankSetProjection(rows=tuple(self.rows), source_rows=len(self.rows))

    def build_rank_sets(self, **kwargs):
        self.rank_batch_calls.append(kwargs)
        return {
            venue: RankSetProjection(rows=tuple(self.rows), source_rows=len(self.rows)) for venue in kwargs["venues"]
        }

    def project_claims(self, **kwargs):
        self.project_calls.append(kwargs)
        return tuple(self.projected_claims)


class FakeRepos:
    def __init__(
        self,
        *,
        publication_status: str = "published",
        rows_written: int = 1,
        publication_error: Exception | None = None,
        invoke_change_callback: bool = False,
        claims: list[dict[str, Any]] | None = None,
    ) -> None:
        self.transaction_entries = 0
        self.token_radar = FakeTokenRadar(
            status=publication_status,
            rows_written=rows_written,
            error=publication_error,
            invoke_change_callback=invoke_change_callback,
        )
        self.token_radar_dirty_targets = FakeDirtyTargets(claims or [])
        self.token_profile_current_dirty_targets = FakeTargetQueue()
        self.asset_profile_refresh_targets = FakeTargetQueue()

    @contextmanager
    def transaction(self):
        self.transaction_entries += 1
        yield


class FakeTokenRadar:
    def __init__(
        self,
        *,
        status: str,
        rows_written: int,
        error: Exception | None,
        invoke_change_callback: bool,
    ) -> None:
        self.status = status
        self.rows_written = rows_written
        self.error = error
        self.invoke_change_callback = invoke_change_callback
        self.publish_calls: list[dict[str, Any]] = []
        self.failed_calls: list[dict[str, Any]] = []

    def publish_current_generation(self, **kwargs):
        self.publish_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.invoke_change_callback:
            kwargs["on_current_changes"](
                window=kwargs["window"],
                scope=kwargs["scope"],
                venue=kwargs["venue"],
                rows=kwargs["rows"],
                exited_rows=[],
                previous_by_key={},
                computed_at_ms=kwargs["published_at_ms"],
            )
        return {
            "status": self.status,
            "generation_id": kwargs["generation_id"],
            "rows_written": self.rows_written,
        }

    def mark_publication_failed(self, **kwargs):
        self.failed_calls.append(kwargs)


class FakeDirtyTargets:
    def __init__(self, claims: list[dict[str, Any]]) -> None:
        self.claims = claims
        self.done: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def claim_due(self, **kwargs):
        return list(self.claims)

    def mark_done(self, keys, **kwargs):
        self.done.extend(dict(key) for key in keys)

    def mark_error(self, keys, *, error, **kwargs):
        self.errors.extend({**dict(key), "error": error} for key in keys)


class FakeTargetQueue:
    def __init__(self) -> None:
        self.targets: list[dict[str, Any]] = []

    def enqueue_targets(self, targets, **kwargs):
        self.targets.extend(dict(target) for target in targets)


def _claim(*, identity_id: str = "asset-1") -> dict[str, Any]:
    return {
        "target_type_key": "Asset",
        "identity_id": identity_id,
        "payload_hash": f"claim:{identity_id}",
        "lease_owner": "worker-1",
        "attempt_count": 1,
    }


def _current_row() -> dict[str, Any]:
    return {
        "lane": "resolved",
        "rank": 1,
        "rank_score": 80,
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "decision": "watch",
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "source_max_received_at_ms": 900,
        "payload_hash": "row-hash",
        "chain_id": "eip155:8453",
        "address": "0x1111111111111111111111111111111111111111",
        "factor_snapshot_json": {
            "subject": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "symbol": "ONE",
                "target_market_type": "dex",
                "chain": "eip155:8453",
                "address": "0x1111111111111111111111111111111111111111",
                "pricefeed_id": None,
            }
        },
        "source_event_ids_json": ["event-1"],
        "data_health_json": {},
        "resolution_json": {},
    }
