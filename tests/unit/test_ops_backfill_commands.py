from __future__ import annotations

import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

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
    assert main(["ops", "enqueue-runtime-worker-dirty-targets", "--work", "retired_work"], stdout=io.StringIO()) == 2


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
    assert registry.read_depths == [0]


@pytest.mark.parametrize(
    "limit",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="bool"),
        pytest.param("25", id="string"),
    ],
)
def test_enqueue_token_capture_tier_rank_set_rejects_malformed_limit_before_repository_call(
    limit: object,
) -> None:
    from parallax.app.surfaces.cli.commands.ops import _enqueue_token_capture_tier_rank_set

    with pytest.raises(ValueError, match="ops_capture_tier_rank_set_limit_required"):
        _enqueue_token_capture_tier_rank_set(
            object(),
            window="24h",
            limit=limit,  # type: ignore[arg-type]
            dry_run=True,
            execute=False,
            now_ms=1_700_000_100_000,
        )


def test_enqueue_token_capture_tier_rank_set_rejects_invalid_window_without_24h_fallback() -> None:
    from parallax.app.surfaces.cli.commands.ops import _enqueue_token_capture_tier_rank_set

    with pytest.raises(ValueError, match="invalid ops window"):
        _enqueue_token_capture_tier_rank_set(
            object(),
            window="bad",
            limit=25,
            dry_run=True,
            execute=False,
            now_ms=1_700_000_100_000,
        )


def test_enqueue_token_capture_tier_rank_set_rejects_missing_source_watermark_without_runtime_fallback() -> None:
    from parallax.app.surfaces.cli.commands.ops import _enqueue_token_capture_tier_rank_set

    registry = _FakeCaptureTierRegistry()
    registry.rows = [
        {key: value for key, value in registry.rows[0].items() if key != "source_max_received_at_ms"},
    ]

    with pytest.raises(ValueError, match="ops_capture_tier_rank_set_source_watermark_required"):
        _enqueue_token_capture_tier_rank_set(
            SimpleNamespace(registry=registry),
            window="1h",
            limit=25,
            dry_run=True,
            execute=False,
            now_ms=1_700_000_100_000,
        )


def test_enqueue_token_capture_tier_rank_set_execute_writes_rank_set_dirty_target(monkeypatch) -> None:
    from parallax.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeOpsConn()
    registry = _FakeCaptureTierRegistry(conn)
    dirty_targets = _FakeCaptureTierDirtyTargets(conn)

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(
            conn=conn,
            transaction=conn.transaction,
            registry=registry,
            token_capture_tier_dirty_targets=dirty_targets,
        )

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
        }
    ]
    assert registry.read_depths == [1]
    assert dirty_targets.enqueue_depths == [1]
    assert conn.events == ["enter", "exit"]


def test_rebuild_news_canonical_items_execute_reads_and_writes_inside_transaction() -> None:
    from parallax.app.surfaces.cli.commands.ops import _rebuild_news_canonical_items

    conn = _FakeOpsConn()
    news = _FakeNewsRepository(conn)
    dirty_targets = _FakeNewsProjectionDirtyTargets(conn)
    repos = SimpleNamespace(
        conn=conn,
        transaction=conn.transaction,
        news_items=news,
        news_pages=news,
        news_projection_dirty_targets=dirty_targets,
    )

    result = _rebuild_news_canonical_items(repos, limit=25, dry_run=False, execute=True, now_ms=1_700_000_100_000)

    assert result == {
        "mode": "execute",
        "dry_run": False,
        "execute": True,
        "matched_canonical_items": 2,
        "would_enqueue": 3,
        "enqueued": 3,
        "deleted_disabled_rows": 3,
    }
    assert news.list_depths == [1]
    assert news.delete_depths == [1]
    assert dirty_targets.enqueue_depths == [1]
    assert conn.events == ["enter", "exit"]


