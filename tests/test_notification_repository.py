from gmgn_twitter_intel.storage.notification_repository import NotificationRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def repository(tmp_path) -> NotificationRepository:
    conn = connect_postgres_test(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    return NotificationRepository(conn)


def test_insert_notification_is_idempotent_by_dedup_key(tmp_path):
    repo = repository(tmp_path)

    first = repo.insert_notification(
        dedup_key="rule:event-1",
        rule_id="watched_account_activity",
        severity="info",
        title="toly has new activity",
        body="A watched account posted.",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={"event_id": "event-1"},
        channels=["in_app"],
    )
    duplicate = repo.insert_notification(
        dedup_key="rule:event-1",
        rule_id="watched_account_activity",
        severity="info",
        title="duplicate",
        body="duplicate",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={"event_id": "event-1"},
        channels=["in_app"],
    )

    rows = repo.list_notifications(limit=10)

    assert first is not None
    assert duplicate is None
    assert len(rows) == 1
    assert rows[0]["notification_id"] == first["notification_id"]
    assert rows[0]["read_at_ms"] is None
    assert rows[0]["payload_json"] == {"event_id": "event-1"}


def test_summary_and_mark_read_use_subscriber_read_state(tmp_path):
    repo = repository(tmp_path)
    info = repo.insert_notification(
        dedup_key="activity:event-1",
        rule_id="watched_account_activity",
        severity="info",
        title="activity",
        body="new post",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={},
        channels=["in_app"],
    )
    high = repo.insert_notification(
        dedup_key="hot:pepe:5m",
        rule_id="hot_quality_token_5m",
        severity="high",
        title="PEPE heat",
        body="heat score 88",
        entity_type="token",
        entity_key="token:eth:pepe",
        symbol="PEPE",
        chain="eth",
        address="0xpepe",
        source_table="token_flow",
        source_id="token:eth:pepe",
        occurrence_at_ms=1_700_000_060_000,
        payload={"social_heat_score": 88},
        channels=["in_app"],
    )
    assert info is not None
    assert high is not None

    summary = repo.summary(subscriber_key="local")
    assert summary["unread_count"] == 2
    assert summary["high_unread_count"] == 1
    assert summary["account_unread_counts"] == {"toly": 1}

    repo.mark_read(notification_id=high["notification_id"], subscriber_key="local", read_at_ms=1_700_000_070_000)

    rows = repo.list_notifications(limit=10, subscriber_key="local", unread_only=True)
    summary = repo.summary(subscriber_key="local")

    assert [row["notification_id"] for row in rows] == [info["notification_id"]]
    assert summary["unread_count"] == 1
    assert summary["high_unread_count"] == 0


def test_mark_all_read_only_affects_selected_subscriber(tmp_path):
    repo = repository(tmp_path)
    row = repo.insert_notification(
        dedup_key="activity:event-1",
        rule_id="watched_account_activity",
        severity="info",
        title="activity",
        body="new post",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={},
        channels=["in_app"],
    )
    assert row is not None

    count = repo.mark_all_read(subscriber_key="alice", read_at_ms=1_700_000_070_000)

    assert count == 1
    assert repo.summary(subscriber_key="alice")["unread_count"] == 0
    assert repo.summary(subscriber_key="bob")["unread_count"] == 1
