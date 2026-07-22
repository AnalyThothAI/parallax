from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from parallax.domains.token_intel.runtime import token_radar_projection_worker as module
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


class FakeTokenRadar:
    def __init__(self, publication_state):
        self.publication_state = publication_state
        self.publication_failures: list[dict[str, object]] = []

    def latest_publication_state(self, *, projection_version, windows, scopes, venues):
        normalized: dict[tuple[str, str, str], dict[str, object]] = {}
        for key, value in self.publication_state.items():
            if len(key) == 2:
                window, scope = key
                normalized[(window, scope, "all")] = value
            else:
                normalized[key] = value
        return normalized

    def mark_publication_failed(self, **kwargs):
        self.publication_failures.append(kwargs)

    def prune_target_features(self, **kwargs):
        return 0


class FakeRankSources:
    def prune_edges(self, **kwargs):
        return 0


class FakeRepos:
    def __init__(self, publication_state, *, dirty_claims=None):
        self.token_radar = FakeTokenRadar(publication_state)
        self.token_radar_rank_sources = FakeRankSources()
        self.token_radar_dirty_targets = FakeDirtyTargets(dirty_claims)

    @contextmanager
    def transaction(self):
        yield


class FakeDirtyTargets:
    def __init__(self, claims=None):
        self.catch_up_calls: list[dict[str, object]] = []
        self.claim_due_calls: list[dict[str, object]] = []
        self.claims = list(claims) if claims is not None else [_default_dirty_claim()]

    def claim_due(self, **kwargs):
        self.claim_due_calls.append(kwargs)
        return [dict(claim, lease_owner=kwargs["lease_owner"]) for claim in self.claims]

    def enqueue_recent_resolved_targets(self, **kwargs):
        self.catch_up_calls.append(kwargs)
        raise AssertionError("token radar runtime worker must not run recent resolved catch-up")


class FakeSession:
    def __init__(self, publication_state, *, dirty_claims=None):
        self.repos = FakeRepos(publication_state, dirty_claims=dirty_claims)

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDB:
    def __init__(self, publication_state, *, dirty_claims=None):
        self.publication_state = publication_state
        self.dirty_claims = dirty_claims
        self.worker_sessions: list[dict[str, object]] = []
        self.sessions: list[FakeSession] = []

    @contextmanager
    def worker_session(self, name, statement_timeout_seconds=None):
        self.worker_sessions.append({"name": name, "statement_timeout_seconds": statement_timeout_seconds})
        session = FakeSession(
            self.publication_state,
            dirty_claims=self.dirty_claims,
        )
        self.sessions.append(session)
        yield session.repos


def _default_dirty_claim() -> dict[str, object]:
    return {
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "payload_hash": "claim-hash",
        "attempt_count": 1,
    }


def test_projection_worker_calls_dirty_incremental_projection_not_window_rebuild(monkeypatch):
    calls: list[dict[str, object]] = []
    publication_state = {}

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

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    db = FakeDB(publication_state)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m", "1h", "4h"), scopes=("all", "matched"), batch_size=7),
        db=db,
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=1_777_800_000_000)

    assert calls == [
        {
            "windows": ("5m", "1h", "4h"),
            "scopes": ("all", "matched"),
            "work_items": (
                ("5m", "all"),
                ("5m", "matched"),
                ("1h", "all"),
            ),
            "now_ms": 1_777_800_000_000,
            "limit": 7,
            "rank_limit": 7,
            "lease_ms": 120_000,
            "retry_ms": 30_000,
            "max_attempts": 3,
            "lease_owner": "token_radar_projection",
            "claimed_targets": (
                {
                    "target_type_key": "Asset",
                    "identity_id": "asset-1",
                    "payload_hash": "claim-hash",
                    "lease_owner": "token_radar_projection",
                    "attempt_count": 1,
                },
            ),
            "score_work_items": (
                ("5m", "all"),
                ("5m", "matched"),
                ("1h", "all"),
                ("1h", "matched"),
                ("4h", "all"),
                ("4h", "matched"),
            ),
        }
    ]
    assert result["rows_written"] == 2
    assert result["windows"]["5m:all"]["status"] == "ready"
    assert isinstance(worker, WorkerBase)
    assert worker.windows == ("5m", "1h", "4h")
    assert worker.scopes == ("all", "matched")
    assert worker.venues == ("all",)
    assert worker.hot_windows == ("5m",)
    assert worker.limit == 7
    assert worker.cold_interval_ms == 60_000
    assert db.worker_sessions[0] == {"name": "token_radar_projection", "statement_timeout_seconds": 120.0}


