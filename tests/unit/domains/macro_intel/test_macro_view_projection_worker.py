from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from parallax.domains.macro_intel._constants import MACRO_CORE_CONCEPTS
from parallax.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)
from parallax.platform.config.settings import MacroViewProjectionWorkerSettings

NOW_MS = 1_779_000_000_000


def test_macro_view_projection_worker_writes_latest_snapshot() -> None:
    target = _concept_dirty_target("vol:vix")
    wake_bus = FakeWakeBus()
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
    worker = _worker(db, wake_emitter=wake_bus)

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
        "refresh_observation_series_rows_for_concepts",
        "observations_for_concepts",
        "insert_snapshot",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.claim_call == {
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
        "limit": 250,
        "lease_ms": 300_000,
        "lease_owner": "macro_view_projection",
        "now_ms": NOW_MS,
        "commit": False,
    }
    assert repo.refresh_call == {
        "projection_version": "macro_regime_v4",
        "now_ms": NOW_MS,
        "lookback_days": 1095,
        "limit_per_series": 800,
        "claimed_targets": [target],
        "concept_keys": ("vol:vix",),
    }
    assert repo.observations_for_series_call == {
        "concept_keys": MACRO_CORE_CONCEPTS,
        "lookback_days": 1095,
        "limit_per_series": 800,
    }
    assert len(repo.snapshots) == 1
    assert repo.snapshots[0]["panels_json"]["volatility"]["regime"] == "carry"
    assert repo.done_targets == [(target, NOW_MS, False)]
    assert wake_bus.macro_view_snapshot_updates == [
        {
            "projection_version": repo.snapshots[0]["projection_version"],
            "status": repo.snapshots[0]["status"],
            "regime": repo.snapshots[0]["regime"],
        }
    ]
    assert repo.call_depths == [
        ("claim_macro_projection_dirty_targets", 1),
        ("refresh_observation_series_rows_for_concepts", 2),
        ("observations_for_concepts", 2),
        ("insert_snapshot", 2),
        ("mark_macro_projection_dirty_targets_done", 2),
    ]
    assert db.transaction_depth == 0


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
        "targets_loaded": 0,
        "rows_written": 0,
    }
    assert repo.calls == ["claim_macro_projection_dirty_targets"]


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"batch_size": 0}, "macro_view_projection_batch_size_required", id="batch-zero"),
        pytest.param({"batch_size": True}, "macro_view_projection_batch_size_required", id="batch-bool"),
        pytest.param({"batch_size": "250"}, "macro_view_projection_batch_size_required", id="batch-string"),
        pytest.param({"lease_ms": 0}, "macro_view_projection_lease_ms_required", id="lease-zero"),
        pytest.param({"lease_ms": True}, "macro_view_projection_lease_ms_required", id="lease-bool"),
        pytest.param({"lease_ms": "300000"}, "macro_view_projection_lease_ms_required", id="lease-string"),
    ],
)
def test_macro_view_projection_worker_rejects_malformed_claim_settings_before_claim(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    repo = FakeMacroIntelRepository(dirty_targets=[_dirty_target()], observations=[])
    worker = _worker(FakeDB(repo), settings=_raw_macro_view_projection_settings(**overrides))

    with pytest.raises(ValueError, match=error_code):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repo.claim_call is None


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"lookback_days": 0}, "macro_view_projection_lookback_days_required", id="lookback-zero"),
        pytest.param({"lookback_days": True}, "macro_view_projection_lookback_days_required", id="lookback-bool"),
        pytest.param({"lookback_days": "1095"}, "macro_view_projection_lookback_days_required", id="lookback-string"),
        pytest.param(
            {"limit_per_series": 0},
            "macro_view_projection_limit_per_series_required",
            id="limit-zero",
        ),
        pytest.param(
            {"limit_per_series": True},
            "macro_view_projection_limit_per_series_required",
            id="limit-bool",
        ),
        pytest.param(
            {"limit_per_series": "800"},
            "macro_view_projection_limit_per_series_required",
            id="limit-string",
        ),
    ],
)
def test_macro_view_projection_worker_rejects_malformed_refresh_settings_before_refresh(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    repo = FakeMacroIntelRepository(dirty_targets=[_concept_dirty_target("rates:dgs10")], observations=[])
    worker = _worker(FakeDB(repo), settings=_raw_macro_view_projection_settings(**overrides))

    with pytest.raises(ValueError, match=error_code):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repo.claim_call is not None
    assert repo.refresh_call is None


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"retry_ms": 0}, "macro_view_projection_retry_ms_required", id="retry-zero"),
        pytest.param({"retry_ms": True}, "macro_view_projection_retry_ms_required", id="retry-bool"),
        pytest.param({"retry_ms": "300000"}, "macro_view_projection_retry_ms_required", id="retry-string"),
        pytest.param({"max_attempts": 0}, "macro_view_projection_max_attempts_required", id="attempts-zero"),
        pytest.param({"max_attempts": True}, "macro_view_projection_max_attempts_required", id="attempts-bool"),
        pytest.param({"max_attempts": "3"}, "macro_view_projection_max_attempts_required", id="attempts-string"),
    ],
)
def test_macro_view_projection_worker_rejects_malformed_error_settings_without_mark_error(
    overrides: dict[str, object],
    error_code: str,
) -> None:
    repo = FakeMacroIntelRepository(
        dirty_targets=[_concept_dirty_target("rates:dgs10")],
        observations=[],
        refresh_error=RuntimeError("boom"),
    )
    worker = _worker(FakeDB(repo), settings=_raw_macro_view_projection_settings(**overrides))

    with pytest.raises(ValueError, match=error_code):
        worker.run_once_sync(now_ms=NOW_MS)

    assert repo.error_targets == []


