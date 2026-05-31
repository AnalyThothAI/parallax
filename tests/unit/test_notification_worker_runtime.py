import asyncio
import time
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.notifications.repositories.notification_repository import NotificationRepository
from parallax.domains.notifications.runtime.notification_worker import NotificationWorker
from parallax.domains.notifications.types import NotificationCandidate
from tests.unit.test_notification_rules import (
    NOW_MS,
    FakePulse,
    _signal_pulse_notifications,
    pulse_candidate,
)
from tests.unit.test_notification_rules import (
    engine as notification_rule_engine,
)


class SlowRuleEngine:
    def evaluate(self, *, now_ms: int | None = None) -> list[Any]:
        time.sleep(0.08)
        return []


class FakeRepos:
    notifications = None


@contextmanager
def fake_repository_session():
    yield FakeRepos()


def test_process_once_does_not_block_event_loop():
    worker = NotificationWorker(
        name="notification_rule",
        settings=SimpleNamespace(enabled=True, interval_seconds=0.2, batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: fake_repository_session()),
        telemetry=SimpleNamespace(),
        rule_engine=SlowRuleEngine(),
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
        settings=SimpleNamespace(enabled=True, interval_seconds=0.2, batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: fake_repository_session()),
        telemetry=SimpleNamespace(),
        rule_engine=SlowRuleEngine(),
    )

    result = asyncio.run(worker.run_once(now_ms=1_700_000_000_000))

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.skipped == 1
    assert result.notes["created"] == 0


def test_worker_does_not_swallow_later_signal_pulse_external_identity():
    notifications = _signal_pulse_notifications(channels=["in_app", "pushdeer"], statuses=["token_watch"])
    in_app_only = _only_signal_pulse_candidate(
        pulse_candidate("pulse-watch", status="token_watch", edge_events=["score_band_crossed"]),
        notifications=notifications,
    )
    external = _only_signal_pulse_candidate(
        pulse_candidate("pulse-watch", status="token_watch", edge_events=["pulse_status_changed"]),
        notifications=notifications,
    )
    repository = DedupConflictNotificationRepository()
    worker = NotificationWorker(
        name="notification_rule",
        settings=SimpleNamespace(enabled=True, interval_seconds=0.2, batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: repository_session(repository)),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[in_app_only], [external]]),
        delivery_channels={
            "pushdeer": SimpleNamespace(
                enabled=True,
                provider="pushdeer",
                url="https://push.example",
                min_severity="info",
            )
        },
    )

    first = asyncio.run(worker.process_once(now_ms=NOW_MS))
    second = asyncio.run(worker.process_once(now_ms=NOW_MS + 1))

    assert in_app_only.payload["in_app_signature"] == external.payload["in_app_signature"]
    assert in_app_only.payload["external_push_signature"] is None
    assert external.payload["external_push_signature"]
    assert len(first) == 1
    assert len(second) == 1
    assert len(repository.deliveries) == 1
    assert repository.deliveries[0]["notification_id"] == second[0]["notification_id"]


def test_worker_suppresses_delivery_when_external_signature_already_exists_for_new_in_app_signature():
    notifications = _signal_pulse_notifications(channels=["in_app", "pushdeer"], statuses=["token_watch"])
    first = _only_signal_pulse_candidate(
        pulse_candidate("pulse-watch", status="token_watch", edge_events=["pulse_status_changed"]),
        notifications=notifications,
    )
    changed = pulse_candidate("pulse-watch", status="token_watch", edge_events=["pulse_status_changed"])
    changed["decision_json"] = {
        **changed["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "4h",
            "watch_signals": ["新增独立作者"],
            "exit_triggers": ["讨论降温"],
        },
    }
    second = _only_signal_pulse_candidate(changed, notifications=notifications)
    repository = InMemoryNotificationRepository()
    worker = NotificationWorker(
        name="notification_rule",
        settings=SimpleNamespace(enabled=True, interval_seconds=0.2, batch_size=10),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: repository_session(repository)),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[first], [second]]),
        delivery_channels={
            "pushdeer": SimpleNamespace(
                enabled=True,
                provider="pushdeer",
                url="https://push.example",
                min_severity="info",
            )
        },
    )

    first_created = asyncio.run(worker.process_once(now_ms=NOW_MS))
    second_created = asyncio.run(worker.process_once(now_ms=NOW_MS + 1))

    assert first.payload["in_app_signature"] != second.payload["in_app_signature"]
    assert first.payload["external_push_signature"] == second.payload["external_push_signature"]
    assert first_created[0]["channels_json"] == ["in_app", "pushdeer"]
    assert first_created[0]["payload_json"]["external_push_eligible"] is True
    assert second_created[0]["channels_json"] == ["in_app"]
    assert second_created[0]["payload_json"]["external_push_eligible"] is False
    assert second_created[0]["payload_json"]["external_push_suppression_reason"] == "external_cooldown_duplicate"
    assert [delivery["notification_id"] for delivery in repository.deliveries] == [first_created[0]["notification_id"]]


