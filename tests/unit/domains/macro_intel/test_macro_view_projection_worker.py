from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from parallax.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_EVIDENCE_CONCEPTS,
)
from parallax.platform.config.settings import MacroViewProjectionWorkerSettings

NOW_MS = 1_779_321_600_000
PROJECTION_CONCEPTS = MACRO_EVIDENCE_CONCEPTS


def test_macro_view_projection_worker_writes_latest_snapshot() -> None:
    target = _concept_dirty_target("vol:vix")
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
    assert result.notes["projection_version"] == "macro_decision_v2"
    assert result.notes["source_rows_scanned"] == 1
    assert result.notes["targets_loaded"] == len(PROJECTION_CONCEPTS)
    assert result.notes["projected_rows_written"] == 3
    assert result.notes["snapshot_rows_written"] == 1
    assert result.notes["series_status"] == "published"
    assert result.notes["source_signature"] == "sig-a"
    assert result.notes["rows_written"] == 4
    assert result.notes["fact_watermark"] == "2026-05-20"
    assert result.notes["market_cutoff"] == "2026-05-20"
    assert db.sessions == ["macro_view_projection"]
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows_for_concepts",
        "observations_for_concepts",
        "insert_snapshot",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.claim_call == {
        "projection_name": "macro_evidence",
        "projection_version": "macro_decision_v2",
        "limit": 250,
        "lease_ms": 300_000,
        "lease_owner": "macro_view_projection",
        "now_ms": NOW_MS,
    }
    assert repo.refresh_call == {
        "projection_version": "macro_decision_v2",
        "now_ms": NOW_MS,
        "lookback_days": 1095,
        "limit_per_series": 800,
        "claimed_targets": [target],
        "concept_keys": ("vol:vix",),
        "prune_unrequested": False,
    }
    assert repo.observations_for_series_call == {
        "concept_keys": PROJECTION_CONCEPTS,
        "lookback_days": 1095,
        "limit_per_series": 800,
    }
    assert len(repo.snapshots) == 1
    assert repo.snapshots[0]["overview"]["page_id"] == "overview"
    assert repo.snapshots[0]["credit"]["page_id"] == "credit"
    assert repo.done_targets == [(target, NOW_MS)]
    assert repo.call_depths == [
        ("claim_macro_projection_dirty_targets", 1),
        ("refresh_observation_series_rows_for_concepts", 2),
        ("observations_for_concepts", 2),
        ("insert_snapshot", 2),
        ("mark_macro_projection_dirty_targets_done", 2),
    ]
    assert db.transaction_depth == 0


def test_macro_view_projection_worker_without_dirty_target_rechecks_snapshot_once_per_clock_bucket() -> None:
    repo = FakeMacroIntelRepository(dirty_targets=[], observations=[], snapshot_changed=False)
    db = FakeDB(repo)
    worker = _worker(db)

    first = worker.run_once_sync()
    second = worker.run_once_sync()

    assert first.processed == 1
    assert first.notes == {
        "claimed": 0,
        "queue_depth": 0,
        "source_rows_scanned": 0,
        "targets_loaded": len(PROJECTION_CONCEPTS),
        "rows_written": 0,
        "projected_rows_written": 0,
        "snapshot_rows_written": 0,
        "projection_version": "macro_decision_v2",
        "fact_watermark": "",
        "market_cutoff": "2026-05-20",
        "recheck_reason": "freshness_clock",
    }
    assert second.processed == 0
    assert second.notes == {
        "claimed": 0,
        "queue_depth": 0,
        "source_rows_scanned": 0,
        "targets_loaded": 0,
        "rows_written": 0,
    }
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "observations_for_concepts",
        "insert_snapshot",
        "claim_macro_projection_dirty_targets",
    ]


