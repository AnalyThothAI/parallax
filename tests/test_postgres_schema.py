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
TOKEN_RADAR_V3_MIGRATION = Path(
    "src/gmgn_twitter_intel/storage/alembic/versions/20260507_0007_token_radar_v3_intents.py"
)
TOKEN_RADAR_V4_MIGRATION = Path(
    "src/gmgn_twitter_intel/storage/alembic/versions/20260507_0008_token_radar_v4_deterministic_registry.py"
)
AGENTS_SDK_AUDIT_MIGRATION = Path(
    "src/gmgn_twitter_intel/storage/alembic/versions/20260507_0010_agents_sdk_model_run_audit.py"
)
EVENT_PRICE_OBSERVATION_MIGRATION = Path(
    "src/gmgn_twitter_intel/storage/alembic/versions/20260508_0011_event_price_observations.py"
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
    assert "llm_enrichment_labels" not in text


def test_queue_claim_migration_indexes_postgres_worker_paths() -> None:
    text = QUEUE_MIGRATION.read_text()

    assert "idx_enrichment_jobs_claim" in text
    assert "idx_notification_deliveries_claim" in text
    assert "WHERE status IN ('pending', 'failed')" in text


def test_enrichment_stale_running_migration_indexes_postgres_recovery_path() -> None:
    text = STALE_RUNNING_MIGRATION.read_text()

    assert "idx_enrichment_jobs_claim" in text
    assert "WHERE status IN ('pending', 'failed', 'running')" in text


def test_agents_sdk_audit_migration_adds_traceable_model_run_columns() -> None:
    text = AGENTS_SDK_AUDIT_MIGRATION.read_text()

    assert "sdk_trace_id" in text
    assert "workflow_name" in text
    assert "artifact_version_hash" in text
    assert "trace_metadata_json JSONB" in text
    assert "idx_model_runs_trace" in text
    assert "DROP TABLE IF EXISTS llm_enrichment_labels" in text


def test_event_price_observation_migration_adds_message_attribution_columns() -> None:
    text = EVENT_PRICE_OBSERVATION_MIGRATION.read_text()

    assert "source_event_id" in text
    assert "source_intent_id" in text
    assert "source_resolution_id" in text
    assert "observation_kind" in text
    assert "event_received_at_ms" in text
    assert "observation_lag_ms" in text
    assert "idx_price_observations_source_event" in text
    assert "idx_price_observations_subject_time_kind" in text


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
        "asset_market_snapshots",
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


def test_token_radar_v3_migration_adds_intent_market_and_projection_tables() -> None:
    text = TOKEN_RADAR_V3_MIGRATION.read_text()

    expected_tables = {
        "token_evidence",
        "token_intents",
        "token_intent_evidence",
        "token_intent_resolutions",
        "token_intent_resolution_candidates",
        "market_provider_observations",
        "token_radar_rows",
        "asset_signal_snapshots",
        "asset_signal_outcomes",
    }
    for table in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text

    assert "ALTER TABLE event_entities ADD COLUMN IF NOT EXISTS span_start" in text
    assert "ux_token_intent_active_resolution" in text
    assert "ux_token_radar_rows_rank" in text
    assert "idx_market_provider_observations_lookup" in text
    for table in (
        "asset_mentions",
        "asset_attributions",
        "asset_resolution_jobs",
        "event_token_attributions",
        "token_market_snapshots",
        "token_signal_snapshots",
    ):
        assert f'"{table}"' in text
    assert "DROP TABLE IF EXISTS {table} CASCADE" in text
    assert "DROP TABLE IF EXISTS token_radar_rows" in text


def test_token_radar_v4_migration_adds_hard_cut_registry_and_price_tables() -> None:
    text = TOKEN_RADAR_V4_MIGRATION.read_text()

    for table in {
        "projects",
        "registry_assets",
        "cex_tokens",
        "price_feeds",
        "registry_aliases",
        "price_observations",
        "registry_versions",
        "token_intent_lookup_keys",
    }:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text

    discovery_result_text = Path(
        "src/gmgn_twitter_intel/storage/alembic/versions/20260507_0009_token_discovery_results.py"
    ).read_text()
    assert "CREATE TABLE IF NOT EXISTS token_discovery_results" in discovery_result_text
    assert "DROP TABLE IF EXISTS discovery_tasks" in discovery_result_text

    assert "ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS target_type TEXT" in text
    assert "ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS is_current BOOLEAN" in text
    assert "ALTER TABLE token_intent_resolutions ALTER COLUMN identity_status DROP NOT NULL" in text
    assert "ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS target_type TEXT" in text
    assert "ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS price_json JSONB" in text
    assert "ux_cex_tokens_identity" in text
    assert "idx_price_observations_subject_latest" in text