def test_macro_view_projection_worker_unchanged_series_marks_done_without_snapshot() -> None:
    target = _concept_dirty_target("rates:dgs10")
    wake_bus = FakeWakeBus()
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
    worker = _worker(db, wake_emitter=wake_bus)

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
    assert repo.done_targets == [(target, NOW_MS, False)]
    assert repo.snapshots == []
    assert wake_bus.macro_view_snapshot_updates == []


def test_macro_view_projection_worker_event_targets_refresh_without_numeric_snapshot() -> None:
    target = _concept_dirty_target("event:fomc_decision_next")
    wake_bus = FakeWakeBus()
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
    worker = _worker(db, wake_emitter=wake_bus)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["series_status"] == "published"
    assert result.notes["projected_rows_written"] == 2
    assert result.notes["snapshot_rows_written"] == 0
    assert result.notes["source_rows_scanned"] == 0
    assert result.notes["targets_loaded"] == 0
    assert result.notes["rows_written"] == 2
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows_for_concepts",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.refresh_call == {
        "projection_version": "macro_regime_v4",
        "now_ms": NOW_MS,
        "lookback_days": 1095,
        "limit_per_series": 800,
        "claimed_targets": [target],
        "concept_keys": ("event:fomc_decision_next",),
    }
    assert repo.done_targets == [(target, NOW_MS, False)]
    assert repo.snapshots == []
    assert wake_bus.macro_view_snapshot_updates == []


def test_macro_view_projection_worker_current_target_rebuilds_snapshot_when_series_is_unchanged() -> None:
    target = _dirty_target()
    wake_bus = FakeWakeBus()
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
    worker = _worker(db, wake_emitter=wake_bus)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["series_status"] == "unchanged"
    assert result.notes["projected_rows_written"] == 0
    assert result.notes["snapshot_rows_written"] == 1
    assert result.notes["source_rows_scanned"] == 1
    assert result.notes["targets_loaded"] == len(MACRO_CORE_CONCEPTS)
    assert result.notes["rows_written"] == 1
    assert repo.calls == [
        "claim_macro_projection_dirty_targets",
        "refresh_observation_series_rows_for_concepts",
        "observations_for_concepts",
        "insert_snapshot",
        "mark_macro_projection_dirty_targets_done",
    ]
    assert repo.done_targets == [(target, NOW_MS, False)]
    assert len(repo.snapshots) == 1
    assert wake_bus.macro_view_snapshot_updates == [
        {
            "projection_version": repo.snapshots[0]["projection_version"],
            "status": repo.snapshots[0]["status"],
            "regime": repo.snapshots[0]["regime"],
        }
    ]


