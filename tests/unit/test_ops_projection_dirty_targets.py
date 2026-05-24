from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from gmgn_twitter_intel.app.ops.projection_dirty_targets import enqueue_projection_dirty_targets
from gmgn_twitter_intel.app.surfaces.cli.parser import build_parser

NOW_MS = 1_779_000_000_000


def test_enqueue_projection_dirty_targets_dry_run_reports_counts_without_writes() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        domain="all",
        execute=False,
        now_ms=NOW_MS,
        source_quality_windows=("4h", "24h"),
    )

    assert result["execute"] is False
    assert result["equity"]["company_event_targets"] == 8
    assert result["equity"]["expected_event_targets"] == 1
    assert result["news"]["news_item_targets"] == 4
    assert result["news"]["source_quality_targets"] == 4
    assert repos.equity_dirty.enqueued == []
    assert repos.news_dirty.enqueued == []
    assert repos.conn.transactions == 0


def test_enqueue_projection_dirty_targets_execute_enqueues_only_dirty_targets() -> None:
    repos = FakeRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        domain="all",
        execute=True,
        now_ms=NOW_MS,
        source_quality_windows=("4h", "24h"),
    )

    assert result["execute"] is True
    assert repos.conn.transactions == 1
    assert [call["reason"] for call in repos.equity_dirty.enqueued] == [
        "ops_projection_dirty_repair",
        "ops_projection_dirty_repair",
    ]
    assert repos.equity_dirty.enqueued[0]["rows"] == [
        {"projection_name": "story", "target_kind": "company_event", "target_id": "event-1"},
        {"projection_name": "page", "target_kind": "company_event", "target_id": "event-1"},
        {"projection_name": "timeline", "target_kind": "company_event", "target_id": "event-1"},
        {"projection_name": "alert", "target_kind": "company_event", "target_id": "event-1"},
        {"projection_name": "story", "target_kind": "company_event", "target_id": "event-2"},
        {"projection_name": "page", "target_kind": "company_event", "target_id": "event-2"},
        {"projection_name": "timeline", "target_kind": "company_event", "target_id": "event-2"},
        {"projection_name": "alert", "target_kind": "company_event", "target_id": "event-2"},
    ]
    assert repos.equity_dirty.enqueued[1]["rows"] == [
        {"projection_name": "calendar", "target_kind": "expected_event", "target_id": "expected-1"}
    ]
    assert repos.news_dirty.enqueued[0]["rows"] == [
        {"projection_name": "story", "target_kind": "news_item", "target_id": "news-1"},
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"},
        {"projection_name": "story", "target_kind": "news_item", "target_id": "news-2"},
        {"projection_name": "page", "target_kind": "news_item", "target_id": "news-2"},
    ]
    assert repos.news_dirty.enqueued[1]["rows"] == [
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "4h"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "24h"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-2", "window": "4h"},
        {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-2", "window": "24h"},
    ]


def test_enqueue_projection_dirty_targets_parser_requires_explicit_mode() -> None:
    args = build_parser().parse_args(["ops", "enqueue-projection-dirty-targets", "--domain", "news", "--dry-run"])

    assert args.command == "ops"
    assert args.ops_command == "enqueue-projection-dirty-targets"
    assert args.domain == "news"
    assert args.dry_run is True
    assert args.execute is False


class FakeRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.equity_dirty = FakeDirtyRepo()
        self.news_dirty = FakeDirtyRepo()
        self.equity_projection_dirty_targets = self.equity_dirty
        self.news_projection_dirty_targets = self.news_dirty


class FakeConn:
    def __init__(self) -> None:
        self.transactions = 0

    def execute(self, sql: str) -> FakeCursor:
        if "FROM equity_company_events" in sql:
            return FakeCursor([{"company_event_id": "event-1"}, {"company_event_id": "event-2"}])
        if "FROM equity_expected_events" in sql:
            return FakeCursor([{"expected_event_id": "expected-1"}])
        if "FROM news_items" in sql:
            return FakeCursor([{"news_item_id": "news-1"}, {"news_item_id": "news-2"}])
        if "FROM news_sources" in sql:
            return FakeCursor([{"source_id": "source-1"}, {"source_id": "source-2"}])
        raise AssertionError(f"unexpected SQL: {sql}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.transactions += 1
        yield


class FakeCursor:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, str]]:
        return list(self.rows)


class FakeDirtyRepo:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(self, rows: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool = True) -> int:
        self.enqueued.append(
            {
                "rows": [dict(row) for row in rows],
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return len(rows)