def test_macro_view_projection_worker_clock_recheck_advances_stale_state_without_new_facts() -> None:
    repo = FakeMacroIntelRepository(
        dirty_targets=[],
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
    worker = _worker(FakeDB(repo))

    first = worker.run_once_sync(now_ms=NOW_MS)
    later = worker.run_once_sync(now_ms=NOW_MS + 8 * 24 * 60 * 60 * 1000)

    assert first.processed == 1
    assert later.processed == 1
    assert len(repo.snapshots) == 2
    first_vix = next(
        item for item in repo.snapshots[0]["cross_asset"]["volatility"] if item["concept_key"] == "vol:vix"
    )
    later_vix = next(
        item for item in repo.snapshots[1]["cross_asset"]["volatility"] if item["concept_key"] == "vol:vix"
    )
    assert first_vix["status"] == "available"
    assert later_vix["status"] == "stale"
    assert later.notes["recheck_reason"] == "freshness_clock"


def test_macro_view_projection_worker_dirty_snapshot_satisfies_same_clock_bucket_recheck() -> None:
    target = _concept_dirty_target("vol:vix")
    repo = FakeMacroIntelRepository(dirty_targets=[target], observations=[])
    worker = _worker(FakeDB(repo))

    first = worker.run_once_sync()
    repo.dirty_targets.clear()
    second = worker.run_once_sync()

    assert first.processed == 1
    assert second.processed == 0
    assert repo.calls.count("observations_for_concepts") == 1
    assert len(repo.snapshots) == 1


def test_macro_view_projection_worker_rechecks_after_market_close_on_same_utc_date() -> None:
    before_close_ms = int(datetime(2026, 7, 23, 19, tzinfo=UTC).timestamp() * 1000)
    after_close_ms = int(datetime(2026, 7, 23, 21, tzinfo=UTC).timestamp() * 1000)
    repo = FakeMacroIntelRepository(dirty_targets=[], observations=[])
    worker = _worker(FakeDB(repo))

    before = worker.run_once_sync(now_ms=before_close_ms)
    after = worker.run_once_sync(now_ms=after_close_ms)

    assert before.processed == 1
    assert after.processed == 1
    assert [snapshot["market_cutoff"].isoformat() for snapshot in repo.snapshots] == [
        "2026-07-22",
        "2026-07-23",
    ]


def test_macro_view_projection_worker_unchanged_series_marks_done_without_snapshot() -> None:
    target = _concept_dirty_target("rates:dgs10")
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
    assert result.notes["targets_loaded"] == 0
    assert result.notes["rows_written"] == 0
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows_for_concepts",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.done_targets == [(target, NOW_MS)]
    assert repo.snapshots == []


def test_macro_view_projection_worker_event_target_rebuilds_route_ready_modules() -> None:
    target = _concept_dirty_target("event:fomc_decision_next")
    repo = FakeMacroIntelRepository(
        dirty_targets=[target],
        observations=[],
        refresh_result={
            "status": "published",
            "rows_written": 2,
            "source_rows": 2,
            "source_signature": "sig-event",
        },
    )
    db = FakeDB(repo)
    worker = _worker(db)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["series_status"] == "published"
    assert result.notes["projected_rows_written"] == 2
    assert result.notes["snapshot_rows_written"] == 1
    assert result.notes["source_rows_scanned"] == 0
    assert result.notes["targets_loaded"] == len(PROJECTION_CONCEPTS)
    assert result.notes["rows_written"] == 3
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows_for_concepts",
        "observations_for_concepts",
        "insert_snapshot",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.refresh_call == {
        "projection_version": "macro_decision_v2",
        "now_ms": NOW_MS,
        "lookback_days": 1095,
        "limit_per_series": 800,
        "claimed_targets": [target],
        "concept_keys": ("event:fomc_decision_next",),
        "prune_unrequested": False,
    }
    assert repo.done_targets == [(target, NOW_MS)]
    assert len(repo.snapshots) == 1
    assert repo.snapshots[0]["overview"]["page_id"] == "overview"


def test_macro_view_projection_worker_current_target_rebuilds_snapshot_when_series_is_unchanged() -> None:
    target = _dirty_target()
    repo = FakeMacroIntelRepository(
        dirty_targets=[target],
        observations=[
            {
                "source_name": "yahoo",
                "concept_key": "commodity:wti_futures",
                "series_key": "yahoo:CL=F",
                "source_priority": 100,
                "observed_at": "2026-06-08",
                "value_numeric": 91.3,
                "unit": "usd",
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": "2026-06-08",
            }
        ],
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
    assert result.notes["series_status"] == "unchanged"
    assert result.notes["projected_rows_written"] == 0
    assert result.notes["snapshot_rows_written"] == 1
    assert result.notes["source_rows_scanned"] == 1
    assert result.notes["targets_loaded"] == len(PROJECTION_CONCEPTS)
    assert result.notes["rows_written"] == 1
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows_for_concepts",
        "observations_for_concepts",
        "insert_snapshot",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.done_targets == [(target, NOW_MS)]
    assert len(repo.snapshots) == 1


def test_macro_view_projection_worker_unchanged_snapshot_writes_no_snapshot_row() -> None:
    target = _concept_dirty_target("vol:vix")
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
        snapshot_changed=False,
    )
    db = FakeDB(repo)
    worker = _worker(db)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["projected_rows_written"] == 3
    assert result.notes["snapshot_rows_written"] == 0
    assert result.notes["rows_written"] == 3


def test_macro_view_projection_worker_refresh_failure_marks_dirty_target_error() -> None:
    target = _concept_dirty_target("rates:dgs10")
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
        "refresh_observation_series_rows_for_concepts",
        "mark_macro_projection_dirty_targets_error",
    ]
    assert repo.error_targets == [(target, "boom", 300_000, 3, "macro_view_projection", NOW_MS)]
    assert repo.call_depths == [
        ("claim_macro_projection_dirty_targets", 1),
        ("refresh_observation_series_rows_for_concepts", 2),
        ("mark_macro_projection_dirty_targets_error", 1),
    ]


