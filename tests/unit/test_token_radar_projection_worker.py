from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.token_intel.runtime import token_radar_projection_worker as module


class FakeTokenRadar:
    def __init__(self, coverage):
        self.coverage = coverage
        self.failed_coverage: list[dict[str, object]] = []

    def latest_coverage(self, *, projection_version, windows, scopes):
        return dict(self.coverage)

    def mark_coverage(self, **kwargs):
        self.failed_coverage.append(kwargs)


class FakeRepos:
    def __init__(self, coverage):
        self.token_radar = FakeTokenRadar(coverage)
        self.token_radar_dirty_targets = FakeDirtyTargets()


class FakeDirtyTargets:
    def __init__(self):
        self.catch_up_calls: list[dict[str, object]] = []

    def enqueue_recent_resolved_targets(self, **kwargs):
        self.catch_up_calls.append(kwargs)
        return 0


class FakeSession:
    def __init__(self, coverage):
        self.repos = FakeRepos(coverage)

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDB:
    def __init__(self, coverage):
        self.coverage = coverage
        self.worker_sessions: list[dict[str, object]] = []
        self.sessions: list[FakeSession] = []

    @contextmanager
    def worker_session(self, name, statement_timeout_seconds=None):
        self.worker_sessions.append({"name": name, "statement_timeout_seconds": statement_timeout_seconds})
        session = FakeSession(self.coverage)
        self.sessions.append(session)
        yield session.repos

    def acquire_advisory_lock_connection(self, worker_name, key):
        return FakeAdvisoryLock()


class FakeAdvisoryLock:
    def release(self):
        return None


def test_projection_worker_calls_dirty_incremental_projection_not_window_rebuild(monkeypatch):
    calls: list[dict[str, object]] = []
    coverage = {}
    wake_bus = FakeWakeBus()

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 2,
                "source_rows": 3,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 1,
                "windows": {"5m:all": {"status": "ready", "rows_written": 2, "source_rows": 3}},
            }

        def rebuild(self, **kwargs):  # pragma: no cover - must not be called by runtime worker
            raise AssertionError("worker must not call full-window rebuild")

    monkeypatch.setattr(module, "_projection_class", lambda: FakeProjection)
    db = FakeDB(coverage)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m", "1h", "4h"), scopes=("all", "matched"), batch_size=7),
        db=db,
        telemetry=object(),
        wake_bus=wake_bus,
    )

    result = worker.rebuild_once(now_ms=1_777_800_000_000)

    assert calls == [
        {
            "windows": ("5m", "1h", "4h"),
            "scopes": ("all", "matched"),
            "now_ms": 1_777_800_000_000,
            "limit": 7,
            "rank_limit": 7,
            "lease_owner": "token_radar_projection",
        }
    ]
    assert result["rows_written"] == 2
    assert result["windows"]["5m:all"]["status"] == "ready"
    assert wake_bus.token_radar_notifications == [{"window": "5m", "scope": "all"}]
    assert isinstance(worker, WorkerBase)
    assert worker.SINGLE_WRITER_KEY == 2026051501
    assert db.worker_sessions[0] == {"name": "token_radar_projection", "statement_timeout_seconds": 120.0}


def test_projection_worker_run_once_returns_worker_result(monkeypatch):
    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            return {
                "rows_written": 2,
                "source_rows": 3,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 1,
                "windows": {"5m:all": {"status": "ready"}},
            }

    monkeypatch.setattr(module, "_projection_class", lambda: FakeProjection)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m",), scopes=("all",), hot_windows=("5m",), batch_size=7),
        db=FakeDB({}),
        telemetry=object(),
    )

    result = asyncio.run(worker.run_once())

    assert isinstance(result, WorkerResult)
    assert result.processed == 1
    assert result.notes["rows_written"] == 2
    assert result.notes["source_rows"] == 3
    assert result.notes["windows"]["5m:all"]["status"] == "ready"


def test_projection_worker_does_not_treat_ready_empty_coverage_as_missing():
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m", "1h"), scopes=("all", "matched")),
        db=FakeDB({}),
        telemetry=object(),
    )

    missing = worker._missing_work_items(
        {
            ("5m", "all"): {"status": "ready", "row_count": 0},
            ("5m", "matched"): {"status": "ready", "row_count": 0},
            ("1h", "all"): {"status": "ready", "row_count": 0},
            ("1h", "matched"): {"status": "ready", "row_count": 0},
        },
        computed_at_ms=1_777_800_000_000,
    )

    assert missing == []


def test_projection_worker_backs_off_recently_failed_missing_windows():
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "24h"),
            scopes=("all",),
            hot_windows=("5m",),
            cold_interval_seconds=60,
        ),
        db=FakeDB({}),
        telemetry=object(),
    )

    missing = worker._missing_work_items(
        {
            ("5m", "all"): {"status": "ready", "computed_at_ms": 1_000},
            ("24h", "all"): {"status": "failed", "computed_at_ms": 1_000},
        },
        computed_at_ms=30_000,
    )

    assert missing == []


def test_projection_worker_retries_failed_missing_windows_after_cold_interval():
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "24h"),
            scopes=("all",),
            hot_windows=("5m",),
            cold_interval_seconds=60,
        ),
        db=FakeDB({}),
        telemetry=object(),
    )

    missing = worker._missing_work_items(
        {
            ("5m", "all"): {"status": "ready", "computed_at_ms": 1_000},
            ("24h", "all"): {"status": "failed", "computed_at_ms": 1_000},
        },
        computed_at_ms=62_000,
    )

    assert missing == [("24h", "all")]


