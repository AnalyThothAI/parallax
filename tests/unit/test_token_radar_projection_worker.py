from __future__ import annotations

from gmgn_twitter_intel.domains.token_intel.runtime import token_radar_projection_worker as module


class FakeSession:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def test_token_radar_projection_worker_rebuilds_all_windows_and_scopes(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild(self, *, window, scope, now_ms=None, limit=100):
            calls.append({"window": window, "scope": scope, "now_ms": now_ms, "limit": limit})
            return {"rows_written": 2, "source_rows": 3, "computed_at_ms": now_ms}

    monkeypatch.setattr(module, "_projection_class", lambda: FakeProjection)
    worker = module.TokenRadarProjectionWorker(
        repository_session=FakeSession,
        windows=("5m", "1h", "4h"),
        scopes=("all", "matched"),
        limit=7,
    )

    first = worker.rebuild_once(now_ms=1_777_800_000_000)
    second = worker.rebuild_once(now_ms=1_777_800_010_000)
    third = worker.rebuild_once(now_ms=1_777_800_020_000)

    assert calls == [
        {"window": "5m", "scope": "all", "now_ms": 1_777_800_000_000, "limit": 7},
        {"window": "5m", "scope": "matched", "now_ms": 1_777_800_000_000, "limit": 7},
        {"window": "1h", "scope": "all", "now_ms": 1_777_800_000_000, "limit": 7},
        {"window": "5m", "scope": "all", "now_ms": 1_777_800_010_000, "limit": 7},
        {"window": "5m", "scope": "matched", "now_ms": 1_777_800_010_000, "limit": 7},
        {"window": "1h", "scope": "matched", "now_ms": 1_777_800_010_000, "limit": 7},
        {"window": "5m", "scope": "all", "now_ms": 1_777_800_020_000, "limit": 7},
        {"window": "5m", "scope": "matched", "now_ms": 1_777_800_020_000, "limit": 7},
        {"window": "4h", "scope": "all", "now_ms": 1_777_800_020_000, "limit": 7},
    ]
    assert first["rows_written"] == 6
    assert first["source_rows"] == 9
    assert first["window"] == "1h"
    assert first["scope"] == "all"
    assert second["window"] == "1h"
    assert second["scope"] == "matched"
    assert third["window"] == "4h"
    assert third["scope"] == "all"
    assert first["windows"]["5m:all"]["rows_written"] == 2
    assert first["windows"]["5m:matched"]["rows_written"] == 2
    assert first["windows"]["1h:all"]["rows_written"] == 2
    assert worker.last_started_at_ms == 1_777_800_020_000
    assert worker.last_run_at_ms is not None
    assert worker.last_result == third
    assert worker.last_error is None
