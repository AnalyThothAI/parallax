from parallax.domains.notifications.repositories.notification_repository import NotificationRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


class RecordingConn:
    def __init__(self, conn):
        self.conn = conn
        self.sql_strings: list[str] = []

    def execute(self, sql, *args, **kwargs):
        self.sql_strings.append(str(sql))
        return self.conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.conn, name)


def repository(tmp_path) -> NotificationRepository:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    return NotificationRepository(conn, running_timeout_ms=300_000, stale_running_terminalization_batch_size=100)


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


def test_insert_notification_suppresses_same_news_semantic_signature_across_external_buckets(tmp_path):
    repo = repository(tmp_path)

    first = repo.insert_notification(
        dedup_key="news_high_signal:semantic:external",
        rule_id="news_high_signal",
        severity="critical",
        title="News high signal",
        body="Agent brief",
        entity_type="news_item",
        entity_key="news_item:news-1",
        symbol="BOV",
        source_table="news_page_rows",
        source_id="news-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={
            "news_item_id": "news-1",
            "semantic_signature": "sha256:news-semantic",
            "external_push_signature": "sha256:news-external",
            "external_push_eligible": True,
        },
        channels=["in_app", "pushdeer"],
    )
    duplicate = repo.insert_notification(
        dedup_key="news_high_signal:semantic:external:new-row",
        rule_id="news_high_signal",
        severity="critical",
        title="News high signal update",
        body="Agent brief again",
        entity_type="news_item",
        entity_key="news_item:news-1",
        symbol="BOV",
        source_table="news_page_rows",
        source_id="news-1-duplicate",
        occurrence_at_ms=1_700_000_060_000,
        payload={
            "news_item_id": "news-1",
            "semantic_signature": "sha256:news-semantic",
            "external_push_signature": "sha256:news-external-next-bucket",
            "external_push_eligible": True,
        },
        channels=["in_app", "pushdeer"],
    )

    rows = repo.list_notifications(limit=10, rule_id="news_high_signal")

    assert first is not None
    assert duplicate is None
    assert len(rows) == 1
    assert rows[0]["occurrence_count"] == 2
    assert rows[0]["payload_json"]["external_push_signature"] == "sha256:news-external-next-bucket"


def test_insert_notification_with_outcome_reports_created_and_aggregated_rows(tmp_path):
    repo = repository(tmp_path)

    created = repo.insert_notification_with_outcome(
        dedup_key="news_high_signal:semantic:first",
        rule_id="news_high_signal",
        severity="critical",
        title="News high signal",
        body="Agent brief",
        entity_type="news_item",
        entity_key="news_item:news-1",
        source_table="news_page_rows",
        source_id="news-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={
            "news_item_id": "news-1",
            "semantic_signature": "sha256:news-semantic",
            "external_push_signature": "sha256:news-external",
            "external_push_eligible": True,
        },
        channels=["in_app", "pushdeer"],
    )
    aggregated = repo.insert_notification_with_outcome(
        dedup_key="news_high_signal:semantic:second",
        rule_id="news_high_signal",
        severity="critical",
        title="News high signal update",
        body="Agent brief update",
        entity_type="news_item",
        entity_key="news_item:news-2",
        source_table="news_page_rows",
        source_id="news-2",
        occurrence_at_ms=1_700_000_060_000,
        payload={
            "news_item_id": "news-2",
            "semantic_signature": "sha256:news-semantic",
            "external_push_signature": "sha256:news-external",
            "external_push_eligible": True,
        },
        channels=["in_app", "pushdeer"],
    )
    legacy_duplicate = repo.insert_notification(
        dedup_key="news_high_signal:semantic:third",
        rule_id="news_high_signal",
        severity="critical",
        title="News high signal legacy update",
        body="Agent brief legacy update",
        entity_type="news_item",
        entity_key="news_item:news-3",
        source_table="news_page_rows",
        source_id="news-3",
        occurrence_at_ms=1_700_000_120_000,
        payload={
            "news_item_id": "news-3",
            "semantic_signature": "sha256:news-semantic",
            "external_push_signature": "sha256:news-external",
            "external_push_eligible": True,
        },
        channels=["in_app", "pushdeer"],
    )

    assert created.created is True
    assert created.aggregated is False
    assert created.row is not None
    assert aggregated.created is False
    assert aggregated.aggregated is True
    assert aggregated.row is not None
    assert aggregated.row["notification_id"] == created.row["notification_id"]
    assert aggregated.row["occurrence_count"] == 2
    assert legacy_duplicate is None


