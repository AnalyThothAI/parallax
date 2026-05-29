from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.projection_dirty_targets import enqueue_projection_dirty_targets
from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
from gmgn_twitter_intel.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_item_brief_worker import NewsItemBriefWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
)
from gmgn_twitter_intel.domains.news_intel.types.source_provider import (
    NewsProviderFetchResult,
    NewsProviderObservation,
    NewsSourceSnapshot,
)
from gmgn_twitter_intel.domains.token_intel.interfaces import TokenIdentityLookupResult

NOW_MS = 1_779_000_000_000


def test_page_projection_worker_empty_dirty_queue_does_not_scan() -> None:
    repos = FakePageRepos(claimed=[])
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert result.notes["projected"] == 0
    assert repos.news.scan_calls == 0
    assert repos.news.loaded_ids == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == []


def test_page_projection_worker_loads_only_claimed_news_item_targets_and_marks_done_with_tokens() -> None:
    token_1 = _claim("news-1", payload_hash="hash-1", attempt_count=1)
    token_2 = _claim("news-2", payload_hash="hash-2", attempt_count=2)
    repos = FakePageRepos(claimed=[token_1, {**token_1}, token_2])
    repos.news.payloads = [_page_payload("news-2"), _page_payload("news-1")]
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 2
    assert result.notes["claimed"] == 3
    assert result.notes["projected"] == 2
    assert result.notes["deleted"] == 0
    assert repos.news.scan_calls == 0
    assert repos.news.loaded_ids == ["news-1", "news-2"]
    assert repos.news.replacements == [
        {
            "news_item_ids": ["news-1", "news-2"],
            "row_ids": ["news-1", "news-2"],
            "commit": False,
        }
    ]
    assert repos.dirty.marked_done == [[token_1, token_1, token_2]]
    assert repos.dirty.marked_error == []


def test_page_projection_worker_marks_error_with_full_claim_token_when_projection_write_fails() -> None:
    token = _claim("news-1", payload_hash="hash-1", attempt_count=3)
    repos = FakePageRepos(claimed=[token])
    repos.news.payloads = [_page_payload("news-1")]
    repos.news.raise_on_replace = RuntimeError("write failed")
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["marked_error"] == 1
    assert repos.news.replacements == []
    assert repos.dirty.marked_done == []
    assert repos.dirty.marked_error == [[token]]


def test_page_projection_worker_deletes_missing_claimed_items_without_fallback_scan() -> None:
    token_1 = _claim("news-1")
    token_2 = _claim("news-deleted")
    repos = FakePageRepos(claimed=[token_1, token_2])
    repos.news.payloads = [_page_payload("news-1")]
    worker = _page_worker(repos)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 2
    assert result.notes["projected"] == 1
    assert result.notes["deleted"] == 1
    assert repos.news.scan_calls == 0
    assert repos.news.loaded_ids == ["news-1", "news-deleted"]
    assert repos.news.replacements == [
        {
            "news_item_ids": ["news-1", "news-deleted"],
            "row_ids": ["news-1"],
            "commit": False,
        }
    ]
    assert repos.dirty.marked_done == [[token_1, token_2]]


def test_load_items_for_page_projection_filters_target_items_before_projection_joins() -> None:
    conn = ScriptedConnection([[]])

    rows = NewsRepository(conn).load_items_for_page_projection(news_item_ids=["news-1", "news-2"])

    assert rows == []
    sql = conn.sql[-1]
    assert "WITH target_items AS (" in sql
    assert "WHERE items.news_item_id = ANY(%s::text[])" in sql
    assert "FROM target_items AS items" in sql
    assert sql.count("WHERE members.news_item_id = items.news_item_id") == 1
    assert "page.computed_at_ms" not in sql
    assert "page.projection_version" not in sql
    assert "HAVING page.row_id IS NULL" not in sql
    assert conn.params[-1] == (["news-1", "news-2"],)


