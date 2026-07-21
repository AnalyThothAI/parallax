from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.notifications.repositories.notification_repository import NotificationRepository

NOW_MS = 1_700_000_000_000
_MISSING = object()


def _repository(conn: Any, **overrides: int) -> NotificationRepository:
    return NotificationRepository(
        conn,
        running_timeout_ms=overrides.get("running_timeout_ms", 300_000),
        stale_running_terminalization_batch_size=overrides.get("stale_batch_size", 100),
    )


def _notification_kwargs() -> dict[str, Any]:
    return {
        "dedup_key": "dedup-1",
        "rule_id": "rule-1",
        "severity": "high",
        "title": "Title",
        "body": "Body",
        "entity_type": "news_item",
        "entity_key": "news-1",
        "source_table": "news_items",
        "source_id": "news-1",
        "event_id": "event-1",
        "occurrence_at_ms": NOW_MS,
        "payload": {"semantic_signature": "sha256:one"},
        "channels": ("in_app",),
    }


def _delivery_claim(**overrides: Any) -> dict[str, Any]:
    return {
        "delivery_id": "delivery-1",
        "notification_id": "notification-1",
        "channel_id": "push",
        "provider": "pushdeer",
        "status": "running",
        "attempt_count": 1,
        "max_attempts": 3,
        "updated_at_ms": NOW_MS,
        **overrides,
    }


class Cursor:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
        rowcount: Any = 0,
    ) -> None:
        self.row = row
        self.rows = rows or []
        if rowcount is not _MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)


class RepositoryConnection:
    """SQL double deliberately has no transaction or commit method."""

    def __init__(self, *, rowcounts: dict[str, Any] | None = None) -> None:
        self.rowcounts = rowcounts or {}
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.notification = {
            "notification_id": "notification-1",
            "dedup_key": "dedup-1",
            "rule_id": "rule-1",
            "severity": "high",
            "title": "Title",
            "body": "Body",
            "entity_type": "news_item",
            "entity_key": "news-1",
            "author_handle": None,
            "symbol": None,
            "chain": None,
            "address": None,
            "event_id": "event-1",
            "source_table": "news_items",
            "source_id": "news-1",
            "occurrence_count": 1,
            "first_seen_at_ms": NOW_MS,
            "last_seen_at_ms": NOW_MS,
            "payload_json": {},
            "channels_json": ["in_app"],
            "created_at_ms": NOW_MS,
            "updated_at_ms": NOW_MS,
            "read_at_ms": None,
        }
        self.delivery = _delivery_claim()

    def execute(self, sql: str, params: Any = None) -> Cursor:
        sql_text = str(sql)
        self.sql.append(sql_text)
        self.params.append(params)
        kind = _statement_kind(sql_text)
        rowcount = self.rowcounts.get(kind, 1 if kind in _WRITE_KINDS else 0)
        if kind in {"semantic_duplicate", "external_duplicate", "dedup_duplicate"}:
            return Cursor(row=None)
        if kind == "notification_read":
            return Cursor(rows=[self.notification])
        if kind in {"delivery_read", "delivery_requeue", "delivery_claim"}:
            return Cursor(row=self.delivery, rowcount=rowcount)
        if kind == "notification_exists":
            return Cursor(row={"notification_id": "notification-1"})
        if kind in {"mark_all_read", "mark_author_read"}:
            rows = [{"notification_id": "notification-1"}]
            return Cursor(rows=rows, rowcount=rowcount)
        return Cursor(rowcount=rowcount)


_WRITE_KINDS = {
    "notification_insert",
    "notification_aggregate",
    "mark_read",
    "mark_all_read",
    "mark_author_read",
    "delivery_enqueue",
    "delivery_requeue",
    "delivery_stale_terminalize",
    "delivery_claim",
    "delivery_complete",
    "delivery_fail",
    "notification_retention_prune",
}


def _statement_kind(sql: str) -> str:
    if "WITH expired_notifications AS" in sql:
        return "notification_retention_prune"
    if "payload_json->>'semantic_signature'" in sql:
        return "semantic_duplicate"
    if "payload_json->>'external_push_signature'" in sql:
        return "external_duplicate"
    if "SELECT * FROM notifications WHERE dedup_key" in sql:
        return "dedup_duplicate"
    if "INSERT INTO notifications" in sql:
        return "notification_insert"
    if "UPDATE notifications" in sql:
        return "notification_aggregate"
    if "SELECT n.*" in sql:
        return "notification_read"
    if "SELECT notification_id FROM notifications" in sql:
        return "notification_exists"
    if "INSERT INTO notification_reads" in sql and "WITH unread" not in sql:
        return "mark_read"
    if "WITH unread" in sql and "n.author_handle" in sql:
        return "mark_author_read"
    if "WITH unread" in sql:
        return "mark_all_read"
    if "INSERT INTO notification_deliveries" in sql and "DO UPDATE" in sql:
        return "delivery_requeue"
    if "INSERT INTO notification_deliveries" in sql:
        return "delivery_enqueue"
    if "SELECT * FROM notification_deliveries" in sql:
        return "delivery_read"
    if "WITH expired AS" in sql:
        return "delivery_stale_terminalize"
    if "WITH picked AS" in sql:
        return "delivery_claim"
    if "SET status = 'delivered'" in sql:
        return "delivery_complete"
    if "SET status = %s" in sql:
        return "delivery_fail"
    return "read"