def test_projection_worker_requires_db_contract() -> None:
    with pytest.raises(RuntimeError, match="token_radar_projection_db_required"):
        module.TokenRadarProjectionWorker(
            name="token_radar_projection",
            settings=_settings(),
            db=None,
            telemetry=object(),
        )


@pytest.mark.parametrize("limit", [0, True, "7"])
def test_projection_worker_rejects_malformed_rebuild_limit_before_session(limit: object) -> None:
    db = FakeDB({})
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(),
        db=db,
        telemetry=object(),
    )

    with pytest.raises(ValueError, match="token_radar_projection_limit_required"):
        worker.rebuild_once(now_ms=1_777_800_000_000, limit=limit)

    assert db.worker_sessions == []
    assert db.sessions == []


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

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
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


def test_token_radar_wake_does_not_bypass_hot_interval_gate(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_001_000
    publication_state = {("5m", "all"): _ready_state(now_ms - 1_000)}

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("fresh publication should idle before projection service is called")

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m",), scopes=("all",), hot_windows=("5m",), interval_seconds=10.0),
        db=FakeDB(publication_state, dirty_claims=[]),
        telemetry=object(),
    )

    result = asyncio.run(worker.run_once(now_ms=now_ms))

    assert calls == []
    assert result.skipped == 1
    assert result.failed == 0
    assert result.notes["status"] == "idle"
    assert result.notes["reason"] == "no_due_work_items"


def test_token_radar_worker_claims_dirty_targets_even_when_publication_cadence_is_fresh(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_001_000
    publication_state = {
        ("5m", "all"): _ready_state(now_ms - 1_000),
        ("1h", "all"): _ready_state(now_ms - 1_000),
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 2,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 1,
                "windows": {},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    db = FakeDB(publication_state)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "1h"),
            scopes=("all",),
            hot_windows=("5m",),
            interval_seconds=10.0,
            cold_interval_seconds=60.0,
        ),
        db=db,
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=now_ms)

    assert result["status"] == "ready"
    assert calls[0]["work_items"] == ()
    assert calls[0]["score_work_items"] == (("5m", "all"), ("1h", "all"))
    assert calls[0]["claimed_targets"] == (
        {
            "target_type_key": "Asset",
            "identity_id": "asset-1",
            "payload_hash": "claim-hash",
            "lease_owner": "token_radar_projection",
            "attempt_count": 1,
        },
    )
    assert db.sessions[0].repos.token_radar_dirty_targets.claim_due_calls


def test_projection_worker_scores_each_window_scope_once_across_product_venues(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_001_000
    windows = ("5m", "1h", "4h", "24h")
    scopes = ("all", "matched")
    venues = ("all", "sol", "eth", "base", "bsc", "cex")
    publication_state = {
        (window, scope, venue): _ready_state(now_ms - 1_000)
        for window in windows
        for scope in scopes
        for venue in venues
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 8,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 1,
                "windows": {},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=windows, scopes=scopes, venues=venues),
        db=FakeDB(publication_state),
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=now_ms)

    assert result["status"] == "ready"
    assert calls[0]["work_items"] == ()
    assert calls[0]["score_work_items"] == tuple((window, scope) for window in windows for scope in scopes)
    assert "venues" not in calls[0]


def test_projection_worker_uses_formal_dirty_lease_and_retry_settings(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_001_000

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 1,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 1,
                "windows": {},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    db = FakeDB({})
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m",),
            scopes=("all",),
            hot_windows=("5m",),
            batch_size=3,
            lease_ms=45_000,
            retry_ms=12_000,
            max_attempts=7,
        ),
        db=db,
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=now_ms)

    assert result["status"] == "ready"
    assert db.sessions[0].repos.token_radar_dirty_targets.claim_due_calls[0]["lease_ms"] == 45_000
    assert calls[0]["lease_ms"] == 45_000
    assert calls[0]["retry_ms"] == 12_000
    assert calls[0]["max_attempts"] == 7


