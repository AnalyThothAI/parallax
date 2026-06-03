from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

from parallax.domains.news_intel.repositories.news_repository import NewsRepository, _source_status_payload
from parallax.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
)
from parallax.domains.news_intel.services.source_quality_projection import (
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
        "useful_fact_rate": 0.6,
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
                    "useful_fact_rate": 0.4,
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
                "useful_item_count": 1,
                "latest_item_published_at_ms": NOW_MS,
            }
        ],
        window="24h",
        window_ms=DAY_MS,
        computed_at_ms=NOW_MS,
    )

    assert rows[0]["diagnostics_json"]["metrics"]["useful_fact_rate"] == 0.5


def test_source_quality_projection_worker_builds_rows_for_configured_windows() -> None:
    repo = FakeSourceQualityRepository()
    db = FakeSourceQualityDB(
        repo,
        claimed=[_source_quality_claim("coindesk", window="_refresh")],
    )
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=SimpleNamespace(
            batch_size=100,
            statement_timeout_seconds=30,
            windows=("4h", "24h"),
        ),
        db=db,
        telemetry=object(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    assert result.processed == 2
    assert db.sessions == ["news_source_quality_projection"]
    assert repo.list_calls == [
        {"source_windows": [("coindesk", "4h"), ("coindesk", "24h")], "now_ms": NOW_MS},
    ]
    assert [row["window"] for row in repo.rows] == ["4h", "24h"]
    assert repo.status_windows == ["4h"]
    assert all(row["source_id"] == "coindesk" for row in repo.rows)
    assert db.dirty.marked_done == [[_source_quality_claim("coindesk", window="_refresh")]]


def test_source_quality_projection_worker_empty_dirty_queue_does_not_scan_sources() -> None:
    repo = FakeSourceQualityRepository()
    db = FakeSourceQualityDB(repo, claimed=[])
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

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert repo.list_calls == []


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
            "latest_item_published_at_ms": NOW_MS - 40_000,
            "latest_item_fetched_at_ms": NOW_MS - 30_000,
            "latest_fetch_run_json": {
                "status": "failed",
                "started_at_ms": NOW_MS - 10_000,
                "finished_at_ms": NOW_MS - 9_000,
                "http_status": 503,
                "fetched_count": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "duplicate_count": 0,
                "error": "upstream timeout",
            },
            "last_success_at_ms": NOW_MS - 50_000,
            "next_fetch_after_ms": 0,
            "consecutive_failures": 1,
            "last_error": "upstream timeout",
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
                "diagnostics_json": {
                    "counts": {"fetch_run_count": 4},
                    "status": "healthy",
                },
                "projection_version": SOURCE_QUALITY_PROJECTION_VERSION,
            },
        }
    )

    assert payload["coverage_tags"] == ["crypto_market"]
    assert payload["quality"]["diagnostics_json"]["status"] == "healthy"
    assert payload["latest_quality_counts"] == {"fetch_run_count": 4}
    assert payload["latest_item_published_at_ms"] == NOW_MS - 40_000
    assert payload["latest_item_fetched_at_ms"] == NOW_MS - 30_000
    assert payload["last_seen_at_ms"] == NOW_MS - 30_000
    assert payload["latest_fetch_run"] == {
        "status": "failed",
        "started_at_ms": NOW_MS - 10_000,
        "finished_at_ms": NOW_MS - 9_000,
        "http_status": 503,
        "fetched_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "duplicate_count": 0,
        "error": "upstream timeout",
    }
    assert payload["provider_health"] == {
        "status": "failing",
        "reason": "consecutive_failures",
        "last_error": "upstream timeout",
        "consecutive_failures": 1,
        "last_success_at_ms": NOW_MS - 50_000,
        "last_seen_at_ms": NOW_MS - 30_000,
    }
    assert payload["provider_capability_tags"] == [
        "poll_primary_items",
        "http_cache",
        "high_trust",
    ]
    json.dumps(payload)


