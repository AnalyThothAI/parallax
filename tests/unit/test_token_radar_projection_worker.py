from __future__ import annotations

import asyncio
import time

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
    worker = module.TokenRadarProjectionWorker(
        repository_session=lambda: FakeSession(coverage),
        windows=("5m", "1h", "4h"),
        scopes=("all", "matched"),
        limit=7,
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
    assert worker.last_result == result
    assert wake_bus.token_radar_notifications == [
        {"window": "5m", "scope": "all"},
        {"window": "5m", "scope": "matched"},
        {"window": "1h", "scope": "all"},
        {"window": "1h", "scope": "matched"},
        {"window": "4h", "scope": "all"},
        {"window": "4h", "scope": "matched"},
    ]


def test_projection_worker_does_not_treat_ready_empty_coverage_as_missing():
    worker = module.TokenRadarProjectionWorker(
        repository_session=lambda: FakeSession({}),
        windows=("5m", "1h"),
        scopes=("all", "matched"),
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

    def repository_session():
        session = FakeSession({})
        sessions.append(session)
        return session

    monkeypatch.setattr(module, "_projection_class", lambda: FakeProjection)
    worker = module.TokenRadarProjectionWorker(
        repository_session=repository_session,
        windows=("1h",),
        scopes=("all", "matched"),
        hot_windows=(),
        limit=7,
    )

    result = worker.rebuild_once(now_ms=1_777_800_000_000)

    assert calls == [("1h", "all"), ("1h", "matched")]
    assert result["windows"]["1h:all"]["status"] == "ready"
    assert result["windows"]["1h:matched"]["status"] == "failed"
    assert result["windows"]["1h:matched"]["error"] == "source query timeout"
    assert worker.last_error == "source query timeout"
    assert worker.last_result == result


def test_projection_worker_can_be_woken_by_listen_notify_before_interval():
    wake_listener = FakeWakeListener()

    async def scenario() -> None:
        worker = module.TokenRadarProjectionWorker(
            repository_session=lambda: FakeSession({}),
            windows=("5m",),
            scopes=("all",),
            interval_seconds=60.0,
            wake_listener=wake_listener,
        )
        worker._loop = asyncio.get_running_loop()
        worker._wake_queue = asyncio.Queue(maxsize=1)
        task = asyncio.create_task(worker._listen_for_wake_hints())
        try:
            await asyncio.wait_for(worker._wake_queue.get(), timeout=1.0)
        finally:
            worker.stop()
            await task

    asyncio.run(scenario())
    assert wake_listener.listen_calls >= 1


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
