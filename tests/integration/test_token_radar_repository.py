from __future__ import annotations

from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.token_intel.interfaces import (
    TOKEN_FACTOR_SNAPSHOT_VERSION,
    TOKEN_RADAR_DEFAULT_VENUE,
    TOKEN_RADAR_PROJECTION_VERSION,
)
from parallax.domains.token_intel.repositories.token_radar_dirty_target_repository import (
    TokenRadarDirtyTargetRepository,
)
from parallax.domains.token_intel.repositories.token_radar_repository import (
    TokenRadarRepository,
    stable_generation_id,
)
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_publication_state_round_trips_ready_zero_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenRadarRepository(conn)
        repo.publish_current_generation(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="5m",
            scope="matched",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-5m-matched-1",
            published_at_ms=1_778_000_000_000,
            source_frontier_ms=1_777_999_999_000,
            rows=[],
            source_rows=17,
            started_at_ms=1_777_999_990_000,
            finished_at_ms=1_778_000_000_000,
        )

        state = repo.latest_publication_state(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=("5m",),
            scopes=("matched",),
            venues=(TOKEN_RADAR_DEFAULT_VENUE,),
        )
    finally:
        conn.close()

    ready_state = state[("5m", "matched", TOKEN_RADAR_DEFAULT_VENUE)]
    assert isinstance(ready_state["updated_at_ms"], int)
    assert state == {
        ("5m", "matched", TOKEN_RADAR_DEFAULT_VENUE): {
            "current_generation_id": "gen-5m-matched-1",
            "current_published_at_ms": 1_778_000_000_000,
            "current_source_frontier_ms": 1_777_999_999_000,
            "current_row_count": 0,
            "current_source_rows": 17,
            "latest_attempt_generation_id": "gen-5m-matched-1",
            "latest_attempt_status": "ready",
            "latest_attempt_started_at_ms": 1_777_999_990_000,
            "latest_attempt_finished_at_ms": 1_778_000_000_000,
            "latest_attempt_error": None,
            "updated_at_ms": ready_state["updated_at_ms"],
        }
    }


def test_publication_state_round_trips_failed_state_without_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = TokenRadarRepository(conn)
        repo.mark_publication_failed(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="gen-1h-all-failed",
            started_at_ms=1_777_999_990_000,
            finished_at_ms=1_778_000_000_000,
            error="statement timeout",
        )

        state = repo.latest_publication_state(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=("1h",),
            scopes=("all",),
            venues=(TOKEN_RADAR_DEFAULT_VENUE,),
        )
    finally:
        conn.close()

    state_key = ("1h", "all", TOKEN_RADAR_DEFAULT_VENUE)
    assert state[state_key]["current_generation_id"] is None
    assert state[state_key]["latest_attempt_status"] == "failed"
    assert state[state_key]["latest_attempt_error"] == "statement timeout"
    assert state[state_key]["latest_attempt_started_at_ms"] == 1_777_999_990_000
    assert state[state_key]["latest_attempt_finished_at_ms"] == 1_778_000_000_000
    assert isinstance(state[state_key]["updated_at_ms"], int)