def test_rebuild_news_canonical_targets_require_story_key() -> None:
    from parallax.app.surfaces.cli.commands.ops import _news_canonical_rebuild_targets

    with pytest.raises(ValueError, match="ops_news_canonical_rebuild_story_key_required"):
        _news_canonical_rebuild_targets(
            [
                {
                    "news_item_id": "news-1",
                    "story_key": "",
                    "source_watermark_ms": 1_700_000_090_000,
                }
            ]
        )


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


class _FakeCaptureTierRegistry:
    def __init__(self, conn: _FakeOpsConn | None = None) -> None:
        self.conn = conn
        self.rows = [
            {
                "target_type": "Asset",
                "target_id": "asset-1",
                "target_type_key": "Asset",
                "identity_id": "asset-1",
                "rank_score": 88,
                "source_max_received_at_ms": 1_700_000_099_000,
                "payload_hash": "hash-1",
            },
            {
                "target_type": "CexToken",
                "target_id": "cex-1",
                "target_type_key": "CexToken",
                "identity_id": "cex-1",
                "rank_score": 77,
                "source_max_received_at_ms": 1_700_000_098_000,
                "payload_hash": "hash-2",
            },
        ]
        self.calls: list[tuple[Any, ...]] = []
        self.read_depths: list[int] = []

    def ranked_live_market_targets(self, *, projection_version: str, since_ms: int, limit: int) -> list[dict[str, Any]]:
        self.calls.append((projection_version, since_ms, limit))
        self.read_depths.append(self.conn.transaction_depth if self.conn is not None else 0)
        return self.rows[:limit]


class _FakeCaptureTierDirtyTargets:
    def __init__(self, conn: _FakeOpsConn | None = None) -> None:
        self.conn = conn
        self.calls: list[dict[str, Any]] = []
        self.enqueue_depths: list[int] = []

    def enqueue_rank_set(
        self,
        *,
        reason: str,
        rows: list[dict[str, Any]],
        exited_rows: list[dict[str, Any]],
        source_watermark_ms: int,
        now_ms: int,
    ) -> dict[str, Any]:
        self.enqueue_depths.append(self.conn.transaction_depth if self.conn is not None else 0)
        self.calls.append(
            {
                "reason": reason,
                "rows": list(rows),
                "exited_rows": list(exited_rows),
                "source_watermark_ms": source_watermark_ms,
                "now_ms": now_ms,
            }
        )
        return {"targets": 1, "payload_hash": "fingerprint"}


class _FakeNewsRepository:
    def __init__(self, conn: _FakeOpsConn) -> None:
        self.conn = conn
        self.list_depths: list[int] = []
        self.delete_depths: list[int] = []

    def list_news_items_for_canonical_rebuild(self, *, limit: int) -> list[dict[str, Any]]:
        assert limit == 25
        self.list_depths.append(self.conn.transaction_depth)
        return [
            {
                "news_item_id": "news-1",
                "story_key": "story-sol",
                "source_watermark_ms": 1_700_000_090_000,
            },
            {
                "news_item_id": "news-2",
                "story_key": "story-sol",
                "source_watermark_ms": 1_700_000_099_000,
            },
        ]

    def delete_page_rows_without_enabled_observation_edges(self) -> int:
        self.delete_depths.append(self.conn.transaction_depth)
        return 3


class _FakeNewsProjectionDirtyTargets:
    def __init__(self, conn: _FakeOpsConn) -> None:
        self.conn = conn
        self.enqueue_depths: list[int] = []

    def enqueue_targets(self, targets: list[dict[str, Any]], *, reason: str, now_ms: int) -> int:
        self.enqueue_depths.append(self.conn.transaction_depth)
        assert targets == [
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "news-1",
                "source_watermark_ms": 1_700_000_090_000,
            },
            {
                "projection_name": "page",
                "target_kind": "news_item",
                "target_id": "news-2",
                "source_watermark_ms": 1_700_000_099_000,
            },
            {
                "projection_name": "story_brief",
                "target_kind": "story",
                "target_id": "story-sol",
                "source_watermark_ms": 1_700_000_099_000,
            },
        ]
        assert reason == "ops_news_canonical_rebuild"
        assert now_ms == 1_700_000_100_000
        return len(targets)


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
