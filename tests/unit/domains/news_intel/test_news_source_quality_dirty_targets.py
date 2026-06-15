from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from parallax.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
)
from parallax.platform.config.settings import NewsSourceQualityProjectionWorkerSettings

NOW_MS = 1_779_000_000_000


def test_source_quality_worker_empty_dirty_queue_does_not_scan_sources() -> None:
    repos = FakeRepos(claimed=[])
    worker = _worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert repos.news.scoped_calls == []
    assert repos.news.broad_scan_calls == 0


def test_source_quality_worker_projects_claimed_source_window_and_reschedules_target() -> None:
    claim = _claim("source-1", window="24h")
    repos = FakeRepos(claimed=[claim])
    worker = _worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["rescheduled"] == 1
    assert repos.news.scoped_calls == [[("source-1", "24h")]]
    assert [row["source_id"] for row in repos.news.replaced_rows] == ["source-1"]
    assert repos.dirty.marked_done == [[claim]]
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "24h",
                    "due_at_ms": NOW_MS + 60 * 60 * 1000,
                    "source_watermark_ms": NOW_MS,
                }
            ],
            "reason": "source_quality_window_due",
            "now_ms": NOW_MS,
            "commit": False,
            "due_at_ms": NOW_MS + 60 * 60 * 1000,
        }
    ]


def test_source_quality_worker_reads_formal_settings_for_claim_session_windows_and_retry() -> None:
    settings = _source_quality_projection_settings(
        batch_size=7,
        lease_ms=45_000,
        retry_ms=90_000,
        statement_timeout_seconds=17,
        windows=("7d",),
    )
    repos = FakeRepos(claimed=[_claim("source-1", window="_refresh")], expected_status_window="7d")
    worker = _worker(repos, settings=settings, expected_statement_timeout=17)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["windows"] == ("7d",)
    assert repos.news.scoped_calls == [[("source-1", "7d")]]
    assert repos.dirty.claim_calls == [
        {
            "projection_name": "source_quality",
            "limit": 7,
            "lease_ms": 45_000,
            "now_ms": NOW_MS,
            "lease_owner": "news_source_quality_projection",
            "commit": False,
        }
    ]

    error_repos = FakeRepos(
        claimed=[_claim("source-1", window="_refresh")],
        expected_status_window="7d",
        input_error=RuntimeError("boom"),
    )
    error_worker = _worker(error_repos, settings=settings, expected_statement_timeout=17)

    error_result = error_worker.run_once_sync(now_ms=NOW_MS)

    assert error_result.failed == 1
    assert error_repos.dirty.error_calls == [
        {
            "rows": [_claim("source-1", window="_refresh")],
            "error": "boom",
            "retry_ms": 90_000,
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]


def _worker(
    repos: FakeRepos,
    *,
    settings: NewsSourceQualityProjectionWorkerSettings | None = None,
    expected_statement_timeout: float = 30,
) -> NewsSourceQualityProjectionWorker:
    return NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=settings or _source_quality_projection_settings(),
        db=FakeDB(repos, expected_statement_timeout=expected_statement_timeout),
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )


def _source_quality_projection_settings(**overrides: Any) -> NewsSourceQualityProjectionWorkerSettings:
    payload: dict[str, Any] = {
        "batch_size": 10,
        "lease_ms": 60_000,
        "retry_ms": 30_000,
        "statement_timeout_seconds": 30,
        "windows": ("24h",),
    }
    payload.update(overrides)
    return NewsSourceQualityProjectionWorkerSettings(**payload)


def _claim(source_id: str, *, window: str) -> dict[str, Any]:
    return {
        "projection_name": "source_quality",
        "target_kind": "source",
        "target_id": source_id,
        "window": window,
        "payload_hash": "hash",
        "lease_owner": "news_source_quality_projection",
        "attempt_count": 1,
    }


class FakeRepos:
    def __init__(
        self,
        *,
        claimed: list[dict[str, Any]],
        expected_status_window: str = "24h",
        input_error: Exception | None = None,
    ) -> None:
        self.conn = FakeConn()
        self.news = FakeNewsRepo(expected_status_window=expected_status_window, input_error=input_error)
        self.dirty = FakeDirtyRepo(claimed)
        self.news_projection_dirty_targets = self.dirty

    def transaction(self) -> Iterator[None]:
        return self.conn.transaction()


