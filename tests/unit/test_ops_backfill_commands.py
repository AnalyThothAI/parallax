from __future__ import annotations

import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.cli import main


def test_rebuild_market_current_calls_application_operation(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    settings = SimpleNamespace()
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: settings)
    monkeypatch.setattr(
        ops_module,
        "rebuild_market_tick_current_batch",
        lambda current_settings, **kwargs: (
            calls.append({"settings": current_settings, **kwargs})
            or {"scanned_targets": 25, "changed_targets": 7, "next_cursor": None, "batch_full": False}
        ),
    )
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "rebuild-market-current",
            "--after-target-type",
            "Asset",
            "--after-target-id",
            "asset:sol",
            "--limit",
            "25",
            "--execute",
        ],
        stdout=stdout,
    )

    assert code == 0
    assert calls == [{"settings": settings, "after": ("Asset", "asset:sol"), "limit": 25}]
    assert json.loads(stdout.getvalue())["data"]["changed_targets"] == 7


def test_rebuild_market_current_rejects_partial_cursor_before_application_call(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(
        ops_module,
        "rebuild_market_tick_current_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("application operation must not run")),
    )
    stdout = io.StringIO()

    code = main(
        ["ops", "rebuild-market-current", "--after-target-type", "Asset", "--execute"],
        stdout=stdout,
    )

    assert code == 2
    assert json.loads(stdout.getvalue()) == {"ok": False, "error": "market_current_rebuild_cursor_pair_required"}


def test_reconcile_event_anchor_jobs_dispatches_to_operator_repository(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeOpsConn()
    event_anchor_jobs = _FakeEventAnchorJobs()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(transaction=conn.transaction, event_anchor_jobs=event_anchor_jobs)

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
    assert conn.events == ["enter", "exit"]
    assert json.loads(stdout.getvalue()) == {
        "ok": True,
        "data": {"mode": "execute", "updated_count": 2},
    }


def test_enqueue_token_radar_dirty_targets_dry_run_counts_without_writing(monkeypatch) -> None:
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
        "would_enqueue": 5,
    }
    assert dirty_targets.calls == [
        ("count_recent_resolved_target_candidates", 0, 1_700_000_100_000, 5000),
        ("count_recent_resolved_target_enqueue_candidates", 0, 1_700_000_100_000, 5000),
    ]


def test_enqueue_token_radar_dirty_targets_execute_enqueues_targets_inside_transaction(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeOpsConn()
    dirty_targets = _FakeDirtyTargetsRepository(conn)

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(
            conn=conn,
            transaction=conn.transaction,
            token_radar_dirty_targets=dirty_targets,
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
        "source": "events",
        "since_ms": 123,
        "limit": 25,
        "dry_run": False,
        "execute": True,
        "candidates": 8,
        "enqueued": 2,
    }
    assert dirty_targets.calls == [
        ("count_recent_resolved_target_candidates", 123, 1_700_000_100_000, 25),
        ("enqueue_recent_resolved_targets", 123, 1_700_000_100_000, 25, "ops_events_repair"),
    ]
    assert dirty_targets.enqueue_depths == [1]
    assert conn.events == ["enter", "exit"]


def test_enqueue_token_radar_dirty_targets_execute_dispatches_to_market_current_repo(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeOpsConn()
    dirty_targets = _FakeDirtyTargetsRepository(conn)

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(
            conn=conn,
            transaction=conn.transaction,
            token_radar_dirty_targets=dirty_targets,
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
        ("enqueue_market_current_targets", 123, 1_700_000_100_000, 25, "ops_market_current_repair"),
    ]
    assert dirty_targets.enqueue_depths == [1]
    assert conn.events == ["enter", "exit"]


@pytest.mark.parametrize(
    ("since_ms", "limit", "error_code"),
    [
        pytest.param(-1, 25, "ops_token_radar_dirty_targets_since_ms_required", id="negative-since"),
        pytest.param(True, 25, "ops_token_radar_dirty_targets_since_ms_required", id="bool-since"),
        pytest.param(0, 0, "ops_token_radar_dirty_targets_limit_required", id="zero-limit"),
        pytest.param(0, -1, "ops_token_radar_dirty_targets_limit_required", id="negative-limit"),
        pytest.param(0, True, "ops_token_radar_dirty_targets_limit_required", id="bool-limit"),
        pytest.param(0, "25", "ops_token_radar_dirty_targets_limit_required", id="string-limit"),
    ],
)
def test_enqueue_token_radar_dirty_targets_rejects_malformed_boundaries_before_repository_call(
    since_ms: object,
    limit: object,
    error_code: str,
) -> None:
    from parallax.app.surfaces.cli.commands.ops import _enqueue_token_radar_dirty_targets

    with pytest.raises(ValueError, match=error_code):
        _enqueue_token_radar_dirty_targets(
            object(),
            source="events",
            since_ms=since_ms,  # type: ignore[arg-type]
            limit=limit,  # type: ignore[arg-type]
            dry_run=True,
            execute=False,
            now_ms=1_700_000_100_000,
        )


class _FakeEventAnchorJobs:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def reconcile_ready_historical_jobs(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"mode": "execute" if kwargs.get("execute") else "dry_run", "updated_count": 2}


class _FakeDirtyTargetsRepository:
    def __init__(self, conn: _FakeOpsConn | None = None) -> None:
        self.conn = conn
        self.calls: list[tuple[Any, ...]] = []
        self.enqueue_depths: list[int] = []

    def count_recent_resolved_target_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        self.calls.append(("count_recent_resolved_target_candidates", since_ms, now_ms, limit))
        return 8

    def count_recent_resolved_target_enqueue_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        self.calls.append(("count_recent_resolved_target_enqueue_candidates", since_ms, now_ms, limit))
        return 5

    def count_market_current_target_candidates(self, *, since_ms: int, now_ms: int, limit: int) -> int:
        self.calls.append(("count_market_current_target_candidates", since_ms, now_ms, limit))
        return 6

    def enqueue_recent_resolved_targets(
        self,
        *,
        since_ms: int,
        now_ms: int,
        limit: int,
        reason: str,
    ) -> int:
        self.calls.append(("enqueue_recent_resolved_targets", since_ms, now_ms, limit, reason))
        self.enqueue_depths.append(self.conn.transaction_depth if self.conn is not None else 0)
        return 2

    def enqueue_market_current_targets(
        self,
        *,
        since_ms: int,
        now_ms: int,
        limit: int,
        reason: str,
    ) -> int:
        self.calls.append(("enqueue_market_current_targets", since_ms, now_ms, limit, reason))
        self.enqueue_depths.append(self.conn.transaction_depth if self.conn is not None else 0)
        return 4


class _FakeOpsConn:
    def __init__(self) -> None:
        self.transaction_depth = 0
        self.events: list[str] = []

    def transaction(self):
        return _FakeOpsTransaction(self)


class _FakeOpsTransaction:
    def __init__(self, conn: _FakeOpsConn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_depth += 1
        self.conn.events.append("enter")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.events.append("rollback" if exc_type is not None else "exit")
        self.conn.transaction_depth -= 1
        return False
