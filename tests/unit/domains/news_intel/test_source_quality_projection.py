from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository, _source_status_payload
from gmgn_twitter_intel.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
)
from gmgn_twitter_intel.domains.news_intel.services.source_quality_projection import (
    SOURCE_QUALITY_PROJECTION_VERSION,
    build_source_quality_row,
    build_source_quality_rows,
    quality_score,
    quality_status,
)

NOW_MS = 1_779_000_000_000
DAY_MS = 24 * 60 * 60 * 1000


def test_source_quality_score_is_deterministic() -> None:
    metrics = {
        "fetch_success_rate": 1.0,
        "process_success_rate": 1.0,
        "resolved_token_rate": 0.8,
        "brief_ready_rate": 0.5,
        "duplicate_rate": 0.2,
        "normalized_freshness": 0.9,
        "useful_fact_or_context_rate": 0.6,
    }

    row = build_source_quality_row(
        source_id="coindesk",
        window="24h",
        computed_at_ms=1_000,
        metrics=metrics,
        counts={"items_fetched": 10, "items_inserted": 8, "median_lag_ms": 500},
    )

    assert quality_score(metrics) == 82.5
    assert row["row_id"] == "news-source-quality:coindesk:24h"
    assert row["quality_score"] == 82.5
    assert row["projection_version"] == SOURCE_QUALITY_PROJECTION_VERSION
    assert row["diagnostics_json"]["metrics"] == metrics
    assert row["diagnostics_json"]["status"] == "healthy"


def test_build_source_quality_rows_derives_metrics_from_aggregate_inputs() -> None:
    rows = build_source_quality_rows(
        aggregate_inputs=[
            {
                "source_id": "coindesk",
                "fetch_run_count": 4,
                "fetch_success_count": 3,
                "items_fetched": 10,
                "items_inserted": 6,
                "items_duplicate": 2,
                "item_count": 5,
                "processed_item_count": 4,
                "mention_count": 4,
                "resolved_mention_count": 3,
                "attention_fact_count": 1,
                "accepted_fact_count": 2,
                "fact_count": 4,
                "ready_brief_count": 2,
                "context_item_count": 1,
                "useful_item_count": 2,
                "latest_item_published_at_ms": NOW_MS - 6 * 60 * 60 * 1000,
                "median_lag_ms": 3_000,
            }
        ],
        window="24h",
        window_ms=DAY_MS,
        computed_at_ms=NOW_MS,
    )

    assert rows == [
        {
            "row_id": "news-source-quality:coindesk:24h",
            "source_id": "coindesk",
            "window": "24h",
            "computed_at_ms": NOW_MS,
            "fetch_success_rate": 0.75,
            "items_fetched": 10,
            "items_inserted": 6,
            "duplicate_rate": 0.2,
            "process_success_rate": 0.8,
            "resolved_token_rate": 0.75,
            "attention_rate": 0.25,
            "accepted_fact_rate": 0.5,
            "brief_ready_rate": 0.4,
            "median_lag_ms": 3_000,
            "quality_score": 67.5,
            "diagnostics_json": {
                "counts": {
                    "accepted_fact_count": 2,
                    "attention_fact_count": 1,
                    "context_item_count": 1,
                    "fact_count": 4,
                    "fetch_run_count": 4,
                    "fetch_success_count": 3,
                    "items_duplicate": 2,
                    "items_fetched": 10,
                    "items_inserted": 6,
                    "item_count": 5,
                    "median_lag_ms": 3_000,
                    "mention_count": 4,
                    "processed_item_count": 4,
                    "ready_brief_count": 2,
                    "resolved_mention_count": 3,
                    "useful_item_count": 2,
                },
                "metrics": {
                    "accepted_fact_rate": 0.5,
                    "attention_rate": 0.25,
                    "brief_ready_rate": 0.4,
                    "duplicate_rate": 0.2,
                    "fetch_success_rate": 0.75,
                    "normalized_freshness": 0.75,
                    "process_success_rate": 0.8,
                    "resolved_token_rate": 0.75,
                    "useful_fact_or_context_rate": 0.4,
                },
                "status": "watch",
                "window_ms": DAY_MS,
            },
            "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
        }
    ]


def test_quality_status_buckets_unknown_and_operational_ranges() -> None:
    assert quality_status(None) == "unknown"
    assert quality_status(24.99) == "poor"
    assert quality_status(25.0) == "degraded"
    assert quality_status(50.0) == "watch"
    assert quality_status(75.0) == "healthy"


def test_useful_item_count_is_not_double_counted_by_projection() -> None:
    rows = build_source_quality_rows(
        aggregate_inputs=[
            {
                "source_id": "coindesk",
                "fetch_run_count": 1,
                "fetch_success_count": 1,
                "items_fetched": 1,
                "items_inserted": 1,
                "items_duplicate": 0,
                "item_count": 2,
                "processed_item_count": 2,
                "mention_count": 0,
                "resolved_mention_count": 0,
                "fact_count": 1,
                "accepted_fact_count": 1,
                "attention_fact_count": 0,
                "ready_brief_count": 0,
                "context_item_count": 1,
                "useful_item_count": 1,
                "latest_item_published_at_ms": NOW_MS,
            }
        ],
        window="24h",
        window_ms=DAY_MS,
        computed_at_ms=NOW_MS,
    )

    assert rows[0]["diagnostics_json"]["metrics"]["useful_fact_or_context_rate"] == 0.5