def test_fetch_worker_enqueues_news_item_and_source_quality_dirty_for_inserted_and_updated_news_items_only() -> None:
    source = _source()
    repos = FakeFetchRepos(
        source=source,
        news_statuses=[
            {"news_item_id": "news-inserted", "status": "inserted"},
            {"news_item_id": "news-updated", "status": "updated"},
            {"news_item_id": "news-duplicate", "status": "duplicate"},
        ],
    )
    worker = _fetch_worker(repos, observations=[_observation("a"), _observation("b"), _observation("c")])

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 2
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {"projection_name": "story", "target_kind": "news_item", "target_id": "news-inserted"},
                {"projection_name": "story", "target_kind": "news_item", "target_id": "news-updated"},
                {"projection_name": "page", "target_kind": "news_item", "target_id": "news-inserted"},
                {"projection_name": "page", "target_kind": "news_item", "target_id": "news-updated"},
            ],
            "reason": "news_item_written",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "24h",
                },
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "7d",
                },
            ],
            "reason": "news_fetch_run_finished",
            "now_ms": NOW_MS,
            "commit": False,
        },
    ]
    assert "tx:upsert_canonical_news_item" in repos.conn.events
    assert "tx:dirty:news_item_written" in repos.conn.events
    assert "autocommit:dirty:news_item_written" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events


def test_fetch_worker_enqueues_page_and_source_quality_dirty_for_material_source_metadata_changes_only() -> None:
    source = _source()
    repos = FakeFetchRepos(
        source=source,
        reconcile_rows=[
            {"source_id": "source-noop", "status": "duplicate"},
            {"source_id": "source-updated", "status": "updated"},
        ],
        existing_items_by_source={"source-updated": ["news-1", "news-2"]},
    )
    wake_bus = FakeWakeBus(transaction_events=repos.conn.events)
    worker = _fetch_worker(repos, observations=[], wake_bus=wake_bus)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert repos.news_item_ids_requested_for_sources == [["source-updated"]]
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"},
                {"projection_name": "page", "target_kind": "news_item", "target_id": "news-2"},
            ],
            "reason": "source_metadata_changed",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-updated",
                    "window": "24h",
                },
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-updated",
                    "window": "7d",
                },
            ],
            "reason": "source_metadata_changed",
            "now_ms": NOW_MS,
            "commit": False,
        },
        {
            "rows": [
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "24h",
                },
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "7d",
                },
            ],
            "reason": "news_fetch_run_finished",
            "now_ms": NOW_MS,
            "commit": False,
        },
    ]
    assert "tx:source_reconcile" in repos.conn.events
    assert "tx:dirty:source_metadata_changed" in repos.conn.events
    assert "autocommit:dirty:source_metadata_changed" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events
    assert wake_bus.notifications == [
        {
            "count": 2,
            "reason": "source_metadata_changed",
            "events_before_notify": [
                "begin",
                "tx:source_reconcile",
                "tx:dirty:source_metadata_changed",
                "tx:dirty:source_metadata_changed",
                "commit",
            ],
        }
    ]


def test_news_repository_source_reconcile_noop_does_not_update_timestamp() -> None:
    source = _source()
    existing = {
        **source,
        "source_role": "observed_source",
        "trust_tier": "standard",
        "managed_by_config": True,
        "enabled": True,
        "refresh_interval_seconds": 300,
        "coverage_tags_json": [],
        "asset_universe_json": [],
        "authority_scope_json": {},
        "fetch_policy_json": {},
        "context_policy_json": {},
        "cost_policy_json": {},
        "updated_at_ms": NOW_MS - 1_000,
    }
    conn = ScriptedConnection([[existing], existing, []])

    rows = NewsRepository(conn).reconcile_configured_sources([source], now_ms=NOW_MS, commit=False)

    assert rows[0]["status"] == "duplicate"
    assert rows[0]["updated_at_ms"] == NOW_MS - 1_000
    assert not any("ON CONFLICT (source_id) DO UPDATE" in sql for sql in conn.sql)


def test_news_repository_material_source_reconcile_reports_updated_status() -> None:
    source = {**_source(), "source_name": "Example Renamed"}
    existing = {
        **_source(),
        "source_role": "observed_source",
        "trust_tier": "standard",
        "managed_by_config": True,
        "enabled": True,
        "refresh_interval_seconds": 300,
        "coverage_tags_json": [],
        "asset_universe_json": [],
        "authority_scope_json": {},
        "fetch_policy_json": {},
        "context_policy_json": {},
        "cost_policy_json": {},
        "updated_at_ms": NOW_MS - 1_000,
    }
    updated = {**existing, "source_name": "Example Renamed", "updated_at_ms": NOW_MS}
    conn = ScriptedConnection([[existing], updated, []])

    rows = NewsRepository(conn).reconcile_configured_sources([source], now_ms=NOW_MS, commit=False)

    assert rows[0]["status"] == "updated"
    assert rows[0]["updated_at_ms"] == NOW_MS
    assert any("ON CONFLICT (source_id) DO UPDATE SET" in sql for sql in conn.sql)