def test_macro_view_projection_worker_failed_refresh_result_is_not_published_or_acked() -> None:
    target = _concept_dirty_target("rates:dgs10")
    error = "macro_observation_series_empty: preserved existing current rows"
    repo = FakeMacroIntelRepository(
        dirty_targets=[target],
        observations=[],
        refresh_result={
            "status": "failed",
            "rows_written": 0,
            "source_rows": 0,
            "source_signature": "sig-failed",
            "latest_attempt_error": error,
        },
    )
    db = FakeDB(repo)
    worker = _worker(db)

    result = worker.run_once_sync()

    assert result.processed == 0
    assert result.failed == 1
    assert result.notes["error"] == error
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows_for_concepts",
        "mark_macro_projection_dirty_targets_error",
    ]
    assert repo.snapshots == []
    assert repo.done_targets == []
    assert repo.error_targets == [(target, error, 300_000, 3, "macro_view_projection", NOW_MS)]
    assert db.transaction_events == [("enter", 1), ("enter", 2), ("exit", 2), ("exit", 1)]


def test_macro_view_projection_worker_reads_formal_settings_for_claim_history_session_and_retry() -> None:
    target = _concept_dirty_target("rates:dgs10")
    settings = _macro_view_projection_settings(
        batch_size=7,
        lease_ms=45_000,
        retry_ms=90_000,
        max_attempts=4,
        lookback_days=1200,
        limit_per_series=900,
        statement_timeout_seconds=17,
    )
    repo = FakeMacroIntelRepository(
        dirty_targets=[target],
        observations=[
            {
                "source_name": "fred",
                "concept_key": "rates:dgs10",
                "series_key": "fred:DGS10",
                "source_priority": 100,
                "observed_at": "2026-06-01",
                "value_numeric": 4.2,
                "unit": "percent",
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": "2026-06-01",
            }
        ],
    )
    db = FakeDB(repo, expected_statement_timeout=17)
    worker = _worker(db, settings=settings)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert repo.claim_call is not None
    assert repo.claim_call["limit"] == 7
    assert repo.claim_call["lease_ms"] == 45_000
    assert repo.refresh_call is not None
    assert repo.refresh_call["lookback_days"] == 1200
    assert repo.refresh_call["limit_per_series"] == 900
    assert repo.observations_for_series_call is not None
    assert repo.observations_for_series_call["lookback_days"] == 1200
    assert repo.observations_for_series_call["limit_per_series"] == 900

    error_repo = FakeMacroIntelRepository(
        dirty_targets=[target],
        observations=[],
        refresh_error=RuntimeError("boom"),
    )
    error_db = FakeDB(error_repo, expected_statement_timeout=17)
    error_worker = _worker(error_db, settings=settings)

    error_result = error_worker.run_once_sync()

    assert error_result.failed == 1
    assert error_repo.error_targets == [(target, "boom", 90_000, 4, "macro_view_projection", NOW_MS)]