def test_source_quality_projection_worker_builds_rows_for_configured_windows() -> None:
    repo = FakeSourceQualityRepository()
    db = FakeSourceQualityDB(repo)
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=SimpleNamespace(
            batch_size=100,
            statement_timeout_seconds=30,
            windows=("24h", "7d"),
        ),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    assert result.processed == 2
    assert db.sessions == ["news_source_quality_projection"]
    assert repo.list_calls == [
        {"window_ms": DAY_MS, "now_ms": NOW_MS},
        {"window_ms": 7 * DAY_MS, "now_ms": NOW_MS},
    ]
    assert [row["window"] for row in repo.rows] == ["24h", "7d"]
    assert repo.status_windows == ["24h", "24h"]
    assert all(row["source_id"] == "coindesk" for row in repo.rows)


def test_source_status_payload_uses_plain_quality_diagnostics() -> None:
    payload = _source_status_payload(
        {
            "source_id": "coindesk",
            "provider_type": "rss",
            "source_domain": "coindesk.com",
            "source_name": "CoinDesk",
            "source_role": "specialist_media",
            "trust_tier": "high",
            "coverage_tags_json": ["crypto_market"],
            "source_quality_status": "healthy",
            "enabled": True,
            "managed_by_config": True,
            "refresh_interval_seconds": 300,
            "item_count": 4,
            "next_fetch_after_ms": 0,
            "consecutive_failures": 0,
            "latest_quality_json": {
                "row_id": "news-source-quality:coindesk:24h",
                "source_id": "coindesk",
                "window": "24h",
                "computed_at_ms": NOW_MS,
                "fetch_success_rate": 1,
                "items_fetched": 10,
                "items_inserted": 8,
                "duplicate_rate": 0.2,
                "process_success_rate": 1,
                "resolved_token_rate": 0.75,
                "attention_rate": 0.25,
                "accepted_fact_rate": 0.5,
                "brief_ready_rate": 0.5,
                "median_lag_ms": 500,
                "quality_score": 82.5,
                "diagnostics_json": {"status": "healthy"},
                "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
            },
        }
    )

    assert payload["coverage_tags"] == ["crypto_market"]
    assert payload["quality"]["diagnostics_json"] == {"status": "healthy"}
    json.dumps(payload)


def test_replace_source_quality_rows_updates_source_status_freshness() -> None:
    conn = CapturingQualityConnection()
    repo = NewsRepository(conn)

    repo.replace_source_quality_rows(
        rows=[
            {
                "row_id": "news-source-quality:coindesk:24h",
                "source_id": "coindesk",
                "window": "24h",
                "computed_at_ms": NOW_MS,
                "fetch_success_rate": 1,
                "items_fetched": 10,
                "items_inserted": 8,
                "duplicate_rate": 0.2,
                "process_success_rate": 1,
                "resolved_token_rate": 0.75,
                "attention_rate": 0.25,
                "accepted_fact_rate": 0.5,
                "brief_ready_rate": 0.5,
                "median_lag_ms": 500,
                "quality_score": 82.5,
                "diagnostics_json": {"status": "healthy"},
                "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
            }
        ],
        status_window="24h",
    )

    status_update = next(sql for sql, _ in conn.calls if "UPDATE news_sources" in sql)
    status_params = next(params for sql, params in conn.calls if "UPDATE news_sources" in sql)
    assert "updated_at_ms = GREATEST(updated_at_ms, %s)" in status_update
    assert "source_quality_status IS DISTINCT FROM %s" in status_update
    assert status_params == ("healthy", NOW_MS, "coindesk", "healthy")
    assert conn.commits == 1


class FakeSourceQualityDB:
    def __init__(self, repo: FakeSourceQualityRepository) -> None:
        self.repo = repo
        self.sessions: list[str] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert statement_timeout_seconds == 30
        self.sessions.append(name)
        yield SimpleNamespace(news=self.repo)


class FakeSourceQualityRepository:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, int]] = []
        self.rows: list[dict[str, object]] = []

        self.status_windows: list[str | None] = []

    def list_source_quality_inputs(self, *, window_ms: int, now_ms: int):
        self.list_calls.append({"window_ms": window_ms, "now_ms": now_ms})
        return [
            {
                "source_id": "coindesk",
                "fetch_run_count": 1,
                "fetch_success_count": 1,
                "items_fetched": 2,
                "items_inserted": 1,
                "items_duplicate": 1,
                "item_count": 1,
                "processed_item_count": 1,
                "mention_count": 1,
                "resolved_mention_count": 1,
                "attention_fact_count": 0,
                "accepted_fact_count": 1,
                "fact_count": 1,
                "ready_brief_count": 1,
                "context_item_count": 0,
                "useful_item_count": 1,
                "latest_item_published_at_ms": now_ms,
                "median_lag_ms": 0,
            }
        ]

    def replace_source_quality_rows(self, *, rows, status_window: str | None = None, commit: bool = True) -> None:
        assert commit is True
        self.status_windows.append(status_window)
        self.rows.extend(dict(row) for row in rows)


class CapturingQualityConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.commits = 0

    def execute(self, sql: str, params: object = None) -> CapturingQualityCursor:
        self.calls.append((sql, params))
        return CapturingQualityCursor()

    def commit(self) -> None:
        self.commits += 1


class CapturingQualityCursor:
    pass
