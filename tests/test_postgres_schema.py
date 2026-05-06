from __future__ import annotations

from pathlib import Path

MIGRATION = Path("src/gmgn_twitter_intel/storage/alembic/versions/20260506_0001_initial_postgresql.py")
QUEUE_MIGRATION = Path("src/gmgn_twitter_intel/storage/alembic/versions/20260506_0002_postgres_queue_claims.py")
STALE_RUNNING_MIGRATION = Path(
    "src/gmgn_twitter_intel/storage/alembic/versions/20260506_0003_enrichment_stale_running_claims.py"
)
PROJECTION_MIGRATION = Path(
    "src/gmgn_twitter_intel/storage/alembic/versions/20260506_0004_projection_operations.py"
)
ASSET_MIGRATION = Path(
    "src/gmgn_twitter_intel/storage/alembic/versions/20260506_0005_asset_identity_resolution.py"
)


def test_initial_postgres_schema_uses_jsonb_boolean_and_tsvector() -> None:
    text = MIGRATION.read_text()

    assert "JSONB" in text
    assert "BOOLEAN" in text
    assert "tsvector" in text
    assert "USING GIN" in text


def test_initial_postgres_schema_has_no_sqlite_pragmas_or_fts5() -> None:
    text = MIGRATION.read_text().lower()

    assert "pragma" not in text
    assert "fts5" not in text
    assert "virtual table" not in text


def test_queue_claim_migration_indexes_postgres_worker_paths() -> None:
    text = QUEUE_MIGRATION.read_text()

    assert "idx_enrichment_jobs_claim" in text
    assert "idx_token_market_observations_claim_ready" in text
    assert "idx_token_market_observations_claim_stale" in text
    assert "idx_notification_deliveries_claim" in text
    assert "WHERE status IN ('pending', 'failed')" in text


def test_enrichment_stale_running_migration_indexes_postgres_recovery_path() -> None:
    text = STALE_RUNNING_MIGRATION.read_text()

    assert "idx_enrichment_jobs_claim" in text
    assert "WHERE status IN ('pending', 'failed', 'running')" in text


def test_projection_migration_adds_pg_only_read_model_tables() -> None:
    text = PROJECTION_MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS projection_offsets" in text
    assert "CREATE TABLE IF NOT EXISTS projection_runs" in text
    assert "CREATE TABLE IF NOT EXISTS projection_dirty_ranges" in text
    assert "FOR UPDATE SKIP LOCKED" not in text
    assert "sqlite" not in text.lower()


def test_asset_migration_adds_identity_resolution_tables() -> None:
    text = ASSET_MIGRATION.read_text()

    expected_tables = {
        "asset_mentions",
        "assets",
        "asset_aliases",
        "asset_venues",
        "asset_resolution_candidates",
        "asset_attributions",
        "asset_market_snapshots",
        "asset_resolution_jobs",
        "asset_attention_buckets",
        "asset_attention_bucket_authors",
        "asset_flow_window_snapshots",
    }
    for table in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text

    assert "venue_type TEXT NOT NULL" in text
    assert "inst_id TEXT" in text
    assert "base_symbol TEXT" in text
    assert "quote_symbol TEXT" in text
    assert "venue_id TEXT REFERENCES asset_venues(venue_id)" in text
    assert "token_id" not in text
    assert "sqlite" not in text.lower()
