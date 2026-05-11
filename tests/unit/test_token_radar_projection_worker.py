from __future__ import annotations

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
