import asyncio
from types import SimpleNamespace

import pytest

from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.notifications.repositories.notification_repository import NotificationRepository
from gmgn_twitter_intel.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from gmgn_twitter_intel.domains.notifications.runtime.notification_worker import NotificationWorker
from gmgn_twitter_intel.domains.notifications.types import NotificationCandidate
from gmgn_twitter_intel.platform.config.settings import NotificationChannelConfig
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


def open_worker(tmp_path, *, candidates, publisher=None, delivery_channels=None, delivery_wake=None):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    repo = NotificationRepository(conn)
    worker = NotificationWorker(
        name="notification_rule",
        settings=worker_settings(),
        db=SingleConnectionDB(conn),
        telemetry=SimpleNamespace(),
        rule_engine=StaticRuleEngine(candidates),
        publisher=publisher,
        delivery_channels=delivery_channels or {},
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
