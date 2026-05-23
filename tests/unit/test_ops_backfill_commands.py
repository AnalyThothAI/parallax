from __future__ import annotations

import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.cli import main


def test_reset_token_radar_postgres_hard_cut_dry_run_returns_plan_without_sql(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeResetConn()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=conn))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(
        ["ops", "reset-token-radar-postgres-hard-cut", "--dry-run"],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["mode"] == "dry_run"
    assert payload["data"]["executed"] is False
    assert payload["data"]["fact_tables_touched"] is False
    assert payload["data"]["config_or_secrets_touched"] is False
    assert "market_ticks" in payload["data"]["preserved_fact_tables"]
    assert conn.sql == [
        (
            "SELECT parent.relname AS parent, child.relname AS partition FROM pg_inherits "
            "JOIN pg_class parent ON parent.oid = pg_inherits.inhparent "
            "JOIN pg_class child ON child.oid = pg_inherits.inhrelid "
            "WHERE parent.relname = ANY(%s) ORDER BY parent.relname ASC, child.relname ASC"
        )
    ]
    assert payload["data"]["affected_partitions"] == []


def test_backfill_watchlist_signal_stats_dispatches_to_repository(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    watchlist_intel = _FakeWatchlistIntel()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(watchlist_intel=watchlist_intel)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(
        ["ops", "backfill-watchlist-signal-stats", "--batch-size", "5000", "--max-batches", "1"],
        stdout=stdout,
    )

    assert code == 0
    assert watchlist_intel.calls == [
        {
            "batch_size": 5000,
            "after_received_at_ms": None,
            "after_event_id": None,
            "dry_run": False,
            "commit": True,
        }
    ]
    assert json.loads(stdout.getvalue()) == {
        "ok": True,
        "data": {
            "processed": 3,
            "upserted": 2,
            "has_more": True,
            "last_cursor": {"received_at_ms": 1700000000123, "event_id": "event-3"},
            "next_after_cursor": "{\"event_id\":\"event-3\",\"received_at_ms\":1700000000123}",
            "batches": 1,
            "signal_events": 2,
            "normalized_handles": 1,
            "last_received_at_ms": 1700000000123,
            "last_event_id": "event-3",
            "dry_run": False,
        },
    }


def test_backfill_watchlist_signal_stats_dry_run_uses_non_mutating_call(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    watchlist_intel = _FakeWatchlistIntel()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(watchlist_intel=watchlist_intel)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(
        ["ops", "backfill-watchlist-signal-stats", "--batch-size", "5000", "--max-batches", "1", "--dry-run"],
        stdout=stdout,
    )

    assert code == 0
    assert watchlist_intel.calls[0]["dry_run"] is True
    assert watchlist_intel.calls[0]["commit"] is False
    assert json.loads(stdout.getvalue())["data"]["dry_run"] is True


def test_reset_token_radar_postgres_hard_cut_execute_runs_reset_sql(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeResetConn()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=conn))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "reset-token-radar-postgres-hard-cut",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["mode"] == "execute"
    assert payload["data"]["executed"] is True
    assert payload["data"]["fact_tables_touched"] is False
    assert conn.commits == 1
    assert [statement.split()[0] for statement in conn.sql] == [
        "DROP",
        "DROP",
        "TRUNCATE",
        "DELETE",
        "DELETE",
        "DELETE",
    ]


def test_ensure_postgres_partitions_execute_runs_partition_sql(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeResetConn()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=conn))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_769_987_654_321)
    stdout = io.StringIO()

    code = main(["ops", "ensure-postgres-partitions", "--execute"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["mode"] == "execute"
    assert payload["data"]["months"] == ["202602", "202603"]
    assert conn.commits == 1
    assert len(conn.sql) == 4


def test_drop_expired_postgres_partitions_execute_is_explicit_noop_without_retention(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    conn = _FakeResetConn()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(signals=SimpleNamespace(conn=conn))

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(["ops", "drop-expired-postgres-partitions", "--execute"], stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["executed"] is False
    assert payload["data"]["reason"] == "retention_not_configured"
    assert conn.sql == []


class _FakeWatchlistIntel:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def backfill_signal_stats_batch(
        self,
        *,
        after_received_at_ms: int | None,
        after_event_id: str | None,
        batch_size: int,
        dry_run: bool = False,
        commit: bool = True,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "batch_size": batch_size,
                "after_received_at_ms": after_received_at_ms,
                "after_event_id": after_event_id,
                "dry_run": dry_run,
                "commit": commit,
            }
        )
        return {
            "processed": 3,
            "signal_events": 2,
            "normalized_handles": 1,
            "last_received_at_ms": 1_700_000_000_123,
            "last_event_id": "event-3",
            "has_more": True,
        }


class _FakeResetConn:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[object] = []
        self.commits = 0

    def execute(self, sql: str, params: object = ()) -> _FakeResetConn:
        self.sql.append(" ".join(sql.split()))
        self.params.append(params)
        return self

    def fetchall(self) -> list[dict[str, str]]:
        return []

    def commit(self) -> None:
        self.commits += 1