def test_macro_view_projection_worker_requires_session_transaction_before_claiming_dirty_target() -> None:
    target = _concept_dirty_target("rates:dgs10")
    repo = FakeMacroIntelRepository(dirty_targets=[target], observations=[])
    db = FakeDB(repo, expose_transaction=False)
    worker = _worker(db)

    with pytest.raises(AttributeError, match="transaction"):
        worker.run_once_sync()

    assert repo.calls == []


def test_macro_view_projection_worker_finishes_transaction_after_publication() -> None:
    target = _concept_dirty_target("vol:vix")
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
    assert db.transaction_events[-1] == ("exit", 1)


def _worker(
    db: FakeDB,
    *,
    settings: MacroViewProjectionWorkerSettings | None = None,
) -> MacroViewProjectionWorker:
    return MacroViewProjectionWorker(
        name="macro_view_projection",
        settings=settings or _macro_view_projection_settings(),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )


def _macro_view_projection_settings(**overrides: object) -> MacroViewProjectionWorkerSettings:
    return MacroViewProjectionWorkerSettings(**overrides)


def _dirty_target() -> dict[str, object]:
    return {
        "projection_name": "macro_evidence",
        "projection_version": "macro_decision_v2",
        "target_kind": "current",
        "target_id": "current",
        "payload_hash": "dirty-hash",
        "lease_owner": "macro_view_projection",
        "attempt_count": 1,
    }


def _concept_dirty_target(concept_key: str) -> dict[str, object]:
    return {
        "projection_name": "macro_evidence",
        "projection_version": "macro_decision_v2",
        "target_kind": "concept",
        "target_id": concept_key,
        "concept_key": concept_key,
        "min_observed_at": "2026-05-20",
        "max_observed_at": "2026-05-20",
        "source_watermark_date": "2026-05-20",
        "payload_hash": f"dirty-hash:{concept_key}",
        "lease_owner": "macro_view_projection",
        "attempt_count": 1,
    }


class FakeDB:
    def __init__(
        self,
        repo: FakeMacroIntelRepository,
        *,
        expose_transaction: bool = True,
        expected_statement_timeout: float = 30,
    ) -> None:
        self.repo = repo
        self.sessions: list[str] = []
        self.expose_transaction = expose_transaction
        self.expected_statement_timeout = expected_statement_timeout
        self.transaction_depth = 0
        self.transaction_events: list[tuple[str, int]] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert statement_timeout_seconds == self.expected_statement_timeout
        self.sessions.append(name)
        if not self.expose_transaction:
            yield SimpleNamespace(macro_intel=self.repo)
            return
        session = FakeRepositorySession(self, self.repo)
        self.repo.session = session
        yield session


class FakeRepositorySession:
    def __init__(self, db: FakeDB, repo: FakeMacroIntelRepository) -> None:
        self.db = db
        self.macro_intel = repo

    @contextmanager
    def transaction(self):
        self.db.transaction_depth += 1
        self.db.transaction_events.append(("enter", self.db.transaction_depth))
        try:
            yield
        except Exception:
            self.db.transaction_events.append(("rollback", self.db.transaction_depth))
            raise
        else:
            self.db.transaction_events.append(("exit", self.db.transaction_depth))
        finally:
            self.db.transaction_depth -= 1

    def require_transaction(self, *, operation: str) -> None:
        if self.db.transaction_depth <= 0:
            raise RuntimeError(f"{operation}_requires_explicit_transaction")