def test_macro_view_projection_worker_unchanged_snapshot_does_not_notify() -> None:
    target = _concept_dirty_target("vol:vix")
    wake_bus = FakeWakeBus()
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
    worker = _worker(db, wake_emitter=wake_bus)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert result.notes["projected_rows_written"] == 3
    assert result.notes["snapshot_rows_written"] == 0
    assert result.notes["rows_written"] == 3
    assert wake_bus.macro_view_snapshot_updates == []


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
    assert repo.error_targets == [(target, "boom", 300_000, 3, "macro_view_projection", NOW_MS, False)]
    assert repo.call_depths == [
        ("claim_macro_projection_dirty_targets", 1),
        ("refresh_observation_series_rows_for_concepts", 2),
        ("mark_macro_projection_dirty_targets_error", 1),
    ]


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
    assert error_repo.error_targets == [(target, "boom", 90_000, 4, "macro_view_projection", NOW_MS, False)]


def test_macro_view_projection_worker_requires_session_transaction_before_claiming_dirty_target() -> None:
    target = _concept_dirty_target("rates:dgs10")
    repo = FakeMacroIntelRepository(dirty_targets=[target], observations=[])
    db = FakeDB(repo, expose_transaction=False)
    worker = _worker(db)

    with pytest.raises(AttributeError, match="transaction"):
        worker.run_once_sync()

    assert repo.calls == []


def test_macro_view_projection_worker_notifies_after_transaction_commit() -> None:
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
    wake_bus = FakeWakeBus(db=db)
    worker = _worker(db, wake_emitter=wake_bus)

    result = worker.run_once_sync()

    assert result.processed == 1
    assert wake_bus.transaction_depths == [0]
    assert db.transaction_events[-1] == ("exit", 1)


def _worker(
    db: FakeDB,
    *,
    wake_emitter: object | None = None,
    settings: MacroViewProjectionWorkerSettings | None = None,
) -> MacroViewProjectionWorker:
    return MacroViewProjectionWorker(
        name="macro_view_projection",
        settings=settings or _macro_view_projection_settings(),
        db=db,
        telemetry=object(),
        wake_emitter=wake_emitter,
        clock_ms=lambda: NOW_MS,
    )


def _macro_view_projection_settings(**overrides: object) -> MacroViewProjectionWorkerSettings:
    return MacroViewProjectionWorkerSettings(**overrides)


def _raw_macro_view_projection_settings(**overrides: object) -> SimpleNamespace:
    values = {
        "enabled": True,
        "interval_seconds": 60,
        "statement_timeout_seconds": 30.0,
        "batch_size": 250,
        "lookback_days": 1095,
        "limit_per_series": 800,
        "lease_ms": 300_000,
        "retry_ms": 300_000,
        "max_attempts": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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


def _concept_dirty_target(concept_key: str) -> dict[str, object]:
    return {
        "projection_name": "macro_view",
        "projection_version": "macro_regime_v4",
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
        self.done_targets: list[tuple[dict[str, object], int, bool]] = []
        self.error_targets: list[tuple[dict[str, object], str, int, int, str, int, bool]] = []
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
        commit: bool = True,
    ) -> list[dict[str, object]]:
        self._record_call("claim_macro_projection_dirty_targets")
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

    def refresh_observation_series_rows_for_concepts(
        self,
        *,
        projection_version: str,
        now_ms: int,
        lookback_days: int,
        limit_per_series: int,
        claimed_targets: list[dict[str, object]],
        concept_keys: tuple[str, ...],
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
        commit: bool = True,
    ) -> int:
        self._record_call("mark_macro_projection_dirty_targets_done")
        self.done_targets.extend((target, now_ms, commit) for target in claimed)
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
        commit: bool = True,
    ) -> int:
        self._record_call("mark_macro_projection_dirty_targets_error")
        self.error_targets.extend(
            (target, error, retry_ms, max_attempts, worker_name, now_ms, commit) for target in claimed
        )
        return len(claimed)


class FakeWakeBus:
    def __init__(self, *, db: FakeDB | None = None) -> None:
        self.db = db
        self.macro_view_snapshot_updates: list[dict[str, object]] = []
        self.transaction_depths: list[int] = []

    def notify_macro_view_snapshot_updated(self, *, projection_version: str, status: str, regime: str) -> None:
        if self.db is not None:
            self.transaction_depths.append(self.db.transaction_depth)
        self.macro_view_snapshot_updates.append(
            {
                "projection_version": projection_version,
                "status": status,
                "regime": regime,
            }
        )
