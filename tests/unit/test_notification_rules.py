from __future__ import annotations

import pytest

from parallax.domains.notifications.services.notification_rules import NotificationRuleEngine
from parallax.platform.config.settings import NotificationsConfig, Settings

NOW_MS = 1_700_000_300_000


class FakeEvidence:
    def __init__(self, events: list[dict[str, object]] | None = None) -> None:
        self.events = events or []
        self.calls: list[dict[str, object]] = []

    def recent_events(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(kwargs)
        return self.events


class FakeAccountAlerts:
    def __init__(self, alerts: list[dict[str, object]] | None = None) -> None:
        self.alerts = alerts or []
        self.calls: list[dict[str, object]] = []

    def account_alerts(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(kwargs)
        return self.alerts


def _engine(
    *,
    events: list[dict[str, object]] | None = None,
    alerts: list[dict[str, object]] | None = None,
    notifications: NotificationsConfig | None = None,
) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=Settings(
            ws_token="secret",
            handles=("toly",),
            notifications=notifications or NotificationsConfig(),
        ),
        evidence=FakeEvidence(events),
        account_alerts=FakeAccountAlerts(alerts),
    )


def test_account_activity_uses_material_event_identity_and_cooldown_bucket() -> None:
    rule_engine = _engine(
        events=[
            {
                "event_id": "event-1",
                "author_handle": "toly",
                "action": "tweet",
                "received_at_ms": NOW_MS - 10_000,
                "text_clean": "building on base",
            }
        ]
    )

    candidate = next(item for item in rule_engine.evaluate(now_ms=NOW_MS) if item.rule_id == "watched_account_activity")

    assert candidate.dedup_key == f"watched_account_activity:account:toly:tweet:{(NOW_MS - 10_000) // 300_000}"
    assert candidate.source_table == "events"
    assert candidate.source_id == "event-1"
    assert candidate.payload == {
        "event_id": "event-1",
        "author_handle": "toly",
        "action": "tweet",
        "received_at_ms": NOW_MS - 10_000,
    }


@pytest.mark.parametrize("received_at_ms", (None, 0, True, "1700000000000"))
def test_account_activity_rejects_invalid_material_timestamp(received_at_ms: object) -> None:
    with pytest.raises(ValueError, match="notification_source_timestamp_required"):
        _engine(
            events=[
                {
                    "event_id": "event-1",
                    "author_handle": "toly",
                    "action": "tweet",
                    "received_at_ms": received_at_ms,
                }
            ]
        ).evaluate(now_ms=NOW_MS)


def test_account_token_alert_preserves_source_identity_and_first_seen_flags() -> None:
    rule_engine = _engine(
        alerts=[
            {
                "alert_id": "alert-1",
                "event_id": "event-1",
                "author_handle": "toly",
                "normalized_value": "PEPE",
                "entity_key": "symbol:PEPE",
                "received_at_ms": NOW_MS - 10_000,
                "is_first_seen_global": True,
                "is_first_seen_by_author": True,
            }
        ]
    )

    candidate = next(
        item for item in rule_engine.evaluate(now_ms=NOW_MS) if item.rule_id == "watched_account_token_alert"
    )

    assert candidate.dedup_key == (
        f"watched_account_token_alert:symbol:PEPE:author:toly:{(NOW_MS - 10_000) // 900_000}"
    )
    assert candidate.severity == "warning"
    assert candidate.source_id == "alert-1"
    assert candidate.payload["is_first_seen_global"] is True


def test_formal_query_windows_are_forwarded() -> None:
    notifications = NotificationsConfig(candidate_limit=4, watched_activity_window_ms=2 * 60 * 60_000)
    rule_engine = _engine(notifications=notifications)

    rule_engine.evaluate(now_ms=NOW_MS)

    assert rule_engine.evidence.calls == [
        {
            "limit": 4,
            "since_ms": NOW_MS - 2 * 60 * 60_000,
            "watched_only": True,
        }
    ]
    assert rule_engine.account_alerts.calls == [{"window": "1h", "limit": 4, "now_ms": NOW_MS}]


def test_disabled_notification_runtime_emits_nothing() -> None:
    rule_engine = _engine(
        events=[{"event_id": "event-1", "received_at_ms": NOW_MS}],
        notifications=NotificationsConfig(enabled=False),
    )

    assert rule_engine.evaluate(now_ms=NOW_MS) == []
