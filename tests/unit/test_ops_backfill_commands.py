from __future__ import annotations

import io
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.cli import main


def test_backfill_token_radar_first_seen_dispatches_to_repository(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    token_radar = _FakeTokenRadar()

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(token_radar=token_radar)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    stdout = io.StringIO()

    code = main(
        ["ops", "backfill-token-radar-first-seen", "--batch-size", "5000", "--max-batches", "1"],
        stdout=stdout,
    )

    assert code == 0
    assert token_radar.calls == [{"batch_size": 5000, "after_computed_at_ms": None, "after_row_id": None}]
    assert json.loads(stdout.getvalue()) == {
        "ok": True,
        "data": {
            "processed": 3,
            "upserted": 2,
            "has_more": True,
            "last_cursor": {"computed_at_ms": 1700000000123, "row_id": "row-3"},
            "batches": 1,
            "rows_scanned": 3,
            "rows_upserted": 2,
        },
    }


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


def test_prune_token_radar_dry_run_reports_planned_rows(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    token_radar = _FakeRetentionTokenRadar(delete_results=[])

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(token_radar=token_radar)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "prune-token-radar",
            "--retention-days",
            "7",
            "--batch-size",
            "10000",
            "--max-batches",
            "1",
            "--dry-run",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["data"]["mode"] == "dry_run"
    assert payload["data"]["rows_planned"] == 2
    assert payload["data"]["rows_deleted"] == 0
    assert token_radar.delete_calls == []
    assert token_radar.retention_runs[0]["status"] == "dry_run"


def test_prune_token_radar_execute_deletes_bounded_batches(monkeypatch) -> None:
    from gmgn_twitter_intel.app.surfaces.cli.commands import ops as ops_module

    token_radar = _FakeRetentionTokenRadar(delete_results=[10_000])

    @contextmanager
    def fake_repositories(_settings: object):
        yield SimpleNamespace(token_radar=token_radar)

    monkeypatch.setattr(ops_module, "load_settings", lambda require_ws_token=False: SimpleNamespace())
    monkeypatch.setattr(ops_module, "repositories", fake_repositories)
    monkeypatch.setattr(ops_module, "_now_ms", lambda: 1_700_000_000_000)
    stdout = io.StringIO()

    code = main(
        [
            "ops",
            "prune-token-radar",
            "--retention-days",
            "7",
            "--batch-size",
            "10000",
            "--max-batches",
            "1",
            "--execute",
        ],
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["data"]["mode"] == "execute"
    assert payload["data"]["rows_planned"] == 2
    assert payload["data"]["rows_deleted"] == 10_000
    assert token_radar.delete_calls == [{"cutoff_ms": 1_699_395_200_000, "batch_size": 10_000}]
    assert token_radar.finished_runs[0]["status"] == "done"


class _FakeTokenRadar:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def backfill_first_seen_rows_batch(
        self,
        *,
        batch_size: int,
        after_computed_at_ms: int | None = None,
        after_row_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "batch_size": batch_size,
                "after_computed_at_ms": after_computed_at_ms,
                "after_row_id": after_row_id,
            }
        )
        return {
            "rows_scanned": 3,
            "rows_upserted": 2,
            "last_computed_at_ms": 1_700_000_000_123,
            "last_row_id": "row-3",
            "has_more": True,
        }


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


class _FakeRetentionTokenRadar:
    def __init__(self, *, delete_results: list[int]) -> None:
        self.delete_results = list(delete_results)
        self.retention_runs: list[dict[str, Any]] = []
        self.finished_runs: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []

    def plan_prunable_rows(self, *, cutoff_ms: int, limit: int) -> list[dict[str, Any]]:
        return [
            {"row_id": "row-1", "computed_at_ms": cutoff_ms - 1},
            {"row_id": "row-2", "computed_at_ms": cutoff_ms - 2},
        ][:limit]

    def protected_batch_counts(self) -> dict[str, int]:
        return {
            "protected_coverage_batches": 1,
            "protected_actual_latest_batches": 1,
        }

    def insert_retention_run(self, run: dict[str, Any]) -> dict[str, Any]:
        self.retention_runs.append(run)
        return run

    def delete_prunable_rows_batch(self, *, cutoff_ms: int, batch_size: int) -> int:
        self.delete_calls.append({"cutoff_ms": cutoff_ms, "batch_size": batch_size})
        return self.delete_results.pop(0) if self.delete_results else 0

    def finish_retention_run(
        self,
        run_id: str,
        *,
        status: str,
        rows_deleted: int,
        error: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "run_id": run_id,
            "status": status,
            "rows_deleted": rows_deleted,
            "error": error,
        }
        self.finished_runs.append(row)
        return row
