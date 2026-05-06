from __future__ import annotations

from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
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
    assert "tokens" in names
    assert "token_market_observations" in names
    assert "harness_snapshots" in names
    assert "notifications" in names
    assert "token_signal_snapshots" in names
    assert "projection_offsets" in names
    assert "projection_runs" in names
    assert "projection_dirty_ranges" in names
    assert "asset_mentions" in names
    assert "assets" in names
    assert "asset_aliases" in names
    assert "asset_venues" in names
    assert "asset_resolution_candidates" in names
    assert "asset_attributions" in names
    assert "asset_market_snapshots" in names
    assert "asset_resolution_jobs" in names
    assert "asset_attention_buckets" in names
    assert "asset_attention_bucket_authors" in names
    assert "asset_flow_window_snapshots" in names


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

    assert [row["version_num"] for row in rows] == ["20260506_0005"]


def test_asset_schema_supports_cex_assets_and_unresolved_attributions(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        venue_columns = {
            row["column_name"]: row["is_nullable"]
            for row in conn.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'asset_venues'
                """
            ).fetchall()
        }
        attribution_columns = {
            row["column_name"]: row["is_nullable"]
            for row in conn.execute(
                """
                SELECT column_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'asset_attributions'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert {"venue_type", "exchange", "inst_id", "base_symbol", "quote_symbol", "inst_type"}.issubset(
        venue_columns
    )
    assert {"chain", "address"}.issubset(venue_columns)
    assert attribution_columns["venue_id"] == "YES"
    assert attribution_columns["attribution_status"] == "NO"
