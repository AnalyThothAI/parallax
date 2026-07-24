import asyncio
from types import SimpleNamespace

from tests.notification_helpers import insert_notification_row
from tests.postgres_test_utils import connect_postgres_test, repository_session_for_connection
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tracefold.notifications import NotificationDeliveryWorker, NotificationRepository
from tracefold.platform.config.settings import NotificationChannelConfig
from tracefold.platform.workers.worker_base import WorkerBase
from tracefold.platform.workers.worker_result import WorkerResult


class RecordingAdapter:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.sent = []

    def notify(self, *, url, title, body, body_format="text"):
        if self.fail:
            raise RuntimeError("provider unavailable")
        self.sent.append({"url": url, "title": title, "body": body, "body_format": body_format})


class RecordingPushDeerAdapter:
    def __init__(self):
        self.sent = []

    def notify_markdown(self, *, url, title, body):
        self.sent.append({"url": url, "title": title, "body": body})


def open_repo(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    return conn, NotificationRepository(conn, running_timeout_ms=300_000, stale_running_terminalization_batch_size=100)


class SingleConnectionDB:
    def __init__(self, conn):
        self.conn = conn

    def worker_session(self, *_args, **_kwargs):
        return repository_session_for_connection(self.conn)


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 0.2,
        "batch_size": 1,
        "max_attempts": 5,
        "statement_timeout_seconds": 30.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def delivery_worker(conn, *, channels, adapter=None, pushdeer_adapter=None, settings=None):
    return NotificationDeliveryWorker(
        name="notification_delivery",
        settings=settings or worker_settings(),
        db=SingleConnectionDB(conn),
        telemetry=SimpleNamespace(),
        channels=channels,
        adapter=adapter,
        pushdeer_adapter=pushdeer_adapter,
    )


def seed_delivery(repo: NotificationRepository, *, max_attempts=3, provider="apprise"):
    notification = insert_notification_row(
        repo,
        dedup_key="watched-account-token-alert:pepe",
        rule_id="watched_account_token_alert",
        severity="high",
        title="$PEPE token watch",
        body="A watched account referenced PEPE.",
        entity_type="token",
        entity_key="token:eth:pepe",
        symbol="PEPE",
        source_table="token_alerts",
        source_id="token:eth:pepe",
        occurrence_at_ms=1_700_000_000_000,
        payload={"alert_id": "token:eth:pepe", "status": "token_watch"},
        channels=["in_app", "pushdeer"],
    )
    assert notification is not None
    delivery = repo.enqueue_delivery(
        notification_id=notification["notification_id"],
        channel_id="pushdeer",
        provider=provider,
        max_attempts=max_attempts,
        next_run_at_ms=1_700_000_000_000,
    )
    assert delivery is not None
    return notification, delivery


def test_delivery_worker_sends_pending_delivery_and_marks_delivered(tmp_path):
    conn, repo = open_repo(tmp_path)
    adapter = RecordingAdapter()
    try:
        notification, delivery = seed_delivery(repo)
        worker = delivery_worker(
            conn,
            channels={
                "pushdeer": NotificationChannelConfig(
                    enabled=True,
                    provider="apprise",
                    url="json://localhost",
                    min_severity="warning",
                )
            },
            adapter=adapter,
        )

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        updated = repo.delivery_by_id(delivery["delivery_id"])
    finally:
        conn.close()

    assert processed is True
    assert updated is not None
    assert updated["status"] == "delivered"
    assert updated["delivered_at_ms"] == 1_700_000_000_100
    assert adapter.sent == [
        {
            "url": "json://localhost",
            "title": "$PEPE token watch",
            "body": "A watched account referenced PEPE.",
            "body_format": "text",
        }
    ]
    assert notification["title"] == "$PEPE token watch"


def test_delivery_worker_retries_and_then_marks_dead_after_max_attempts(tmp_path):
    conn, repo = open_repo(tmp_path)
    adapter = RecordingAdapter(fail=True)
    try:
        _, delivery = seed_delivery(repo, max_attempts=1)
        worker = delivery_worker(
            conn,
            channels={
                "pushdeer": NotificationChannelConfig(
                    enabled=True,
                    provider="apprise",
                    url="json://localhost",
                    min_severity="warning",
                )
            },
            adapter=adapter,
        )

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        updated = repo.delivery_by_id(delivery["delivery_id"])
    finally:
        conn.close()

    assert processed is True
    assert updated is not None
    assert updated["status"] == "dead"
    assert updated["attempt_count"] == 1
    assert "provider unavailable" in updated["last_error"]


def test_delivery_worker_completes_log_channel_without_url_or_adapter(tmp_path):
    conn, repo = open_repo(tmp_path)
    adapter = RecordingAdapter(fail=True)
    try:
        notification, delivery = seed_delivery(repo)
        conn.execute(
            """
            UPDATE notification_deliveries
            SET channel_id = 'audit_log',
                provider = 'log'
            WHERE delivery_id = %s
            """,
            (delivery["delivery_id"],),
        )
        conn.commit()
        worker = delivery_worker(
            conn,
            channels={
                "audit_log": NotificationChannelConfig(
                    enabled=True,
                    provider="log",
                    min_severity="info",
                )
            },
            adapter=adapter,
        )

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        updated = repo.delivery_by_id(delivery["delivery_id"])
    finally:
        conn.close()

    assert processed is True
    assert updated is not None
    assert updated["status"] == "delivered"
    assert adapter.sent == []
    assert notification["notification_id"] == updated["notification_id"]


def test_delivery_worker_sends_pushdeer_provider_as_markdown(tmp_path):
    conn, repo = open_repo(tmp_path)
    pushdeer_adapter = RecordingPushDeerAdapter()
    try:
        _, delivery = seed_delivery(repo, provider="pushdeer")
        worker = delivery_worker(
            conn,
            channels={
                "pushdeer": NotificationChannelConfig(
                    enabled=True,
                    provider="pushdeer",
                    url="pushdeers://pushKey",
                    min_severity="high",
                )
            },
            pushdeer_adapter=pushdeer_adapter,
        )

        processed = asyncio.run(worker.process_one(now_ms=1_700_000_000_100))
        updated = repo.delivery_by_id(delivery["delivery_id"])
    finally:
        conn.close()

    assert processed is True
    assert updated is not None
    assert updated["status"] == "delivered"
    assert pushdeer_adapter.sent == [
        {
            "url": "pushdeers://pushKey",
            "title": "$PEPE token watch",
            "body": "A watched account referenced PEPE.",
        }
    ]


def test_delivery_worker_is_worker_base_and_run_once_returns_result(tmp_path):
    conn, repo = open_repo(tmp_path)
    adapter = RecordingAdapter()
    try:
        _, delivery = seed_delivery(repo)
        worker = delivery_worker(
            conn,
            channels={
                "pushdeer": NotificationChannelConfig(
                    enabled=True,
                    provider="apprise",
                    url="json://localhost",
                    min_severity="warning",
                )
            },
            adapter=adapter,
        )

        result = asyncio.run(worker.run_once(now_ms=1_700_000_000_100))
        updated = repo.delivery_by_id(delivery["delivery_id"])
    finally:
        conn.close()

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.processed == 1
    assert updated is not None
    assert updated["status"] == "delivered"
