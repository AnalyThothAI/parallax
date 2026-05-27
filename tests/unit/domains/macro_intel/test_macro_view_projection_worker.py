from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CORE_CONCEPTS
from gmgn_twitter_intel.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)

NOW_MS = 1_779_000_000_000


def test_macro_view_projection_worker_writes_latest_snapshot() -> None:
    target = _dirty_target()
    repo = FakeMacroIntelRepository(
        dirty_targets=[target],
        observations=[
            {
                "source_name": "fred",
                "concept_key": "vol:vix",
                "series_key": "fred:VIXCLS",
                "source_priority": 100,
                "observed_at": "2026-05-20",
                "value_numeric": 18.2,
                "unit": "index",
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": "2026-05-20",
            }
        ],
    )
    db = FakeDB(repo)
    worker = _worker(db)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["projection_version"] == "macro_regime_v4"
    assert result.notes["status"] == "partial"
    assert result.notes["source_rows_scanned"] == 1
    assert result.notes["targets_loaded"] == len(MACRO_CORE_CONCEPTS)
    assert result.notes["projected_rows_written"] == 3
    assert result.notes["snapshot_rows_written"] == 1
    assert result.notes["series_status"] == "published"
    assert result.notes["source_signature"] == "sig-a"
    assert result.notes["rows_written"] == 4
    assert result.notes["history_coverage_ratio"] == "0.0"
    assert "data_gap_count" in result.notes
    assert int(result.notes["data_gap_count"]) > 0
    assert db.sessions == ["macro_view_projection"]
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows",
        "observations_for_concepts",
        "insert_snapshot",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.claim_call == {
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
        "limit": 1,
        "lease_ms": 300_000,
        "lease_owner": "macro_view_projection",
        "now_ms": NOW_MS,
        "commit": True,
    }
    assert repo.refresh_call == {
        "projection_version": "macro_regime_v4",
        "now_ms": NOW_MS,
        "lookback_days": 730,
        "limit_per_series": 99,
    }
    assert repo.observations_for_series_call == {
        "concept_keys": MACRO_CORE_CONCEPTS,
        "lookback_days": 730,
        "limit_per_series": 99,
    }
    assert len(repo.snapshots) == 1
    assert repo.snapshots[0]["snapshot_id"] == "macro-view:macro_regime_v4:current"
    assert repo.snapshots[0]["panels_json"]["volatility"]["regime"] == "carry"
    assert repo.done_targets == [(target, NOW_MS, True)]


def test_macro_view_projection_worker_without_dirty_target_does_not_scan_sources() -> None:
    repo = FakeMacroIntelRepository(dirty_targets=[], observations=[])
    db = FakeDB(repo)
    worker = _worker(db)

    result = worker.run_once_sync()

    assert result.processed == 0
    assert result.notes == {
        "claimed": 0,
        "queue_depth": 0,
        "source_rows_scanned": 0,
        "rows_written": 0,
    }
    assert repo.calls == ["claim_macro_projection_dirty_targets"]


def test_macro_view_projection_worker_unchanged_series_marks_done_without_snapshot() -> None:
    target = _dirty_target()
    repo = FakeMacroIntelRepository(
        dirty_targets=[target],
        observations=[],
        refresh_result={
            "status": "unchanged",
            "rows_written": 0,
            "source_rows": 3,
            "source_signature": "sig-same",
        },
    )
    db = FakeDB(repo)
    worker = _worker(db)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["series_status"] == "unchanged"
    assert result.notes["projected_rows_written"] == 0
    assert result.notes["snapshot_rows_written"] == 0
    assert result.notes["source_signature"] == "sig-same"
    assert result.notes["source_rows_scanned"] == 0
    assert result.notes["rows_written"] == 0
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.done_targets == [(target, NOW_MS, True)]
    assert repo.snapshots == []


def test_macro_view_projection_worker_refresh_failure_marks_dirty_target_error() -> None:
    target = _dirty_target()
    repo = FakeMacroIntelRepository(dirty_targets=[target], observations=[], refresh_error=RuntimeError("boom"))
    db = FakeDB(repo)
    worker = _worker(db)

    result = worker.run_once_sync()

    assert result.failed == 1
    assert result.processed == 0
    assert result.notes["claimed"] == 1
    assert result.notes["error"] == "boom"
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows",
        "mark_macro_projection_dirty_targets_error",
    ]
    assert repo.error_targets == [(target, "boom", 300_000, NOW_MS, True)]