def test_insert_notification_creates_new_news_row_when_semantic_signature_changes(tmp_path):
    repo = repository(tmp_path)

    created = repo.insert_notification_with_outcome(
        dedup_key="news_high_signal:sha256:provider-context",
        rule_id="news_high_signal",
        severity="critical",
        title="Provider headline",
        body="Provider body",
        entity_type="news_item",
        entity_key="news_item:news-1",
        source_table="news_page_rows",
        source_id="news-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={
            "news_item_id": "news-1",
            "semantic_signature": "sha256:provider-context",
            "external_push_signature": None,
            "external_push_eligible": False,
        },
        channels=["in_app"],
    )
    upgraded = repo.insert_notification_with_outcome(
        dedup_key="news_high_signal:sha256:agent-driver",
        rule_id="news_high_signal",
        severity="critical",
        title="Agent title",
        body="Agent body",
        entity_type="news_item",
        entity_key="news_item:news-1",
        source_table="news_page_rows",
        source_id="news-1",
        occurrence_at_ms=1_700_000_120_000,
        payload={
            "news_item_id": "news-1",
            "semantic_signature": "sha256:agent-driver",
            "external_push_signature": "sha256:agent-push",
            "external_push_eligible": True,
        },
        channels=["in_app", "pushdeer"],
    )

    rows = repo.list_notifications(limit=10, rule_id="news_high_signal")

    assert created.created is True
    assert upgraded.created is True
    assert upgraded.aggregated is False
    assert len(rows) == 2
    assert {row["title"] for row in rows} == {"Provider headline", "Agent title"}
    assert {row["payload_json"]["semantic_signature"] for row in rows} == {
        "sha256:provider-context",
        "sha256:agent-driver",
    }


def test_insert_notification_suppresses_same_semantic_signature_only(tmp_path):
    repo = repository(tmp_path)

    first = repo.insert_notification(
        dedup_key="watched_account_token_alert:alert-1:sha256:first",
        rule_id="watched_account_token_alert",
        severity="high",
        title="$SLOP token watch",
        body="Token alert",
        entity_type="token",
        entity_key="token:SLOP",
        symbol="SLOP",
        source_table="token_alerts",
        source_id="alert-1",
        occurrence_at_ms=1_700_000_000_000,
        payload={
            "alert_id": "alert-1",
            "status": "token_watch",
            "symbol": "SLOP",
            "semantic_signature": "sha256:first",
        },
        channels=["in_app", "pushdeer"],
    )
    same_signature = repo.insert_notification(
        dedup_key="watched_account_token_alert:alert-1:sha256:first",
        rule_id="watched_account_token_alert",
        severity="high",
        title="$SLOP token watch",
        body="Token alert",
        entity_type="token",
        entity_key="token:SLOP",
        symbol="SLOP",
        source_table="token_alerts",
        source_id="alert-1",
        occurrence_at_ms=1_700_000_060_000,
        payload={
            "alert_id": "alert-1",
            "status": "token_watch",
            "symbol": "SLOP",
            "semantic_signature": "sha256:first",
        },
        channels=["in_app", "pushdeer"],
    )
    changed_signature = repo.insert_notification(
        dedup_key="watched_account_token_alert:alert-1:sha256:second",
        rule_id="watched_account_token_alert",
        severity="high",
        title="$SLOP token watch",
        body="Token alert",
        entity_type="token",
        entity_key="token:SLOP",
        symbol="SLOP",
        source_table="token_alerts",
        source_id="alert-1",
        occurrence_at_ms=1_700_000_120_000,
        payload={
            "alert_id": "alert-1",
            "status": "token_watch",
            "symbol": "SLOP",
            "semantic_signature": "sha256:second",
        },
        channels=["in_app", "pushdeer"],
    )

    rows = repo.list_notifications(limit=10, rule_id="watched_account_token_alert")

    assert first is not None
    assert same_signature is None
    assert changed_signature is not None
    assert len(rows) == 2
    assert rows[0]["dedup_key"] == "watched_account_token_alert:alert-1:sha256:second"
    assert rows[1]["dedup_key"] == "watched_account_token_alert:alert-1:sha256:first"
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
        dedup_key="news:pepe",
        rule_id="news_high_signal",
        severity="high",
        title="PEPE news",
        body="agent news driver",
        entity_type="token",
        entity_key="token:eth:pepe",
        symbol="PEPE",
        chain="eth",
        address="0xpepe",
        source_table="news_items",
        source_id="token:eth:pepe",
        occurrence_at_ms=1_700_000_060_000,
        payload={"decision_class": "driver"},
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


