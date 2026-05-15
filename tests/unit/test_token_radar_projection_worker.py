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


def test_projection_worker_refreshes_hot_windows_before_missing_current_version_windows(monkeypatch):
    calls: list[dict[str, object]] = []
    coverage = {
        ("5m", "all"): {
            "status": "ready",
            "row_count": 0,
            "source_rows": 0,
            "computed_at_ms": 1_777_799_000_000,
        }
    }
    wake_bus = FakeWakeBus()

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild(self, *, window, scope, now_ms=None, limit=100):
            calls.append({"window": window, "scope": scope, "now_ms": now_ms, "limit": limit})
            return {"rows_written": 2, "source_rows": 3, "computed_at_ms": now_ms, "status": "ready"}

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
        {"window": "5m", "scope": "all", "now_ms": 1_777_800_000_000, "limit": 7},
        {"window": "5m", "scope": "matched", "now_ms": 1_777_800_000_000, "limit": 7},
        {"window": "1h", "scope": "all", "now_ms": 1_777_800_000_000, "limit": 7},
        {"window": "1h", "scope": "matched", "now_ms": 1_777_800_000_000, "limit": 7},
        {"window": "4h", "scope": "all", "now_ms": 1_777_800_000_000, "limit": 7},
        {"window": "4h", "scope": "matched", "now_ms": 1_777_800_000_000, "limit": 7},
    ]
    assert result["rows_written"] == 12
    assert result["windows"]["1h:all"]["status"] == "ready"
    assert wake_bus.token_radar_notifications == [
        {"window": "5m", "scope": "all"},
        {"window": "5m", "scope": "matched"},
        {"window": "1h", "scope": "all"},
        {"window": "1h", "scope": "matched"},
        {"window": "4h", "scope": "all"},
        {"window": "4h", "scope": "matched"},
    ]
    assert isinstance(worker, WorkerBase)
    assert worker.SINGLE_WRITER_KEY == 2026051501
    assert db.worker_sessions[0] == {"name": "token_radar_projection", "statement_timeout_seconds": 120.0}


def test_projection_worker_run_once_returns_worker_result(monkeypatch):
    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild(self, *, window, scope, now_ms=None, limit=100):
            return {"rows_written": 2, "source_rows": 3, "computed_at_ms": now_ms, "status": "ready"}

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
        }
    )

    assert missing == []


def test_projection_worker_records_partial_window_results_before_background_failure(monkeypatch):
    calls: list[tuple[str, str]] = []
    sessions: list[FakeSession] = []

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild(self, *, window, scope, now_ms=None, limit=100):
            calls.append((window, scope))
            if (window, scope) == ("1h", "matched"):
                raise RuntimeError("source query timeout")
            return {"rows_written": 2, "source_rows": 3, "computed_at_ms": now_ms, "status": "ready"}

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

    assert calls == [("1h", "all"), ("1h", "matched")]
    assert result["windows"]["1h:all"]["status"] == "ready"
    assert result["windows"]["1h:matched"]["status"] == "failed"
    assert result["windows"]["1h:matched"]["error"] == "source query timeout"
    assert worker.last_error == "source query timeout"


def test_projection_worker_uses_wake_waiter_before_interval(monkeypatch):
    wake_waiter = FakeWakeWaiter()

    async def scenario() -> None:
        class FakeProjection:
            def __init__(self, *, repos):
                self.repos = repos

            def rebuild(self, *, window, scope, now_ms=None, limit=100):
                return {"rows_written": 0, "source_rows": 0, "computed_at_ms": now_ms, "status": "ready"}

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
        "wakes_on": ("market_observation_written", "resolution_updated"),
        "windows": ("5m", "1h", "4h", "24h"),
        "scopes": ("all", "matched"),
        "hot_windows": ("5m",),
    }
    values.update(overrides)
    return SimpleNamespace(**values)
