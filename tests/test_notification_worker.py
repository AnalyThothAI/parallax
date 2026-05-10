import asyncio

from gmgn_twitter_intel.pipeline.notification_delivery import NotificationDeliveryWorker
from gmgn_twitter_intel.pipeline.notification_models import NotificationCandidate
from gmgn_twitter_intel.pipeline.notification_worker import NotificationWorker
from gmgn_twitter_intel.platform.config.settings import NotificationChannelConfig
from gmgn_twitter_intel.storage.notification_repository import NotificationRepository
from tests.postgres_test_utils import connect_postgres_test, repository_session_for_connection
from tests.postgres_test_utils import reset_postgres_schema as migrate


class StaticRuleEngine:
    def __init__(self, candidates):
        self.candidates = candidates

    def evaluate(self, *, now_ms=None):
        self.now_ms = now_ms
        return self.candidates


class RecordingPublisher:
    def __init__(self):
        self.payloads = []

    async def publish(self, payload):
        self.payloads.append(payload)


def candidate(dedup_key="watched_account_activity:event:event-1", channels=("in_app",), severity="info"):
    return NotificationCandidate(
        dedup_key=dedup_key,
        rule_id="watched_account_activity",
        severity=severity,
        title="activity",
        body="new watched activity",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={"event_id": "event-1"},
        channels=channels,
    )


def open_worker(tmp_path, *, candidates, publisher=None, delivery_channels=None):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    repo = NotificationRepository(conn)
    worker = NotificationWorker(
        rule_engine=StaticRuleEngine(candidates),
        publisher=publisher,
        delivery_channels=delivery_channels or {},
        repository_session=lambda: repository_session_for_connection(conn),
        poll_interval=0.2,
    )
    return conn, repo, worker


def test_process_once_inserts_only_new_notifications_and_publishes_them(tmp_path):
    publisher = RecordingPublisher()
    conn, repo, worker = open_worker(
        tmp_path,
        candidates=[candidate(), candidate()],
        publisher=publisher,
    )
    try:
        first = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        second = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        rows = repo.list_notifications(limit=10)
    finally:
        conn.close()

    assert [item["dedup_key"] for item in first] == ["watched_account_activity:event:event-1"]
    assert second == []
    assert len(rows) == 1
    assert [payload["type"] for payload in publisher.payloads] == ["notification"]
    assert publisher.payloads[0]["notification"]["dedup_key"] == "watched_account_activity:event:event-1"


def test_process_once_returns_empty_when_rule_engine_has_no_candidates(tmp_path):
    conn, repo, worker = open_worker(tmp_path, candidates=[])
    try:
        inserted = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        rows = repo.list_notifications(limit=10)
    finally:
        conn.close()

    assert inserted == []
    assert rows == []


def test_process_once_enqueues_external_deliveries_for_new_notifications(tmp_path):
    conn, repo, worker = open_worker(
        tmp_path,
        candidates=[candidate(channels=("in_app", "pushdeer"), severity="high")],
        delivery_channels={
            "pushdeer": NotificationChannelConfig(
                enabled=True,
                provider="apprise",
                url="json://localhost",
                min_severity="warning",
            )
        },
    )
    try:
        inserted = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        deliveries = repo.list_deliveries(limit=10)
        duplicate = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
    finally:
        conn.close()

    assert len(inserted) == 1
    assert len(deliveries) == 1
    assert deliveries[0]["channel_id"] == "pushdeer"
    assert deliveries[0]["provider"] == "apprise"
    assert duplicate == []


def test_process_once_enqueues_log_delivery_without_url(tmp_path):
    conn, repo, worker = open_worker(
        tmp_path,
        candidates=[candidate(channels=("in_app", "audit_log"), severity="warning")],
        delivery_channels={
            "audit_log": NotificationChannelConfig(
                enabled=True,
                provider="log",
                min_severity="info",
            )
        },
    )
    try:
        inserted = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert len(inserted) == 1
    assert len(deliveries) == 1
    assert deliveries[0]["channel_id"] == "audit_log"
    assert deliveries[0]["provider"] == "log"


def test_duplicate_notification_does_not_block_delivery_claim_transaction(tmp_path):
    conn, repo, worker = open_worker(
        tmp_path,
        candidates=[candidate(channels=("in_app", "audit_log"), severity="warning")],
        delivery_channels={
            "audit_log": NotificationChannelConfig(
                enabled=True,
                provider="log",
                min_severity="info",
            )
        },
    )
    try:
        inserted = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        duplicate = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))

        assert len(inserted) == 1
        assert duplicate == []
        assert conn.in_transaction is False

        delivery_worker = NotificationDeliveryWorker(
            channels={
                "audit_log": NotificationChannelConfig(
                    enabled=True,
                    provider="log",
                    min_severity="info",
                )
            },
            repository_session=lambda: repository_session_for_connection(conn),
            poll_interval=0.2,
        )
        processed = asyncio.run(delivery_worker.process_one(now_ms=9_999_999_999_999))
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert processed is True
    assert deliveries[0]["status"] == "delivered"