def test_summary_uses_sql_aggregates_without_materializing_unread_rows(tmp_path):
    repo = repository(tmp_path)
    high_indices = {1, 2, 3, 5}
    rows = []
    for index in range(25):
        row = repo.insert_notification(
            dedup_key=f"activity:event-{index}",
            rule_id="watched_account_activity",
            severity="high" if index in high_indices else "info",
            title="activity",
            body="new post",
            entity_type="account",
            entity_key=f"account:handle{index % 3}",
            author_handle=f"handle{index % 3}",
            event_id=f"event-{index}",
            source_table="events",
            source_id=f"event-{index}",
            occurrence_at_ms=1_700_000_000_000 + index,
            payload={},
            channels=["in_app"],
        )
        assert row is not None
        rows.append(row)
    for index, row in enumerate(rows):
        if index % 4 == 0:
            repo.mark_read(
                notification_id=row["notification_id"],
                subscriber_key="local",
                read_at_ms=1_700_000_100_000 + index,
            )

    recording = RecordingConn(repo.conn)
    summary = NotificationRepository(
        recording, running_timeout_ms=300_000, stale_running_terminalization_batch_size=100
    ).summary(subscriber_key="local")

    assert summary["unread_count"] == 18
    assert summary["critical_unread_count"] == 0
    assert summary["high_unread_count"] == 4
    assert summary["highest_unread_severity"] == "high"
    assert summary["account_unread_counts"] == {"handle0": 6, "handle1": 6, "handle2": 6}
    joined_sql = "\n".join(recording.sql_strings)
    assert "COUNT(*)" in joined_sql
    assert "GROUP BY n.author_handle" in joined_sql
    assert "SELECT n.notification_id, n.severity, n.author_handle" not in joined_sql


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
        repo = NotificationRepository(conn, running_timeout_ms=300_000, stale_running_terminalization_batch_size=100)
        locked_notification = repo.insert_notification(
            dedup_key="delivery:locked",
            rule_id="news_high_signal",
            severity="high",
            title="locked",
            body="locked",
            entity_type="token",
            entity_key="token:eth:locked",
            source_table="news_items",
            source_id="token:eth:locked",
            occurrence_at_ms=1_700_000_000_000,
            payload={},
            channels=["pushdeer"],
        )
        available_notification = repo.insert_notification(
            dedup_key="delivery:available",
            rule_id="news_high_signal",
            severity="high",
            title="available",
            body="available",
            entity_type="token",
            entity_key="token:eth:available",
            source_table="news_items",
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

        claimed = NotificationRepository(
            second_conn, running_timeout_ms=300_000, stale_running_terminalization_batch_size=100
        ).claim_next_delivery(now_ms=1_700_000_000_100)
    finally:
        conn.execute("ROLLBACK")
        second_conn.execute("RESET statement_timeout")
        second_conn.close()
        conn.close()

    assert claimed is not None
    assert claimed["delivery_id"] == available["delivery_id"]


def test_claim_next_delivery_reclaims_stale_running_delivery(tmp_path):
    repo = repository(tmp_path)
    notification = repo.insert_notification(
        dedup_key="delivery:stale",
        rule_id="news_high_signal",
        severity="high",
        title="stale",
        body="stale",
        entity_type="token",
        entity_key="token:eth:stale",
        source_table="news_items",
        source_id="token:eth:stale",
        occurrence_at_ms=1_700_000_000_000,
        payload={},
        channels=["pushdeer"],
    )
    assert notification is not None
    delivery = repo.enqueue_delivery(
        notification_id=notification["notification_id"],
        channel_id="pushdeer",
        provider="apprise",
        max_attempts=5,
        next_run_at_ms=1_700_000_000_000,
    )
    assert delivery is not None
    repo.conn.execute(
        """
        UPDATE notification_deliveries
        SET status = 'running', attempt_count = 1, updated_at_ms = 1_700_000_000_000
        WHERE delivery_id = %s
        """,
        (delivery["delivery_id"],),
    )
    repo.conn.commit()

    claimed = NotificationRepository(
        repo.conn, running_timeout_ms=1_000, stale_running_terminalization_batch_size=100
    ).claim_next_delivery(now_ms=1_700_000_002_000)

    assert claimed is not None
    assert claimed["delivery_id"] == delivery["delivery_id"]
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 2


def test_complete_and_fail_delivery_ignore_stale_claim_after_reclaim(tmp_path):
    repo = repository(tmp_path)
    notification = repo.insert_notification(
        dedup_key="delivery:stale-claim-cas",
        rule_id="news_high_signal",
        severity="high",
        title="stale claim",
        body="stale claim",
        entity_type="token",
        entity_key="token:eth:stale-claim",
        source_table="news_page_rows",
        source_id="token:eth:stale-claim",
        occurrence_at_ms=1_700_000_000_000,
        payload={},
        channels=["pushdeer"],
    )
    assert notification is not None
    delivery = repo.enqueue_delivery(
        notification_id=notification["notification_id"],
        channel_id="pushdeer",
        provider="apprise",
        max_attempts=5,
        next_run_at_ms=1_700_000_000_000,
    )
    assert delivery is not None
    strict_repo = NotificationRepository(
        repo.conn,
        running_timeout_ms=1_000,
        stale_running_terminalization_batch_size=100,
    )

    stale_claim = strict_repo.claim_next_delivery(now_ms=1_700_000_000_100)
    reclaimed = strict_repo.claim_next_delivery(now_ms=1_700_000_001_200)
    assert stale_claim is not None
    assert reclaimed is not None
    assert stale_claim["delivery_id"] == reclaimed["delivery_id"]
    assert stale_claim["attempt_count"] == 1
    assert reclaimed["attempt_count"] == 2

    strict_repo.complete_delivery(stale_claim, delivered_at_ms=1_700_000_001_300)
    strict_repo.fail_delivery(stale_claim, error="late stale failure", now_ms=1_700_000_001_400)
    after_stale_update = strict_repo.delivery_by_id(delivery["delivery_id"])

    assert after_stale_update is not None
    assert after_stale_update["status"] == "running"
    assert after_stale_update["attempt_count"] == 2
    assert after_stale_update["delivered_at_ms"] is None
    assert after_stale_update["last_error"] is None

    strict_repo.complete_delivery(reclaimed, delivered_at_ms=1_700_000_001_500)
    completed = strict_repo.delivery_by_id(delivery["delivery_id"])

    assert completed is not None
    assert completed["status"] == "delivered"
    assert completed["attempt_count"] == 2
    assert completed["delivered_at_ms"] == 1_700_000_001_500


def test_claim_next_delivery_terminalizes_stale_running_rows_in_bounded_batches(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    now_ms = 1_700_000_002_000
    stale_ms = 1_700_000_000_000
    try:
        conn.execute(
            """
            INSERT INTO notifications(
              notification_id, dedup_key, rule_id, severity, title, body,
              entity_type, entity_key, source_table, source_id,
              first_seen_at_ms, last_seen_at_ms, created_at_ms, updated_at_ms
            )
            SELECT 'notif-stale-' || item::text,
                   'dedup-stale-' || item::text,
                   'news_high_signal',
                   'high',
                   'stale',
                   'stale',
                   'news_item',
                   'news:' || item::text,
                   'news_items',
                   'news:' || item::text,
                   %s,
                   %s,
                   %s,
                   %s
              FROM generate_series(1, 101) AS item
            """,
            (stale_ms, stale_ms, stale_ms, stale_ms),
        )
        conn.execute(
            """
            INSERT INTO notification_deliveries(
              delivery_id, notification_id, channel_id, provider, status,
              attempt_count, max_attempts, next_run_at_ms, last_attempt_at_ms,
              created_at_ms, updated_at_ms
            )
            SELECT 'delivery-stale-' || item::text,
                   'notif-stale-' || item::text,
                   'pushdeer',
                   'apprise',
                   'running',
                   5,
                   5,
                   %s,
                   %s,
                   %s,
                   %s
              FROM generate_series(1, 101) AS item
            """,
            (stale_ms, stale_ms, stale_ms, stale_ms),
        )
        repo = NotificationRepository(conn, running_timeout_ms=1_000, stale_running_terminalization_batch_size=100)

        claimed = repo.claim_next_delivery(now_ms=now_ms)
        dead_count = conn.execute(
            "SELECT count(*) AS value FROM notification_deliveries WHERE status = 'dead'"
        ).fetchone()["value"]
    finally:
        conn.close()

    assert claimed is None
    assert dead_count == 100


def test_enqueue_or_requeue_delivery_only_reactivates_failed_or_dead_rows(tmp_path):
    repo = repository(tmp_path)
    rows_by_status = {}
    for index, status in enumerate(("pending", "running", "delivered", "failed", "dead"), start=1):
        notification = repo.insert_notification(
            dedup_key=f"delivery:reactivate:{status}",
            rule_id="news_high_signal",
            severity="critical",
            title=status,
            body=status,
            entity_type="news_item",
            entity_key=f"news_item:{status}",
            source_table="news_page_rows",
            source_id=f"news-{status}",
            occurrence_at_ms=1_700_000_000_000 + index,
            payload={},
            channels=["pushdeer"],
        )
        assert notification is not None
        delivery = repo.enqueue_delivery(
            notification_id=notification["notification_id"],
            channel_id="pushdeer",
            provider="pushdeer",
            max_attempts=5,
            next_run_at_ms=1_700_000_100_000,
        )
        assert delivery is not None
        repo.conn.execute(
            """
            UPDATE notification_deliveries
               SET status = %s,
                   attempt_count = 3,
                   last_error = 'previous_error',
                   delivered_at_ms = CASE WHEN %s = 'delivered' THEN 1700000120000 ELSE NULL END,
                   updated_at_ms = 1700000110000
             WHERE delivery_id = %s
            """,
            (status, status, delivery["delivery_id"]),
        )
        rows_by_status[status] = (notification, delivery)
    repo.conn.commit()

    results = {}
    for status, (notification, delivery) in rows_by_status.items():
        result = repo.enqueue_or_requeue_delivery(
            notification_id=notification["notification_id"],
            channel_id="pushdeer",
            provider="pushdeer",
            max_attempts=5,
            next_run_at_ms=1_700_000_200_000,
        )
        stored = repo.delivery_by_id(delivery["delivery_id"])
        assert stored is not None
        results[status] = (result, stored)

    for status in ("failed", "dead"):
        result, stored = results[status]
        assert result is not None
        assert stored["status"] == "pending"
        assert stored["attempt_count"] == 0
        assert stored["last_error"] is None
        assert stored["next_run_at_ms"] == 1_700_000_200_000

    for status in ("pending", "running", "delivered"):
        result, stored = results[status]
        assert result is None
        assert stored["status"] == status
        assert stored["attempt_count"] == 3
        assert stored["last_error"] == "previous_error"