def test_repository_writes_use_only_the_callers_transaction() -> None:
    conn = RepositoryConnection(rowcounts={"delivery_stale_terminalize": 0})
    repository = _repository(conn)

    outcome = repository.insert_notification_with_outcome(**_notification_kwargs())
    delivery = repository.enqueue_delivery(
        notification_id="notification-1",
        channel_id="push",
        provider="pushdeer",
        max_attempts=3,
    )
    claimed = repository.claim_next_delivery(now_ms=NOW_MS)
    assert claimed is not None
    repository.complete_delivery(claimed, delivered_at_ms=NOW_MS)

    assert outcome.created is True
    assert outcome.row is not None
    assert delivery is not None
    assert not hasattr(conn, "transaction")
    assert not hasattr(conn, "commit")


def test_notification_read_state_is_a_caller_owned_write() -> None:
    conn = RepositoryConnection()
    repository = _repository(conn)

    assert repository.mark_read(notification_id="notification-1", subscriber_key="local") is True
    assert repository.mark_all_read(subscriber_key="local") == 1
    assert repository.mark_author_read(author_handle="Account", subscriber_key="local") == 1


def test_notification_retention_prune_is_bounded_and_protects_active_deliveries() -> None:
    conn = RepositoryConnection(rowcounts={"notification_retention_prune": 4})

    deleted = _repository(conn).prune_expired_notifications(cutoff_ms=NOW_MS, limit=4)

    assert deleted == 4
    sql = conn.sql[-1]
    assert "n.last_seen_at_ms < %s" in sql
    assert "delivery.status IN ('pending', 'running', 'failed')" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "DELETE FROM notifications" in sql
    assert conn.params[-1] == (NOW_MS, 4)


@pytest.mark.parametrize(
    ("kind", "operation", "error_code"),
    [
        (
            "notification_insert",
            lambda repository: repository.insert_notification_with_outcome(**_notification_kwargs()),
            "notification_insert_rowcount_invalid",
        ),
        (
            "delivery_enqueue",
            lambda repository: repository.enqueue_delivery(
                notification_id="notification-1",
                channel_id="push",
                provider="pushdeer",
                max_attempts=3,
            ),
            "notification_delivery_enqueue_rowcount_invalid",
        ),
        (
            "delivery_claim",
            lambda repository: repository.claim_next_delivery(now_ms=NOW_MS),
            "notification_delivery_claim_rowcount_invalid",
        ),
        (
            "delivery_complete",
            lambda repository: repository.complete_delivery(_delivery_claim(), delivered_at_ms=NOW_MS),
            "notification_delivery_complete_rowcount_invalid",
        ),
        (
            "delivery_fail",
            lambda repository: repository.fail_delivery(_delivery_claim(), error="down", now_ms=NOW_MS),
            "notification_delivery_fail_rowcount_invalid",
        ),
    ],
)
def test_write_transitions_require_exact_cursor_counts(kind: str, operation: Any, error_code: str) -> None:
    conn = RepositoryConnection(rowcounts={kind: _MISSING, "delivery_stale_terminalize": 0})

    with pytest.raises(TypeError, match=error_code):
        operation(_repository(conn))


@pytest.mark.parametrize("rowcount", [True, -1, 2])
def test_single_row_transition_rejects_ambiguous_counts(rowcount: Any) -> None:
    conn = RepositoryConnection(rowcounts={"notification_insert": rowcount})

    with pytest.raises(TypeError, match="notification_insert_rowcount_invalid"):
        _repository(conn).insert_notification_with_outcome(**_notification_kwargs())


def test_claim_terminalizes_stale_exhausted_deliveries_in_a_bounded_batch() -> None:
    conn = RepositoryConnection(rowcounts={"delivery_stale_terminalize": 100, "delivery_claim": 1})
    repository = _repository(conn, stale_batch_size=100)

    assert repository.claim_next_delivery(now_ms=NOW_MS) == conn.delivery

    stale_index = next(index for index, sql in enumerate(conn.sql) if "WITH expired AS" in sql)
    assert conn.params[stale_index][1] == 100


def test_delivery_state_requires_claim_identity_before_sql() -> None:
    conn = RepositoryConnection()
    repository = _repository(conn)

    with pytest.raises(RuntimeError, match="notification_delivery_claim_contract_required"):
        repository.complete_delivery(
            {"delivery_id": "delivery-1", "attempt_count": 1},
            delivered_at_ms=NOW_MS,
        )
    with pytest.raises(RuntimeError, match="notification_delivery_attempt_contract_required"):
        repository.fail_delivery(
            {"delivery_id": "delivery-1", "attempt_count": 1, "updated_at_ms": NOW_MS},
            error="down",
            now_ms=NOW_MS,
        )

    assert conn.sql == []


@pytest.mark.parametrize(
    ("kwargs", "error_code"),
    [
        ({"running_timeout_ms": 0}, "notification_delivery_running_timeout_ms_required"),
        ({"stale_batch_size": 0}, "notification_delivery_stale_running_terminalization_batch_size_required"),
    ],
)
def test_repository_requires_positive_delivery_policy(kwargs: dict[str, int], error_code: str) -> None:
    with pytest.raises(RuntimeError, match=error_code):
        _repository(RepositoryConnection(), **kwargs)


def test_enqueue_requires_positive_attempt_budget_before_sql() -> None:
    conn = RepositoryConnection()

    with pytest.raises(RuntimeError, match="notification_delivery_max_attempts_required"):
        _repository(conn).enqueue_delivery(
            notification_id="notification-1",
            channel_id="push",
            provider="pushdeer",
            max_attempts=0,
        )

    assert conn.sql == []
