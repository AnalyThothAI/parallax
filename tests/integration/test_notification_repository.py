from gmgn_twitter_intel.domains.notifications.repositories.notification_repository import NotificationRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def repository(tmp_path) -> NotificationRepository:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    return NotificationRepository(conn)


def test_insert_notification_aggregates_duplicate_dedup_key_without_returning_new_row(tmp_path):
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
        payload={"event_id": "event-1", "version": 1},
        channels=["in_app"],
    )
    duplicate = repo.insert_notification(
        dedup_key="rule:event-1",
        rule_id="watched_account_activity",
        severity="info",
        title="toly has new activity",
        body="A watched account posted again.",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-2",
        source_table="events",
        source_id="event-2",
        occurrence_at_ms=1_700_000_060_000,
        payload={"event_id": "event-2", "version": 2},
        channels=["in_app"],
    )

    rows = repo.list_notifications(limit=10)

    assert first is not None
    assert duplicate is None
    assert len(rows) == 1
    assert rows[0]["notification_id"] == first["notification_id"]
    assert rows[0]["read_at_ms"] is None
    assert rows[0]["occurrence_count"] == 2
    assert rows[0]["first_seen_at_ms"] == 1_700_000_000_000
    assert rows[0]["last_seen_at_ms"] == 1_700_000_060_000
    assert rows[0]["payload_json"]["event_id"] == "event-2"
    assert rows[0]["payload_json"]["version"] == 2
    assert rows[0]["payload_json"]["_aggregation_source_refs"] == ["events:event-1", "events:event-2"]


def test_insert_notification_does_not_recount_same_source_conflicts(tmp_path):
    repo = repository(tmp_path)

    first = repo.insert_notification(
        dedup_key="activity:toly:post:bucket",
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
        payload={"event_id": "event-1", "version": 1},
        channels=["in_app"],
    )
    duplicate_poll = repo.insert_notification(
        dedup_key="activity:toly:post:bucket",
        rule_id="watched_account_activity",
        severity="info",
        title="toly has new activity",
        body="A watched account posted again.",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_120_000,
        payload={"event_id": "event-1", "version": 2},
        channels=["in_app"],
    )

    rows = repo.list_notifications(limit=10)

    assert first is not None
    assert duplicate_poll is None
    assert len(rows) == 1
    assert rows[0]["occurrence_count"] == 1
    assert rows[0]["last_seen_at_ms"] == 1_700_000_000_000
    assert rows[0]["payload_json"]["version"] == 1


def test_insert_notification_aggregates_each_source_once_per_dedup_key(tmp_path):
    repo = repository(tmp_path)

    repo.insert_notification(
        dedup_key="activity:toly:post:bucket",
        rule_id="watched_account_activity",
        severity="info",
        title="toly has new activity",
        body="First post.",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={"event_id": "event-1", "version": 1},
        channels=["in_app"],
    )
    repo.insert_notification(
        dedup_key="activity:toly:post:bucket",
        rule_id="watched_account_activity",
        severity="info",
        title="toly has new activity",
        body="Second post.",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-2",
        source_table="events",
        source_id="event-2",
        occurrence_at_ms=1_700_000_060_000,
        payload={"event_id": "event-2", "version": 2},
        channels=["in_app"],
    )
    repo.insert_notification(
        dedup_key="activity:toly:post:bucket",
        rule_id="watched_account_activity",
        severity="info",
        title="toly has new activity",
        body="First post reappeared in the next scan.",
        entity_type="account",
        entity_key="account:toly",
        author_handle="toly",
        event_id="event-1",
        source_table="events",
        source_id="event-1",
        occurrence_at_ms=1_700_000_120_000,
        payload={"event_id": "event-1", "version": 3},
        channels=["in_app"],
    )

    rows = repo.list_notifications(limit=10)

    assert len(rows) == 1
    assert rows[0]["occurrence_count"] == 2
    assert rows[0]["last_seen_at_ms"] == 1_700_000_060_000
    assert rows[0]["payload_json"]["event_id"] == "event-2"


