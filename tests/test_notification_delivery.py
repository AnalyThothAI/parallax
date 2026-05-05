import asyncio

from gmgn_twitter_intel.pipeline.notification_delivery import NotificationDeliveryWorker
from gmgn_twitter_intel.settings import NotificationChannelConfig
from gmgn_twitter_intel.storage.notification_repository import NotificationRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate


class RecordingAdapter:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.sent = []

    def notify(self, *, url, title, body, body_format="text"):
        if self.fail:
            raise RuntimeError("provider unavailable")
        self.sent.append({"url": url, "title": title, "body": body, "body_format": body_format})


def open_repo(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    return conn, NotificationRepository(conn)


def seed_delivery(repo: NotificationRepository, *, max_attempts=3):
    notification = repo.insert_notification(
        dedup_key="hot:pepe",
        rule_id="hot_quality_token_5m",
        severity="high",
        title="PEPE heat",
        body="Heat 88, quality 76",
        entity_type="token",
        entity_key="token:eth:pepe",
        symbol="PEPE",
        source_table="token_flow",
        source_id="token:eth:pepe",
        occurrence_at_ms=1_700_000_000_000,
        payload={"social_heat_score": 88},
        channels=["in_app", "pushdeer"],
    )
    assert notification is not None
    delivery = repo.enqueue_delivery(
        notification_id=notification["notification_id"],
        channel_id="pushdeer",
        provider="apprise",
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
        worker = NotificationDeliveryWorker(
            repository=repo,
            channels={
                "pushdeer": NotificationChannelConfig(
                    enabled=True,
                    provider="apprise",
                    url="json://localhost",
                    min_severity="warning",
                )
            },
            adapter=adapter,
            poll_interval=0.2,
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
            "title": "PEPE heat",
            "body": "Heat 88, quality 76",
            "body_format": "text",
        }
    ]
    assert notification["title"] == "PEPE heat"


def test_delivery_worker_retries_and_then_marks_dead_after_max_attempts(tmp_path):
    conn, repo = open_repo(tmp_path)
    adapter = RecordingAdapter(fail=True)
    try:
        _, delivery = seed_delivery(repo, max_attempts=1)
        worker = NotificationDeliveryWorker(
            repository=repo,
            channels={
                "pushdeer": NotificationChannelConfig(
                    enabled=True,
                    provider="apprise",
                    url="json://localhost",
                    min_severity="warning",
                    max_attempts=1,
                )
            },
            adapter=adapter,
            poll_interval=0.2,
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
            WHERE delivery_id = ?
            """,
            (delivery["delivery_id"],),
        )
        conn.commit()
        worker = NotificationDeliveryWorker(
            repository=repo,
            channels={
                "audit_log": NotificationChannelConfig(
                    enabled=True,
                    provider="log",
                    min_severity="info",
                )
            },
            adapter=adapter,
            poll_interval=0.2,
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
