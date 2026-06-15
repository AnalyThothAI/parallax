import asyncio
from types import SimpleNamespace

import pytest

from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.notifications.repositories.notification_repository import NotificationRepository
from parallax.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from parallax.domains.notifications.runtime.notification_worker import NotificationWorker
from parallax.domains.notifications.types import NotificationCandidate
from parallax.platform.config.settings import NotificationChannelConfig
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


class RecordingWake:
    def __init__(self):
        self.count = 0

    def wake(self):
        self.count += 1


class SingleConnectionDB:
    def __init__(self, conn):
        self.conn = conn

    def worker_session(self, *_args, **_kwargs):
        return repository_session_for_connection(self.conn)


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 0.2,
        "batch_size": 50,
        "max_attempts": 5,
        "statement_timeout_seconds": 30.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def candidate(
    dedup_key="watched_account_activity:event:event-1",
    channels=("in_app",),
    severity="info",
    event_id="event-1",
    source_id="event-1",
    occurrence_at_ms=1_700_000_000_000,
):
    return NotificationCandidate(
        dedup_key=dedup_key,
        rule_id="watched_account_activity",
        severity=severity,
        title="activity",
        body="new watched activity",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id=event_id,
        source_table="events",
        source_id=source_id,
        occurrence_at_ms=occurrence_at_ms,
        payload={"event_id": event_id},
        channels=channels,
    )


def news_candidate(
    *,
    news_item_id: str,
    source_id: str,
    occurrence_at_ms: int,
    semantic_signature: str = "sha256:news-semantic",
    external_push_eligible: bool = True,
    channels=("in_app", "pushdeer"),
    title: str | None = None,
    body: str | None = None,
):
    return NotificationCandidate(
        dedup_key=f"news_high_signal:{semantic_signature}",
        rule_id="news_high_signal",
        severity="critical",
        title=title or f"news {news_item_id}",
        body=body or f"news body {news_item_id}",
        entity_type="news_item",
        entity_key=f"news_item:{news_item_id}",
        source_table="news_page_rows",
        source_id=source_id,
        occurrence_at_ms=occurrence_at_ms,
        payload={
            "news_item_id": news_item_id,
            "semantic_signature": semantic_signature,
            "external_push_signature": "sha256:news-external",
            "external_push_eligible": external_push_eligible,
        },
        channels=channels,
    )


