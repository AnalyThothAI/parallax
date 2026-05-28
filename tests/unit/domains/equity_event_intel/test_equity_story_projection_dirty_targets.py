from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.repositories.equity_event_repository import (
    EquityEventRepository,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime import (
    equity_event_process_worker as process_module,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_process_worker import (
    EquityEventProcessWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_story_projection_worker import (
    EquityEventStoryProjectionWorker,
)

NOW_MS = 1_700_000_000_000


def test_empty_dirty_queue_does_not_call_missing_story_scan() -> None:
    equity_repo = _FakeStoryEquityRepository()
    dirty_repo = _FakeDirtyTargetRepository(claimed=[])
    worker = _story_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.notes["claimed"] == 0
    assert "event_scan" not in result.notes
    assert equity_repo.missing_story_scan_calls == 0
    assert dirty_repo.claims == [{"projection_name": "story", "target_kind": "company_event"}]


def test_claimed_story_targets_load_only_claimed_company_event_ids_and_enqueue_downstream() -> None:
    event_id = "event-1"
    event = _story_event(company_event_id=event_id)
    equity_repo = _FakeStoryEquityRepository(events=[event])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("story", "company_event", event_id)])
    worker = _story_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["story_rows"] == 1
    assert equity_repo.loaded_company_event_ids == [[event_id]]
    assert equity_repo.created_story_events == [event_id]
    assert equity_repo.added_story_members == [event_id]
    assert dirty_repo.done == dirty_repo.claimed
    assert dirty_repo.errors == []
    assert dirty_repo.enqueue_commits == [False]
    assert {(row["projection_name"], row["target_kind"], row["target_id"]) for row in dirty_repo.enqueued} == {
        ("brief_input", "company_event", event_id),
        ("page", "company_event", event_id),
        ("timeline", "company_event", event_id),
        ("alert", "company_event", event_id),
    }


def test_claimed_story_target_with_existing_membership_refreshes_existing_story_without_regrouping() -> None:
    event_id = "event-1"
    event = _story_event(company_event_id=event_id) | {
        "current_story_id": "story-existing",
        "current_story_relation": "representative",
    }
    equity_repo = _FakeStoryEquityRepository(events=[event])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("story", "company_event", event_id)])
    worker = _story_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["story_rows"] == 1
    assert equity_repo.story_candidate_events == []
    assert equity_repo.created_story_events == []
    assert equity_repo.refreshed_story_events == [event_id]
    assert equity_repo.added_story_member_rows == [
        {
            "story_id": "story-existing",
            "company_event_id": event_id,
            "relation": "representative",
            "match_reason": "existing_membership",
            "match_score": 1.0,
        }
    ]
    assert dirty_repo.done == dirty_repo.claimed
    assert dirty_repo.errors == []


def test_story_update_notify_runs_after_projection_transaction_commit() -> None:
    event_id = "event-1"
    equity_repo = _FakeStoryEquityRepository(events=[_story_event(company_event_id=event_id)])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("story", "company_event", event_id)])
    wake_bus = _FakeWakeBus(transaction_events=equity_repo.conn.transaction_events)
    worker = _story_worker(equity_repo=equity_repo, dirty_repo=dirty_repo, wake_bus=wake_bus)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert wake_bus.notifications == [1]
    assert equity_repo.conn.transaction_events.index("commit") < equity_repo.conn.transaction_events.index("notify")


def test_story_update_notify_failure_does_not_mark_error_or_roll_back_committed_projection() -> None:
    event_id = "event-1"
    equity_repo = _FakeStoryEquityRepository(events=[_story_event(company_event_id=event_id)])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("story", "company_event", event_id)])
    wake_bus = _FakeWakeBus(transaction_events=equity_repo.conn.transaction_events, fail=True)
    worker = _story_worker(equity_repo=equity_repo, dirty_repo=dirty_repo, wake_bus=wake_bus)

    try:
        worker.run_once_sync(now_ms=NOW_MS)
    except RuntimeError as exc:
        assert str(exc) == "notify failed"
    else:  # pragma: no cover - this test is specifically about thrown notify.
        raise AssertionError("wake bus failure should still propagate after commit")

    assert equity_repo.created_story_events == [event_id]
    assert equity_repo.added_story_members == [event_id]
    assert dirty_repo.done == dirty_repo.claimed
    assert dirty_repo.errors == []
    assert wake_bus.notifications == [1]
    assert equity_repo.conn.transaction_events.index("commit") < equity_repo.conn.transaction_events.index("notify")