def test_publish_and_latest_current_rows_persist_factor_snapshot_json(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    row = {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 1_778_000_000_000,
        "lane": "resolved",
        "rank": 1,
        "intent_id": "intent-1",
        "event_id": "event-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": "feed-1",
        "intent_json": {"display_symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(rank_score=12),
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "decision": "discard",
        "rank_score": 12,
        "quality_status": "ready",
        "degraded_reasons_json": [],
        "data_health_json": {"factor_snapshot": "ready"},
        "source_event_ids_json": ["event-1"],
        "created_at_ms": 1_778_000_000_000,
    }
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        _publish_generation(
            repo,
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
        )

        latest = repo.latest_current_rows(
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            limit=10,
            projection_version="token-radar-v11-factor-alpha-gated",
        )
    finally:
        conn.close()

    assert latest[0]["factor_snapshot_json"]["schema_version"] == TOKEN_FACTOR_SNAPSHOT_VERSION
    assert latest[0]["target_type_key"] == "Asset"
    assert latest[0]["identity_id"] == "asset-1"
    assert latest[0]["rank_score"] == 12
    assert latest[0]["quality_status"] == "ready"
    assert latest[0]["degraded_reasons_json"] == []
    assert latest[0]["payload_hash"]


def test_publish_current_generation_replaces_current_and_updates_publication_state(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    older = _valid_factor_row()
    older["row_id"] = "row-factor-older"
    older["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=25)
    older["rank_score"] = 25
    newer = _valid_factor_row()
    newer["row_id"] = "row-factor-newer"
    newer["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=75)
    newer["rank_score"] = 75
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        _publish_generation(
            repo,
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[older],
        )
        _publish_generation(
            repo,
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_060_000,
            rows=[newer],
        )
        current = repo.latest_current_rows(
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            limit=10,
            projection_version="token-radar-v11-factor-alpha-gated",
        )
        state = repo.latest_publication_state(
            projection_version="token-radar-v11-factor-alpha-gated",
            windows=("1h",),
            scopes=("all",),
            venues=(TOKEN_RADAR_DEFAULT_VENUE,),
        )
    finally:
        conn.close()

    assert [row["row_id"] for row in current] == ["row-factor-newer"]
    assert current[0]["listed_at_ms"] == 1_778_000_000_000
    assert state[("1h", "all", TOKEN_RADAR_DEFAULT_VENUE)]["current_generation_id"] == stable_generation_id(
        projection_version="token-radar-v11-factor-alpha-gated",
        window="1h",
        scope="all",
        venue=TOKEN_RADAR_DEFAULT_VENUE,
        rows=[newer],
    )
    assert state[("1h", "all", TOKEN_RADAR_DEFAULT_VENUE)]["current_row_count"] == 1


def test_publish_current_generation_unchanged_skips_current_rows_and_first_seen_rewrite(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    row = _valid_factor_row()
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        _publish_generation(
            repo,
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[row],
        )
        state_after_first = repo.latest_publication_state(
            projection_version="token-radar-v11-factor-alpha-gated",
            windows=("1h",),
            scopes=("all",),
            venues=(TOKEN_RADAR_DEFAULT_VENUE,),
        )
        conn.execute(
            """
            UPDATE token_radar_target_first_seen
            SET updated_at_ms = 1234
            WHERE identity_id = 'asset-1'
            """
        )
        row["row_id"] = "row-factor-same-later"
        second_result = _publish_generation(
            repo,
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_060_000,
            rows=[row],
        )
        counts = conn.execute(
            """
            SELECT
              (
                SELECT computed_at_ms
                FROM token_radar_current_rows
                WHERE identity_id = 'asset-1'
              ) AS current_computed_at_ms,
              (
                SELECT updated_at_ms
                FROM token_radar_target_first_seen
                WHERE identity_id = 'asset-1'
              ) AS first_seen_updated_at_ms,
              (
                SELECT current_published_at_ms
                FROM token_radar_publication_state
                WHERE projection_version = 'token-radar-v11-factor-alpha-gated'
                  AND "window" = '1h'
                  AND scope = 'all'
              ) AS state_published_at_ms,
              (
                SELECT latest_attempt_status
                FROM token_radar_publication_state
                WHERE projection_version = 'token-radar-v11-factor-alpha-gated'
                  AND "window" = '1h'
                  AND scope = 'all'
              ) AS latest_attempt_status
            """
        ).fetchone()
    finally:
        conn.close()

    assert second_result == {
        "status": "unchanged",
        "generation_id": state_after_first[("1h", "all", TOKEN_RADAR_DEFAULT_VENUE)]["current_generation_id"],
        "rows_written": 0,
    }
    assert counts["current_computed_at_ms"] == 1_778_000_000_000
    assert counts["first_seen_updated_at_ms"] == 1234
    assert counts["state_published_at_ms"] == 1_778_000_060_000
    assert counts["latest_attempt_status"] == "ready"


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


def test_enqueue_market_targets_clears_stale_lease_without_claim_hash_suffix(tmp_path):
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
    assert after_reenqueue["payload_hash"] == old_claim["payload_hash"]
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


def test_empty_target_without_feature_has_no_target_projection_coverage_debounce(tmp_path):
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

        claimed = repos.token_radar_dirty_targets.claim_due(
            limit=1,
            lease_ms=120_000,
            now_ms=1_778_000_001_000,
            lease_owner="projection-a",
        )
        repos.token_radar_dirty_targets.mark_done(claimed, now_ms=1_778_000_002_000)
        target_coverage_tables = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'token_radar_target_projection_coverage'
            """
        ).fetchall()
        second_count = repos.token_radar_dirty_targets.enqueue_market_targets(
            [("chain_token", "eip155:1:0xabc")],
            reason="market_tick_current_changed",
            now_ms=1_778_000_030_000,
        )
        dirty_count = conn.execute("SELECT count(*) AS count FROM token_radar_dirty_targets").fetchone()
    finally:
        conn.close()

    assert first_count == 1
    assert len(claimed) == 1
    assert target_coverage_tables == []
    assert second_count == 1
    assert dirty_count["count"] == 1


def test_recent_resolved_catch_up_is_stable_and_skips_projected_targets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-catch-up-1", event_id="event-catch-up-1")
        _insert_token_resolution(
            conn,
            resolution_id="resolution-catch-up-1",
            intent_id="intent-catch-up-1",
            event_id="event-catch-up-1",
            target_type="Asset",
            target_id="asset-1",
        )
        dirty_repo = TokenRadarDirtyTargetRepository(conn)
        first_count = dirty_repo.enqueue_recent_resolved_targets(
            since_ms=1_777_999_000_000,
            now_ms=1_778_000_060_000,
            limit=10,
            reason="projection_catch_up",
        )
        second_count = dirty_repo.enqueue_recent_resolved_targets(
            since_ms=1_777_999_000_000,
            now_ms=1_778_000_120_000,
            limit=10,
            reason="projection_catch_up",
        )
        dirty_after_replay = conn.execute("SELECT count(*) AS count FROM token_radar_dirty_targets").fetchone()

        conn.execute("DELETE FROM token_radar_dirty_targets")
        TokenRadarRepository(conn).upsert_target_feature(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="1h",
            scope="all",
            row=_valid_factor_row(),
            computed_at_ms=1_778_000_001_000,
        )
        covered_count = dirty_repo.enqueue_recent_resolved_targets(
            since_ms=1_777_999_000_000,
            now_ms=1_778_000_180_000,
            limit=10,
            reason="projection_catch_up",
        )
    finally:
        conn.close()

    assert first_count == 1
    assert second_count == 0
    assert dirty_after_replay["count"] == 1
    assert covered_count == 0


def test_publish_current_generation_removes_exited_current_rows(tmp_path):
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
    second["identity_id"] = "asset-2"
    second["target_id"] = "asset-2"
    entrant = _valid_factor_row()
    entrant["row_id"] = "row-asset-3"
    entrant["rank"] = 1
    entrant["intent_id"] = "intent-3"
    entrant["event_id"] = "event-3"
    entrant["identity_id"] = "asset-3"
    entrant["target_id"] = "asset-3"
    entrant["factor_snapshot_json"] = _valid_factor_snapshot(rank_score=99)
    entrant["rank_score"] = 99
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_token_intent(conn, intent_id="intent-2", event_id="event-2")
        _insert_token_intent(conn, intent_id="intent-3", event_id="event-3")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        _publish_generation(
            repo,
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[first, second],
        )
        _publish_generation(
            repo,
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
    finally:
        conn.close()

    assert [(row["identity_id"], row["rank"]) for row in current] == [("asset-3", 1)]


def test_publish_current_generation_can_replace_rank_swaps(tmp_path):
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
    second["identity_id"] = "asset-2"
    second["target_id"] = "asset-2"
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_token_intent(conn, intent_id="intent-2", event_id="event-2")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        _publish_generation(
            repo,
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
        first["rank_score"] = 10
        second["rank_score"] = 90
        _publish_generation(
            repo,
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


def test_publish_current_generation_rejects_old_rows_after_newer_zero_row_generation(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    stale_row = _valid_factor_row()
    stale_row["row_id"] = "row-factor-stale"
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)
        repo.publish_current_generation(
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            generation_id="newer-empty-generation",
            published_at_ms=1_778_000_060_000,
            source_frontier_ms=1_778_000_060_000,
            rows=[],
            source_rows=0,
        )

        result = _publish_generation(
            repo,
            projection_version="token-radar-v11-factor-alpha-gated",
            window="1h",
            scope="all",
            computed_at_ms=1_778_000_000_000,
            rows=[stale_row],
        )
        current = repo.latest_current_rows(
            window="1h",
            scope="all",
            venue=TOKEN_RADAR_DEFAULT_VENUE,
            limit=10,
            projection_version="token-radar-v11-factor-alpha-gated",
        )
    finally:
        conn.close()

    assert result["status"] == "stale_skipped"
    assert result["rows_written"] == 0
    assert current == []


def _publish_generation(
    repo: TokenRadarRepository,
    *,
    projection_version: str,
    window: str,
    scope: str,
    venue: str = TOKEN_RADAR_DEFAULT_VENUE,
    computed_at_ms: int,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    return repo.publish_current_generation(
        projection_version=projection_version,
        window=window,
        scope=scope,
        venue=venue,
        generation_id=stable_generation_id(
            projection_version=projection_version,
            window=window,
            scope=scope,
            venue=venue,
            rows=rows,
        ),
        published_at_ms=computed_at_ms,
        source_frontier_ms=max((int(row.get("source_max_received_at_ms") or 0) for row in rows), default=0),
        rows=rows,
        source_rows=len(rows),
    )


def _valid_factor_row() -> dict[str, object]:
    return {
        "row_id": "row-factor-1",
        "source_max_received_at_ms": 1_778_000_000_000,
        "lane": "resolved",
        "rank": 1,
        "intent_id": "intent-1",
        "event_id": "event-1",
        "target_type_key": "Asset",
        "identity_id": "asset-1",
        "target_type": "Asset",
        "target_id": "asset-1",
        "pricefeed_id": "feed-1",
        "intent_json": {"display_symbol": "BOV"},
        "factor_snapshot_json": _valid_factor_snapshot(),
        "factor_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "decision": "discard",
        "rank_score": 12,
        "quality_status": "ready",
        "degraded_reasons_json": [],
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


def _insert_token_resolution(
    conn,
    *,
    resolution_id: str,
    intent_id: str,
    event_id: str,
    target_type: str,
    target_id: str,
) -> None:
    conn.execute(
        """
        INSERT INTO token_intent_resolutions(
          resolution_id, intent_id, event_id, resolution_status, identity_status,
          confidence, resolver_policy_version, reasons_json, risks_json,
          decision_time_ms, created_at_ms, target_type, target_id, pricefeed_id,
          reason_codes_json, candidate_ids_json, lookup_keys_json, registry_version,
          record_status, is_current
        )
        VALUES (
          %s, %s, %s, 'resolved', 'identified', 1.0, 'test_fixture',
          '[]'::jsonb, '[]'::jsonb, %s, %s, %s, %s, NULL,
          '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 'test_fixture', 'current', true
        )
        ON CONFLICT(resolution_id) DO NOTHING
        """,
        (
            resolution_id,
            intent_id,
            event_id,
            1_778_000_000_000,
            1_778_000_000_000,
            target_type,
            target_id,
        ),
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
