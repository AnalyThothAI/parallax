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
    assert token_radar.calls == [{"batch_size": 5000, "after_key": None}]
    assert json.loads(stdout.getvalue()) == {
        "ok": True,
        "data": {
            "processed": 2,
            "upserted": 2,
            "has_more": True,
            "last_cursor": ["v1", "1h", "all", "token", "solana:abc"],
            "batches": 1,
            "rows_upserted": 2,
            "next_after_key": ["v1", "1h", "all", "token", "solana:abc"],
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


class _FakeTokenRadar:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def backfill_first_seen_from_history(
        self,
        *,
        batch_size: int,
        after_key: tuple[str, str, str, str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"batch_size": batch_size, "after_key": after_key})
        return {
            "rows_upserted": 2,
            "next_after_key": ("v1", "1h", "all", "token", "solana:abc"),
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