def test_projection_worker_runs_bounded_private_cache_retention_from_formal_settings(monkeypatch) -> None:
    retention_calls: list[dict[str, object]] = []
    now_ms = 1_777_800_001_000

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):  # pragma: no cover - retention-only path must stay idle
            raise AssertionError("retention test should not run dirty projection")

    def fake_retention(**kwargs):
        retention_calls.append({key: value for key, value in kwargs.items() if key != "repos"})
        return {
            "status": "ready",
            "target_features_deleted": 2,
            "rank_source_edges_deleted": 1,
            "cutoff_ms": kwargs["now_ms"] - kwargs["retention_ms"],
            "limit": kwargs["limit"],
        }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    monkeypatch.setattr(module, "prune_token_radar_private_cache", fake_retention)
    publication_state = {
        ("5m", "all"): _ready_state(now_ms),
        ("5m", "matched"): _ready_state(now_ms),
        ("1h", "all"): _ready_state(now_ms),
        ("1h", "matched"): _ready_state(now_ms),
    }
    db = FakeDB(publication_state, dirty_claims=[])
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "1h"),
            scopes=("all", "matched"),
            hot_windows=("5m",),
            batch_size=23,
            private_cache_retention_ms=600_000,
        ),
        db=db,
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=now_ms)

    assert result["status"] == "ready"
    assert result["reason"] == "private_cache_retention"
    assert retention_calls == [
        {
            "windows": ("5m", "1h"),
            "scopes": ("all", "matched"),
            "now_ms": now_ms,
            "retention_ms": 600_000,
            "limit": 23,
        }
    ]
    assert result["private_cache_retention"]["status"] == "ready"
    assert result["private_cache_retention"]["target_features_deleted"] == 2
    assert result["private_cache_retention"]["rank_source_edges_deleted"] == 1


def test_token_radar_worker_runs_only_due_hot_items_after_interval(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_000_000
    publication_state = {
        ("5m", "all"): _ready_state(now_ms - 11_000),
        ("5m", "matched"): _ready_state(now_ms - 1_000),
        ("1h", "all"): _ready_state(now_ms - 59_000),
        ("1h", "matched"): _ready_state(now_ms - 59_000),
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 0,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 0,
                "windows": {"5m:all": {"status": "ready"}},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "1h"),
            scopes=("all", "matched"),
            hot_windows=("5m",),
            interval_seconds=10.0,
            cold_interval_seconds=60.0,
        ),
        db=FakeDB(publication_state, dirty_claims=[]),
        telemetry=object(),
    )

    worker.rebuild_once(now_ms=now_ms)

    assert calls[0]["work_items"] == (("5m", "all"),)
    assert calls[0]["windows"] == ("5m",)
    assert calls[0]["scopes"] == ("all",)


def test_token_radar_worker_idles_when_cold_grouped_window_is_fresh(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_000_000
    publication_state = {
        ("5m", "matched"): _ready_state(now_ms - 1_000),
        ("1h", "matched"): _ready_state(now_ms - 59_000),
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("fresh cold grouped publication should not run projection")

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "1h"),
            scopes=("matched",),
            hot_windows=("5m",),
            interval_seconds=10.0,
            cold_interval_seconds=60.0,
        ),
        db=FakeDB(publication_state, dirty_claims=[]),
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=now_ms)

    assert calls == []
    assert result["status"] == "idle"
    assert result["reason"] == "no_due_work_items"


def test_token_radar_worker_runs_due_cold_grouped_window_after_interval(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_000_000
    publication_state = {
        ("5m", "all"): _ready_state(now_ms - 1_000),
        ("5m", "matched"): _ready_state(now_ms - 1_000),
        ("1h", "all"): _ready_state(now_ms - 1_000),
        ("1h", "matched"): _ready_state(now_ms - 61_000),
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 0,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 0,
                "windows": {"1h:matched": {"status": "ready"}},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "1h"),
            scopes=("all", "matched"),
            hot_windows=("5m",),
            interval_seconds=10.0,
            cold_interval_seconds=60.0,
        ),
        db=FakeDB(publication_state, dirty_claims=[]),
        telemetry=object(),
    )

    worker.rebuild_once(now_ms=now_ms)

    assert calls[0]["work_items"] == (("1h", "matched"),)
    assert calls[0]["windows"] == ("1h",)
    assert calls[0]["scopes"] == ("matched",)


