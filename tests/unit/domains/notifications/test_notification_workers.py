from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.notifications.repositories.notification_repository import NotificationInsertOutcome
from parallax.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from parallax.domains.notifications.runtime.notification_worker import NotificationWorker
from parallax.domains.notifications.types import NotificationCandidate
from parallax.platform.config.settings import NotificationDeliveryWorkerSettings, NotificationRuleWorkerSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult

NOW_MS = 1_700_000_000_000


def _rule_settings(**overrides: object) -> NotificationRuleWorkerSettings:
    return NotificationRuleWorkerSettings(
        **{
            "enabled": True,
            "interval_seconds": 0.2,
            "batch_size": 10,
            "statement_timeout_seconds": 30,
            **overrides,
        }
    )


def _delivery_settings(**overrides: object) -> NotificationDeliveryWorkerSettings:
    return NotificationDeliveryWorkerSettings(
        **{
            "enabled": True,
            "interval_seconds": 0.2,
            "batch_size": 1,
            "statement_timeout_seconds": 30,
            **overrides,
        }
    )


class TransactionState:
    def __init__(self) -> None:
        self.active = False
        self.enters = 0
        self.exits = 0

    @contextmanager
    def transaction(self):
        assert not self.active
        self.active = True
        self.enters += 1
        try:
            yield None
        finally:
            self.active = False
            self.exits += 1


class WorkerSessionDB:
    def __init__(self, repository: Any, transaction_state: TransactionState) -> None:
        self.repository = repository
        self.transaction_state = transaction_state
        self.calls: list[dict[str, object]] = []

    @contextmanager
    def worker_session(self, name: str, *, statement_timeout_seconds: float | None = None):
        self.calls.append({"name": name, "statement_timeout_seconds": statement_timeout_seconds})
        yield SimpleNamespace(
            notifications=self.repository,
            transaction=self.transaction_state.transaction,
        )


class SequenceRuleEngine:
    def __init__(self, candidates: list[NotificationCandidate], *, delay_seconds: float = 0) -> None:
        self.candidates = candidates
        self.delay_seconds = delay_seconds

    def evaluate(self, *, now_ms: int | None = None) -> list[NotificationCandidate]:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        return list(self.candidates)


class NotificationRepositoryDouble:
    def __init__(
        self,
        *,
        duplicates: set[str] | None = None,
        aggregated: set[str] | None = None,
        pruned: int = 0,
    ) -> None:
        self.duplicates = duplicates or set()
        self.aggregated = aggregated or set()
        self.pruned = pruned
        self.inserted: list[str] = []
        self.deliveries: list[tuple[str, str, bool]] = []
        self.prune_calls: list[dict[str, int]] = []
        self.transaction_state: TransactionState | None = None

    def prune_expired_notifications(self, *, cutoff_ms: int, limit: int) -> int:
        if self.transaction_state is not None:
            assert self.transaction_state.active
        self.prune_calls.append({"cutoff_ms": cutoff_ms, "limit": limit})
        return self.pruned

    def insert_notification_with_outcome(self, **kwargs: Any) -> NotificationInsertOutcome:
        dedup_key = str(kwargs["dedup_key"])
        if dedup_key in self.duplicates:
            return NotificationInsertOutcome(row=None, created=False, aggregated=False)
        row = {
            "notification_id": f"notification:{dedup_key}",
            "dedup_key": dedup_key,
            "rule_id": kwargs["rule_id"],
            "channels_json": list(kwargs["channels"]),
            "payload_json": dict(kwargs["payload"]),
        }
        if dedup_key in self.aggregated:
            return NotificationInsertOutcome(row=row, created=False, aggregated=True)
        self.inserted.append(dedup_key)
        return NotificationInsertOutcome(row=row, created=True, aggregated=False)

    def enqueue_delivery(self, **kwargs: Any) -> dict[str, Any]:
        self.deliveries.append((str(kwargs["notification_id"]), str(kwargs["channel_id"]), False))
        return dict(kwargs)

    def enqueue_or_requeue_delivery(self, **kwargs: Any) -> dict[str, Any]:
        self.deliveries.append((str(kwargs["notification_id"]), str(kwargs["channel_id"]), True))
        return dict(kwargs)


class DeliveryRepositoryDouble:
    def __init__(self, *, delivery: dict[str, Any] | None, notification: dict[str, Any] | None) -> None:
        self.delivery = delivery
        self.notification = notification
        self.calls: list[tuple[Any, ...]] = []

    def claim_next_delivery(self, *, now_ms: int | None = None) -> dict[str, Any] | None:
        self.calls.append(("claim", now_ms))
        return self.delivery

    def notification_by_id(self, notification_id: str, *, subscriber_key: str | None = None) -> dict[str, Any] | None:
        self.calls.append(("notification", notification_id, subscriber_key))
        return self.notification

    def complete_delivery(self, delivery: dict[str, Any], *, delivered_at_ms: int | None = None) -> None:
        self.calls.append(("complete", delivery["delivery_id"], delivered_at_ms))

    def fail_delivery(self, delivery: dict[str, Any], *, error: str, now_ms: int | None = None) -> None:
        self.calls.append(("fail", delivery["delivery_id"], error, now_ms))


class RecordingPushAdapter:
    def __init__(self, transaction_state: TransactionState, *, error: str | None = None) -> None:
        self.transaction_state = transaction_state
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def notify_markdown(self, *, url: str, title: str, body: str) -> None:
        assert not self.transaction_state.active
        self.calls.append((url, title, body))
        if self.error:
            raise RuntimeError(self.error)


def _candidate(dedup_key: str, *, rule_id: str = "news_high_signal") -> NotificationCandidate:
    return NotificationCandidate(
        dedup_key=dedup_key,
        rule_id=rule_id,
        severity="high",
        title=dedup_key,
        body=dedup_key,
        entity_type="news_item",
        entity_key=dedup_key,
        source_table="news_items",
        source_id=dedup_key,
        occurrence_at_ms=NOW_MS,
        payload={"semantic_signature": dedup_key},
        channels=("in_app",),
    )


def _rule_worker(
    repository: NotificationRepositoryDouble,
    transaction_state: TransactionState,
    candidates: list[NotificationCandidate],
    **kwargs: Any,
) -> NotificationWorker:
    return NotificationWorker(
        name="notification_rule",
        settings=kwargs.pop("settings", _rule_settings()),
        db=WorkerSessionDB(repository, transaction_state),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine(candidates, delay_seconds=kwargs.pop("delay_seconds", 0)),
        delivery_max_attempts=5,
        retention_days=30,
        **kwargs,
    )


def _delivery_worker(
    repository: DeliveryRepositoryDouble,
    transaction_state: TransactionState,
    adapter: RecordingPushAdapter,
) -> NotificationDeliveryWorker:
    return NotificationDeliveryWorker(
        name="notification_delivery",
        settings=_delivery_settings(),
        db=WorkerSessionDB(repository, transaction_state),
        telemetry=SimpleNamespace(),
        channels={
            "push": SimpleNamespace(
                enabled=True,
                provider="pushdeer",
                url="pushdeer://key",
                min_severity="info",
            )
        },
        adapter=SimpleNamespace(notify=lambda **_kwargs: None),
        pushdeer_adapter=adapter,
    )


def test_rule_worker_offloads_blocking_evaluation_and_returns_worker_result() -> None:
    state = TransactionState()
    repository = NotificationRepositoryDouble()
    worker = _rule_worker(repository, state, [], delay_seconds=0.08)

    async def probe() -> WorkerResult:
        task = asyncio.create_task(worker.run_once(now_ms=NOW_MS))
        await asyncio.sleep(0.01)
        assert not task.done()
        return await task

    result = asyncio.run(probe())

    assert isinstance(worker, WorkerBase)
    assert result == WorkerResult(
        processed=0,
        skipped=1,
        notes={"created": 0, "external_deliveries_enqueued": False, "retention_pruned": 0},
    )
    assert (state.enters, state.exits) == (1, 1)


def test_rule_worker_counts_created_rows_for_batch_limit() -> None:
    state = TransactionState()
    repository = NotificationRepositoryDouble(duplicates={"duplicate-a", "duplicate-b"})
    candidates = [_candidate("duplicate-a"), _candidate("duplicate-b"), _candidate("created")]
    worker = _rule_worker(repository, state, candidates, settings=_rule_settings(batch_size=1))

    rows = asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert [row["dedup_key"] for row in rows] == ["created"]
    assert repository.inserted == ["created"]
    assert (state.enters, state.exits) == (1, 1)


def test_rule_worker_prunes_expired_notifications_at_most_once_per_hour() -> None:
    state = TransactionState()
    repository = NotificationRepositoryDouble(pruned=3)
    repository.transaction_state = state
    worker = _rule_worker(repository, state, [], settings=_rule_settings(batch_size=7))

    first = asyncio.run(worker.run_once(now_ms=NOW_MS))
    asyncio.run(worker.run_once(now_ms=NOW_MS + 3_599_999))
    third = asyncio.run(worker.run_once(now_ms=NOW_MS + 3_600_000))

    retention_ms = 30 * 24 * 60 * 60 * 1_000
    assert repository.prune_calls == [
        {"cutoff_ms": NOW_MS - retention_ms, "limit": 7},
        {"cutoff_ms": NOW_MS + 3_600_000 - retention_ms, "limit": 7},
    ]
    assert first.notes["retention_pruned"] == 3
    assert third.notes["retention_pruned"] == 3


def test_rule_worker_commits_notification_and_delivery_together() -> None:
    state = TransactionState()
    repository = NotificationRepositoryDouble()
    candidate = replace(_candidate("external"), channels=("in_app", "push"))
    worker = _rule_worker(
        repository,
        state,
        [candidate],
        delivery_channels={
            "push": SimpleNamespace(enabled=True, provider="pushdeer", url="pushdeer://key", min_severity="info")
        },
    )

    rows = asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert [row["dedup_key"] for row in rows] == ["external"]
    assert repository.deliveries == [("notification:external", "push", False)]
    assert (state.enters, state.exits) == (1, 1)


def test_rule_worker_requeues_aggregated_external_delivery() -> None:
    state = TransactionState()
    repository = NotificationRepositoryDouble(aggregated={"aggregate"})
    candidate = replace(
        _candidate("aggregate"),
        payload={"semantic_signature": "aggregate", "external_push_eligible": True},
        channels=("in_app", "push"),
    )
    worker = _rule_worker(
        repository,
        state,
        [candidate],
        delivery_channels={
            "push": SimpleNamespace(enabled=True, provider="pushdeer", url="pushdeer://key", min_severity="info")
        },
    )

    assert asyncio.run(worker.process_once(now_ms=NOW_MS)) == []
    assert repository.deliveries == [("notification:aggregate", "push", True)]


def test_delivery_worker_keeps_external_io_outside_transactions() -> None:
    state = TransactionState()
    delivery = {
        "delivery_id": "delivery-1",
        "notification_id": "notification-1",
        "channel_id": "push",
        "provider": "pushdeer",
        "attempt_count": 1,
        "max_attempts": 3,
        "updated_at_ms": NOW_MS,
    }
    repository = DeliveryRepositoryDouble(
        delivery=delivery,
        notification={"notification_id": "notification-1", "title": "Title", "body": "Body"},
    )
    adapter = RecordingPushAdapter(state)
    worker = _delivery_worker(repository, state, adapter)

    assert asyncio.run(worker.process_one(now_ms=NOW_MS)) is True

    assert repository.calls == [
        ("claim", NOW_MS),
        ("notification", "notification-1", None),
        ("complete", "delivery-1", NOW_MS),
    ]
    assert adapter.calls == [("pushdeer://key", "Title", "Body")]
    assert (state.enters, state.exits) == (2, 2)


def test_delivery_worker_records_provider_failure_in_a_new_transaction() -> None:
    state = TransactionState()
    delivery = {
        "delivery_id": "delivery-1",
        "notification_id": "notification-1",
        "channel_id": "push",
        "provider": "pushdeer",
        "attempt_count": 1,
        "max_attempts": 3,
        "updated_at_ms": NOW_MS,
    }
    repository = DeliveryRepositoryDouble(
        delivery=delivery,
        notification={"notification_id": "notification-1", "title": "Title", "body": "Body"},
    )
    worker = _delivery_worker(repository, state, RecordingPushAdapter(state, error="provider-down"))

    result = asyncio.run(worker.run_once(now_ms=NOW_MS))

    assert result.processed == 1
    assert result.failed == 1
    assert repository.calls[-1] == ("fail", "delivery-1", "provider-down", NOW_MS)
    assert (state.enters, state.exits) == (2, 2)


def test_workers_use_formal_statement_timeout() -> None:
    state = TransactionState()
    repository = NotificationRepositoryDouble()
    db = WorkerSessionDB(repository, state)
    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(statement_timeout_seconds=17),
        db=db,
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([]),
        delivery_max_attempts=5,
        retention_days=30,
    )

    asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert db.calls == [{"name": "notification_rule", "statement_timeout_seconds": 17}]


def test_rule_worker_requires_application_transaction_contract() -> None:
    repository = NotificationRepositoryDouble()

    @contextmanager
    def session():
        yield SimpleNamespace(notifications=repository)

    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: session()),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([_candidate("missing-transaction")]),
        delivery_max_attempts=5,
        retention_days=30,
    )

    with pytest.raises(AttributeError, match="transaction"):
        asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert repository.inserted == []