def open_worker(tmp_path, *, candidates, publisher=None, delivery_channels=None, delivery_wake=None):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    repo = NotificationRepository(conn, running_timeout_ms=300_000, stale_running_terminalization_batch_size=100)
    worker = NotificationWorker(
        name="notification_rule",
        settings=worker_settings(),
        db=SingleConnectionDB(conn),
        telemetry=SimpleNamespace(),
        rule_engine=StaticRuleEngine(candidates),
        publisher=publisher,
        delivery_channels=delivery_channels or {},
        delivery_max_attempts=5,
        delivery_wake=delivery_wake,
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


def test_process_once_requeues_failed_delivery_for_new_aggregated_news_occurrence(tmp_path):
    conn, repo, worker = open_worker(
        tmp_path,
        candidates=[
            news_candidate(
                news_item_id="news-1",
                source_id="news-1",
                occurrence_at_ms=1_700_000_000_000,
            )
        ],
        delivery_channels={
            "pushdeer": NotificationChannelConfig(
                enabled=True,
                provider="pushdeer",
                url="pushdeer://test-key",
                min_severity="high",
            )
        },
    )
    try:
        inserted = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        assert len(inserted) == 1
        deliveries = repo.list_deliveries(limit=10)
        assert len(deliveries) == 1
        repo.conn.execute(
            """
            UPDATE notification_deliveries
               SET status = 'dead',
                   attempt_count = 5,
                   max_attempts = 5,
                   last_error = 'pushdeer_notify_failed:80501',
                   updated_at_ms = 1_700_000_120_000
             WHERE delivery_id = %s
            """,
            (deliveries[0]["delivery_id"],),
        )
        repo.conn.commit()

        worker.rule_engine = StaticRuleEngine(
            [
                news_candidate(
                    news_item_id="news-2",
                    source_id="news-2",
                    occurrence_at_ms=1_700_000_300_000,
                )
            ]
        )
        duplicate = asyncio.run(worker.process_once(now_ms=1_700_000_300_500))
        notifications = repo.list_notifications(limit=10, rule_id="news_high_signal")
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert duplicate == []
    assert len(notifications) == 1
    assert notifications[0]["occurrence_count"] == 2
    assert notifications[0]["payload_json"]["news_item_id"] == "news-2"
    assert deliveries[0]["status"] == "pending"
    assert deliveries[0]["attempt_count"] == 0
    assert deliveries[0]["last_error"] is None


def test_process_once_enqueues_news_external_delivery_when_agent_ready_upgrades_same_source(tmp_path):
    conn, repo, worker = open_worker(
        tmp_path,
        candidates=[
            news_candidate(
                news_item_id="news-1",
                source_id="news-1",
                occurrence_at_ms=1_700_000_000_000,
                external_push_eligible=False,
                channels=("in_app",),
                title="provider headline",
                body="provider raw body",
            )
        ],
        delivery_channels={
            "pushdeer": NotificationChannelConfig(
                enabled=True,
                provider="pushdeer",
                url="pushdeer://test-key",
                min_severity="high",
            )
        },
    )
    try:
        inserted = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        assert len(inserted) == 1
        assert repo.list_deliveries(limit=10) == []

        worker.rule_engine = StaticRuleEngine(
            [
                news_candidate(
                    news_item_id="news-1",
                    source_id="news-1",
                    occurrence_at_ms=1_700_000_300_000,
                    external_push_eligible=True,
                    channels=("in_app", "pushdeer"),
                    title="agent title",
                    body="agent brief body",
                )
            ]
        )
        duplicate = asyncio.run(worker.process_once(now_ms=1_700_000_300_500))
        notifications = repo.list_notifications(limit=10, rule_id="news_high_signal")
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert duplicate == []
    assert len(notifications) == 1
    assert notifications[0]["occurrence_count"] == 1
    assert notifications[0]["title"] == "agent title"
    assert notifications[0]["body"] == "agent brief body"
    assert notifications[0]["channels_json"] == ["in_app", "pushdeer"]
    assert len(deliveries) == 1
    assert deliveries[0]["channel_id"] == "pushdeer"
    assert deliveries[0]["status"] == "pending"


def test_process_once_does_not_requeue_failed_delivery_for_non_news_aggregation(tmp_path):
    conn, repo, worker = open_worker(
        tmp_path,
        candidates=[
            candidate(
                dedup_key="watched_account_activity:toly:post:bucket",
                channels=("in_app", "pushdeer"),
                severity="high",
            )
        ],
        delivery_channels={
            "pushdeer": NotificationChannelConfig(
                enabled=True,
                provider="pushdeer",
                url="pushdeer://test-key",
                min_severity="high",
            )
        },
    )
    try:
        inserted = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        assert len(inserted) == 1
        deliveries = repo.list_deliveries(limit=10)
        assert len(deliveries) == 1
        repo.conn.execute(
            """
            UPDATE notification_deliveries
               SET status = 'dead',
                   attempt_count = 5,
                   max_attempts = 5,
                   last_error = 'pushdeer_notify_failed:80501',
                   updated_at_ms = 1_700_000_120_000
             WHERE delivery_id = %s
            """,
            (deliveries[0]["delivery_id"],),
        )
        repo.conn.commit()

        worker.rule_engine = StaticRuleEngine(
            [
                candidate(
                    dedup_key="watched_account_activity:toly:post:bucket",
                    channels=("in_app", "pushdeer"),
                    severity="high",
                    event_id="event-2",
                    source_id="event-2",
                    occurrence_at_ms=1_700_000_300_000,
                )
            ]
        )
        duplicate = asyncio.run(worker.process_once(now_ms=1_700_000_300_500))
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert duplicate == []
    assert deliveries[0]["status"] == "dead"
    assert deliveries[0]["attempt_count"] == 5
    assert deliveries[0]["last_error"] == "pushdeer_notify_failed:80501"


def test_process_once_does_not_requeue_suppressed_news_external_delivery(tmp_path):
    conn, repo, worker = open_worker(
        tmp_path,
        candidates=[
            news_candidate(
                news_item_id="news-1",
                source_id="news-1",
                occurrence_at_ms=1_700_000_000_000,
            )
        ],
        delivery_channels={
            "pushdeer": NotificationChannelConfig(
                enabled=True,
                provider="pushdeer",
                url="pushdeer://test-key",
                min_severity="high",
            )
        },
    )
    try:
        inserted = asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        assert len(inserted) == 1
        deliveries = repo.list_deliveries(limit=10)
        assert len(deliveries) == 1
        repo.conn.execute(
            """
            UPDATE notification_deliveries
               SET status = 'dead',
                   attempt_count = 5,
                   max_attempts = 5,
                   last_error = 'pushdeer_notify_failed:80501',
                   updated_at_ms = 1_700_000_120_000
             WHERE delivery_id = %s
            """,
            (deliveries[0]["delivery_id"],),
        )
        repo.conn.commit()

        worker.rule_engine = StaticRuleEngine(
            [
                news_candidate(
                    news_item_id="news-2",
                    source_id="news-2",
                    occurrence_at_ms=1_700_000_300_000,
                    external_push_eligible=False,
                    channels=("in_app", "pushdeer"),
                )
            ]
        )
        duplicate = asyncio.run(worker.process_once(now_ms=1_700_000_300_500))
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert duplicate == []
    assert deliveries[0]["status"] == "dead"
    assert deliveries[0]["attempt_count"] == 5
    assert deliveries[0]["last_error"] == "pushdeer_notify_failed:80501"


def test_run_once_returns_result_and_wakes_delivery_after_external_enqueue(tmp_path):
    wake = RecordingWake()
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
        delivery_wake=wake,
    )
    try:
        result = asyncio.run(worker.run_once(now_ms=1_700_000_100_000))
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert isinstance(result, WorkerResult)
    assert result.processed == 1
    assert result.notes["external_deliveries_enqueued"] is True
    assert len(deliveries) == 1
    assert wake.count == 1


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


def test_process_once_rolls_back_notification_when_delivery_enqueue_fails(tmp_path, monkeypatch):
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

    def raise_after_notification_insert(self, **_kwargs):
        raise RuntimeError("delivery enqueue failed")

    monkeypatch.setattr(NotificationRepository, "enqueue_delivery", raise_after_notification_insert)
    try:
        with pytest.raises(RuntimeError, match="delivery enqueue failed"):
            asyncio.run(worker.process_once(now_ms=1_700_000_100_000))
        conn.rollback()
        rows = repo.list_notifications(limit=10)
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert rows == []
    assert deliveries == []


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
            name="notification_delivery",
            settings=worker_settings(batch_size=1),
            db=SingleConnectionDB(conn),
            telemetry=SimpleNamespace(),
            channels={
                "audit_log": NotificationChannelConfig(
                    enabled=True,
                    provider="log",
                    min_severity="info",
                )
            },
        )
        processed = asyncio.run(delivery_worker.process_one(now_ms=9_999_999_999_999))
        deliveries = repo.list_deliveries(limit=10)
    finally:
        conn.close()

    assert processed is True
    assert deliveries[0]["status"] == "delivered"