def test_source_status_payload_redacts_secret_error_fragments() -> None:
    secret_error = (
        "GET https://api.example.test/feed?api_key=sk-live&token=raw-token\n"
        "https://api-token@example.test failed\n"
        "upstream says Bearer bearer-secret expired\n"
        "Authorization: Basic basic-secret\n"
        "Cookie: sid=session-secret; refresh=refresh-secret\n"
        "api_key='quoted secret with spaces'\n"
        "postgres://user:pg-secret@db"
    )

    payload = _source_status_payload(
        {
            "source_id": "coindesk",
            "provider_type": "rss",
            "source_domain": "coindesk.com",
            "source_name": "CoinDesk",
            "source_role": "specialist_media",
            "trust_tier": "high",
            "coverage_tags_json": [],
            "source_quality_status": "unknown",
            "enabled": True,
            "managed_by_config": True,
            "refresh_interval_seconds": 300,
            "item_count": 0,
            "next_fetch_after_ms": 0,
            "consecutive_failures": 1,
            "last_error": secret_error,
            "latest_fetch_run_json": {
                "status": "failed",
                "started_at_ms": NOW_MS,
                "finished_at_ms": NOW_MS + 1,
                "error": secret_error,
            },
            "latest_quality_json": None,
        }
    )

    returned_errors = (
        payload["last_error"],
        payload["provider_health"]["last_error"],
        payload["latest_fetch_run"]["error"],
    )
    for returned_error in returned_errors:
        assert returned_error is not None
        assert "sk-live" not in returned_error
        assert "raw-token" not in returned_error
        assert "api-token" not in returned_error
        assert "bearer-secret" not in returned_error
        assert "basic-secret" not in returned_error
        assert "session-secret" not in returned_error
        assert "refresh-secret" not in returned_error
        assert "quoted secret" not in returned_error
        assert "pg-secret" not in returned_error
        assert "<redacted>" in returned_error


def test_source_status_payload_marks_disabled_and_api_backed_capabilities() -> None:
    payload = _source_status_payload(
        {
            "source_id": "cryptopanic",
            "provider_type": "cryptopanic",
            "source_domain": "cryptopanic.com",
            "source_name": "CryptoPanic",
            "source_role": "aggregator",
            "trust_tier": "standard",
            "coverage_tags_json": [],
            "source_quality_status": "unknown",
            "enabled": False,
            "managed_by_config": True,
            "refresh_interval_seconds": 300,
            "item_count": 0,
            "next_fetch_after_ms": 0,
            "consecutive_failures": 0,
            "last_error": "disabled by config",
            "latest_quality_json": None,
        }
    )

    assert payload["last_seen_at_ms"] is None
    assert payload["latest_fetch_run"] is None
    assert payload["latest_quality_counts"] == {}
    assert payload["provider_health"] == {
        "status": "disabled",
        "reason": "source_disabled",
        "last_error": "disabled by config",
        "consecutive_failures": 0,
        "last_success_at_ms": None,
        "last_seen_at_ms": None,
    }
    assert payload["provider_capability_tags"] == ["poll_primary_items", "api_backed"]


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


def test_source_quality_repository_query_uses_narrow_item_and_fact_hotpaths() -> None:
    conn = CapturingQualityConnection()
    repo = NewsRepository(conn)

    rows = repo.list_source_quality_inputs_for_targets(source_windows=[("coindesk", "24h")], now_ms=NOW_MS)

    assert rows == []
    query = next(sql for sql, _ in conn.calls if "WITH source_rows AS" in sql)
    normalized_query = " ".join(query.split())
    assert "SELECT items.*" not in query
    assert (
        "SELECT items.news_item_id, items.source_id, items.published_at_ms, items.fetched_at_ms, "
        "items.lifecycle_status FROM source_rows AS sources JOIN news_items AS items"
    ) in normalized_query
    assert "JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id" in normalized_query
    assert "news_context_items" not in normalized_query
    assert "context_items" not in normalized_query


