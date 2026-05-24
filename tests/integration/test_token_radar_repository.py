from __future__ import annotations

from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_PROJECTION_VERSION,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    TokenRadarDirtyTargetRepository,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository
from gmgn_twitter_intel.domains.token_intel.services.token_radar_projection import TokenRadarProjection
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_projection_coverage_round_trips_ready_zero_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenRadarRepository(conn)
        repo.mark_coverage(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="5m",
            scope="matched",
            status="ready",
            reason=None,
            source_rows=17,
            row_count=0,
            computed_at_ms=1_778_000_000_000,
            started_at_ms=1_777_999_990_000,
            finished_at_ms=1_778_000_000_000,
            error=None,
        )

        coverage = repo.latest_coverage(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=("5m",),
            scopes=("matched",),
        )
    finally:
        conn.close()

    assert coverage == {
        ("5m", "matched"): {
            "status": "ready",
            "reason": None,
            "source_rows": 17,
            "row_count": 0,
            "computed_at_ms": 1_778_000_000_000,
            "error": None,
        }
    }


def test_projection_coverage_round_trips_failed_state_without_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenRadarRepository(conn)
        repo.mark_coverage(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="1h",
            scope="all",
            status="failed",
            reason="query_timeout",
            source_rows=0,
            row_count=0,
            computed_at_ms=1_778_000_000_000,
            started_at_ms=1_777_999_990_000,
            finished_at_ms=1_778_000_000_000,
            error="statement timeout",
        )

        coverage = repo.latest_coverage(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=("1h",),
            scopes=("all",),
        )
    finally:
        conn.close()

    assert coverage[("1h", "all")]["status"] == "failed"
    assert coverage[("1h", "all")]["reason"] == "query_timeout"
    assert coverage[("1h", "all")]["error"] == "statement timeout"


def test_publish_and_latest_current_rows_persist_factor_snapshot_json(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    row = {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 1_778_000_000_000,
        "lane": "resolved",
        "rank": 1,
        "intent_id": "intent-1",
        "event_id": "event-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": "feed-1",
        "intent_json": {"display_symbol": "BOV"},
        "asset_json": {},
        "primary_venue_json": None,
        "target_json": {"symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(rank_score=12),
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "decision": "discard",
        "data_health_json": {"factor_snapshot": "ready"},
        "source_event_ids_json": ["event-1"],
        "created_at_ms": 1_778_000_000_000,
    }
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
        )

        latest = repo.latest_current_rows(
            window="1h",
            scope="all",
            limit=10,
            projection_version="token-radar-v11-factor-alpha-gated",
        )
    finally:
        conn.close()

    assert latest[0]["factor_snapshot_json"]["schema_version"] == TOKEN_FACTOR_SNAPSHOT_VERSION
    assert latest[0]["target_type_key"] == "Asset"
    assert latest[0]["identity_id"] == "asset-1"
    assert latest[0]["payload_hash"]


def test_publish_rows_replaces_current_and_retains_audit_history(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    older = _valid_factor_row()
    older["row_id"] = "row-factor-older"
    older["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=25)
    newer = _valid_factor_row()
    newer["row_id"] = "row-factor-newer"
    newer["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=75)
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[older],
        )
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_060_000,
            rows=[newer],
        )
        retained = conn.execute(
            """
            SELECT row_id
            FROM token_radar_snapshot_audit
            WHERE projection_version = %s AND "window" = %s AND scope = %s
            ORDER BY computed_at_ms ASC
            """,
            ("token-radar-v11-factor-alpha-gated", "1h", "all"),
        ).fetchall()
        current = repo.latest_current_rows(
            window="1h",
            scope="all",
            limit=10,
            projection_version="token-radar-v11-factor-alpha-gated",
        )
    finally:
        conn.close()

    assert [row["row_id"] for row in retained] == ["row-factor-older", "row-factor-newer"]
    assert [row["row_id"] for row in current] == ["row-factor-newer"]
    assert current[0]["listed_at_ms"] == 1_778_000_000_000


def test_publish_rows_does_not_duplicate_history_or_audit_for_unchanged_payload(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    row = _valid_factor_row()
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
        )
        conn.execute(
            """
            UPDATE token_radar_target_first_seen
            SET updated_at_ms = 1234
            WHERE identity_id = 'asset-1'
            """
        )
        row["row_id"] = "row-factor-same-later"
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_060_000,
            rows=[row],
        )
        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM token_radar_rank_history) AS rank_history_count,
              (SELECT count(*) FROM token_radar_snapshot_audit) AS snapshot_audit_count,
              (
                SELECT computed_at_ms
                FROM token_radar_current_rows
                WHERE identity_id = 'asset-1'
              ) AS current_computed_at_ms,
              (
                SELECT updated_at_ms
                FROM token_radar_target_first_seen
                WHERE identity_id = 'asset-1'
              ) AS first_seen_updated_at_ms
            """
        ).fetchone()
    finally:
        conn.close()

    assert counts["rank_history_count"] == 1
    assert counts["snapshot_audit_count"] == 1
    assert counts["current_computed_at_ms"] == 1_778_000_000_000
    assert counts["first_seen_updated_at_ms"] == 1234


def test_upsert_target_feature_unchanged_payload_does_not_advance_score_timestamps(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    row = _valid_factor_row()
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        first_count = repo.upsert_target_feature(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            row=row,
            computed_at_ms=1_778_000_000_000,
        )
        second_count = repo.upsert_target_feature(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            row=row,
            computed_at_ms=1_778_000_060_000,
        )
        persisted = conn.execute(
            """
            SELECT last_scored_at_ms, updated_at_ms
            FROM token_radar_target_features
            WHERE identity_id = 'asset-1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert first_count == 1
    assert second_count == 0
    assert persisted["last_scored_at_ms"] == 1_778_000_000_000
    assert persisted["updated_at_ms"] == 1_778_000_000_000