class FakeMacroIntelRepository:
    def __init__(
        self,
        *,
        dirty_targets: list[dict[str, object]],
        observations: list[dict[str, object]],
        refresh_result: dict[str, object] | None = None,
        refresh_error: Exception | None = None,
        snapshot_changed: bool = True,
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
        self.snapshot_changed = snapshot_changed
        self.calls: list[str] = []
        self.call_depths: list[tuple[str, int]] = []
        self.claim_call: dict[str, object] | None = None
        self.refresh_call: dict[str, object] | None = None
        self.observations_for_series_call: dict[str, object] | None = None
        self.snapshots: list[dict[str, object]] = []
        self.done_targets: list[tuple[dict[str, object], int]] = []
        self.error_targets: list[tuple[dict[str, object], str, int, int, str, int]] = []
        self.session: FakeRepositorySession | None = None

    def _transaction_depth(self) -> int:
        if self.session is None:
            return 0
        return self.session.db.transaction_depth

    def _record_call(self, name: str) -> None:
        self.calls.append(name)
        self.call_depths.append((name, self._transaction_depth()))

    def claim_macro_projection_dirty_targets(
        self,
        *,
        projection_name: str,
        projection_version: str,
        limit: int,
        lease_ms: int,
        lease_owner: str,
        now_ms: int,
    ) -> list[dict[str, object]]:
        self._record_call("claim_macro_projection_dirty_targets")
        self.claim_call = {
            "projection_name": projection_name,
            "projection_version": projection_version,
            "limit": limit,
            "lease_ms": lease_ms,
            "lease_owner": lease_owner,
            "now_ms": now_ms,
        }
        return self.dirty_targets[:limit]

    def refresh_observation_series_rows_for_concepts(
        self,
        *,
        projection_version: str,
        now_ms: int,
        lookback_days: int,
        limit_per_series: int,
        claimed_targets: list[dict[str, object]],
        concept_keys: tuple[str, ...],
        prune_unrequested: bool,
    ) -> dict[str, object]:
        self._record_call("refresh_observation_series_rows_for_concepts")
        if self.refresh_error is not None:
            raise self.refresh_error
        self.refresh_call = {
            "projection_version": projection_version,
            "now_ms": now_ms,
            "lookback_days": lookback_days,
            "limit_per_series": limit_per_series,
            "claimed_targets": claimed_targets,
            "concept_keys": concept_keys,
            "prune_unrequested": prune_unrequested,
        }
        return self.refresh_result

    def observations_for_concepts(
        self,
        *,
        concept_keys: tuple[str, ...],
        lookback_days: int,
        limit_per_series: int,
    ) -> list[dict[str, object]]:
        self._record_call("observations_for_concepts")
        self.observations_for_series_call = {
            "concept_keys": concept_keys,
            "lookback_days": lookback_days,
            "limit_per_series": limit_per_series,
        }
        return self.observations

    def insert_snapshot(self, snapshot: dict[str, object]) -> bool:
        self._record_call("insert_snapshot")
        self.snapshots.append(snapshot)
        return self.snapshot_changed

    def mark_macro_projection_dirty_targets_done(
        self,
        claimed: list[dict[str, object]],
        *,
        now_ms: int,
    ) -> int:
        self._record_call("mark_macro_projection_dirty_targets_done")
        self.done_targets.extend((target, now_ms) for target in claimed)
        return len(claimed)

    def mark_macro_projection_dirty_targets_error(
        self,
        claimed: list[dict[str, object]],
        *,
        error: str,
        retry_ms: int,
        max_attempts: int,
        worker_name: str,
        now_ms: int,
    ) -> int:
        self._record_call("mark_macro_projection_dirty_targets_error")
        self.error_targets.extend((target, error, retry_ms, max_attempts, worker_name, now_ms) for target in claimed)
        return len(claimed)