def test_token_radar_failed_without_current_backs_off_recent_attempt(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_000_000
    publication_state = {
        ("5m", "all"): _failed_state(
            latest_attempt_finished_at_ms=now_ms - 1_000,
            current_generation_id=None,
            current_published_at_ms=None,
        ),
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("recent failed attempt without current generation should back off")

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m",), scopes=("all",), hot_windows=("5m",), interval_seconds=10.0),
        db=FakeDB(publication_state, dirty_claims=[]),
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=now_ms)

    assert calls == []
    assert result["status"] == "idle"
    assert result["reason"] == "no_due_work_items"


def test_token_radar_failed_with_previous_generation_uses_attempt_backoff(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_000_000
    publication_state = {
        ("5m", "all"): _ready_state(now_ms - 1_000),
        ("1h", "all"): _failed_state(
            current_generation_id="previous-generation",
            current_published_at_ms=now_ms - 1_000_000,
            latest_attempt_finished_at_ms=now_ms - 1_000,
        ),
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("recent failed attempt should not retry from old current publication time")

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "1h"),
            scopes=("all",),
            hot_windows=("5m",),
            interval_seconds=10.0,
            cold_interval_seconds=60.0,
        ),
        db=FakeDB(publication_state, dirty_claims=[]),
        telemetry=object(),
    )

    result = worker.rebuild_once(now_ms=now_ms)

    assert calls == []
    assert result["status"] == "idle"
    assert result["reason"] == "no_due_work_items"


def test_token_radar_ready_state_without_publish_time_is_due(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_000_000
    publication_state = {
        ("5m", "all"): {"current_generation_id": "malformed-ready", "latest_attempt_status": "ready"},
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 0,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 0,
                "windows": {"5m:all": {"status": "ready"}},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m",), scopes=("all",), hot_windows=("5m",), interval_seconds=10.0),
        db=FakeDB(publication_state),
        telemetry=object(),
    )

    worker.rebuild_once(now_ms=now_ms)

    assert calls[0]["work_items"] == (("5m", "all"),)


def test_token_radar_worker_limits_partial_cold_missing_to_one_background_item(monkeypatch):
    calls: list[dict[str, object]] = []
    now_ms = 1_777_800_000_000
    publication_state = {
        ("5m", "all"): _ready_state(now_ms - 1_000),
        ("5m", "matched"): _ready_state(now_ms - 1_000),
    }

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 0,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 0,
                "windows": {"1h:all": {"status": "ready"}},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "1h", "4h"),
            scopes=("all", "matched"),
            hot_windows=("5m",),
            interval_seconds=10.0,
            cold_interval_seconds=60.0,
        ),
        db=FakeDB(publication_state, dirty_claims=[]),
        telemetry=object(),
    )

    worker.rebuild_once(now_ms=now_ms)

    assert calls[0]["work_items"] == (("1h", "all"),)
    assert calls[0]["windows"] == ("1h",)
    assert calls[0]["scopes"] == ("all",)


def test_projection_worker_limits_dirty_rebuild_to_hot_and_due_cold_work_items(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 0,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 1,
                "windows": {"5m:all": {"status": "ready"}},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    publication_state = {
        ("1h", "all"): {"latest_attempt_status": "ready", "current_published_at_ms": 1_777_799_990_000},
        ("1h", "matched"): {"latest_attempt_status": "ready", "current_published_at_ms": 1_777_799_990_000},
        ("4h", "all"): {"latest_attempt_status": "ready", "current_published_at_ms": 1_777_799_990_000},
        ("4h", "matched"): {"latest_attempt_status": "ready", "current_published_at_ms": 1_777_799_990_000},
    }
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(windows=("5m", "1h", "4h"), scopes=("all", "matched"), batch_size=7),
        db=FakeDB(publication_state),
        telemetry=object(),
    )

    worker.rebuild_once(now_ms=1_777_800_000_000)

    assert calls[0]["work_items"] == (("5m", "all"), ("5m", "matched"))