def test_projection_worker_records_partial_window_results_before_background_failure(monkeypatch):
    sessions: list[FakeSession] = []

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            return {
                "rows_written": 2,
                "source_rows": 3,
                "computed_at_ms": kwargs["now_ms"],
                "status": "failed",
                "error": "target projection timeout",
                "claimed": 2,
                "windows": {
                    "1h:all": {"status": "ready", "rows_written": 2, "source_rows": 3},
                    "1h:matched": {"status": "failed", "error": "target projection timeout"},
                },
            }

    @contextmanager
    def repository_session(name, statement_timeout_seconds=None):
        session = FakeSession({})
        sessions.append(session)
        yield session.repos

    monkeypatch.setattr(module, "_projection_class", lambda: FakeProjection)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("1h",), scopes=("all", "matched"), hot_windows=(), batch_size=7),
        db=FakeDB({}),
        telemetry=object(),
    )
    worker.db.worker_session = repository_session

    result = worker.rebuild_once(now_ms=1_777_800_000_000)

    assert result["windows"]["1h:all"]["status"] == "ready"
    assert result["windows"]["1h:matched"]["status"] == "failed"
    assert result["windows"]["1h:matched"]["error"] == "target projection timeout"
    assert worker.last_error == "target projection timeout"


def test_projection_worker_uses_wake_waiter_before_interval(monkeypatch):
    wake_waiter = FakeWakeWaiter()

    async def scenario() -> None:
        class FakeProjection:
            def __init__(self, *, repos):
                self.repos = repos

            def rebuild_dirty_targets(self, **kwargs):
                return {
                    "rows_written": 0,
                    "source_rows": 0,
                    "computed_at_ms": kwargs["now_ms"],
                    "status": "idle",
                    "claimed": 0,
                    "windows": {},
                }

        monkeypatch.setattr(module, "_projection_class", lambda: FakeProjection)
        worker = module.TokenRadarProjectionWorker(
            name="token_radar_projection",
            settings=_settings(windows=("5m",), scopes=("all",), interval_seconds=60.0),
            db=FakeDB({}),
            telemetry=object(),
            wake_waiter=wake_waiter,
        )
        task = asyncio.create_task(worker.run())
        try:
            await _wait_until(lambda: wake_waiter.wait_calls >= 1)
        finally:
            await worker.stop()
            await task

    asyncio.run(scenario())
    assert wake_waiter.wait_calls >= 1


class FakeWakeListener:
    def __init__(self) -> None:
        self.listen_calls = 0
        self.emitted = False

    def listen_projection_wakes(self, *, on_wake, should_stop, interval_seconds):
        self.listen_calls += 1
        if not self.emitted:
            self.emitted = True
            on_wake()
        time.sleep(0.05)


class FakeWakeWaiter:
    def __init__(self) -> None:
        self.wait_calls = 0

    async def async_wait(self, timeout: float) -> bool:
        self.wait_calls += 1
        await asyncio.sleep(0.01)
        return True

    def wake(self) -> None:
        return None


class FakeWakeBus:
    def __init__(self) -> None:
        self.token_radar_notifications: list[dict[str, str]] = []

    def notify_token_radar_updated(self, *, window: str, scope: str) -> None:
        self.token_radar_notifications.append({"window": window, "scope": scope})


async def _wait_until(predicate, *, timeout_seconds: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("timed out waiting for condition")
        await asyncio.sleep(0.01)


def _settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 10.0,
        "timeout_seconds": 120.0,
        "batch_size": 100,
        "statement_timeout_seconds": 120.0,
        "advisory_lock_key": 2026051501,
        "wakes_on": ("market_tick_written", "resolution_updated"),
        "windows": ("5m", "1h", "4h", "24h"),
        "scopes": ("all", "matched"),
        "hot_windows": ("5m",),
        "cold_interval_seconds": 60.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _worker(
    *,
    windows,
    scopes,
    hot_windows,
    cold_interval_seconds,
    coverage,
    batch_size=7,
):
    import pytest

    class _FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            return {
                "rows_written": 1,
                "source_rows": 1,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 1,
                "windows": {"5m:all": {"status": "ready"}},
            }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "_projection_class", lambda: _FakeProjection)
    db = FakeDB(coverage)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=windows,
            scopes=scopes,
            hot_windows=hot_windows,
            batch_size=batch_size,
            cold_interval_seconds=cold_interval_seconds,
        ),
        db=db,
        telemetry=object(),
    )
    worker._test_monkeypatch = monkeypatch  # type: ignore[attr-defined]
    return worker


def test_projection_worker_enqueues_bounded_catch_up_when_no_dirty_claims(monkeypatch) -> None:
    class _FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            return {
                "rows_written": 0,
                "source_rows": 0,
                "computed_at_ms": kwargs["now_ms"],
                "status": "idle",
                "claimed": 0,
                "windows": {},
            }

    monkeypatch.setattr(module, "_projection_class", lambda: _FakeProjection)
    db = FakeDB({})
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m", "1h"), scopes=("all",), hot_windows=("5m",), batch_size=7),
        db=db,
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=122_000)

    assert result["status"] == "idle"
    assert result["catch_up_enqueued"] == 0
    assert db.sessions[-1].repos.token_radar_dirty_targets.catch_up_calls[-1]["limit"] == 7


def test_projection_worker_does_not_run_window_scan_after_catch_up() -> None:
    worker = _worker(
        windows=("5m", "1h"),
        scopes=("all",),
        hot_windows=("5m",),
        cold_interval_seconds=60,
        coverage={},
    )
    try:
        result = worker.rebuild_once(now_ms=122_000)
        assert list(result["windows"]) == ["5m:all"]
    finally:
        worker._test_monkeypatch.undo()