def _worker(db: FakeDB) -> MacroViewProjectionWorker:
    return MacroViewProjectionWorker(
        name="macro_view_projection",
        settings=SimpleNamespace(
            batch_size=250,
            lookback_days=730,
            limit_per_series=99,
            lease_ms=300_000,
            retry_ms=300_000,
            statement_timeout_seconds=30,
        ),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )


def _dirty_target() -> dict[str, object]:
    return {
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
        "target_kind": "current",
        "target_id": "current",
        "payload_hash": "dirty-hash",
        "lease_owner": "macro_view_projection",
        "attempt_count": 1,
    }


class FakeDB:
    def __init__(self, repo: FakeMacroIntelRepository) -> None:
        self.repo = repo
        self.sessions: list[str] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert statement_timeout_seconds == 30
        self.sessions.append(name)
        yield SimpleNamespace(macro_intel=self.repo)


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        dirty_targets: list[dict[str, object]],
        observations: list[dict[str, object]],
        refresh_result: dict[str, object] | None = None,
        refresh_error: Exception | None = None,
    ) -> None:
        self.dirty_targets = dirty_targets
        self.observations = observations
        self.refresh_result = refresh_result or {
            "status": "published",
            "rows_written": 3,
            "source_rows": 3,
            "source_signature": "sig-a",
        }
        self.refresh_error = refresh_error
        self.calls: list[str] = []
        self.claim_call: dict[str, object] | None = None
        self.refresh_call: dict[str, object] | None = None
        self.observations_for_series_call: dict[str, object] | None = None
        self.snapshots: list[dict[str, object]] = []
        self.done_targets: list[tuple[dict[str, object], int, bool]] = []
        self.error_targets: list[tuple[dict[str, object], str, int, int, bool]] = []

    def claim_macro_projection_dirty_targets(
        self,
        *,
        projection_name: str,
        projection_version: str,
        limit: int,
        lease_ms: int,
        lease_owner: str,
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, object]]:
        self.calls.append("claim_macro_projection_dirty_targets")
        self.claim_call = {
            "projection_name": projection_name,
            "projection_version": projection_version,
            "limit": limit,
            "lease_ms": lease_ms,
            "lease_owner": lease_owner,
            "now_ms": now_ms,
            "commit": commit,
        }
        return self.dirty_targets[:limit]

    def refresh_observation_series_rows(
        self,
        *,
        projection_version: str,
        now_ms: int,
        lookback_days: int,
        limit_per_series: int,
    ) -> dict[str, object]:
        self.calls.append("refresh_observation_series_rows")
        if self.refresh_error is not None:
            raise self.refresh_error
        self.refresh_call = {
            "projection_version": projection_version,
            "now_ms": now_ms,
            "lookback_days": lookback_days,
            "limit_per_series": limit_per_series,
        }
        return self.refresh_result

    def observations_for_concepts(
        self,
        *,
        concept_keys: tuple[str, ...],
        lookback_days: int,
        limit_per_series: int,
    ) -> list[dict[str, object]]:
        self.calls.append("observations_for_concepts")
        self.observations_for_series_call = {
            "concept_keys": concept_keys,
            "lookback_days": lookback_days,
            "limit_per_series": limit_per_series,
        }
        return self.observations

    def insert_snapshot(self, snapshot: dict[str, object]) -> bool:
        self.calls.append("insert_snapshot")
        self.snapshots.append(snapshot)
        return True

    def mark_macro_projection_dirty_targets_done(
        self,
        claimed: list[dict[str, object]],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        self.calls.append("mark_macro_projection_dirty_targets_done")
        self.done_targets.extend((target, now_ms, commit) for target in claimed)
        return len(claimed)

    def mark_macro_projection_dirty_targets_error(
        self,
        claimed: list[dict[str, object]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        self.calls.append("mark_macro_projection_dirty_targets_error")
        self.error_targets.extend((target, error, retry_ms, now_ms, commit) for target in claimed)
        return len(claimed)