def test_process_worker_enqueues_story_page_and_source_quality_dirty_in_same_transaction_after_writes() -> None:
    repos = FakeProcessRepos()
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=FakeDB("news_item_process", repos),
        telemetry=object(),
        identity_lookup=FakeIdentityLookup(),
        wake_bus=None,
        source_quality_windows=("4h", "24h"),
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert repos.news.write_commits == [False, False, False, False, False]
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {"projection_name": "story", "target_kind": "news_item", "target_id": "news-1"},
                {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"},
                {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "4h"},
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "24h",
                },
            ],
            "reason": "news_item_processed",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert "tx:replace_item_entities" in repos.conn.events
    assert "tx:dirty:news_item_processed" in repos.conn.events
    assert "autocommit:dirty:news_item_processed" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events


def test_ops_projection_repair_enqueues_provider_signal_brief_input_dirty_target() -> None:
    repos = FakeOpsProjectionRepos()

    result = enqueue_projection_dirty_targets(
        repos,
        domain="news",
        execute=True,
        now_ms=NOW_MS,
        projection="brief_input",
        since_ms=NOW_MS - 60_000,
    )

    assert result["news"]["news_item_targets"] == 1
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {
                    "projection_name": "brief_input",
                    "target_kind": "news_item",
                    "target_id": "news-provider",
                    "source_watermark_ms": NOW_MS - 1_000,
                    "priority": 5,
                }
            ],
            "reason": "ops_projection_dirty_repair",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]


def test_brief_worker_enqueues_page_and_source_quality_dirty_in_same_transaction_after_current_brief_write() -> None:
    repos = FakeBriefRepos()
    worker = object.__new__(NewsItemBriefWorker)
    WorkerAttrs = {
        "name": "news_item_brief",
        "settings": SimpleNamespace(statement_timeout_seconds=30),
        "db": FakeDB("news_item_brief", repos),
    }
    for key, value in WorkerAttrs.items():
        setattr(worker, key, value)
    packet = SimpleNamespace(
        news_item=SimpleNamespace(news_item_id="news-1"),
        input_hash="input-1",
    )

    worker._upsert_current(
        run_id="run-1",
        packet=packet,
        agent_config=SimpleNamespace(
            artifact_version_hash="artifact-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
        ),
        payload={"status": "ready", "direction": "bullish", "decision_class": "watch"},
        computed_at_ms=NOW_MS,
    )

    assert repos.news.brief_commits == [False]
    assert repos.dirty.enqueued == [
        {
            "rows": [
                {"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"},
                {
                    "projection_name": "source_quality",
                    "target_kind": "source",
                    "target_id": "source-1",
                    "window": "24h",
                },
                {"projection_name": "source_quality", "target_kind": "source", "target_id": "source-1", "window": "7d"},
            ],
            "reason": "news_item_brief_updated",
            "now_ms": NOW_MS,
            "commit": False,
        }
    ]
    assert "tx:upsert_news_item_agent_brief" in repos.conn.events
    assert "tx:dirty:news_item_brief_updated" in repos.conn.events
    assert "autocommit:dirty:news_item_brief_updated" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events


