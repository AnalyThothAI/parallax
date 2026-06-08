from __future__ import annotations

import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from parallax.cli import main


def test_retired_backfill_watchlist_signal_stats_command_is_not_registered() -> None:
    assert (
        main(
            ["ops", "backfill-watchlist-signal-stats", "--batch-size", "5000", "--max-batches", "1"],
            stdout=io.StringIO(),
        )
        == 2
    )
    assert (
        main(
            ["ops", "backfill-watchlist-signal-stats", "--batch-size", "5000", "--max-batches", "1", "--dry-run"],
            stdout=io.StringIO(),
        )
        == 2
    )


def test_removed_token_radar_partition_ops_commands_are_not_registered() -> None:
    assert main(["ops", "ensure-postgres-partitions", "--execute"], stdout=io.StringIO()) == 2
    assert main(["ops", "drop-expired-postgres-partitions", "--execute"], stdout=io.StringIO()) == 2
    assert main(["ops", "reset-token-radar-postgres-hard-cut", "--dry-run"], stdout=io.StringIO()) == 2
    assert main(["ops", "enqueue-runtime-worker-dirty-targets", "--work", "pulse_trigger"], stdout=io.StringIO()) == 2


def test_reconcile_event_anchor_jobs_dispatches_to_operator_repository(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    event_anchor_jobs = _FakeEventAnchorJobs()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(event_anchor_jobs=event_anchor_jobs)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_010_000)
    stdout = io.StringIO()

    code = main(["ops", "reconcile-event-anchor-jobs", "--limit", "250", "--execute"], stdout=stdout)

    assert code == 0
    assert event_anchor_jobs.calls == [
        {
            "limit": 250,
            "now_ms": 1_700_000_010_000,
            "execute": True,
        }
    ]
    assert json.loads(stdout.getvalue()) == {
        "ok": True,
        "data": {"mode": "execute", "updated_count": 2},
    }