def test_worker_batch_limit_counts_created_rows_not_duplicate_candidates():
    duplicate_a = _notification_candidate("duplicate-a", rule_id="watched_account_activity")
    duplicate_b = _notification_candidate("duplicate-b", rule_id="watched_account_activity")
    news = _notification_candidate("news-ready", rule_id="news_high_signal")
    repository = DedupConflictNotificationRepository()
    repository.rows_by_dedup[duplicate_a.dedup_key] = {"notification_id": "existing-a"}
    repository.rows_by_dedup[duplicate_b.dedup_key] = {"notification_id": "existing-b"}
    worker = NotificationWorker(
        name="notification_rule",
        settings=SimpleNamespace(enabled=True, interval_seconds=0.2, batch_size=1),
        db=SimpleNamespace(worker_session=lambda *_args, **_kwargs: repository_session(repository)),
        telemetry=SimpleNamespace(),
        rule_engine=SequenceRuleEngine([[duplicate_a, duplicate_b, news]]),
    )

    created = asyncio.run(worker.process_once(now_ms=NOW_MS))

    assert len(created) == 1
    assert created[0]["dedup_key"] == "news-ready"
    assert created[0]["rule_id"] == "news_high_signal"


def test_signal_pulse_duplicate_lookup_uses_in_app_and_external_signatures():
    class RecordingConn:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))
            return SimpleNamespace(fetchone=lambda: {"notification_id": "existing"})

    conn = RecordingConn()
    repo = NotificationRepository(conn)

    row = repo._semantic_signature_duplicate(
        rule_id="signal_pulse_candidate",
        payload={"in_app_signature": "sha256:in-app", "external_push_signature": "sha256:external"},
    )

    assert row == {"notification_id": "existing"}
    sql, params = conn.calls[-1]
    assert "COALESCE(payload_json->>'semantic_signature', payload_json->>'in_app_signature')" in sql
    assert "COALESCE(payload_json->>'external_push_signature', 'in_app')" in sql
    assert "notification_signature" not in sql
    assert params == ("signal_pulse_candidate", "sha256:in-app", "sha256:external")


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

    def enqueue_delivery(self, **kwargs):
        delivery = {
            "notification_id": kwargs["notification_id"],
            "channel_id": kwargs["channel_id"],
            "provider": kwargs["provider"],
        }
        self.deliveries.append(delivery)
        return delivery


class InMemoryNotificationRepository(NotificationRepository):
    def __init__(self):
        self.memory_conn = InMemoryNotificationConn()
        self.deliveries: list[dict[str, Any]] = []
        super().__init__(self.memory_conn)

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
        if "COALESCE(payload_json->>'in_app_signature'" in sql:
            return _MemoryCursor(self._row_by_signature(rule_id=params[0], in_app=params[1], external=params[2]))
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

    def _row_by_signature(self, *, rule_id: str, in_app: str, external: str):
        for row in reversed(self.rows):
            payload = row["payload_json"]
            row_in_app = payload.get("in_app_signature")
            row_external = payload.get("external_push_signature") or "in_app"
            if row["rule_id"] == rule_id and row_in_app == in_app and row_external == external:
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


@contextmanager
def repository_session(repository):
    yield SimpleNamespace(notifications=repository)


def _only_signal_pulse_candidate(row: dict, *, notifications):
    candidates = notification_rule_engine(pulse=FakePulse([row]), notifications=notifications).evaluate(now_ms=NOW_MS)
    pulse_candidates = [item for item in candidates if item.rule_id == "signal_pulse_candidate"]
    assert len(pulse_candidates) == 1
    return pulse_candidates[0]


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
        payload={"in_app_signature": dedup_key},
        channels=("in_app",),
    )
