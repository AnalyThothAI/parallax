from __future__ import annotations

from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.postgres_migrations import latest_migration_version
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_postgres_schema_bootstraps_core_tables(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "alembic_version" in names
    assert "raw_frames" in names
    assert "events" in names
    assert "event_fts" not in names
    assert "event_entities" in names
    assert "harness_snapshots" in names
    assert "notifications" in names
    assert "projection_offsets" in names
    assert "projection_runs" in names
    assert "projection_dirty_ranges" in names
    assert "assets" in names
    assert "asset_aliases" in names
    assert "asset_venues" in names
    assert "asset_market_snapshots" in names
    assert "token_evidence" in names
    assert "token_intents" in names
    assert "token_intent_evidence" in names
    assert "token_intent_resolutions" in names
    assert "token_intent_resolution_candidates" in names
    assert "market_provider_observations" in names
    assert "token_radar_rows" in names
    assert "asset_signal_snapshots" in names
    assert "asset_signal_outcomes" in names
    for legacy_table in {
        "asset_mentions",
        "asset_attributions",
        "asset_resolution_jobs",
        "event_token_mentions",
        "event_token_attributions",
        "token_market_snapshots",
        "token_market_observations",
        "token_signal_snapshots",
    }:
        assert legacy_table not in names


def test_postgres_generated_tsvector_matches_inserted_event(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        EvidenceRepository(conn).insert_event(
            make_event(text="$PEPE mainnet stablecoin on base"),
            is_watched=True,
        )
        rows = conn.execute(
            """
            SELECT event_id
            FROM events
            WHERE search_tsv @@ websearch_to_tsquery('simple', %s)
            """,
            ("stablecoin base",),
        ).fetchall()
    finally:
        conn.close()

    assert [row["event_id"] for row in rows] == ["event-1"]


def test_alembic_migration_is_idempotent(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        migrate(conn)
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    finally:
        conn.close()

    assert [row["version_num"] for row in rows] == [latest_migration_version()]


def test_token_radar_schema_supports_span_aware_intents(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        entity_columns = {
            row["column_name"]: row["is_nullable"]
            for row in conn.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'event_entities'
                """
            ).fetchall()
        }
        intent_columns = {
            row["column_name"]: row["is_nullable"]
            for row in conn.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_intents'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"text_surface", "span_start", "span_end", "sentence_id", "local_group_key"}.issubset(entity_columns)
    assert {"display_symbol", "chain_hint", "address_hint", "intent_status"}.issubset(intent_columns)
    assert intent_columns["intent_status"] == "NO"


def test_token_radar_schema_supports_hard_cut_targets(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        table_names = {
            row["table_name"]
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
        resolution_columns = {
            row["column_name"]: row["is_nullable"]
            for row in conn.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_intent_resolutions'
                """
            ).fetchall()
        }
        radar_columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_radar_rows'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"projects", "registry_assets", "cex_tokens", "price_feeds", "price_observations"}.issubset(table_names)
    assert {"token_discovery_results", "registry_versions", "token_intent_lookup_keys"}.issubset(table_names)
    assert "discovery_tasks" not in table_names
    assert {"target_type", "target_id", "pricefeed_id", "reason_codes_json", "lookup_keys_json"}.issubset(
        resolution_columns
    )
    assert resolution_columns["identity_status"] == "YES"
    assert {"target_type", "target_id", "pricefeed_id", "target_json", "price_json"}.issubset(radar_columns)