def test_claimed_story_target_with_no_loaded_event_marks_done_without_scan_fallback() -> None:
    event_id = "event-rejected"
    equity_repo = _FakeStoryEquityRepository(events=[])
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("story", "company_event", event_id)])
    worker = _story_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["claimed"] == 1
    assert result.notes["story_rows"] == 0
    assert equity_repo.loaded_company_event_ids == [[event_id]]
    assert equity_repo.missing_story_scan_calls == 0
    assert dirty_repo.done == dirty_repo.claimed
    assert dirty_repo.errors == []
    assert dirty_repo.enqueued == []


def test_story_projection_failure_marks_error_with_full_claim_token() -> None:
    event_id = "event-1"
    equity_repo = _FakeStoryEquityRepository(events=[_story_event(company_event_id=event_id)], fail_add=True)
    dirty_repo = _FakeDirtyTargetRepository(claimed=[_claim("story", "company_event", event_id)])
    worker = _story_worker(equity_repo=equity_repo, dirty_repo=dirty_repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert dirty_repo.done == []
    assert dirty_repo.errors == [dirty_repo.claimed]
    assert "add story failed" in dirty_repo.error_messages[0]
    assert "rollback_savepoint" in equity_repo.conn.transaction_events
    assert equity_repo.created_story_events == []
    assert equity_repo.added_story_members == []
    assert dirty_repo.enqueued == []


def test_process_worker_enqueues_story_page_timeline_alert_and_matching_calendar_targets(monkeypatch) -> None:
    event_id = "event-1"
    document_id = "doc-1"
    equity_repo = _FakeProcessEquityRepository(
        document={"event_document_id": document_id, "source_id": "source-1", "body_text": "Revenue was up."},
        old_event_ids=["old-event-1"],
        matching_expected_event_ids=["expected-1"],
    )
    dirty_repo = _FakeDirtyTargetRepository()
    monkeypatch.setattr(
        process_module,
        "validate_company_identity",
        lambda _document: SimpleNamespace(validation_status="accepted"),
    )
    monkeypatch.setattr(
        process_module,
        "classify_equity_event",
        lambda _document: SimpleNamespace(
            company_event_id=event_id,
            company_id="company-1",
            ticker="MSFT",
            primary_document_id=document_id,
            event_type="quarterly_report",
            priority="P0",
            source_role="official_issuer",
            fiscal_period="2026Q1",
            event_time_ms=NOW_MS - 1_000,
            discovered_at_ms=NOW_MS - 900,
            lifecycle_status="processed",
            summary="MSFT report",
        ),
    )
    monkeypatch.setattr(process_module, "build_source_spans", lambda **_kwargs: [SimpleNamespace(span_id="span-1")])
    monkeypatch.setattr(process_module, "build_fact_candidates", lambda **_kwargs: [])
    worker = EquityEventProcessWorker(
        name="equity_event_process",
        settings=SimpleNamespace(batch_size=10, statement_timeout_seconds=None),
        db=_FakeDb(equity_repo=equity_repo, dirty_repo=dirty_repo),
        telemetry=SimpleNamespace(),
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert equity_repo.conn.commits == 1
    assert dirty_repo.enqueue_commits == [False]
    target_keys = {(row["projection_name"], row["target_kind"], row["target_id"]) for row in dirty_repo.enqueued}
    for projection_name in ("story", "brief_input", "page", "timeline", "alert"):
        assert (projection_name, "company_event", event_id) in target_keys
        assert (projection_name, "company_event", "old-event-1") in target_keys
    assert ("calendar", "expected_event", "expected-1") in target_keys


def test_story_repository_loader_filters_by_explicit_ids_without_missing_story_predicate() -> None:
    conn = _ScriptedConnection([[]])
    repo = EquityEventRepository(conn)

    repo.load_events_for_story_projection(company_event_ids=["event-1"])

    sql = conn.sql[0]
    assert "WITH target_events AS" in sql
    assert "FROM target_events AS events" in sql
    assert sql.index("company_event_id = ANY(%s::text[])") < sql.index("LEFT JOIN")
    assert "documents.accession_number" in sql
    assert "current_member.story_id AS current_story_id" in sql
    assert "members.company_event_id = events.company_event_id" in sql
    assert "members.company_event_id IS NULL" not in sql
    assert "validation_status <> 'rejected'" in sql


def _story_worker(
    *,
    equity_repo: _FakeStoryEquityRepository,
    dirty_repo: _FakeDirtyTargetRepository,
    batch_size: int = 10,
    wake_bus: Any | None = None,
) -> EquityEventStoryProjectionWorker:
    return EquityEventStoryProjectionWorker(
        name="equity_event_story_projection",
        settings=SimpleNamespace(
            batch_size=batch_size,
            statement_timeout_seconds=None,
            lease_ms=60_000,
            retry_ms=30_000,
        ),
        db=_FakeDb(equity_repo=equity_repo, dirty_repo=dirty_repo),
        telemetry=SimpleNamespace(),
        wake_bus=wake_bus,
    )


def _claim(projection_name: str, target_kind: str, target_id: str) -> dict[str, Any]:
    return {
        "projection_name": projection_name,
        "target_kind": target_kind,
        "target_id": target_id,
        "payload_hash": f"hash:{projection_name}:{target_id}",
        "lease_owner": "worker-a",
        "attempt_count": 1,
    }


def _story_event(*, company_event_id: str) -> dict[str, Any]:
    return {
        "company_event_id": company_event_id,
        "company_id": "company-1",
        "ticker": "MSFT",
        "primary_document_id": "doc-1",
        "event_type": "quarterly_report",
        "priority": "P0",
        "source_role": "official_issuer",
        "fiscal_period": "2026Q1",
        "event_time_ms": NOW_MS - 1_000,
        "discovered_at_ms": NOW_MS - 900,
        "lifecycle_status": "processed",
        "validation_status": "accepted",
        "summary": "MSFT quarterly report",
        "accession_number": "0000789019-26-000001",
        "updated_at_ms": NOW_MS - 100,
    }


class _FakeStoryEquityRepository:
    def __init__(
        self,
        *,
        events: list[dict[str, Any]] | None = None,
        load_error: Exception | None = None,
        fail_add: bool = False,
    ) -> None:
        self.events = events or []
        self.load_error = load_error
        self.fail_add = fail_add
        self.conn = _FakeConn()
        self.loaded_company_event_ids: list[list[str]] = []
        self.missing_story_scan_calls = 0
        self.created_story_events: list[str] = []
        self.refreshed_story_events: list[str] = []
        self.added_story_members: list[str] = []
        self.added_story_member_rows: list[dict[str, Any]] = []
        self.story_candidate_events: list[str] = []

    def list_events_missing_story(self, *, limit: int) -> list[dict[str, Any]]:
        self.missing_story_scan_calls += 1
        raise AssertionError("story worker must not call list_events_missing_story")

    def load_events_for_story_projection(self, *, company_event_ids: list[str]) -> list[dict[str, Any]]:
        self.loaded_company_event_ids.append(list(company_event_ids))
        if self.load_error is not None:
            raise self.load_error
        wanted = set(company_event_ids)
        return [dict(row) for row in self.events if row["company_event_id"] in wanted]

    def find_story_candidates_for_event(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        self.story_candidate_events.append(str(event["company_event_id"]))
        return []

    def create_story_from_event(self, *, event: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.conn.record_write(lambda: self.created_story_events.append(str(event["company_event_id"])))
        return {}

    def refresh_story_from_member(self, *, event: dict[str, Any], **_kwargs: Any) -> None:
        self.conn.record_write(lambda: self.refreshed_story_events.append(str(event["company_event_id"])))

    def add_story_member(
        self,
        *,
        story_id: str,
        company_event_id: str,
        relation: str,
        match_reason: str,
        match_score: float,
        **_kwargs: Any,
    ) -> None:
        if self.fail_add:
            raise RuntimeError("add story failed")

        def write() -> None:
            self.added_story_members.append(str(company_event_id))
            self.added_story_member_rows.append(
                {
                    "story_id": story_id,
                    "company_event_id": company_event_id,
                    "relation": relation,
                    "match_reason": match_reason,
                    "match_score": match_score,
                }
            )

        self.conn.record_write(write)

    def list_company_event_ids_for_stories(self, *, story_ids: list[str]) -> list[str]:
        wanted = set(story_ids)
        return [
            str(row["company_event_id"])
            for row in self.added_story_member_rows
            if str(row.get("story_id") or "") in wanted
        ]


class _FakeProcessEquityRepository:
    def __init__(
        self,
        *,
        document: dict[str, Any],
        old_event_ids: list[str],
        matching_expected_event_ids: list[str],
    ) -> None:
        self.document = document
        self.old_event_ids = old_event_ids
        self.matching_expected_event_ids = matching_expected_event_ids
        self.conn = _FakeConn()

    def expire_stale_process_jobs(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def claim_due_process_jobs(self, *, lease_owner: str, **_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {
                "event_document_id": self.document["event_document_id"],
                "lease_owner": lease_owner,
                "attempt_count": 1,
                "input_payload_hash": "process-input-hash",
            }
        ]

    def load_process_packets_for_claims(self, *, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not claims:
            return []
        document = self.list_event_documents_for_processing(limit=1)[0]
        document.update(
            {
                "lease_owner": claims[0]["lease_owner"],
                "attempt_count": claims[0]["attempt_count"],
                "input_payload_hash": claims[0]["input_payload_hash"],
            }
        )
        return [document]

    def list_event_documents_for_processing(self, *, limit: int) -> list[dict[str, Any]]:
        document = dict(self.document)
        document.setdefault("evidence_status", "ready")
        document.setdefault("evidence_reason", "")
        document.setdefault(
            "evidence_artifacts",
            [{"extraction_status": "ready", "content_text": "Revenue was up."}],
        )
        return [document]

    def company_event_ids_for_document(self, *, event_document_id: str) -> list[str]:
        return list(self.old_event_ids)

    def clear_story_members_for_document(self, **_kwargs: Any) -> int:
        return 0

    def upsert_company_event(self, **kwargs: Any) -> dict[str, Any]:
        return {"company_event_id": kwargs["company_event_id"], "updated_at_ms": kwargs["now_ms"]}

    def replace_source_spans(self, **_kwargs: Any) -> None:
        return None

    def replace_fact_candidates(self, **_kwargs: Any) -> None:
        return None

    def mark_event_document_evidence_status(self, **_kwargs: Any) -> None:
        return None

    def mark_event_document_fact_extraction_status(self, **_kwargs: Any) -> None:
        return None

    def mark_event_document_processed(self, **_kwargs: Any) -> None:
        return None

    def mark_event_document_process_failed(self, **_kwargs: Any) -> None:
        return None

    def finish_process_job_success(self, **_kwargs: Any) -> bool:
        return True

    def finish_process_job_failure(self, **_kwargs: Any) -> bool:
        return True

    def matching_expected_event_ids_for_company_events(self, *, company_event_ids: list[str]) -> list[str]:
        return list(self.matching_expected_event_ids)


class _FakeDirtyTargetRepository:
    def __init__(self, *, claimed: list[dict[str, Any]] | None = None) -> None:
        self.claimed = claimed or []
        self.pending = [dict(row) for row in self.claimed]
        self.claims: list[dict[str, str]] = []
        self.done: list[dict[str, Any]] = []
        self.errors: list[list[dict[str, Any]]] = []
        self.error_messages: list[str] = []
        self.enqueued: list[dict[str, Any]] = []
        self.enqueue_commits: list[bool] = []

    def claim_due(
        self,
        *,
        limit: int,
        lease_ms: int,
        now_ms: int,
        lease_owner: str,
        projection_name: str | None = None,
        target_kind: str | None = None,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        self.claims.append({"projection_name": str(projection_name), "target_kind": str(target_kind)})
        rows = [
            row
            for row in self.pending
            if row["projection_name"] == projection_name
            and (target_kind is None or row["target_kind"] == target_kind)
            and int(row.get("due_at_ms") or 0) <= int(now_ms)
        ][:limit]
        return [dict(row) for row in rows]

    def mark_done(self, keys: list[dict[str, Any]], *, now_ms: int, commit: bool = True) -> int:
        def apply() -> None:
            self.done.extend(dict(key) for key in keys)
            done_keys = {_target_key(key) for key in keys}
            self.pending = [row for row in self.pending if _target_key(row) not in done_keys]

        self.conn.record_write(apply)
        return len(keys)

    def mark_error(
        self,
        keys: list[dict[str, Any]],
        *,
        error: str,
        retry_ms: int,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        def apply() -> None:
            self.errors.append([dict(key) for key in keys])
            self.error_messages.append(error)

        self.conn.record_write(apply)
        return len(keys)

    def enqueue_targets(
        self,
        rows: list[dict[str, Any]],
        *,
        reason: str,
        now_ms: int,
        due_at_ms: int | None = None,
        commit: bool = True,
    ) -> int:
        self.enqueue_commits.append(commit)

        def apply() -> None:
            for row in rows:
                record = dict(row)
                record["due_at_ms"] = int(due_at_ms if due_at_ms is not None else now_ms)
                self.enqueued.append(record)

        self.conn.record_write(apply)
        return len(rows)


class _FakeWakeBus:
    def __init__(self, *, transaction_events: list[str], fail: bool = False) -> None:
        self.transaction_events = transaction_events
        self.fail = fail
        self.notifications: list[int] = []

    def notify_equity_event_story_updated(self, *, count: int) -> None:
        self.transaction_events.append("notify")
        self.notifications.append(int(count))
        if self.fail:
            raise RuntimeError("notify failed")


class _FakeConn:
    def __init__(self) -> None:
        self.commits = 0
        self.transaction_events: list[str] = []
        self._frames: list[list[Any]] = []

    def commit(self) -> None:
        self.commits += 1

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def record_write(self, apply: Any) -> None:
        if self._frames:
            self._frames[-1].append(apply)
            return
        apply()


class _FakeTransaction:
    def __init__(self, conn: _FakeConn) -> None:
        self.conn = conn
        self.depth = 0

    def __enter__(self) -> _FakeTransaction:
        self.depth = len(self.conn._frames)
        self.conn._frames.append([])
        self.conn.transaction_events.append("begin" if self.depth == 0 else "savepoint")
        return self

    def __exit__(self, exc_type: Any, _exc: Any, _tb: Any) -> bool:
        frame = self.conn._frames.pop()
        if exc_type is not None:
            self.conn.transaction_events.append("rollback" if self.depth == 0 else "rollback_savepoint")
            return False
        if self.conn._frames:
            self.conn._frames[-1].extend(frame)
            self.conn.transaction_events.append("release_savepoint")
        else:
            for apply in frame:
                apply()
            self.conn.transaction_events.append("commit")
        return False


class _FakeSession:
    def __init__(self, *, equity_repo: Any, dirty_repo: _FakeDirtyTargetRepository) -> None:
        self.equity_events = equity_repo
        self.equity_projection_dirty_targets = dirty_repo
        self.conn = equity_repo.conn
        dirty_repo.conn = self.conn
        self.registry = SimpleNamespace(find_us_equity_symbol=lambda *_args, **_kwargs: None)

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def unit_of_work(self) -> _FakeTransaction:
        return self.conn.transaction()


class _FakeDb:
    def __init__(self, *, equity_repo: Any, dirty_repo: _FakeDirtyTargetRepository) -> None:
        self.equity_repo = equity_repo
        self.dirty_repo = dirty_repo

    def worker_session(self, *_args: Any, **_kwargs: Any) -> _FakeSession:
        return _FakeSession(equity_repo=self.equity_repo, dirty_repo=self.dirty_repo)


class _ScriptedConnection:
    def __init__(self, results: list[list[dict[str, Any]]]) -> None:
        self.results = list(results)
        self.sql: list[str] = []

    def execute(self, sql: str, *_args: Any) -> _ScriptedCursor:
        self.sql.append(sql)
        rows = self.results.pop(0) if self.results else []
        return _ScriptedCursor(rows)


class _ScriptedCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


def _target_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row["projection_name"]), str(row["target_kind"]), str(row["target_id"]))