def test_projection_worker_treats_failed_publication_state_as_due_work(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakeProjection:
        def __init__(self, *, repos):
            self.repos = repos

        def rebuild_dirty_targets(self, **kwargs):
            calls.append(kwargs)
            return {
                "rows_written": 0,
                "source_rows": 0,
                "computed_at_ms": kwargs["now_ms"],
                "status": "ready",
                "claimed": 0,
                "windows": {"24h:matched": {"status": "ready"}},
            }

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    now_ms = 1_777_800_000_000
    publication_state = {
        ("5m", "matched"): _ready_state(now_ms - 1_000),
        ("24h", "matched"): {
            "latest_attempt_status": "failed",
            "current_published_at_ms": 1_777_799_000_000,
            "latest_attempt_finished_at_ms": 1_777_799_900_000,
        },
    }
    worker = module.TokenRadarProjectionWorker(
        name="token_radar_projection",
        settings=_settings(
            windows=("5m", "24h"),
            scopes=("matched",),
            hot_windows=("5m",),
            batch_size=7,
            cold_interval_seconds=60,
        ),
        db=FakeDB(publication_state),
        telemetry=object(),
    )

    worker.rebuild_once(now_ms=now_ms)

    assert calls[0]["work_items"] == (("24h", "matched"),)


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

    monkeypatch.setattr(module, "TokenRadarProjector", FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
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


def _settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 10.0,
        "timeout_seconds": 120.0,
        "batch_size": 100,
        "lease_ms": 120_000,
        "retry_ms": 30_000,
        "max_attempts": 3,
        "private_cache_retention_ms": 172_800_000,
        "statement_timeout_seconds": 120.0,
        "backoff": SimpleNamespace(base_ms=1, max_ms=5),
        "windows": ("5m", "1h", "4h", "24h"),
        "scopes": ("all", "matched"),
        "venues": ("all",),
        "hot_windows": ("5m",),
        "cold_interval_seconds": 60.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _ready_state(published_at_ms: int) -> dict[str, object]:
    return {
        "current_generation_id": f"generation:{published_at_ms}",
        "current_published_at_ms": published_at_ms,
        "latest_attempt_status": "ready",
    }


def _failed_state(
    *,
    latest_attempt_finished_at_ms: int,
    current_generation_id: str | None = None,
    current_published_at_ms: int | None = None,
) -> dict[str, object]:
    return {
        "current_generation_id": current_generation_id,
        "current_published_at_ms": current_published_at_ms,
        "latest_attempt_generation_id": f"failed:{latest_attempt_finished_at_ms}",
        "latest_attempt_status": "failed",
        "latest_attempt_finished_at_ms": latest_attempt_finished_at_ms,
        "updated_at_ms": latest_attempt_finished_at_ms,
    }


def _worker(
    *,
    windows,
    scopes,
    hot_windows,
    cold_interval_seconds,
    publication_state,
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
    monkeypatch.setattr(module, "TokenRadarProjector", _FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
    db = FakeDB(publication_state)
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


def test_projection_worker_leaves_catch_up_to_projection_service(monkeypatch) -> None:
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

    monkeypatch.setattr(module, "TokenRadarProjector", _FakeProjection)
    monkeypatch.setattr(module, "TokenRadarPublisher", lambda *, repos, projector: projector)
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
    assert db.sessions[-1].repos.token_radar_dirty_targets.catch_up_calls == []


def test_projection_worker_does_not_run_window_scan_or_runtime_catch_up_when_idle() -> None:
    worker = _worker(
        windows=("5m", "1h"),
        scopes=("all",),
        hot_windows=("5m",),
        cold_interval_seconds=60,
        publication_state={},
    )
    try:
        result = worker.rebuild_once(now_ms=122_000)
        assert list(result["windows"]) == ["5m:all"]
    finally:
        worker._test_monkeypatch.undo()