class FakeNewsRepo:
    def __init__(self, *, expected_status_window: str = "24h", input_error: Exception | None = None) -> None:
        self.scoped_calls: list[list[tuple[str, str]]] = []
        self.broad_scan_calls = 0
        self.replaced_rows: list[dict[str, Any]] = []
        self.expected_status_window = expected_status_window
        self.input_error = input_error

    def list_source_quality_inputs(self, *, window_ms: int, now_ms: int) -> list[dict[str, Any]]:
        self.broad_scan_calls += 1
        raise AssertionError("source quality worker must not call broad source scan")

    def list_source_quality_inputs_for_targets(
        self,
        *,
        source_windows: list[tuple[str, str]],
        now_ms: int,
    ) -> list[dict[str, Any]]:
        self.scoped_calls.append(list(source_windows))
        if self.input_error is not None:
            raise self.input_error
        return [
            {
                "source_id": source_id,
                "window": window,
                "fetch_run_count": 1,
                "fetch_success_count": 1,
                "items_fetched": 1,
                "items_inserted": 1,
                "items_duplicate": 0,
                "item_count": 1,
                "processed_item_count": 1,
                "mention_count": 1,
                "resolved_mention_count": 1,
                "fact_count": 1,
                "attention_fact_count": 0,
                "accepted_fact_count": 1,
                "ready_brief_count": 1,
                "useful_item_count": 1,
                "latest_item_published_at_ms": now_ms - 1_000,
                "median_lag_ms": 100,
            }
            for source_id, window in source_windows
        ]

    def replace_source_quality_rows(
        self,
        *,
        rows: list[Mapping[str, Any]],
        status_window: str,
        commit: bool = True,
    ) -> list[str]:
        assert status_window == self.expected_status_window
        assert commit is False
        self.replaced_rows.extend(dict(row) for row in rows)
        return []


class FakeDirtyRepo:
    def __init__(self, claimed: list[dict[str, Any]]) -> None:
        self.claimed = [dict(row) for row in claimed]
        self.claim_calls: list[dict[str, Any]] = []
        self.marked_done: list[list[dict[str, Any]]] = []
        self.marked_error: list[list[dict[str, Any]]] = []
        self.error_calls: list[dict[str, Any]] = []
        self.enqueued: list[dict[str, Any]] = []

    def claim_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        assert kwargs["projection_name"] == "source_quality"
        assert kwargs["commit"] is False
        self.claim_calls.append(dict(kwargs))
        return [dict(row) for row in self.claimed[: kwargs["limit"]]]

    def mark_done(self, rows: list[Mapping[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        assert commit is False
        self.marked_done.append([dict(row) for row in rows])
        return len(rows)

    def mark_error(
        self,
        rows: list[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        count_attempt: bool = True,
        commit: bool = True,
    ) -> int:
        del count_attempt
        self.marked_error.append([dict(row) for row in rows])
        self.error_calls.append(
            {
                "rows": [dict(row) for row in rows],
                "error": error,
                "retry_ms": retry_ms,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return len(rows)

    def enqueue_targets(
        self,
        rows: list[Mapping[str, Any]],
        *,
        reason: str,
        now_ms: int,
        commit: bool = True,
        due_at_ms: int | None = None,
    ) -> int:
        payload = {
            "rows": [dict(row) for row in rows],
            "reason": reason,
            "now_ms": now_ms,
            "commit": commit,
        }
        if due_at_ms is not None:
            payload["due_at_ms"] = due_at_ms
        self.enqueued.append(payload)
        return len(rows)


class FakeDB:
    def __init__(self, repos: FakeRepos, *, expected_statement_timeout: float = 30) -> None:
        self.repos = repos
        self.expected_statement_timeout = expected_statement_timeout

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None) -> Iterator[FakeRepos]:
        assert name == "news_source_quality_projection"
        assert statement_timeout_seconds == self.expected_statement_timeout
        yield self.repos


class FakeConn:
    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield
