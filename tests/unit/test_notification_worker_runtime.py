import asyncio
import time
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.notifications.repositories.notification_repository import (
    NotificationInsertOutcome,
    NotificationRepository,
)
from parallax.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from parallax.domains.notifications.runtime.notification_worker import NotificationWorker
from parallax.domains.notifications.types import NotificationCandidate
from parallax.platform.config.settings import NotificationDeliveryWorkerSettings, NotificationRuleWorkerSettings
from tests.unit.test_notification_rules import NOW_MS


def _rule_settings(**overrides: object) -> NotificationRuleWorkerSettings:
    payload = {
        "enabled": True,
        "interval_seconds": 0.2,
        "batch_size": 10,
        "statement_timeout_seconds": 30,
        **overrides,
    }
    return NotificationRuleWorkerSettings(**payload)


def _delivery_settings(**overrides: object) -> NotificationDeliveryWorkerSettings:
    payload = {
        "enabled": True,
        "interval_seconds": 0.2,
        "batch_size": 1,
        "statement_timeout_seconds": 30,
        **overrides,
    }
    return NotificationDeliveryWorkerSettings(**payload)


def _notification_repository(
    conn: Any,
    *,
    running_timeout_ms: int = 300_000,
    stale_running_terminalization_batch_size: int = 100,
) -> NotificationRepository:
    return NotificationRepository(
        conn,
        running_timeout_ms=running_timeout_ms,
        stale_running_terminalization_batch_size=stale_running_terminalization_batch_size,
    )


class SlowRuleEngine:
    def evaluate(self, *, now_ms: int | None = None) -> list[Any]:
        time.sleep(0.08)
        return []


class FakeRepos:
    notifications = None

    @contextmanager
    def unit_of_work(self):
        yield None


@contextmanager
def fake_repository_session():
    yield FakeRepos()


def test_process_once_does_not_block_event_loop():
    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: fake_repository_session()),
        telemetry=SimpleNamespace(),
        rule_engine=SlowRuleEngine(),
        delivery_max_attempts=5,
    )

    async def run_probe() -> None:
        task = asyncio.create_task(worker.process_once(now_ms=1_700_000_000_000))
        await asyncio.sleep(0.01)
        assert not task.done()
        assert await task == []

    asyncio.run(run_probe())


def test_notification_worker_is_worker_base_and_run_once_returns_result():
    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: fake_repository_session()),
        telemetry=SimpleNamespace(),
        rule_engine=SlowRuleEngine(),
        delivery_max_attempts=5,
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.skipped == 1
    assert result.notes["created"] == 0


def test_worker_batch_limit_counts_created_rows_not_duplicate_candidates():
    duplicate_a = _notification_candidate("duplicate-a", rule_id="watched_account_activity")
    duplicate_b = _notification_candidate("duplicate-b", rule_id="watched_account_activity")
    news = _notification_candidate("news-ready", rule_id="news_high_signal")
    repository = DedupConflictNotificationRepository()
    repository.rows_by_dedup[duplicate_a.dedup_key] = {"notification_id": "existing-a"}
    repository.rows_by_dedup[duplicate_b.dedup_key] = {"notification_id": "existing-b"}
    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(batch_size=1),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: repository_session(repository)),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[duplicate_a, duplicate_b, news]]),
        delivery_max_attempts=5,
    )

    created = asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert len(created) == 1
    assert created[0]["dedup_key"] == "news-ready"
    assert created[0]["rule_id"] == "news_high_signal"


def test_notification_workers_read_formal_settings_for_batch_and_statement_timeout():
    candidate_a = _notification_candidate("formal-a", rule_id="watched_account_activity")
    candidate_b = _notification_candidate("formal-b", rule_id="watched_account_activity")
    repository = DedupConflictNotificationRepository()
    rule_db = RecordingWorkerSessionDB(lambda: repository_session(repository))
    rule_worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(batch_size=1, statement_timeout_seconds=17),
        db=rule_db,
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[candidate_a, candidate_b]]),
        delivery_max_attempts=5,
    )

    created = asyncio.run(rule_worker.process_once(now_ms=NOW_MS))

    assert [row["dedup_key"] for row in created] == ["formal-a"]
    assert rule_db.calls == [{"name": "notification_rule", "statement_timeout_seconds": 17}]

    delivery_repository = RecordingDeliveryRepository(delivery=None, notification=None)
    delivery_state = RecordingTransactionState()
    delivery_db = RecordingWorkerSessionDB(lambda: delivery_repository_session(delivery_repository, delivery_state))
    delivery_worker = NotificationDeliveryWorker(
        name="notification_delivery",
        settings=_delivery_settings(batch_size=2, statement_timeout_seconds=19),
        db=delivery_db,
        telemetry=SimpleNamespace(),
        channels={},
        adapter=NoopNotificationAdapter(),
        pushdeer_adapter=NoopPushDeerAdapter(),
    )

    result = asyncio.run(delivery_worker.run_once(now_ms=NOW_MS))

    assert result.skipped == 1
    assert result.notes["reasons"] == ["no_delivery"]
    assert delivery_db.calls == [{"name": "notification_delivery", "statement_timeout_seconds": 19}]


def test_worker_requires_requeue_contract_for_aggregated_external_delivery():
    base = _notification_candidate("news-aggregated", rule_id="news_high_signal")
    candidate = replace(
        base,
        payload={**base.payload, "external_push_eligible": True},
        channels=("in_app", "pushdeer"),
    )
    repository = AggregatedNotificationRepositoryWithoutRequeue()
    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: repository_session(repository)),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[candidate]]),
        delivery_max_attempts=5,
        delivery_channels={
            "pushdeer": SimpleNamespace(
                enabled=True,
                provider="pushdeer",
                url="https://push.example",
                min_severity="info",
            )
        },
    )

    with pytest.raises(AttributeError, match="enqueue_or_requeue_delivery"):
        asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert repository.deliveries == []


def test_worker_requires_unit_of_work_session_contract():
    candidate = _notification_candidate("requires-uow", rule_id="news_high_signal")
    repository = DedupConflictNotificationRepository()
    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: missing_unit_of_work_session(repository)),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[candidate]]),
        delivery_max_attempts=5,
    )

    with pytest.raises(AttributeError, match="unit_of_work"):
        asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert repository.rows_by_dedup == {}
    assert repository.deliveries == []


def test_worker_requires_formal_insert_outcome_contract_without_row_fallback():
    candidate = _notification_candidate("bad-outcome", rule_id="news_high_signal")

    class BareRowOutcomeRepository:
        def insert_notification_with_outcome(self, **kwargs):
            return {
                "notification_id": "notification-bad-outcome",
                "dedup_key": kwargs["dedup_key"],
                "rule_id": kwargs["rule_id"],
                "channels_json": list(kwargs.get("channels") or []),
                "payload_json": kwargs.get("payload") or {},
            }

    repository = BareRowOutcomeRepository()
    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: repository_session(repository)),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[candidate]]),
        delivery_max_attempts=5,
    )

    with pytest.raises(AttributeError, match="row"):
        asyncio.run(worker.process_once(now_ms=NOW_MS))


def test_worker_requires_delivery_wake_contract_when_external_deliveries_are_enqueued():
    candidate = _notification_candidate("wake-contract", rule_id="news_high_signal")
    candidate = replace(candidate, channels=("in_app", "pushdeer"))
    repository = DedupConflictNotificationRepository()
    worker = NotificationWorker(
        name="notification_rule",
        settings=_rule_settings(batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: repository_session(repository)),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[candidate]]),
        delivery_max_attempts=5,
        delivery_channels={
            "pushdeer": SimpleNamespace(
                enabled=True,
                provider="pushdeer",
                url="https://push.example",
                min_severity="info",
            )
        },
        delivery_wake=object(),
    )

    with pytest.raises(AttributeError, match="wake"):
        asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert len(repository.deliveries) == 1


def test_delivery_worker_requires_session_transaction_before_claim():
    repository = RecordingDeliveryRepository(delivery=None, notification=None)
    worker = NotificationDeliveryWorker(
        name="notification_delivery",
        settings=_delivery_settings(batch_size=1),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: missing_transaction_delivery_session(repository)),
        telemetry=SimpleNamespace(),
        channels={},
        adapter=NoopNotificationAdapter(),
        pushdeer_adapter=NoopPushDeerAdapter(),
    )

    with pytest.raises(AttributeError, match="transaction"):
        asyncio.run(worker.process_one(now_ms=NOW_MS))

    assert repository.calls == []


def test_delivery_worker_keeps_external_io_outside_session_transaction():
    transaction_state = RecordingTransactionState()
    delivery = {
        "delivery_id": "delivery-1",
        "notification_id": "notification-1",
        "channel_id": "pushdeer",
        "provider": "pushdeer",
        "attempt_count": 1,
        "max_attempts": 5,
    }
    notification = {
        "notification_id": "notification-1",
        "title": "Token alert",
        "body": "Body",
    }
    repository = RecordingDeliveryRepository(delivery=delivery, notification=notification)
    pushdeer_adapter = RecordingPushDeerAdapter(transaction_state)
    worker = NotificationDeliveryWorker(
        name="notification_delivery",
        settings=_delivery_settings(batch_size=1),
        db=SimpleNamespace(
            worker_session=lambda *_args, **_kwargs: delivery_repository_session(repository, transaction_state)
        ),
        telemetry=SimpleNamespace(),
        channels={
            "pushdeer": SimpleNamespace(
                enabled=True,
                provider="pushdeer",
                url="pushdeer://push-key",
                min_severity="info",
            )
        },
        adapter=NoopNotificationAdapter(),
        pushdeer_adapter=pushdeer_adapter,
    )

    assert asyncio.run(worker.process_one(now_ms=NOW_MS)) is True

    assert repository.calls == [
        ("claim", NOW_MS, False),
        ("notification_by_id", "notification-1", None),
        ("complete", "delivery-1", NOW_MS, False),
    ]
    assert pushdeer_adapter.calls == [("pushdeer://push-key", "Token alert", "Body")]
    assert transaction_state.enter_count == 2
    assert transaction_state.exit_count == 2


def test_delivery_worker_rejects_malformed_delivery_attempt_contract_without_default():
    transaction_state = RecordingTransactionState()
    delivery = {
        "delivery_id": "delivery-1",
        "notification_id": "notification-1",
        "channel_id": "pushdeer",
        "provider": "pushdeer",
        "attempt_count": 1,
    }
    notification = {
        "notification_id": "notification-1",
        "title": "Token alert",
        "body": "Body",
    }
    repository = RecordingDeliveryRepository(delivery=delivery, notification=notification)
    worker = NotificationDeliveryWorker(
        name="notification_delivery",
        settings=_delivery_settings(batch_size=1),
        db=SimpleNamespace(
            worker_session=lambda *_args, **_kwargs: delivery_repository_session(repository, transaction_state)
        ),
        telemetry=SimpleNamespace(),
        channels={},
        adapter=NoopNotificationAdapter(),
        pushdeer_adapter=NoopPushDeerAdapter(),
    )

    with pytest.raises(RuntimeError, match="notification_delivery_attempt_contract_required"):
        asyncio.run(worker.process_one(now_ms=NOW_MS))

    assert repository.calls == [
        ("claim", NOW_MS, False),
        ("notification_by_id", "notification-1", None),
        ("fail", "delivery-1", "channel_not_configured", NOW_MS, False),
    ]
    assert transaction_state.enter_count == 1
    assert transaction_state.exit_count == 1


def test_notification_repository_writes_require_connection_transaction_before_sql_when_committing():
    conn = NoTransactionNotificationRepositoryConn()

    with pytest.raises(RuntimeError, match="notification_repository_transaction_required"):
        _notification_repository(conn).insert_notification_with_outcome(**_notification_insert_kwargs())

    assert conn.sqls == []


def test_notification_repository_commit_owned_writes_use_connection_transaction_without_manual_commit():
    conn = NotificationRepositoryConn()
    repository = _notification_repository(conn)

    outcome = repository.insert_notification_with_outcome(**_notification_insert_kwargs())
    read_updated = repository.mark_read(notification_id="notification-1", subscriber_key="local")
    read_all_count = repository.mark_all_read(subscriber_key="local")
    author_read_count = repository.mark_author_read(author_handle="Acct", subscriber_key="local")
    delivery = repository.enqueue_delivery(
        notification_id="notification-1",
        channel_id="pushdeer",
        provider="pushdeer",
        max_attempts=3,
    )
    requeued = repository.enqueue_or_requeue_delivery(
        notification_id="notification-1",
        channel_id="pushdeer",
        provider="pushdeer",
        max_attempts=3,
    )

    assert outcome.created is True
    assert read_updated is True
    assert read_all_count == 1
    assert author_read_count == 1
    assert delivery == conn.delivery_row
    assert requeued == conn.delivery_row
    assert conn.commit_count == 0
    assert conn.transaction_enter_count == 6
    assert conn.transaction_exit_count == 6
    assert conn.sql_transaction_depths
    assert all(depth == 1 for depth in conn.sql_transaction_depths)


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repository: repository.insert_notification_with_outcome(**_notification_insert_kwargs()),
            "notification_insert_rowcount_required",
            id="insert-notification",
        ),
        pytest.param(
            lambda repository: repository.enqueue_delivery(
                notification_id="notification-1",
                channel_id="pushdeer",
                provider="pushdeer",
                max_attempts=3,
            ),
            "notification_delivery_enqueue_rowcount_required",
            id="enqueue-delivery",
        ),
        pytest.param(
            lambda repository: repository.enqueue_or_requeue_delivery(
                notification_id="notification-1",
                channel_id="pushdeer",
                provider="pushdeer",
                max_attempts=3,
            ),
            "notification_delivery_requeue_rowcount_required",
            id="requeue-delivery",
        ),
        pytest.param(
            lambda repository: repository.claim_next_delivery(now_ms=NOW_MS),
            "notification_delivery_claim_rowcount_required",
            id="claim-delivery",
        ),
    ],
)
def test_notification_repository_insert_state_requires_cursor_rowcount(operation, error_code):
    conn = NotificationRepositoryConn(omit_rowcount=True)
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match=error_code):
        operation(repository)


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repository: repository.insert_notification_with_outcome(**_notification_insert_kwargs()),
            "notification_insert_rowcount_invalid",
            id="insert-notification",
        ),
        pytest.param(
            lambda repository: repository.enqueue_delivery(
                notification_id="notification-1",
                channel_id="pushdeer",
                provider="pushdeer",
                max_attempts=3,
            ),
            "notification_delivery_enqueue_rowcount_invalid",
            id="enqueue-delivery",
        ),
        pytest.param(
            lambda repository: repository.enqueue_or_requeue_delivery(
                notification_id="notification-1",
                channel_id="pushdeer",
                provider="pushdeer",
                max_attempts=3,
            ),
            "notification_delivery_requeue_rowcount_invalid",
            id="requeue-delivery",
        ),
        pytest.param(
            lambda repository: repository.claim_next_delivery(now_ms=NOW_MS),
            "notification_delivery_claim_rowcount_invalid",
            id="claim-delivery",
        ),
    ],
)
@pytest.mark.parametrize("rowcount", ["bad", True, -1, 2])
def test_notification_repository_insert_state_rejects_invalid_cursor_rowcount(operation, error_code, rowcount):
    conn = NotificationRepositoryConn(rowcount=rowcount)
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match=error_code):
        operation(repository)


def test_notification_repository_aggregate_update_requires_cursor_rowcount():
    conn = AggregateNotificationRepositoryConn(omit_aggregate_rowcount=True)
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match="notification_aggregate_rowcount_required"):
        repository.insert_notification_with_outcome(**_aggregate_notification_insert_kwargs())

    assert any("UPDATE notifications" in sql for sql in conn.sqls)


@pytest.mark.parametrize("rowcount", ["bad", True, -1, 0, 2])
def test_notification_repository_aggregate_update_rejects_invalid_cursor_rowcount(rowcount):
    conn = AggregateNotificationRepositoryConn(aggregate_rowcount=rowcount)
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match="notification_aggregate_rowcount_invalid"):
        repository.insert_notification_with_outcome(**_aggregate_notification_insert_kwargs())

    assert any("UPDATE notifications" in sql for sql in conn.sqls)


def test_notification_repository_aggregate_update_accepts_single_rowcount():
    conn = AggregateNotificationRepositoryConn(aggregate_rowcount=1)
    repository = _notification_repository(conn)

    outcome = repository.insert_notification_with_outcome(**_aggregate_notification_insert_kwargs())

    assert outcome.created is False
    assert outcome.aggregated is True
    assert outcome.row is not None
    assert outcome.row["notification_id"] == "notification-existing"


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repository: repository.enqueue_or_requeue_delivery(
                notification_id="notification-1",
                channel_id="pushdeer",
                provider="pushdeer",
                max_attempts=3,
            ),
            "notification_delivery_requeue_rowcount_invalid",
            id="requeue-delivery",
        ),
        pytest.param(
            lambda repository: repository.claim_next_delivery(now_ms=NOW_MS),
            "notification_delivery_claim_rowcount_invalid",
            id="claim-delivery",
        ),
    ],
)
def test_notification_repository_delivery_returning_rows_reject_rowcount_row_mismatch(operation, error_code):
    conn = NotificationRepositoryConn(rowcount=0)
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match=error_code):
        operation(repository)


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(
            lambda repository: repository.enqueue_or_requeue_delivery(
                notification_id="notification-1",
                channel_id="pushdeer",
                provider="pushdeer",
                max_attempts=3,
            ),
            id="requeue-delivery",
        ),
        pytest.param(
            lambda repository: repository.claim_next_delivery(now_ms=NOW_MS),
            id="claim-delivery",
        ),
    ],
)
def test_notification_repository_delivery_returning_rows_accept_zero_row_noop(operation):
    conn = NotificationRepositoryConn(rowcount=0, return_delivery_row=False)
    repository = _notification_repository(conn)

    assert operation(repository) is None


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repository: repository.mark_read(notification_id="notification-1", subscriber_key="local"),
            "notification_read_mark_rowcount_required",
            id="mark-read",
        ),
        pytest.param(
            lambda repository: repository.mark_all_read(subscriber_key="local"),
            "notification_read_bulk_rowcount_required",
            id="mark-all-read",
        ),
        pytest.param(
            lambda repository: repository.mark_author_read(author_handle="Acct", subscriber_key="local"),
            "notification_read_bulk_rowcount_required",
            id="mark-author-read",
        ),
    ],
)
def test_notification_repository_read_state_requires_cursor_rowcount(operation, error_code):
    conn = NotificationRepositoryConn(omit_rowcount=True)
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match=error_code):
        operation(repository)


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repository: repository.mark_read(notification_id="notification-1", subscriber_key="local"),
            "notification_read_mark_rowcount_invalid",
            id="mark-read",
        ),
        pytest.param(
            lambda repository: repository.mark_all_read(subscriber_key="local"),
            "notification_read_bulk_rowcount_invalid",
            id="mark-all-read",
        ),
        pytest.param(
            lambda repository: repository.mark_author_read(author_handle="Acct", subscriber_key="local"),
            "notification_read_bulk_rowcount_invalid",
            id="mark-author-read",
        ),
    ],
)
@pytest.mark.parametrize("rowcount", ["bad", True, -1, 2])
def test_notification_repository_read_state_rejects_invalid_cursor_rowcount(operation, error_code, rowcount):
    conn = NotificationRepositoryConn(rowcount=rowcount)
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match=error_code):
        operation(repository)


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repository: repository.list_notifications(limit=-1),
            "notification_list_limit_required",
            id="notification-negative",
        ),
        pytest.param(
            lambda repository: repository.list_notifications(limit=True),
            "notification_list_limit_required",
            id="notification-bool",
        ),
        pytest.param(
            lambda repository: repository.list_notifications(limit="10"),
            "notification_list_limit_required",
            id="notification-string",
        ),
        pytest.param(
            lambda repository: repository.list_deliveries(limit=-1),
            "notification_delivery_list_limit_required",
            id="delivery-negative",
        ),
        pytest.param(
            lambda repository: repository.list_deliveries(limit=True),
            "notification_delivery_list_limit_required",
            id="delivery-bool",
        ),
        pytest.param(
            lambda repository: repository.list_deliveries(limit="10"),
            "notification_delivery_list_limit_required",
            id="delivery-string",
        ),
    ],
)
def test_notification_repository_read_lists_reject_malformed_limits_before_sql(operation, error_code):
    conn = NotificationRepositoryConn()
    repository = _notification_repository(conn)

    with pytest.raises(RuntimeError, match=error_code):
        operation(repository)

    assert conn.sqls == []


def test_notification_repository_caller_owned_writes_do_not_open_inner_transaction():
    conn = NotificationRepositoryConn()
    repository = _notification_repository(conn)

    repository.insert_notification_with_outcome(**_notification_insert_kwargs(commit=False))
    repository.enqueue_delivery(
        notification_id="notification-1",
        channel_id="pushdeer",
        provider="pushdeer",
        max_attempts=3,
        commit=False,
    )
    repository.enqueue_or_requeue_delivery(
        notification_id="notification-1",
        channel_id="pushdeer",
        provider="pushdeer",
        max_attempts=3,
        commit=False,
    )

    assert conn.commit_count == 0
    assert conn.transaction_enter_count == 0
    assert conn.sql_transaction_depths
    assert all(depth == 0 for depth in conn.sql_transaction_depths)


def test_notification_repository_fail_delivery_requires_attempt_contract_before_sql():
    conn = NotificationRepositoryConn()
    repository = _notification_repository(conn)

    with pytest.raises(RuntimeError, match="notification_delivery_attempt_contract_required"):
        repository.fail_delivery(
            {
                "delivery_id": "delivery-1",
                "attempt_count": 1,
            },
            error="boom",
            now_ms=NOW_MS,
            commit=False,
        )

    assert conn.sqls == []


def test_notification_repository_complete_delivery_requires_claim_contract_before_sql():
    conn = NotificationRepositoryConn()
    repository = _notification_repository(conn)

    with pytest.raises(RuntimeError, match="notification_delivery_claim_contract_required"):
        repository.complete_delivery(
            {
                "delivery_id": "delivery-1",
                "attempt_count": 1,
            },
            delivered_at_ms=NOW_MS,
            commit=False,
        )

    assert conn.sqls == []


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repository: repository.complete_delivery(
                _delivery_claim(),
                delivered_at_ms=NOW_MS,
                commit=False,
            ),
            "notification_delivery_complete_rowcount_required",
            id="complete-delivery",
        ),
        pytest.param(
            lambda repository: repository.fail_delivery(
                _delivery_claim(),
                error="boom",
                now_ms=NOW_MS,
                commit=False,
            ),
            "notification_delivery_fail_rowcount_required",
            id="fail-delivery",
        ),
        pytest.param(
            lambda repository: repository.claim_next_delivery(now_ms=NOW_MS),
            "notification_delivery_stale_terminalize_rowcount_required",
            id="stale-terminalize",
        ),
    ],
)
def test_notification_repository_delivery_terminal_state_requires_cursor_rowcount(operation, error_code):
    conn = NotificationRepositoryConn(
        omit_rowcount=True,
        omit_stale_terminalization_rowcount=error_code == "notification_delivery_stale_terminalize_rowcount_required",
    )
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match=error_code):
        operation(repository)


@pytest.mark.parametrize(
    ("operation", "error_code"),
    [
        pytest.param(
            lambda repository: repository.complete_delivery(
                _delivery_claim(),
                delivered_at_ms=NOW_MS,
                commit=False,
            ),
            "notification_delivery_complete_rowcount_invalid",
            id="complete-delivery",
        ),
        pytest.param(
            lambda repository: repository.fail_delivery(
                _delivery_claim(),
                error="boom",
                now_ms=NOW_MS,
                commit=False,
            ),
            "notification_delivery_fail_rowcount_invalid",
            id="fail-delivery",
        ),
        pytest.param(
            lambda repository: repository.claim_next_delivery(now_ms=NOW_MS),
            "notification_delivery_stale_terminalize_rowcount_invalid",
            id="stale-terminalize",
        ),
    ],
)
@pytest.mark.parametrize("rowcount", ["bad", True, -1, 2])
def test_notification_repository_delivery_terminal_state_rejects_invalid_cursor_rowcount(
    operation,
    error_code,
    rowcount,
):
    stale_rowcount = (
        101 if error_code == "notification_delivery_stale_terminalize_rowcount_invalid" and rowcount == 2 else rowcount
    )
    conn = NotificationRepositoryConn(
        rowcount=rowcount,
        stale_terminalization_rowcount=stale_rowcount
        if error_code == "notification_delivery_stale_terminalize_rowcount_invalid"
        else 0,
    )
    repository = _notification_repository(conn)

    with pytest.raises(TypeError, match=error_code):
        operation(repository)


@pytest.mark.parametrize(
    ("kwargs", "error_code"),
    [
        (
            {"running_timeout_ms": 0},
            "notification_delivery_running_timeout_ms_required",
        ),
        (
            {"stale_running_terminalization_batch_size": 0},
            "notification_delivery_stale_running_terminalization_batch_size_required",
        ),
    ],
)
def test_notification_repository_requires_positive_running_policy_ints(kwargs, error_code):
    conn = NotificationRepositoryConn()

    with pytest.raises(RuntimeError, match=error_code):
        _notification_repository(conn, **kwargs)


def test_notification_repository_enqueue_delivery_requires_positive_max_attempts_before_sql():
    conn = NotificationRepositoryConn()
    repository = _notification_repository(conn)

    with pytest.raises(RuntimeError, match="notification_delivery_max_attempts_required"):
        repository.enqueue_delivery(
            notification_id="notification-1",
            channel_id="pushdeer",
            provider="pushdeer",
            max_attempts=0,
            commit=False,
        )

    assert conn.sqls == []


class SequenceRuleEngine:
    def __init__(self, batches: list[list[Any]]):
        self.batches = batches

    def evaluate(self, *, now_ms: int | None = None) -> list[Any]:
        if not self.batches:
            return []
        return self.batches.pop(0)


class DedupConflictNotificationRepository:
    def __init__(self):
        self.rows_by_dedup: dict[str, dict[str, Any]] = {}
        self.deliveries: list[dict[str, Any]] = []
        self.conn = SimpleNamespace(commit=lambda: None)

    def insert_notification(self, **kwargs):
        dedup_key = str(kwargs["dedup_key"])
        if dedup_key in self.rows_by_dedup:
            return None
        notification_id = f"notification-{len(self.rows_by_dedup) + 1}"
        row = {
            "notification_id": notification_id,
            "dedup_key": dedup_key,
            "rule_id": kwargs["rule_id"],
            "channels_json": list(kwargs.get("channels") or []),
            "payload_json": kwargs.get("payload") or {},
        }
        self.rows_by_dedup[dedup_key] = row
        return row

    def insert_notification_with_outcome(self, **kwargs):
        row = self.insert_notification(**kwargs)
        return NotificationInsertOutcome(row=row, created=row is not None, aggregated=False)

    def enqueue_delivery(self, **kwargs):
        delivery = {
            "notification_id": kwargs["notification_id"],
            "channel_id": kwargs["channel_id"],
            "provider": kwargs["provider"],
        }
        self.deliveries.append(delivery)
        return delivery


class AggregatedNotificationRepositoryWithoutRequeue(DedupConflictNotificationRepository):
    def insert_notification_with_outcome(self, **kwargs):
        row = {
            "notification_id": "notification-aggregated",
            "dedup_key": kwargs["dedup_key"],
            "rule_id": kwargs["rule_id"],
            "channels_json": list(kwargs.get("channels") or []),
            "payload_json": kwargs.get("payload") or {},
        }
        return NotificationInsertOutcome(row=row, created=False, aggregated=True)


class InMemoryNotificationRepository(NotificationRepository):
    def __init__(self):
        self.memory_conn = InMemoryNotificationConn()
        self.deliveries: list[dict[str, Any]] = []
        super().__init__(
            self.memory_conn,
            running_timeout_ms=300_000,
            stale_running_terminalization_batch_size=100,
        )

    def enqueue_delivery(self, **kwargs):
        delivery = {
            "notification_id": kwargs["notification_id"],
            "channel_id": kwargs["channel_id"],
            "provider": kwargs["provider"],
        }
        self.deliveries.append(delivery)
        return delivery


class InMemoryNotificationConn:
    def __init__(self):
        self.rows: list[dict[str, Any]] = []

    def execute(self, sql, params=()):
        if "INSERT INTO notifications" in sql:
            return self._insert_notification(params)
        if "SELECT * FROM notifications WHERE dedup_key" in sql:
            return _MemoryCursor(self._row_by_dedup(str(params[0])))
        if "payload_json->>'semantic_signature'" in sql:
            return _MemoryCursor(self._row_by_signature(rule_id=params[0], semantic=params[1], external=params[2]))
        if "payload_json->>'external_push_signature'" in sql:
            return _MemoryCursor(self._row_by_external_signature(rule_id=params[0], external=params[1]))
        if "SELECT n.*" in sql:
            return _MemoryCursor(rows=[self._row_by_id(str(params[0]))])
        raise AssertionError(f"unexpected SQL: {sql}")

    def commit(self):
        return None

    def _insert_notification(self, params):
        dedup_key = str(params[1])
        if self._row_by_dedup(dedup_key) is not None:
            return _MemoryCursor(rowcount=0)
        row = {
            "notification_id": params[0],
            "dedup_key": dedup_key,
            "rule_id": params[2],
            "severity": params[3],
            "title": params[4],
            "body": params[5],
            "entity_type": params[6],
            "entity_key": params[7],
            "author_handle": params[8],
            "symbol": params[9],
            "chain": params[10],
            "address": params[11],
            "event_id": params[12],
            "source_table": params[13],
            "source_id": params[14],
            "occurrence_count": params[15],
            "first_seen_at_ms": params[16],
            "last_seen_at_ms": params[17],
            "payload_json": _json_obj(params[18]),
            "channels_json": _json_obj(params[19]),
            "created_at_ms": params[20],
            "updated_at_ms": params[21],
            "read_at_ms": None,
        }
        self.rows.append(row)
        return _MemoryCursor(rowcount=1)

    def _row_by_dedup(self, dedup_key: str):
        return next((row for row in self.rows if row["dedup_key"] == dedup_key), None)

    def _row_by_id(self, notification_id: str):
        return next((row for row in self.rows if row["notification_id"] == notification_id), None)

    def _row_by_signature(self, *, rule_id: str, semantic: str, external: str):
        for row in reversed(self.rows):
            payload = row["payload_json"]
            row_semantic = payload.get("semantic_signature")
            row_external = payload.get("external_push_signature") or "in_app"
            if row["rule_id"] == rule_id and row_semantic == semantic and row_external == external:
                return row
        return None

    def _row_by_external_signature(self, *, rule_id: str, external: str):
        for row in reversed(self.rows):
            payload = row["payload_json"]
            if row["rule_id"] == rule_id and payload.get("external_push_signature") == external:
                return row
        return None


class _MemoryCursor:
    def __init__(self, row=None, rows=None, rowcount: int = 0):
        self.row = row
        self.rows = [row for row in rows if row is not None] if rows is not None else None
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        if self.rows is not None:
            return self.rows
        return [self.row] if self.row is not None else []


def _json_obj(value):
    return getattr(value, "obj", value)


class RecordingDeliveryRepository:
    def __init__(self, *, delivery: dict[str, Any] | None, notification: dict[str, Any] | None):
        self.delivery = delivery
        self.notification = notification
        self.calls: list[tuple[Any, ...]] = []
        self.conn = SimpleNamespace(commit=lambda: self.calls.append(("manual_commit",)))

    def claim_next_delivery(self, *, now_ms: int | None = None, commit: bool = True):
        self.calls.append(("claim", now_ms, commit))
        if commit is not False:
            raise AssertionError("delivery worker must let the session transaction commit claims")
        return self.delivery

    def notification_by_id(self, notification_id: str, *, subscriber_key: str | None = None):
        self.calls.append(("notification_by_id", notification_id, subscriber_key))
        return self.notification

    def complete_delivery(self, delivery: dict[str, Any], *, delivered_at_ms: int | None = None, commit: bool = True):
        self.calls.append(("complete", delivery["delivery_id"], delivered_at_ms, commit))
        if commit is not False:
            raise AssertionError("delivery worker must let the session transaction commit completions")

    def fail_delivery(
        self,
        delivery: dict[str, Any],
        *,
        error: str,
        now_ms: int | None = None,
        commit: bool = True,
    ):
        self.calls.append(("fail", delivery["delivery_id"], error, now_ms, commit))
        if commit is not False:
            raise AssertionError("delivery worker must let the session transaction commit failures")


class RecordingTransactionState:
    def __init__(self):
        self.active = False
        self.enter_count = 0
        self.exit_count = 0

    @contextmanager
    def transaction(self):
        assert not self.active
        self.active = True
        self.enter_count += 1
        try:
            yield None
        finally:
            self.active = False
            self.exit_count += 1


class RecordingWorkerSessionDB:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.calls: list[dict[str, object]] = []

    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        self.calls.append(
            {
                "name": name,
                "statement_timeout_seconds": statement_timeout_seconds,
            }
        )
        return self.session_factory()


class RecordingPushDeerAdapter:
    def __init__(self, transaction_state: RecordingTransactionState):
        self.transaction_state = transaction_state
        self.calls: list[tuple[str, str, str]] = []

    def notify_markdown(self, *, url: str, title: str, body: str) -> None:
        assert not self.transaction_state.active
        self.calls.append((url, title, body))


class NoopNotificationAdapter:
    def notify(self, **_kwargs) -> None:
        return None


class NoopPushDeerAdapter:
    def notify_markdown(self, **_kwargs) -> None:
        return None


class NotificationRepositoryConn:
    def __init__(
        self,
        *,
        rowcount: object = 1,
        omit_rowcount: bool = False,
        return_delivery_row: bool = True,
        stale_terminalization_rowcount: object = 0,
        omit_stale_terminalization_rowcount: bool = False,
    ) -> None:
        self.sqls: list[str] = []
        self.params: list[Any] = []
        self.commit_count = 0
        self.transaction_enter_count = 0
        self.transaction_exit_count = 0
        self.transaction_depth = 0
        self.sql_transaction_depths: list[int] = []
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.stale_terminalization_rowcount = stale_terminalization_rowcount
        self.omit_stale_terminalization_rowcount = omit_stale_terminalization_rowcount
        self.notification_row = {
            "notification_id": "notification-1",
            "dedup_key": "dedup-1",
            "rule_id": "rule-1",
            "severity": "high",
            "title": "Title",
            "body": "Body",
            "entity_type": None,
            "entity_key": None,
            "author_handle": "acct",
            "symbol": None,
            "chain": None,
            "address": None,
            "event_id": "event-1",
            "source_table": "events",
            "source_id": "event-1",
            "occurrence_count": 1,
            "first_seen_at_ms": NOW_MS,
            "last_seen_at_ms": NOW_MS,
            "payload_json": {},
            "channels_json": ["in_app"],
            "created_at_ms": NOW_MS,
            "updated_at_ms": NOW_MS,
        }
        self.delivery_row = (
            {
                "delivery_id": "delivery-1",
                "notification_id": "notification-1",
                "channel_id": "pushdeer",
                "provider": "pushdeer",
                "status": "pending",
                "attempt_count": 0,
                "max_attempts": 3,
                "updated_at_ms": NOW_MS,
            }
            if return_delivery_row
            else None
        )

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.sqls.append(sql_text)
        self.params.append(params)
        self.sql_transaction_depths.append(self.transaction_depth)
        return NotificationRepositoryCursor(self, sql_text)

    def commit(self):
        self.commit_count += 1
        raise AssertionError("manual commit is not allowed in notification repository tests")

    def transaction(self):
        return NotificationRepositoryTransaction(self)


class NoTransactionNotificationRepositoryConn(NotificationRepositoryConn):
    transaction = None


class NotificationRepositoryTransaction:
    def __init__(self, conn: NotificationRepositoryConn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_enter_count += 1
        self.conn.transaction_depth += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.transaction_depth -= 1
        self.conn.transaction_exit_count += 1
        return False


class NotificationRepositoryCursor:
    def __init__(self, conn: NotificationRepositoryConn, sql: str) -> None:
        self.conn = conn
        self.sql = sql
        if "WITH expired AS" in sql:
            if not conn.omit_stale_terminalization_rowcount:
                self.rowcount = conn.stale_terminalization_rowcount
        elif not conn.omit_rowcount:
            self.rowcount = conn.rowcount

    def fetchone(self):
        if "SELECT notification_id FROM notifications WHERE notification_id" in self.sql:
            return {"notification_id": "notification-1"}
        if "FROM notification_deliveries" in self.sql:
            return self.conn.delivery_row
        if "INSERT INTO notification_deliveries" in self.sql and "RETURNING *" in self.sql:
            return self.conn.delivery_row
        if "SELECT n.*" in self.sql:
            return None
        if "highest_unread_rank" in self.sql:
            return {
                "unread_count": 1,
                "high_unread_count": 1,
                "critical_unread_count": 0,
                "highest_unread_rank": 2,
            }
        return None

    def fetchall(self):
        if "SELECT n.*" in self.sql:
            return [self.conn.notification_row]
        if "INSERT INTO notification_reads" in self.sql and "RETURNING notification_id" in self.sql:
            return [{"notification_id": "notification-1"}]
        if "SELECT n.notification_id" in self.sql:
            return [{"notification_id": "notification-1"}]
        if "GROUP BY n.author_handle" in self.sql:
            return [{"author_handle": "acct", "unread_count": 1}]
        return []


class AggregateNotificationRepositoryConn(NotificationRepositoryConn):
    def __init__(
        self,
        *,
        aggregate_rowcount: object = 1,
        omit_aggregate_rowcount: bool = False,
    ) -> None:
        super().__init__(rowcount=1)
        self.aggregate_rowcount = aggregate_rowcount
        self.omit_aggregate_rowcount = omit_aggregate_rowcount
        self.notification_row = {
            **self.notification_row,
            "notification_id": "notification-existing",
            "source_id": "event-existing",
            "event_id": "event-existing",
            "payload_json": {"semantic_signature": "sha256:existing"},
        }

    def execute(self, sql, params=None):
        sql_text = str(sql)
        self.sqls.append(sql_text)
        self.params.append(params)
        self.sql_transaction_depths.append(self.transaction_depth)
        return AggregateNotificationRepositoryCursor(self, sql_text)


class AggregateNotificationRepositoryCursor(NotificationRepositoryCursor):
    conn: AggregateNotificationRepositoryConn

    def __init__(self, conn: AggregateNotificationRepositoryConn, sql: str) -> None:
        self.conn = conn
        self.sql = sql
        if "INSERT INTO notifications" in sql:
            self.rowcount = 0
        elif "UPDATE notifications" in sql:
            if not conn.omit_aggregate_rowcount:
                self.rowcount = conn.aggregate_rowcount
        elif not conn.omit_rowcount:
            self.rowcount = conn.rowcount

    def fetchone(self):
        if "SELECT * FROM notifications WHERE dedup_key" in self.sql:
            return self.conn.notification_row
        return super().fetchone()


def _notification_insert_kwargs(**overrides):
    kwargs = {
        "dedup_key": "dedup-1",
        "rule_id": "rule-1",
        "severity": "high",
        "title": "Title",
        "body": "Body",
        "entity_type": None,
        "entity_key": None,
        "source_table": "events",
        "source_id": "event-1",
        "event_id": "event-1",
        "occurrence_at_ms": NOW_MS,
        "payload": {},
        "channels": ("in_app",),
    }
    kwargs.update(overrides)
    return kwargs


def _aggregate_notification_insert_kwargs(**overrides):
    kwargs = _notification_insert_kwargs(
        source_id="event-new",
        event_id="event-new",
        occurrence_at_ms=NOW_MS + 1,
        payload={"semantic_signature": "sha256:new"},
    )
    kwargs.update(overrides)
    return kwargs


def _delivery_claim(**overrides):
    claim = {
        "delivery_id": "delivery-1",
        "notification_id": "notification-1",
        "channel_id": "pushdeer",
        "provider": "pushdeer",
        "status": "running",
        "attempt_count": 1,
        "max_attempts": 3,
        "updated_at_ms": NOW_MS,
    }
    claim.update(overrides)
    return claim


@contextmanager
def repository_session(repository):
    yield SimpleNamespace(notifications=repository, unit_of_work=fake_unit_of_work)


@contextmanager
def delivery_repository_session(repository, transaction_state: RecordingTransactionState):
    yield SimpleNamespace(notifications=repository, transaction=transaction_state.transaction)


@contextmanager
def missing_unit_of_work_session(repository):
    yield SimpleNamespace(notifications=repository)


@contextmanager
def missing_transaction_delivery_session(repository):
    yield SimpleNamespace(notifications=repository)


@contextmanager
def fake_unit_of_work():
    yield None


def _notification_candidate(dedup_key: str, *, rule_id: str) -> NotificationCandidate:
    return NotificationCandidate(
        dedup_key=dedup_key,
        rule_id=rule_id,
        severity="high",
        title=dedup_key,
        body=dedup_key,
        entity_type="news_item",
        entity_key=dedup_key,
        source_table="test",
        source_id=dedup_key,
        occurrence_at_ms=NOW_MS,
        payload={"semantic_signature": dedup_key},
        channels=("in_app",),
    )