def test_rebuild_market_tick_current_dry_run_reports_estimate_without_mutation(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    db = _FakeMarketTickCurrentDB()
    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: _market_settings())
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", staticmethod(lambda settings, telemetry: db))
    stdout = io.StringIO()

    code = main(["ops", "rebuild-market-tick-current", "--dry-run"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"] == {
        "mode": "dry_run",
        "dry_run": True,
        "execute": False,
        "scanned": 7,
        "estimated_rows": 3,
        "changed": 0,
        "counts_by_target_type": {"cex_symbol": 1, "chain_token": 2},
    }
    assert db.lock_events == []
    assert db.repos.market_tick_current.truncated is False
    assert db.repos.market_tick_current.upserted == []


def test_rebuild_market_tick_current_execute_acquires_lock_and_dispatches_rebuild(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    db = _FakeMarketTickCurrentDB()
    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: _market_settings())
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", staticmethod(lambda settings, telemetry: db))
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    stdout = io.StringIO()

    code = main(["ops", "rebuild-market-tick-current", "--execute"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["mode"] == "execute"
    assert payload["data"]["dry_run"] is False
    assert payload["data"]["execute"] is True
    assert payload["data"]["scanned"] == 3
    assert payload["data"]["changed"] == 2
    assert payload["data"]["estimated_rows"] == 3
    assert db.lock_events == [
        ("acquire", "market_tick_current_projection", 2026052401),
        ("release", "market_tick_current_projection"),
    ]
    assert db.repos.market_tick_current.truncated is True
    assert db.repos.market_tick_current.upserted == ["tick-1", "tick-2", "tick-3"]


def test_rebuild_market_tick_current_execute_skips_when_projection_lock_is_held(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    db = _FakeMarketTickCurrentDB(lock_available=False)
    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: _market_settings())
    monkeypatch.setattr(ops_module.DBPoolBundle, "create", staticmethod(lambda settings, telemetry: db))
    stdout = io.StringIO()

    code = main(["ops", "rebuild-market-tick-current", "--execute"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["status"] == "skipped"
    assert payload["data"]["notes"] == {
        "reason": "advisory_lock_unavailable",
        "worker_name": "market_tick_current_projection",
        "lock_key": 2026052401,
    }
    assert db.repos.market_tick_current.truncated is False
    assert db.lock_events == [("acquire", "market_tick_current_projection", 2026052401)]


def test_enqueue_token_radar_dirty_targets_dry_run_counts_without_writing(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    dirty_targets = _FakeDirtyTargetsRepository()
    source_dirty_events = _FakeSourceDirtyEventsRepository()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(
            token_radar_dirty_targets=dirty_targets,
            token_radar_source_dirty_events=source_dirty_events,
        )

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "enqueue-token-radar-dirty-targets",
            "--source",
            "events",
            "--since-ms",
            "0",
            "--dry-run",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"] == {
        "source": "events",
        "since_ms": 0,
        "limit": 5000,
        "dry_run": True,
        "execute": False,
        "candidates": 8,
        "would_enqueue": 8,
    }
    assert source_dirty_events.calls == [
        ("count_recent_resolved_event_candidates", 0, 1_700_000_100_000, 5000),
    ]


def test_enqueue_token_radar_dirty_targets_execute_dispatches_to_market_current_repo(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    dirty_targets = _FakeDirtyTargetsRepository()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(token_radar_dirty_targets=dirty_targets)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "enqueue-token-radar-dirty-targets",
            "--source",
            "market-current",
            "--since-ms",
            "123",
            "--limit",
            "25",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"] == {
        "source": "market-current",
        "since_ms": 123,
        "limit": 25,
        "dry_run": False,
        "execute": True,
        "candidates": 6,
        "enqueued": 4,
    }
    assert dirty_targets.calls == [
        ("count_market_current_target_candidates", 123, 1_700_000_100_000, 25),
        ("enqueue_market_current_targets", 123, 1_700_000_100_000, 25, "ops_market_current_repair", True),
    ]


def test_enqueue_token_capture_tier_rank_set_dry_run_reads_bounded_current_rows(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    registry = _FakeCaptureTierRegistry()
    dirty_targets = _FakeCaptureTierDirtyTargets()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(registry=registry, token_capture_tier_dirty_targets=dirty_targets)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        ["ops", "enqueue-token-capture-tier-rank-set", "--window", "24h", "--limit", "25", "--dry-run"],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["window"] == "24h"
    assert payload["data"]["since_ms"] == 1_700_000_100_000 - 24 * 60 * 60 * 1000
    assert payload["data"]["target_count"] == 2
    assert payload["data"]["would_enqueue"] == 1
    assert payload["data"]["enqueued"] == 0
    assert dirty_targets.calls == []
    assert registry.calls == [("token-radar-v13-social-attention", 1_700_000_100_000 - 24 * 60 * 60 * 1000, 25)]


def test_enqueue_token_capture_tier_rank_set_execute_writes_rank_set_dirty_target(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    registry = _FakeCaptureTierRegistry()
    dirty_targets = _FakeCaptureTierDirtyTargets()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(registry=registry, token_capture_tier_dirty_targets=dirty_targets)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_100_000)
    stdout = io.StringIO()

    code = main(
        ["ops", "enqueue-token-capture-tier-rank-set", "--window", "1h", "--limit", "25", "--execute"],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["window"] == "1h"
    assert payload["data"]["since_ms"] == 1_700_000_100_000 - 60 * 60 * 1000
    assert payload["data"]["target_count"] == 2
    assert payload["data"]["enqueued"] == 1
    assert payload["data"]["skipped"] == 0
    assert dirty_targets.calls == [
        {
            "reason": "ops_capture_tier_repair:1h",
            "rows": registry.rows,
            "exited_rows": [],
            "source_watermark_ms": 1_700_000_099_000,
            "now_ms": 1_700_000_100_000,
            "commit": True,
        }
    ]


def test_rebuild_token_radar_rank_inputs_command_is_not_registered() -> None:
    assert (
        main(
            ["ops", "rebuild-token-radar-rank-inputs", "--execute", "--reason", "post-migration", "--limit", "123"],
            stdout=io.StringIO(),
        )
        == 2
    )


class _FakeEventAnchorJobs:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def reconcile_ready_historical_jobs(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"mode": "execute" if kwargs.get("execute") else "dry_run", "updated_count": 2}


def _market_settings() -> SimpleNamespace:
    return SimpleNamespace(
        workers=SimpleNamespace(
            market_tick_current_projection=SimpleNamespace(
                advisory_lock_key=2026052401,
                statement_timeout_seconds=30,
            )
        )
    )


class _FakePool:
    def close(self) -> None:
        return None


class _FakeMarketTickCurrentDB:
    api_pool = worker_pool = lock_pool = tool_pool = wake_pool = _FakePool()

    def __init__(self, *, lock_available: bool = True) -> None:
        self.lock_available = lock_available
        self.lock_events: list[tuple[str, str, int] | tuple[str, str]] = []
        self.repos = SimpleNamespace(
            conn=_FakeMarketTickCurrentConn(),
            market_tick_current=_FakeMarketTickCurrentRepository(),
        )
        self.repos.transaction = self._transaction

    def acquire_advisory_lock_connection(self, worker_name: str, key: int) -> _FakeMarketLock:
        self.lock_events.append(("acquire", worker_name, key))
        if not self.lock_available:
            raise RuntimeError("advisory_lock_unavailable")
        return _FakeMarketLock(self, worker_name)

    @contextmanager
    def _transaction(self):
        yield

    @contextmanager
    def worker_session(self, _name: str, statement_timeout_seconds: int | None = None):
        self.repos.statement_timeout_seconds = statement_timeout_seconds
        yield self.repos


class _FakeMarketLock:
    def __init__(self, db: _FakeMarketTickCurrentDB, worker_name: str) -> None:
        self.db = db
        self.worker_name = worker_name

    def release(self) -> None:
        self.db.lock_events.append(("release", self.worker_name))


class _FakeMarketTickCurrentConn:
    def __init__(self) -> None:
        self.results = [
            [{"scanned": 7}],
            [
                {"target_type": "cex_symbol", "estimated_rows": 1},
                {"target_type": "chain_token", "estimated_rows": 2},
            ],
            [{"scanned": 7}],
            [
                {"target_type": "cex_symbol", "estimated_rows": 1},
                {"target_type": "chain_token", "estimated_rows": 2},
            ],
        ]

    def execute(self, _sql: str, _params: object = None) -> _FakeMarketTickCurrentConn:
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.results.pop(0)


class _FakeMarketTickCurrentRepository:
    def __init__(self) -> None:
        self.truncated = False
        self.upserted: list[str] = []

    def truncate_current(self) -> None:
        self.truncated = True

    def latest_ticks_for_all_targets(self) -> list[dict[str, Any]]:
        return [
            {"tick_id": "tick-1"},
            {"tick_id": "tick-2"},
            {"tick_id": "tick-3"},
        ]

    def upsert_current_from_tick(self, tick_row: dict[str, Any], *, now_ms: int) -> bool:
        assert now_ms == 1_700_000_000_000
        self.upserted.append(str(tick_row["tick_id"]))
        return str(tick_row["tick_id"]) != "tick-2"


class _FakeDirtyTargetsRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def count_recent_resolved_target_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        self.calls.append(("count_recent_resolved_target_candidates", since_ms, now_ms, limit))
        return 8

    def count_recent_resolved_target_enqueue_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        self.calls.append(("count_recent_resolved_target_enqueue_candidates", since_ms, now_ms, limit))
        return 5

    def count_market_current_target_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        self.calls.append(("count_market_current_target_candidates", since_ms, now_ms, limit))
        return 6

    def enqueue_market_current_targets(
        self,
        *,
        since_ms: int,
        now_ms: int,
        limit: int,
        reason: str,
        commit: bool = True,
    ) -> int:
        self.calls.append(("enqueue_market_current_targets", since_ms, now_ms, limit, reason, commit))
        return 4


class _FakeCaptureTierRegistry:
    def __init__(self) -> None:
        self.rows = [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "rank_score": 88,
                "source_max_received_at_ms": 1_700_000_099_000,
                "payload_hash": "hash-1",
            },
            {
                "target_type": "CexToken",
                "target_id": "cex-1",
                "rank_score": 77,
                "source_max_received_at_ms": 1_700_000_098_000,
                "payload_hash": "hash-2",
            },
        ]
        self.calls: list[tuple[Any, ...]] = []

    def ranked_live_market_targets(self, *, projection_version: str, since_ms: int, limit: int) -> list[dict[str, Any]]:
        self.calls.append((projection_version, since_ms, limit))
        return self.rows[:limit]


class _FakeCaptureTierDirtyTargets:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def enqueue_rank_set(
        self,
        *,
        reason: str,
        rows: list[dict[str, Any]],
        exited_rows: list[dict[str, Any]],
        source_watermark_ms: int,
        now_ms: int,
        commit: bool,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "reason": reason,
                "rows": list(rows),
                "exited_rows": list(exited_rows),
                "source_watermark_ms": source_watermark_ms,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return {"targets": 1, "payload_hash": "fingerprint"}


class _FakeSourceDirtyEventsRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def count_recent_resolved_event_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        self.calls.append(("count_recent_resolved_event_candidates", since_ms, now_ms, limit))
        return 8