def test_enqueue_market_targets_clears_previous_error_without_timestamp_churn(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_registry_asset(conn)
        repo = TokenRadarDirtyTargetRepository(conn)
        first_count = repo.enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_000_000,
        )
        conn.execute(
            """
            UPDATE token_radar_dirty_targets
            SET last_error = 'projection failed',
                updated_at_ms = 1
            WHERE target_type_key = 'Asset'
              AND identity_id = 'asset-1'
            """
        )
        second_count = repo.enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_060_000,
        )
        stored = conn.execute(
            """
            SELECT last_error, due_at_ms, updated_at_ms
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset'
              AND identity_id = 'asset-1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert first_count == 1
    assert second_count == 1
    assert stored["last_error"] is None
    assert stored["due_at_ms"] == 1_778_000_000_000
    assert stored["updated_at_ms"] == 1_778_000_060_000


def test_enqueue_market_targets_skips_when_target_feature_market_data_is_fresh(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_registry_asset(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        TokenRadarRepository(conn).upsert_target_feature(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="1h",
            scope="all",
            row=_valid_factor_row(),
            computed_at_ms=1_778_000_000_000,
        )
        count = TokenRadarDirtyTargetRepository(conn).enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_030_000,
        )
        stored_count = conn.execute("SELECT count(*) AS count FROM token_radar_dirty_targets").fetchone()
    finally:
        conn.close()

    assert count == 0
    assert stored_count["count"] == 0


def test_enqueue_market_targets_does_not_let_old_claim_delete_new_market_dirty(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_registry_asset(conn)
        repo = TokenRadarDirtyTargetRepository(conn)
        repo.enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_000_000,
        )
        claimed = repo.claim_due(
            limit=1,
            lease_ms=120_000,
            now_ms=1_778_000_001_000,
            lease_owner="projection-a",
        )
        old_claim = claimed[0]

        reenqueue_count = repo.enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_002_000,
        )
        after_reenqueue = conn.execute(
            """
            SELECT payload_hash, leased_until_ms, lease_owner
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset'
              AND identity_id = 'asset-1'
            """
        ).fetchone()
        old_done_count = repo.mark_done([old_claim], now_ms=1_778_000_003_000)
        remaining = conn.execute(
            """
            SELECT payload_hash, leased_until_ms, lease_owner
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset'
              AND identity_id = 'asset-1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert reenqueue_count == 1
    assert after_reenqueue["payload_hash"] != old_claim["payload_hash"]
    assert after_reenqueue["leased_until_ms"] is None
    assert after_reenqueue["lease_owner"] is None
    assert old_done_count == 0
    assert remaining is not None
    assert remaining["payload_hash"] == after_reenqueue["payload_hash"]


def test_mark_done_does_not_let_expired_claim_delete_successor_claim(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_registry_asset(conn)
        repo = TokenRadarDirtyTargetRepository(conn)
        repo.enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_000_000,
        )
        old_claim = repo.claim_due(
            limit=1,
            lease_ms=1_000,
            now_ms=1_778_000_001_000,
            lease_owner="projection-a",
        )[0]
        successor_claim = repo.claim_due(
            limit=1,
            lease_ms=120_000,
            now_ms=1_778_000_003_000,
            lease_owner="projection-b",
        )[0]

        old_done_count = repo.mark_done([old_claim], now_ms=1_778_000_004_000)
        remaining = conn.execute(
            """
            SELECT payload_hash, attempt_count, lease_owner
            FROM token_radar_dirty_targets
            WHERE target_type_key = 'Asset'
              AND identity_id = 'asset-1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert successor_claim["payload_hash"] == old_claim["payload_hash"]
    assert successor_claim["attempt_count"] > old_claim["attempt_count"]
    assert old_done_count == 0
    assert remaining is not None
    assert remaining["attempt_count"] == successor_claim["attempt_count"]
    assert remaining["lease_owner"] == "projection-b"


def test_empty_target_projection_marks_market_freshness_to_debounce_market_ticks(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_registry_asset(conn)
        repos = type(
            "Repos",
            (),
            {
                "conn": conn,
                "token_radar": TokenRadarRepository(conn),
                "token_radar_dirty_targets": TokenRadarDirtyTargetRepository(conn),
            },
        )()
        first_count = repos.token_radar_dirty_targets.enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_000_000,
        )

        result = TokenRadarProjection(repos=repos).rebuild_dirty_targets(
            windows=("5m",),
            scopes=("all",),
            now_ms=1_778_000_001_000,
            limit=10,
        )
        second_count = repos.token_radar_dirty_targets.enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_030_000,
        )
        target_coverage = conn.execute(
            """
            SELECT latest_market_observed_at_ms
            FROM token_radar_target_projection_coverage
            WHERE projection_version = %s
              AND target_type_key = 'Asset'
              AND identity_id = 'asset-1'
            """,
            (TOKEN_RADAR_PROJECTION_VERSION,),
        ).fetchone()
        dirty_count = conn.execute("SELECT count(*) AS count FROM token_radar_dirty_targets").fetchone()
    finally:
        conn.close()

    assert first_count == 1
    assert result["status"] == "ready"
    assert target_coverage["latest_market_observed_at_ms"] == 1_778_000_001_000
    assert second_count == 0
    assert dirty_count["count"] == 0


def test_publish_rows_removes_exited_current_rows_and_audits_rank_exit(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    first = _valid_factor_row()
    first["row_id"] = "row-asset-1"
    first["rank"] = 1
    first["target_id"] = "asset-1"
    second = _valid_factor_row()
    second["row_id"] = "row-asset-2"
    second["rank"] = 2
    second["intent_id"] = "intent-2"
    second["event_id"] = "event-2"
    second["target_id"] = "asset-2"
    entrant = _valid_factor_row()
    entrant["row_id"] = "row-asset-3"
    entrant["rank"] = 1
    entrant["intent_id"] = "intent-3"
    entrant["event_id"] = "event-3"
    entrant["target_id"] = "asset-3"
    entrant["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=99)
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_token_intent(conn, intent_id="intent-2", event_id="event-2")
        _insert_token_intent(conn, intent_id="intent-3", event_id="event-3")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[first, second],
        )
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_060_000,
            rows=[entrant],
        )
        current = conn.execute(
            """
            SELECT identity_id, rank
            FROM token_radar_current_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s
            ORDER BY rank ASC
            """,
            ("token-radar-v11-factor-alpha-gated", "1h", "all"),
        ).fetchall()
        audit_reasons = conn.execute(
            """
            SELECT audit_reason, identity_id
            FROM token_radar_snapshot_audit
            WHERE projection_version = %s AND "window" = %s AND scope = %s
              AND recorded_at_ms = %s
            ORDER BY audit_reason ASC, identity_id ASC
            """,
            ("token-radar-v11-factor-alpha-gated", "1h", "all", 1_778_000_060_000),
        ).fetchall()
    finally:
        conn.close()

    assert [(row["identity_id"], row["rank"]) for row in current] == [("asset-3", 1)]
    assert [(row["audit_reason"], row["identity_id"]) for row in audit_reasons] == [
        ("rank_enter", "asset-3"),
        ("rank_exit", "asset-1"),
        ("rank_exit", "asset-2"),
    ]


def test_publish_rows_can_upsert_rank_swaps_without_current_row_delete(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    first = _valid_factor_row()
    first["row_id"] = "row-asset-1"
    first["rank"] = 1
    first["target_id"] = "asset-1"
    second = _valid_factor_row()
    second["row_id"] = "row-asset-2"
    second["rank"] = 2
    second["intent_id"] = "intent-2"
    second["event_id"] = "event-2"
    second["target_id"] = "asset-2"
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_token_intent(conn, intent_id="intent-2", event_id="event-2")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[first, second],
        )
        first["rank"] = 2
        second["rank"] = 1
        first["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=10)
        second["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=90)
        repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_060_000,
            rows=[second, first],
        )
        ranks = conn.execute(
            """
            SELECT identity_id, rank
            FROM token_radar_current_rows
            WHERE projection_version = %s AND "window" = %s AND scope = %s
            ORDER BY rank ASC
            """,
            ("token-radar-v11-factor-alpha-gated", "1h", "all"),
        ).fetchall()
    finally:
        conn.close()

    assert [(row["identity_id"], row["rank"]) for row in ranks] == [("asset-2", 1), ("asset-1", 2)]


def test_publish_rows_rejects_old_rows_after_newer_zero_row_coverage(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    stale_row = _valid_factor_row()
    stale_row["row_id"] = "row-factor-stale"
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        repo.mark_coverage(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            status="ready",
            row_count=0,
            computed_at_ms=1_778_000_060_000,
        )

        written = repo.publish_rows(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[stale_row],
        )
        current = repo.latest_current_rows(
            window="1h",
            scope="all",
            limit=10,
            projection_version="token-radar-v11-factor-alpha-gated",
        )
    finally:
        conn.close()

    assert written is False
    assert current == []


def _valid_factor_row() -> dict[str, object]:
    return {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 1_778_000_000_000,
        "lane": "resolved",
        "rank": 1,
        "intent_id": "intent-1",
        "event_id": "event-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": "feed-1",
        "intent_json": {"display_symbol": "BOV"},
        "asset_json": {},
        "primary_venue_json": None,
        "target_json": {"symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(),
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "decision": "discard",
        "data_health_json": {"factor_snapshot": "ready"},
        "source_event_ids_json": ["event-1"],
        "created_at_ms": 1_778_000_000_000,
    }


def _insert_pricefeed(conn, pricefeed_id: str) -> None:
    conn.execute(
        """
        INSERT INTO price_feeds(
          pricefeed_id, feed_type, provider, subject_type, subject_id, native_market_id,
          status, evidence_level, first_seen_at_ms, updated_at_ms
        )
        VALUES (%s, 'test_feed', 'test', 'Asset', 'asset-1', %s, 'canonical', 'test_fixture', %s, %s)
        ON CONFLICT(pricefeed_id) DO NOTHING
        """,
        (pricefeed_id, pricefeed_id, 1_778_000_000_000, 1_778_000_000_000),
    )


def _insert_registry_asset(conn) -> None:
    conn.execute(
        """
        INSERT INTO registry_assets(
          asset_id, chain_id, token_standard, address, status, first_seen_at_ms, updated_at_ms
        )
        VALUES (
          'asset-1', 'eip155:1', 'erc20', '0xabc', 'canonical', %s, %s
        )
        ON CONFLICT(asset_id) DO NOTHING
        """,
        (1_778_000_000_000, 1_778_000_000_000),
    )


def _insert_token_intent(conn, *, intent_id: str, event_id: str) -> None:
    EvidenceRepository(conn).insert_event(
        make_event(event_id, text="$BOV", received_at_ms=1_778_000_000_000),
        is_watched=True,
    )
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, display_symbol,
          intent_status, intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (%s, %s, %s, 'test_fixture', 'BOV', 'active', 1.0, %s, %s)
        ON CONFLICT(intent_id) DO NOTHING
        """,
        (intent_id, event_id, f"symbol:BOV:{intent_id}", 1_778_000_000_000, 1_778_000_000_000),
    )


def _valid_factor_snapshot(*, rank_score: object = 12) -> dict[str, object]:
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": {"target_type": "Asset", "target_id": "asset-1", "symbol": "BOV"},
        "market": {
            "event_anchor": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "observed_at_ms": 1_778_000_000_000,
                "received_at_ms": 1_778_000_000_000,
                "source": "event_anchor",
                "provider": "okx",
                "pricefeed_id": "feed-1",
                "price_usd": 1.0,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": None,
                "liquidity_usd": None,
                "holders": None,
                "volume_24h_usd": None,
                "open_interest_usd": None,
                "raw_payload_hash": None,
            },
            "decision_latest": {
                "target_type": "Asset",
                "target_id": "asset-1",
                "observed_at_ms": 1_778_000_030_000,
                "received_at_ms": 1_778_000_030_000,
                "source": "decision_latest",
                "provider": "okx",
                "pricefeed_id": "feed-1",
                "price_usd": 1.1,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": 1_000_000,
                "liquidity_usd": 250_000,
                "holders": 1000,
                "volume_24h_usd": 12_000,
                "open_interest_usd": None,
                "raw_payload_hash": None,
            },
            "readiness": {
                "anchor_status": "ready",
                "latest_status": "live",
                "dex_floor_status": "ready",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "families": {
            "social_heat": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.35,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "social_propagation": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.30,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "semantic_catalyst": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.25,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
            "timing_risk": {
                "raw_score": 80,
                "score": 80,
                "weight": 0.10,
                "data_health": "ready",
                "facts": {},
                "factors": {},
            },
        },
        "gates": {
            "eligible_for_high_alert": False,
            "max_decision": "watch",
            "blocked_reasons": ["liquidity_below_high_alert_floor"],
            "risk_reasons": [],
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
        "normalization": {
            "status": "ranked",
            "cohort_status": "ready",
            "cohort": {},
            "factor_ranks": {},
            "alpha_rank": None,
        },
        "composite": {
            "family_scores": {
                "social_heat": 80,
                "social_propagation": 80,
                "semantic_catalyst": 80,
                "timing_risk": 80,
            },
            "rank_score": rank_score,
            "recommended_decision": "discard",
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_778_000_000_000},
    }