def test_insert_notification_suppresses_same_pulse_source_status_with_different_key(tmp_path):
    repo = repository(tmp_path)

    old_key = repo.insert_notification(
        dedup_key="signal_pulse_candidate:pulse-1:sha256:old-signature",
        rule_id="signal_pulse_candidate",
        severity="high",
        title="$SLOP token watch",
        body="Signal Pulse",
        entity_type="pulse_candidate",
        entity_key="pulse_candidate:pulse-1",
        symbol="SLOP",
        source_table="pulse_candidates",
        source_id="pulse-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={"candidate_id": "pulse-1", "pulse_status": "token_watch", "symbol": "SLOP"},
        channels=["in_app", "pushdeer"],
    )
    same_source_status = repo.insert_notification(
        dedup_key="signal_pulse_candidate:pulse-1:token_watch:944444",
        rule_id="signal_pulse_candidate",
        severity="high",
        title="$SLOP token watch",
        body="Signal Pulse",
        entity_type="pulse_candidate",
        entity_key="pulse_candidate:pulse-1",
        symbol="SLOP",
        source_table="pulse_candidates",
        source_id="pulse-1",
        occurrence_at_ms=1_700_000_060_000,
        payload={"candidate_id": "pulse-1", "pulse_status": "token_watch", "symbol": "SLOP"},
        channels=["in_app", "pushdeer"],
    )

    rows = repo.list_notifications(limit=10, rule_id="signal_pulse_candidate")

    assert old_key is not None
    assert same_source_status is None
    assert len(rows) == 1
    assert rows[0]["dedup_key"] == "signal_pulse_candidate:pulse-1:sha256:old-signature"
    assert rows[0]["occurrence_count"] == 1


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


def test_claim_next_delivery_skips_row_locked_by_another_worker(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    second_conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        repo = NotificationRepository(conn)
        locked_notification = repo.insert_notification(
            dedup_key="delivery:locked",
            rule_id="hot_quality_token_5m",
            severity="high",
            title="locked",
            body="locked",
            entity_type="token",
            entity_key="token:eth:locked",
            source_table="token_flow",
            source_id="token:eth:locked",
            occurrence_at_ms=1_700_000_000_000,
            payload={},
            channels=["pushdeer"],
        )
        available_notification = repo.insert_notification(
            dedup_key="delivery:available",
            rule_id="hot_quality_token_5m",
            severity="high",
            title="available",
            body="available",
            entity_type="token",
            entity_key="token:eth:available",
            source_table="token_flow",
            source_id="token:eth:available",
            occurrence_at_ms=1_700_000_000_001,
            payload={},
            channels=["pushdeer"],
        )
        assert locked_notification is not None
        assert available_notification is not None
        locked = repo.enqueue_delivery(
            notification_id=locked_notification["notification_id"],
            channel_id="pushdeer",
            provider="apprise",
            max_attempts=5,
            next_run_at_ms=1_700_000_000_000,
        )
        available = repo.enqueue_delivery(
            notification_id=available_notification["notification_id"],
            channel_id="pushdeer",
            provider="apprise",
            max_attempts=5,
            next_run_at_ms=1_700_000_000_000,
        )
        assert locked is not None
        assert available is not None
        conn.execute(
            """
            UPDATE notification_deliveries
            SET next_run_at_ms = 1_700_000_000_000, created_at_ms = 1_700_000_000_000
            WHERE delivery_id = %s
            """,
            (locked["delivery_id"],),
        )
        conn.execute(
            """
            UPDATE notification_deliveries
            SET next_run_at_ms = 1_700_000_000_000, created_at_ms = 1_700_000_000_001
            WHERE delivery_id = %s
            """,
            (available["delivery_id"],),
        )
        conn.commit()
        conn.execute("BEGIN")
        conn.execute(
            "SELECT delivery_id FROM notification_deliveries WHERE delivery_id = %s FOR UPDATE",
            (locked["delivery_id"],),
        )
        second_conn.execute("SET statement_timeout TO 200")

        claimed = NotificationRepository(second_conn).claim_next_delivery(now_ms=1_700_000_000_100)
    finally:
        conn.execute("ROLLBACK")
        second_conn.execute("RESET statement_timeout")
        second_conn.close()
        conn.close()

    assert claimed is not None
    assert claimed["delivery_id"] == available["delivery_id"]