def test_source_quality_worker_enqueues_page_dirty_when_source_quality_status_changes() -> None:
    repos = FakeSourceQualityRepos()
    wake_bus = FakeWakeBus(transaction_events=repos.conn.events)
    worker = NewsSourceQualityProjectionWorker(
        name="news_source_quality_projection",
        settings=SimpleNamespace(windows=("24h",), statement_timeout_seconds=30),
        db=FakeDB("news_source_quality_projection", repos),
        telemetry=object(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["rescheduled"] == 1
    assert repos.news_item_ids_requested_for_sources == [["source-1"]]
    assert repos.dirty.enqueued == [
        {
            "rows": [{"projection_name": "page", "target_kind": "news_item", "target_id": "news-1"}],
            "reason": "source_quality_status_changed",
            "now_ms": NOW_MS,
            "commit": False,
        },
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
        },
    ]
    assert "tx:replace_source_quality_rows" in repos.conn.events
    assert "tx:dirty:source_quality_status_changed" in repos.conn.events
    assert "tx:dirty:source_quality_window_due" in repos.conn.events
    assert "autocommit:dirty:source_quality_status_changed" not in repos.conn.events
    assert "direct_commit" not in repos.conn.events
    assert wake_bus.notifications == [
        {
            "count": 1,
            "reason": "source_quality_status_changed",
            "events_before_notify": [
                "begin",
                "begin",
                "tx:replace_source_quality_rows",
                "tx:dirty:source_quality_status_changed",
                "tx:dirty:source_quality_window_due",
                "commit",
                "commit",
            ],
        }
    ]


def _page_worker(repos: FakePageRepos) -> NewsPageProjectionWorker:
    return NewsPageProjectionWorker(
        name="news_page_projection",
        settings=SimpleNamespace(batch_size=10, lease_ms=60_000, retry_ms=30_000, statement_timeout_seconds=30),
        db=FakeDB("news_page_projection", repos),
        telemetry=object(),
        wake_bus=None,
        clock_ms=lambda: NOW_MS,
    )


def _claim(news_item_id: str, *, payload_hash: str = "hash", attempt_count: int = 1) -> dict[str, Any]:
    return {
        "projection_name": "page",
        "target_kind": "news_item",
        "target_id": news_item_id,
        "window": "",
        "payload_hash": payload_hash,
        "lease_owner": "news_page_projection",
        "attempt_count": attempt_count,
    }


def _source_quality_claim(
    source_id: str,
    *,
    window: str = "24h",
    payload_hash: str = "hash",
    attempt_count: int = 1,
) -> dict[str, Any]:
    return {
        "projection_name": "source_quality",
        "target_kind": "source",
        "target_id": source_id,
        "window": window,
        "payload_hash": payload_hash,
        "lease_owner": "news_source_quality_projection",
        "attempt_count": attempt_count,
    }


def _page_payload(news_item_id: str) -> dict[str, Any]:
    return {
        "item": {
            "news_item_id": news_item_id,
            "title": f"Title {news_item_id}",
            "summary": "",
            "source_id": "source-1",
            "provider_type": "rss",
            "source_domain": "example.com",
            "source_name": "Example",
            "canonical_url": f"https://example.com/{news_item_id}",
            "published_at_ms": 1000,
            "lifecycle_status": "processed",
        },
        "story": None,
        "current_brief": None,
        "token_mentions": [],
        "fact_candidates": [],
    }


class FakePageRepos:
    def __init__(self, *, claimed: list[dict[str, Any]]) -> None:
        self.conn = FakeConn()
        self.news = FakePageNewsRepository()
        self.dirty = FakeDirtyRepository(claimed)
        self.news_projection_dirty_targets = self.dirty


class FakeOpsProjectionRepos:
    def __init__(self) -> None:
        self.conn = FakeOpsProjectionConn()
        self.dirty = FakeDirtyRepository(expected_projection_name=None)
        self.news_projection_dirty_targets = self.dirty


class FakeOpsProjectionConn:
    def execute(self, sql: str, _params: dict[str, Any] | None = None) -> Any:
        if "FROM news_items" in sql:
            return FakeRowsCursor(
                [
                    {
                        "news_item_id": "news-provider",
                        "source_watermark_ms": NOW_MS - 1_000,
                        "provider_type": "opennews",
                        "provider_signal_json": {
                            "source": "provider",
                            "provider": "opennews",
                            "status": "ready",
                            "score": 95,
                        },
                    }
                ]
            )
        if "FROM news_sources" in sql:
            return FakeRowsCursor([])
        raise AssertionError(f"unexpected SQL: {sql}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield


class FakeRowsCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)


class FakePageNewsRepository:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.loaded_ids: list[str] = []
        self.replacements: list[dict[str, Any]] = []
        self.raise_on_replace: Exception | None = None
        self.scan_calls = 0

    def list_items_for_page_projection(self, *, limit: int) -> list[dict[str, Any]]:
        self.scan_calls += 1
        raise AssertionError("legacy page scan must not be called")

    def load_items_for_page_projection(self, *, news_item_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_ids = list(news_item_ids)
        return list(self.payloads)

    def replace_page_rows_for_items(
        self,
        *,
        news_item_ids: list[str],
        rows: list[dict[str, Any]],
        commit: bool,
    ) -> None:
        if self.raise_on_replace is not None:
            raise self.raise_on_replace
        self.replacements.append(
            {
                "news_item_ids": list(news_item_ids),
                "row_ids": [str(row["news_item_id"]) for row in rows],
                "commit": commit,
            }
        )


class FakeDirtyRepository:
    def __init__(
        self,
        claimed: list[dict[str, Any]] | None = None,
        *,
        expected_projection_name: str | None = "page",
    ) -> None:
        self.claimed = claimed or []
        self.expected_projection_name = expected_projection_name
        self.enqueued: list[dict[str, Any]] = []
        self.marked_done: list[list[dict[str, Any]]] = []
        self.marked_error: list[list[dict[str, Any]]] = []
        self.conn: FakeConn | None = None

    def claim_due(self, **kwargs: Any) -> list[dict[str, Any]]:
        if self.expected_projection_name is not None:
            assert kwargs["projection_name"] == self.expected_projection_name
        assert kwargs["commit"] is False
        return [dict(row) for row in self.claimed[: kwargs["limit"]]]

    def enqueue_targets(
        self,
        rows: list[Mapping[str, Any]],
        *,
        reason: str,
        now_ms: int,
        commit: bool = True,
        due_at_ms: int | None = None,
    ) -> int:
        if self.conn is not None:
            self.conn.record(f"dirty:{reason}")
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

    def mark_done(self, rows: list[Mapping[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        self.marked_done.append([dict(row) for row in rows])
        return len(rows)

    def mark_error(
        self,
        rows: list[Mapping[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        self.marked_error.append([dict(row) for row in rows])
        return len(rows)


def _fetch_worker(
    repos: FakeFetchRepos,
    *,
    observations: list[NewsProviderObservation],
    wake_bus: Any | None = None,
) -> NewsFetchWorker:
    return NewsFetchWorker(
        name="news_fetch",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=FakeDB("news_fetch", repos),
        telemetry=object(),
        news_settings=SimpleNamespace(sources=(_source(),)),
        wake_bus=wake_bus,
        feed_client=FakeProvider(observations),
    )


class FakeFetchRepos:
    def __init__(
        self,
        *,
        source: dict[str, Any],
        news_statuses: list[dict[str, Any]] | None = None,
        reconcile_rows: list[dict[str, Any]] | None = None,
        existing_items_by_source: dict[str, list[str]] | None = None,
    ) -> None:
        self.conn = FakeConn()
        self.source = source
        self.news_statuses = list(news_statuses or [])
        self.reconcile_rows = list(reconcile_rows or [])
        self.existing_items_by_source = dict(existing_items_by_source or {})
        self.news_item_ids_requested_for_sources: list[list[str]] = []
        self.news = self
        self.dirty = FakeDirtyRepository()
        self.dirty.conn = self.conn
        self.news_projection_dirty_targets = self.dirty
        self.sync_cursors: dict[str, dict[str, Any]] = {}
        self.sync_updates: list[dict[str, Any]] = []

    def reconcile_configured_sources(
        self,
        sources: tuple[dict[str, Any], ...],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        assert commit is False
        self.conn.record("source_reconcile")
        return [dict(row) for row in self.reconcile_rows]

    def claim_due_sources(self, *, now_ms: int, limit: int, commit: bool = True) -> list[dict[str, Any]]:
        assert commit is False
        return [dict(self.source)]

    def list_news_item_ids_for_sources(self, *, source_ids: list[str]) -> list[str]:
        self.news_item_ids_requested_for_sources.append(list(source_ids))
        result: list[str] = []
        for source_id in source_ids:
            result.extend(self.existing_items_by_source.get(source_id, []))
        return result

    def start_fetch_run(self, *, source_id: str, started_at_ms: int, commit: bool = True) -> str:
        assert commit is False
        self.conn.record("start_fetch_run")
        return "fetch-run-1"

    def source_sync_cursor(self, source_id: str) -> dict[str, Any]:
        return dict(self.sync_cursors.get(source_id, {}))

    def update_source_sync_state(
        self,
        source_id: str,
        next_cursor: dict[str, Any],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        assert commit is False
        self.conn.record("update_source_sync_state")
        self.sync_updates.append(
            {"source_id": source_id, "next_cursor": dict(next_cursor), "now_ms": now_ms, "commit": commit}
        )

    def upsert_provider_item(self, **payload: Any) -> dict[str, Any]:
        self.conn.record("upsert_provider_item")
        provider_article_id = str(payload["raw_payload"].get("id") or "")
        return {
            "provider_item_id": f"provider-{payload['source_item_key']}",
            "provider_article_id": provider_article_id,
            "provider_article_key": f"fake:{provider_article_id}" if provider_article_id else "",
            "status": "inserted",
        }

    def upsert_canonical_news_item(self, **payload: Any) -> dict[str, Any]:
        self.conn.record("upsert_canonical_news_item")
        assert payload["canonical_identity"].canonical_item_key.startswith("canonical-url:")
        return dict(self.news_statuses.pop(0))

    def update_source_http_cache(self, **payload: Any) -> None:
        self.conn.record("update_source_http_cache")

    def finish_fetch_run(self, **payload: Any) -> dict[str, Any]:
        self.conn.record("finish_fetch_run")
        return dict(payload)

    def upsert_news_context_item(self, **payload: Any) -> dict[str, Any]:
        return dict(payload)


class FakeProvider:
    provider_type = "fake"

    def __init__(self, observations: list[NewsProviderObservation]) -> None:
        self.observations = observations

    def fetch(self, source: NewsSourceSnapshot, **kwargs: Any) -> NewsProviderFetchResult:
        return NewsProviderFetchResult(status_code=200, observations=self.observations)


def _source() -> dict[str, Any]:
    return {
        "source_id": "source-1",
        "provider_type": "rss",
        "feed_url": "https://example.com/rss.xml",
        "source_domain": "example.com",
        "source_name": "Example",
    }


def _observation(key: str) -> NewsProviderObservation:
    return NewsProviderObservation(
        source_item_key=key,
        canonical_url=f"https://example.com/news/{key}",
        title=f"Title {key}",
        summary="",
        body_text="",
        language="en",
        published_at_ms=NOW_MS,
        raw_payload={"id": key},
    )


class FakeProcessRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news = self
        self.dirty = FakeDirtyRepository()
        self.dirty.conn = self.conn
        self.news_projection_dirty_targets = self.dirty
        self.write_commits: list[bool] = []

    def list_unprocessed_items(self, *, limit: int, now_ms: int) -> list[dict[str, Any]]:
        return [
            {
                "news_item_id": "news-1",
                "source_id": "source-1",
                "source_role": "official_exchange",
                "source_domain": "coinbase.com",
                "authority_scope_json": {"event_types": ["exchange_listing"], "domains": ["coinbase.com"]},
                "title": "Coinbase lists $BTC for trading",
                "summary": "",
                "body_text": "",
            }
        ]

    def replace_item_entities(self, news_item_id: str, entities: list[Any], *, commit: bool = True) -> None:
        self.conn.record("replace_item_entities")
        self.write_commits.append(commit)

    def replace_token_mentions(self, news_item_id: str, mentions: list[Any], *, commit: bool = True) -> None:
        self.conn.record("replace_token_mentions")
        self.write_commits.append(commit)

    def replace_fact_candidates(self, news_item_id: str, candidates: list[Any], *, commit: bool = True) -> None:
        self.conn.record("replace_fact_candidates")
        self.write_commits.append(commit)

    def update_item_content_classification(self, **payload: Any) -> None:
        self.conn.record("update_item_content_classification")
        self.write_commits.append(payload["commit"])

    def mark_item_processed(self, *, news_item_id: str, processed_at_ms: int, commit: bool = True) -> None:
        self.conn.record("mark_item_processed")
        self.write_commits.append(commit)

    def mark_item_process_failed(self, **payload: Any) -> None:
        raise AssertionError("process should not fail")


class FakeIdentityLookup:
    def resolve_address(self, *, chain_id: str | None, address: str) -> Any:
        raise AssertionError("address lookup should not be called")

    def resolve_symbol(self, *, symbol: str) -> TokenIdentityLookupResult:
        return TokenIdentityLookupResult(
            resolution_status="EXACT",
            target_type="CexToken",
            target_id=f"cex:{symbol}",
            display_symbol=symbol,
            display_name="Bitcoin",
            reason_codes=["CONFIRMED_CEX_TOKEN"],
            candidate_targets=[],
        )


class FakeBriefRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news = self
        self.dirty = FakeDirtyRepository()
        self.dirty.conn = self.conn
        self.news_projection_dirty_targets = self.dirty
        self.brief_commits: list[bool] = []

    def upsert_news_item_agent_brief(self, **payload: Any) -> dict[str, Any]:
        self.conn.record("upsert_news_item_agent_brief")
        self.brief_commits.append(payload["commit"])
        return dict(payload)

    def list_source_ids_for_news_items(self, *, news_item_ids: list[str]) -> list[str]:
        assert news_item_ids == ["news-1"]
        return ["source-1"]


class FakeSourceQualityRepos:
    def __init__(self) -> None:
        self.conn = FakeConn()
        self.news = self
        self.dirty = FakeDirtyRepository(
            [_source_quality_claim("source-1")],
            expected_projection_name="source_quality",
        )
        self.dirty.conn = self.conn
        self.news_projection_dirty_targets = self.dirty
        self.news_item_ids_requested_for_sources: list[list[str]] = []

    def list_source_quality_inputs_for_targets(
        self,
        *,
        source_windows: list[tuple[str, str]],
        now_ms: int,
    ) -> list[dict[str, Any]]:
        assert source_windows == [("source-1", "24h")]
        return [
            {
                "source_id": "source-1",
                "window": "24h",
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
                "context_item_count": 0,
                "context_parent_item_count": 0,
                "useful_item_count": 1,
                "latest_item_published_at_ms": NOW_MS - 1_000,
                "median_lag_ms": 100,
            }
        ]

    def replace_source_quality_rows(
        self,
        *,
        rows: list[Mapping[str, Any]],
        status_window: str,
        commit: bool = True,
    ) -> list[str]:
        assert commit is False
        self.conn.record("replace_source_quality_rows")
        return ["source-1"]

    def list_news_item_ids_for_sources(self, *, source_ids: list[str]) -> list[str]:
        self.news_item_ids_requested_for_sources.append(list(source_ids))
        return ["news-1"]


class FakeDB:
    def __init__(self, expected_name: str, repos: Any) -> None:
        self.expected_name = expected_name
        self.repos = repos

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None) -> Iterator[Any]:
        assert name == self.expected_name
        assert statement_timeout_seconds == 30
        yield self.repos


class FakeWakeBus:
    def __init__(self, *, transaction_events: list[str]) -> None:
        self.transaction_events = transaction_events
        self.notifications: list[dict[str, Any]] = []

    def notify_news_page_dirty(self, *, count: int, reason: str) -> None:
        self.notifications.append(
            {
                "count": int(count),
                "reason": str(reason),
                "events_before_notify": list(self.transaction_events),
            }
        )


class FakeConn:
    def __init__(self) -> None:
        self.commits = 0
        self.events: list[str] = []
        self._transaction_depth = 0

    def commit(self) -> None:
        self.commits += 1
        self.events.append("direct_commit")

    def record(self, label: str) -> None:
        prefix = "tx" if self._transaction_depth else "autocommit"
        self.events.append(f"{prefix}:{label}")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.events.append("begin")
        self._transaction_depth += 1
        try:
            yield
        except Exception:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")
        finally:
            self._transaction_depth -= 1


class ScriptedConnection:
    def __init__(self, results: list[Any]) -> None:
        self.results = list(results)
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> ScriptedCursor:
        self.sql.append(sql)
        self.params.append(params)
        result = self.results.pop(0) if self.results else []
        return ScriptedCursor(result)

    def commit(self) -> None:
        self.commits += 1


class ScriptedCursor:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.rowcount = len(result) if isinstance(result, list) else 1

    def fetchone(self) -> Any:
        if isinstance(self.result, list):
            return self.result[0] if self.result else None
        return self.result

    def fetchall(self) -> list[Any]:
        if isinstance(self.result, list):
            return self.result
        return [self.result]
