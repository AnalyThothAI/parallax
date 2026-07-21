import time

from psycopg.types.json import Jsonb

from parallax.domains.evidence.interfaces import Author, Content, Source, TwitterEvent
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from parallax.domains.narrative_intel.repositories.narrative_repository import NarrativeRepository
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def make_event(event_id: str) -> TwitterEvent:
    received_at_ms = int(time.time() * 1000)
    return TwitterEvent(
        event_id=event_id,
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_basic",
        ),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle="toly", name="toly", avatar=None, followers=100, tags=[]),
        content=Content(text=f"SOL breakout discussion {event_id}", media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["toly"],
        raw={"id": event_id},
    )


def open_repo(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    return conn, evidence, NarrativeRepository(conn)


def test_migration_keeps_only_narrative_admission_read_model(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "narrative_admissions" in tables
    assert "narrative_model_runs" not in tables
    assert "token_mention_semantics" not in tables
    assert "token_discussion_digests" not in tables


def test_upsert_admissions_uses_product_identity_and_zero_writes_unchanged(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        row = {
            "target_type": "chain_token",
            "target_id": "solana:Stable",
            "window": "1h",
            "scope": "matched",
            "schema_version": NARRATIVE_SCHEMA_VERSION,
            "status": "admitted",
            "reason": "radar_row",
            "priority": 10,
            "last_radar_rank": 1,
            "last_rank_score": 88.5,
            "source_event_ids": ["event-stable"],
            "source_max_received_at_ms": 2_000,
            "projection_computed_at_ms": 2_000,
            "source_window_start_ms": 1_000,
            "source_window_end_ms": 2_000,
            "source_event_count": 1,
            "independent_author_count": 1,
            "admission_generation": "1h:matched:2000",
        }

        first = repo.upsert_admissions([row], now_ms=2_000)
        second = repo.upsert_admissions([row], now_ms=3_000)
        count = conn.execute("SELECT COUNT(*) AS count FROM narrative_admissions").fetchone()["count"]
    finally:
        conn.close()

    assert first == {"upserted": 1, "seen": 1}
    assert second == {"upserted": 0, "seen": 1}
    assert count == 1


def test_load_radar_admission_target_uses_exact_latest_ready_projection_frontier(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-old-1", "event-old-2", "event-latest"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
            _insert_intent(conn, intent_id=f"intent-{event_id}", event_id=event_id, observed_at_ms=1_000)
        _insert_radar_publication_state(
            conn,
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            computed_at_ms=1_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-old",
            event_id="event-old-1",
            intent_id="intent-event-old-1",
            target_id="asset:old",
            rank=1,
            computed_at_ms=1_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-latest",
            event_id="event-latest",
            intent_id="intent-event-latest",
            target_id="asset:latest",
            rank=2,
            computed_at_ms=1_000,
        )

        context = repo.load_radar_admission_target(
            target_type="Asset",
            target_id="asset:latest",
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    assert context["radar_row"]["target_id"] == "asset:latest"
    assert context["radar_row"]["rank"] == 2
    assert context["existing_admission"] is None


def test_current_narrative_admissions_are_derived_from_admissions(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Ready",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "status": "admitted",
                    "reason": "radar_row",
                    "priority": 10,
                    "last_radar_rank": 1,
                    "last_rank_score": 88.5,
                    "source_event_ids": ["event-ready"],
                    "source_max_received_at_ms": 2_000,
                    "projection_computed_at_ms": 2_000,
                    "source_window_start_ms": 1_000,
                    "source_window_end_ms": 2_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                    "admission_generation": "1h:matched:2000",
                }
            ],
            now_ms=2_000,
        )

        current = repo.current_narrative_admissions_for_targets(
            [
                {"target_type": "chain_token", "target_id": "solana:Ready"},
                {"target_type": "chain_token", "target_id": "solana:Missing"},
            ],
            window="1h",
            scope="matched",
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    ready = current[("chain_token", "solana:Ready")]
    missing = current[("chain_token", "solana:Missing")]
    assert ready["status"] == "admitted"
    assert ready["currentness"] == {"display_status": "current", "reason": "radar_row"}
    assert ready["source_event_count"] == 1
    assert missing["status"] == "missing"
    assert missing["currentness"] == {"display_status": "not_ready", "reason": "no_current_admission"}


def _insert_intent(conn, *, intent_id: str, event_id: str, observed_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (%s, %s, %s, 'unit-test', 'active', 1.0, %s, %s)
        """,
        (intent_id, event_id, f"intent-key:{intent_id}", observed_at_ms, observed_at_ms),
    )


def _insert_radar_publication_state(
    conn,
    *,
    window: str,
    scope: str,
    projection_version: str,
    computed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_radar_publication_state(
          projection_version, "window", scope, current_generation_id, current_published_at_ms,
          current_source_frontier_ms, current_row_count, current_source_rows,
          latest_attempt_generation_id, latest_attempt_status, latest_attempt_started_at_ms,
          latest_attempt_finished_at_ms, latest_attempt_error, updated_at_ms
        )
        VALUES (%s, %s, %s, %s, %s, %s, 2, 2, %s, 'ready', %s, %s, NULL, %s)
        """,
        (
            projection_version,
            window,
            scope,
            f"test-generation:{computed_at_ms}",
            computed_at_ms,
            computed_at_ms,
            f"test-generation:{computed_at_ms}",
            computed_at_ms,
            computed_at_ms,
            computed_at_ms,
        ),
    )


def _insert_radar_row(
    conn,
    *,
    row_id: str,
    event_id: str,
    intent_id: str,
    target_id: str,
    rank: int,
    computed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_radar_current_rows(
          row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
          generation_id, published_at_ms, source_frontier_ms,
          lane, target_type_key, identity_id, rank, rank_score, intent_id, event_id, intent_json,
          resolution_json, factor_snapshot_json, factor_version, decision,
          quality_status, degraded_reasons_json, data_health_json,
          source_event_ids_json, payload_hash, listed_at_ms, created_at_ms, target_type, target_id,
          pricefeed_id
        )
        VALUES (
          %s, %s, '24h', 'all', %s, %s,
          %s, %s, %s,
          'all', 'Asset', %s, %s, %s, %s, %s, %s,
          %s, %s, 'token_factor_snapshot_v3_social_attention', 'watch',
          'ready', %s, %s,
          %s, %s, %s, %s, 'Asset', %s, NULL
        )
        """,
        (
            row_id,
            TOKEN_RADAR_PROJECTION_VERSION,
            computed_at_ms,
            computed_at_ms,
            f"test-generation:{computed_at_ms}",
            computed_at_ms,
            computed_at_ms,
            target_id,
            rank,
            max(0, 100 - rank),
            intent_id,
            event_id,
            Jsonb({"intent_id": intent_id}),
            Jsonb({"status": "EXACT", "target_type": "Asset", "target_id": target_id}),
            Jsonb(
                {
                    "schema_version": "token_factor_snapshot_v3_social_attention",
                    "subject": {"target_type": "Asset", "target_id": target_id, "target_market_type": "dex"},
                    "composite": {"rank_score": max(0, 100 - rank), "recommended_decision": "watch"},
                }
            ),
            Jsonb([]),
            Jsonb({"alpha": "ready"}),
            Jsonb([event_id]),
            f"test-payload-hash:{row_id}",
            computed_at_ms,
            computed_at_ms,
            target_id,
        ),
    )