def test_source_status_query_uses_preaggregated_source_hotpaths() -> None:
    conn = CapturingQualityConnection()
    repo = NewsRepository(conn)

    rows = repo.list_source_status()

    assert rows == []
    query = conn.calls[0][0]
    normalized_query = " ".join(query.split())
    assert "WITH edge_item_aggregate AS" in query
    assert "page_row_aggregate AS" in query
    assert "latest_fetch_run AS" in query
    assert "LEFT JOIN LATERAL" not in query
    assert "COUNT(DISTINCT edges.news_item_id)::int AS canonical_item_count" in normalized_query
    assert "COUNT(DISTINCT rows.row_id)::int AS serving_row_count" in normalized_query
    assert "ORDER BY fetch_runs.source_id, fetch_runs.started_at_ms DESC, fetch_runs.fetch_run_id DESC" in (
        normalized_query
    )


def _source_quality_claim(
    source_id: str,
    *,
    window: str,
    payload_hash: str = "hash",
    attempt_count: int = 1,
) -> dict[str, object]:
    return {
        "projection_name": "source_quality",
        "target_kind": "source",
        "target_id": source_id,
        "window": window,
        "payload_hash": payload_hash,
        "lease_owner": "news_source_quality_projection",
        "attempt_count": attempt_count,
    }


class FakeSourceQualityDB:
    def __init__(self, repo: FakeSourceQualityRepository, *, claimed: list[dict[str, object]]) -> None:
        self.repo = repo
        self.conn = CapturingQualityConnection()
        self.dirty = FakeDirtyTargets(claimed)
        self.sessions: list[str] = []

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        assert statement_timeout_seconds == 30
        self.sessions.append(name)
        yield SimpleNamespace(news=self.repo, news_projection_dirty_targets=self.dirty, conn=self.conn)


class FakeSourceQualityRepository:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, int]] = []
        self.rows: list[dict[str, object]] = []

        self.status_windows: list[str | None] = []

    def list_source_quality_inputs_for_targets(self, *, source_windows, now_ms: int):
        normalized = [(str(source_id), str(window)) for source_id, window in source_windows]
        self.list_calls.append({"source_windows": normalized, "now_ms": now_ms})
        return [
            {
                "source_id": source_id,
                "window": window,
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
                "useful_item_count": 1,
                "latest_item_published_at_ms": now_ms,
                "median_lag_ms": 0,
            }
            for source_id, window in normalized
        ]

    def replace_source_quality_rows(self, *, rows, status_window: str | None = None, commit: bool = True) -> list[str]:
        assert commit is False
        self.status_windows.append(status_window)
        self.rows.extend(dict(row) for row in rows)
        return []

    def list_news_item_ids_for_sources(self, *, source_ids):
        return []


class FakeDirtyTargets:
    def __init__(self, claimed: list[dict[str, object]]) -> None:
        self.claimed = [dict(row) for row in claimed]
        self.marked_done: list[list[dict[str, object]]] = []
        self.enqueued: list[dict[str, object]] = []

    def claim_due(self, **kwargs):
        assert kwargs["projection_name"] == "source_quality"
        assert kwargs["commit"] is False
        return [dict(row) for row in self.claimed[: kwargs["limit"]]]

    def mark_done(self, rows, *, now_ms: int, commit: bool = True):
        assert commit is False
        self.marked_done.append([dict(row) for row in rows])
        return len(rows)

    def mark_error(
        self,
        rows,
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        count_attempt: bool = True,
        commit: bool = True,
    ):
        del count_attempt
        raise AssertionError(f"source quality worker should not mark error: {error}")

    def enqueue_targets(self, rows, *, reason: str, now_ms: int, commit: bool = True, due_at_ms: int | None = None):
        self.enqueued.append(
            {
                "rows": [dict(row) for row in rows],
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
                "due_at_ms": due_at_ms,
            }
        )
        return len(rows)


class CapturingQualityConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.commits = 0

    def execute(self, sql: str, params: object = None) -> CapturingQualityCursor:
        self.calls.append((sql, params))
        return CapturingQualityCursor()

    def commit(self) -> None:
        self.commits += 1

    @contextmanager
    def transaction(self):
        yield


class CapturingQualityCursor:
    def fetchall(self):
        return []
