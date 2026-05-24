from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
from gmgn_twitter_intel.domains.news_intel.runtime import news_item_process_worker as process_module
from gmgn_twitter_intel.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from gmgn_twitter_intel.domains.news_intel.runtime.news_story_projection_worker import NewsStoryProjectionWorker

NOW_MS = 1_700_000_000_000


def test_empty_dirty_queue_does_not_call_missing_story_scan() -> None:
    news_repo = FakeStoryNewsRepository()
    dirty_repo = FakeDirtyTargetRepository(claimed=[])
    worker = _story_worker(news_repo=news_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert "item_scan" not in result.notes
    assert news_repo.missing_story_scan_calls == 0
    assert dirty_repo.claims == [{"projection_name": "story"}]


def test_claimed_story_targets_load_only_claimed_ids_and_enqueue_page() -> None:
    item = _story_item(news_item_id="news-1")
    news_repo = FakeStoryNewsRepository(items=[item])
    dirty_repo = FakeDirtyTargetRepository(claimed=[_claim("story", "news_item", "news-1")])
    worker = _story_worker(news_repo=news_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["story_rows"] == 1
    assert news_repo.loaded_news_item_ids == [["news-1"]]
    assert news_repo.created_story_items == ["news-1"]
    assert news_repo.added_story_members == ["news-1"]
    assert dirty_repo.done == dirty_repo.claimed
    assert dirty_repo.errors == []
    assert dirty_repo.enqueued == [
        {
            "projection_name": "page",
            "target_kind": "news_item",
            "target_id": "news-1",
            "source_watermark_ms": NOW_MS,
        }
    ]


def test_claimed_story_target_with_no_loaded_item_marks_done_without_fallback() -> None:
    news_repo = FakeStoryNewsRepository(items=[])
    dirty_repo = FakeDirtyTargetRepository(claimed=[_claim("story", "news_item", "news-missing")])
    worker = _story_worker(news_repo=news_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["story_rows"] == 0
    assert news_repo.loaded_news_item_ids == [["news-missing"]]
    assert news_repo.missing_story_scan_calls == 0
    assert dirty_repo.done == dirty_repo.claimed
    assert dirty_repo.errors == []
    assert dirty_repo.enqueued == []


def test_story_write_failure_marks_error_and_rolls_back_partial_writes() -> None:
    news_repo = FakeStoryNewsRepository(items=[_story_item(news_item_id="news-1")], fail_add=True)
    dirty_repo = FakeDirtyTargetRepository(claimed=[_claim("story", "news_item", "news-1")])
    worker = _story_worker(news_repo=news_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert dirty_repo.done == []
    assert dirty_repo.errors == [dirty_repo.claimed]
    assert "add story failed" in dirty_repo.error_messages[0]
    assert "rollback_savepoint" in news_repo.conn.events
    assert news_repo.created_story_items == []
    assert news_repo.added_story_members == []
    assert dirty_repo.enqueued == []


def test_story_notify_runs_after_commit() -> None:
    news_repo = FakeStoryNewsRepository(items=[_story_item(news_item_id="news-1")])
    dirty_repo = FakeDirtyTargetRepository(claimed=[_claim("story", "news_item", "news-1")])
    wake_bus = FakeWakeBus(transaction_events=news_repo.conn.events)
    worker = _story_worker(news_repo=news_repo, dirty_repo=dirty_repo, wake_bus=wake_bus)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert wake_bus.notifications == [
        {
            "count": 1,
            "events_before_notify": [
                "begin",
                "savepoint",
                "release_savepoint",
                "tx:dirty:news_story_projected",
                "commit",
            ],
        }
    ]


def test_process_worker_enqueues_story_and_page_in_same_transaction(monkeypatch) -> None:
    news_repo = FakeProcessNewsRepository(item=_story_item(news_item_id="news-1"))
    dirty_repo = FakeDirtyTargetRepository()
    monkeypatch.setattr(process_module, "extract_news_entities", lambda **_kwargs: [])
    monkeypatch.setattr(process_module, "build_news_token_mentions", lambda **_kwargs: [])
    monkeypatch.setattr(process_module, "build_fact_candidates", lambda **_kwargs: [])
    monkeypatch.setattr(
        process_module,
        "classify_news_item_content",
        lambda **_kwargs: SimpleNamespace(
            content_class="market_update",
            content_tags=["crypto"],
            classification_payload={},
        ),
    )
    worker = NewsItemProcessWorker(
        name="news_item_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=30),
        db=FakeDB("news_item_process", news_repo, dirty_repo),
        telemetry=object(),
        identity_lookup=object(),
        wake_bus=None,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert {
        (row["projection_name"], row["target_kind"], row["target_id"])
        for call in dirty_repo.enqueue_calls
        for row in call["rows"]
    } == {
        ("story", "news_item", "news-1"),
        ("page", "news_item", "news-1"),
        ("source_quality", "source", "source-1"),
    }
    assert "tx:replace_item_entities" in news_repo.conn.events
    assert "tx:dirty:news_item_processed" in news_repo.conn.events
    assert "autocommit:dirty:news_item_processed" not in news_repo.conn.events
    assert "direct_commit" not in news_repo.conn.events


def test_story_repository_loader_filters_by_explicit_ids_without_missing_story_predicate() -> None:
    conn = ScriptedConnection([[]])
    repo = NewsRepository(conn)

    repo.load_items_for_story_projection(news_item_ids=["news-1"])

    sql = conn.sql[0]
    assert "WITH target_items AS" in sql
    assert "items.news_item_id = ANY(%s::text[])" in sql
    assert sql.index("items.news_item_id = ANY(%s::text[])") < sql.index("LEFT JOIN LATERAL")
    assert "members.news_item_id IS NULL" not in sql
    assert "items.lifecycle_status = 'processed'" in sql


def _story_worker(
    *,
    news_repo: Any,
    dirty_repo: FakeDirtyTargetRepository,
    wake_bus: Any | None = None,
) -> NewsStoryProjectionWorker:
    return NewsStoryProjectionWorker(
        name="news_story_projection",
        settings=SimpleNamespace(batch_size=10, lease_ms=60_000, retry_ms=30_000, statement_timeout_seconds=30),
        db=FakeDB("news_story_projection", news_repo, dirty_repo),
        telemetry=object(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )


def _claim(projection_name: str, target_kind: str, target_id: str) -> dict[str, Any]:
    return {
        "projection_name": projection_name,
        "target_kind": target_kind,
        "target_id": target_id,
        "window": "",
        "payload_hash": f"hash:{projection_name}:{target_id}",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }


def _story_item(*, news_item_id: str) -> dict[str, Any]:
    return {
        "news_item_id": news_item_id,
        "title": "SOL ETF approved",
        "title_fingerprint": "sol etf approved",
        "canonical_url": "https://example.com/sol-etf",
        "published_at_ms": NOW_MS - 1_000,
        "lifecycle_status": "processed",
        "source_domain": "example.com",
        "source_id": "source-1",
        "token_targets": ["asset:SOL"],
    }


class FakeStoryNewsRepository:
    def __init__(self, *, items: list[dict[str, Any]] | None = None, fail_add: bool = False) -> None:
        self.conn = FakeConn()
        self.items = items or []
        self.fail_add = fail_add
        self.missing_story_scan_calls = 0
        self.loaded_news_item_ids: list[list[str]] = []
        self.created_story_items: list[str] = []
        self.added_story_members: list[str] = []

    def list_items_missing_story(self, *, limit: int) -> list[dict[str, Any]]:
        self.missing_story_scan_calls += 1
        raise AssertionError("story worker must not call list_items_missing_story")

    def load_items_for_story_projection(self, *, news_item_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_news_item_ids.append(list(news_item_ids))
        wanted = set(news_item_ids)
        return [dict(item) for item in self.items if item["news_item_id"] in wanted]

    def find_story_candidates_for_item(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def create_story_from_item(self, *, item: dict[str, Any], **_kwargs: Any) -> None:
        self.conn.record_write(lambda: self.created_story_items.append(str(item["news_item_id"])))

    def refresh_story_from_member(self, *, item: dict[str, Any], **_kwargs: Any) -> None:
        self.conn.record_write(lambda: self.created_story_items.append(str(item["news_item_id"])))

    def add_story_member(self, *, news_item_id: str, **_kwargs: Any) -> None:
        if self.fail_add:
            raise RuntimeError("add story failed")
        self.conn.record_write(lambda: self.added_story_members.append(str(news_item_id)))


class FakeProcessNewsRepository:
    def __init__(self, *, item: dict[str, Any]) -> None:
        self.conn = FakeConn()
        self.item = item

    def list_unprocessed_items(self, *, limit: int, now_ms: int) -> list[dict[str, Any]]:
        return [dict(self.item)]

    def replace_item_entities(self, **_kwargs: Any) -> None:
        self.conn.record_write(lambda: self.conn.events.append("tx:replace_item_entities"))

    def replace_token_mentions(self, **_kwargs: Any) -> None:
        self.conn.record_write(lambda: self.conn.events.append("tx:replace_token_mentions"))

    def replace_fact_candidates(self, **_kwargs: Any) -> None:
        self.conn.record_write(lambda: self.conn.events.append("tx:replace_fact_candidates"))

    def update_item_content_classification(self, **_kwargs: Any) -> None:
        self.conn.record_write(lambda: self.conn.events.append("tx:update_item_content_classification"))

    def mark_item_processed(self, **_kwargs: Any) -> None:
        self.conn.record_write(lambda: self.conn.events.append("tx:mark_item_processed"))


class FakeDirtyTargetRepository:
    def __init__(self, *, claimed: list[dict[str, Any]] | None = None) -> None:
        self.claimed = claimed or []
        self.pending = [dict(row) for row in self.claimed]
        self.claims: list[dict[str, str]] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[list[dict[str, Any]]] = []
        self.error_messages: list[str] = []
        self.enqueued: list[dict[str, Any]] = []
        self.enqueue_calls: list[dict[str, Any]] = []
        self.conn: FakeConn

    def claim_due(self, *, projection_name: str | None = None, limit: int, **_kwargs: Any) -> list[dict[str, Any]]:
        self.claims.append({"projection_name": str(projection_name)})
        return [dict(row) for row in self.pending if row["projection_name"] == projection_name][:limit]

    def mark_done(self, keys: list[dict[str, Any]], **_kwargs: Any) -> int:
        def apply() -> None:
            self.done.extend(dict(key) for key in keys)
            done_keys = {_target_key(key) for key in keys}
            self.pending = [row for row in self.pending if _target_key(row) not in done_keys]

        self.conn.record_write(apply)
        return len(keys)

    def mark_error(self, keys: list[dict[str, Any]], *, error: str, **_kwargs: Any) -> int:
        def apply() -> None:
            self.errors.append([dict(key) for key in keys])
            self.error_messages.append(error)

        self.conn.record_write(apply)
        return len(keys)

    def enqueue_targets(self, rows: list[dict[str, Any]], *, reason: str, now_ms: int, commit: bool = True) -> int:
        call = {"rows": [dict(row) for row in rows], "reason": reason, "now_ms": now_ms, "commit": commit}
        self.enqueue_calls.append(call)
        marker = f"tx:dirty:{reason}" if self.conn.in_transaction else f"autocommit:dirty:{reason}"

        def apply() -> None:
            self.conn.events.append(marker)
            self.enqueued.extend(dict(row) for row in rows)

        self.conn.record_write(apply)
        return len(rows)


class FakeWakeBus:
    def __init__(self, *, transaction_events: list[str]) -> None:
        self.transaction_events = transaction_events
        self.notifications: list[dict[str, Any]] = []

    def notify_news_story_updated(self, *, count: int) -> None:
        self.notifications.append({"count": int(count), "events_before_notify": list(self.transaction_events)})


class FakeConn:
    def __init__(self) -> None:
        self.events: list[str] = []
        self._frames: list[list[Any]] = []

    @property
    def in_transaction(self) -> bool:
        return bool(self._frames)

    def commit(self) -> None:
        self.events.append("direct_commit")

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def record_write(self, apply: Any) -> None:
        if self._frames:
            self._frames[-1].append(apply)
            return
        apply()


class FakeTransaction:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self.depth = 0

    def __enter__(self) -> FakeTransaction:
        self.depth = len(self.conn._frames)
        self.conn._frames.append([])
        self.conn.events.append("begin" if self.depth == 0 else "savepoint")
        return self

    def __exit__(self, exc_type: Any, _exc: Any, _tb: Any) -> bool:
        frame = self.conn._frames.pop()
        if exc_type is not None:
            self.conn.events.append("rollback" if self.depth == 0 else "rollback_savepoint")
            return False
        if self.conn._frames:
            self.conn._frames[-1].extend(frame)
            self.conn.events.append("release_savepoint")
            return False
        for apply in frame:
            apply()
        self.conn.events.append("commit")
        return False


class FakeSession:
    def __init__(self, *, news_repo: Any, dirty_repo: FakeDirtyTargetRepository) -> None:
        self.news = news_repo
        self.news_projection_dirty_targets = dirty_repo
        self.conn = news_repo.conn
        dirty_repo.conn = self.conn

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class FakeDB:
    def __init__(self, expected_name: str, news_repo: Any, dirty_repo: FakeDirtyTargetRepository) -> None:
        self.expected_name = expected_name
        self.news_repo = news_repo
        self.dirty_repo = dirty_repo

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None) -> Any:
        assert name == self.expected_name
        assert statement_timeout_seconds == 30
        yield FakeSession(news_repo=self.news_repo, dirty_repo=self.dirty_repo)


class ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]]]) -> None:
        self.results = list(results)
        self.sql: list[str] = []

    def execute(self, sql: str, *_args: Any) -> ScriptedCursor:
        self.sql.append(sql)
        return ScriptedCursor(self.results.pop(0) if self.results else [])


class ScriptedCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


def _target_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (str(row["projection_name"]), str(row["target_kind"]), str(row["target_id"]), str(row.get("window") or ""))
