from __future__ import annotations

from pathlib import Path

MIGRATION = Path("src/gmgn_twitter_intel/platform/db/alembic/versions/20260506_0001_initial_postgresql.py")
QUEUE_MIGRATION = Path("src/gmgn_twitter_intel/platform/db/alembic/versions/20260506_0002_postgres_queue_claims.py")
STALE_RUNNING_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260506_0003_enrichment_stale_running_claims.py"
)
PROJECTION_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260506_0004_projection_operations.py"
)
ASSET_MIGRATION = Path("src/gmgn_twitter_intel/platform/db/alembic/versions/20260506_0005_asset_identity_resolution.py")
TOKEN_RADAR_INTENT_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260507_0007_token_radar_v3_intents.py"
)
TOKEN_RADAR_REGISTRY_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260507_0008_token_radar_deterministic_registry.py"
)
AGENTS_SDK_AUDIT_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260507_0010_agents_sdk_model_run_audit.py"
)
EVENT_PRICE_OBSERVATION_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260508_0011_event_price_observations.py"
)
TOKEN_RADAR_PRUNE_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260508_0012_prune_legacy_token_radar_projection.py"
)
TOKEN_RESOLUTION_RETIRE_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260508_0013_retire_legacy_token_resolutions.py"
)
TOKEN_RADAR_V6_PRUNE_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260508_0014_prune_token_radar_v6_projection.py"
)
SIGNAL_PULSE_AGENT_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260508_0015_signal_pulse_agent_hard_cut.py"
)
TOKEN_SEARCH_DEMOTION_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260509_0017_demote_search_only_registry_assets.py"
)
TOKEN_SEARCH_AUDIT_TAIL_DEMOTION_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260509_0018_demote_search_tail_candidate_audit_refs.py"
)
TOKEN_SYMBOL_SEARCH_TARGET_DEMOTION_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260509_0019_demote_symbol_search_tail_targets.py"
)
TOKEN_SYMBOL_SEARCH_TAIL_SWEEP_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260509_0020_sweep_symbol_search_tail_assets.py"
)
ASSET_IDENTITY_EVIDENCE_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260510_0021_asset_identity_evidence_hard_cut.py"
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


def test_token_radar_migration_adds_intent_market_and_projection_tables() -> None:
    text = TOKEN_RADAR_INTENT_MIGRATION.read_text()

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


def test_token_radar_registry_migration_adds_hard_cut_registry_and_price_tables() -> None:
    text = TOKEN_RADAR_REGISTRY_MIGRATION.read_text()

    for table in (
        "projects",
        "registry_assets",
        "cex_tokens",
        "price_feeds",
        "registry_aliases",
        "price_observations",
        "registry_versions",
        "token_intent_lookup_keys",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text

    discovery_result_text = Path(
        "src/gmgn_twitter_intel/platform/db/alembic/versions/20260507_0009_token_discovery_results.py"
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


def test_token_radar_prune_migration_removes_non_current_projection_versions() -> None:
    text = TOKEN_RADAR_V6_PRUNE_MIGRATION.read_text()

    assert "DELETE FROM token_radar_rows" in text
    assert "projection_version <> 'token-radar-v6-auditable'" in text
    assert "DELETE FROM projection_runs" in text
    assert "DELETE FROM projection_offsets" in text


def test_token_resolution_retire_migration_deactivates_old_resolver_policies() -> None:
    text = TOKEN_RESOLUTION_RETIRE_MIGRATION.read_text()

    assert "UPDATE token_intent_resolutions" in text
    assert "record_status = 'retired'" in text
    assert "is_current = false" in text
    assert "resolver_policy_version <> 'token_radar_v5_identity_resolver'" in text


def test_signal_pulse_agent_hard_cut_migration_defines_pulse_tables() -> None:
    text = SIGNAL_PULSE_AGENT_MIGRATION.read_text()

    assert 'revision = "20260508_0015"' in text
    assert 'down_revision = "20260508_0014"' in text
    for table in (
        "pulse_agent_jobs",
        "pulse_agent_runs",
        "pulse_candidates",
        "pulse_playbook_snapshots",
        "pulse_playbook_outcomes",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text

    assert "UNIQUE(candidate_id)" in text
    assert "context_json JSONB NOT NULL DEFAULT '{}'::jsonb" in text
    assert "REFERENCES pulse_agent_jobs(job_id) ON DELETE CASCADE" in text
    assert "REFERENCES pulse_agent_runs(run_id) ON DELETE SET NULL" in text
    assert "playbook_id TEXT PRIMARY KEY" in text
    assert "side TEXT NOT NULL" in text
    assert "setup_json JSONB NOT NULL" in text
    assert "confirmation_json JSONB NOT NULL" in text
    assert "invalidation_json JSONB NOT NULL" in text
    assert "risk_json JSONB NOT NULL" in text
    assert "actual_return DOUBLE PRECISION" in text
    assert "confirmation_hit BOOLEAN NOT NULL DEFAULT false" in text
    assert "idx_pulse_candidates_latest" in text
    assert 'ON pulse_candidates(pulse_version, "window", scope, pulse_status, updated_at_ms DESC)' in text
    assert "idx_pulse_candidates_target" in text
    assert "idx_pulse_candidates_subject" in text
    assert "idx_pulse_agent_jobs_claim" in text
    assert "idx_pulse_agent_runs_job_finished" in text
    assert "idx_pulse_playbook_snapshots_candidate" in text
    assert "idx_pulse_playbook_snapshots_target" in text
    assert "idx_pulse_playbook_outcomes_settled" in text


def test_token_search_demotion_migration_demotes_only_unprotected_search_assets() -> None:
    text = TOKEN_SEARCH_DEMOTION_MIGRATION.read_text()

    assert 'revision = "20260509_0017"' in text
    assert 'down_revision = "20260509_0016"' in text
    assert "status = 'demoted_search'" in text
    assert "status = 'candidate'" in text
    assert "primary_source = 'okx_dex_search'" in text
    assert "ROW_NUMBER() OVER" in text
    assert "PARTITION BY registry_assets.symbol, registry_assets.chain_id" in text
    assert "candidate_ids_json" in text
    assert "target_id" in text
    assert "CREATE TABLE" not in text


def test_token_search_audit_tail_migration_does_not_protect_candidate_audit_lists() -> None:
    text = TOKEN_SEARCH_AUDIT_TAIL_DEMOTION_MIGRATION.read_text()

    assert 'revision = "20260509_0018"' in text
    assert 'down_revision = "20260509_0017"' in text
    assert "status = 'demoted_search'" in text
    assert "primary_source = 'okx_dex_search'" in text
    assert "ROW_NUMBER() OVER" in text
    assert "protected_targets" in text
    assert "target_id" in text
    assert "candidate_ids_json" not in text
    assert "CREATE TABLE" not in text


def test_token_symbol_search_target_migration_preserves_only_address_targets() -> None:
    text = TOKEN_SYMBOL_SEARCH_TARGET_DEMOTION_MIGRATION.read_text()

    assert 'revision = "20260509_0019"' in text
    assert 'down_revision = "20260509_0018"' in text
    assert "status = 'demoted_search'" in text
    assert "primary_source = 'okx_dex_search'" in text
    assert "protected_address_targets" in text
    assert "CHAIN_ADDRESS_EXACT" in text
    assert "ADDRESS_UNIQUE_ACROSS_TRACKED_CHAINS" in text
    assert "MARKET_DOMINANT_CHAIN_ASSET" not in text
    assert "SINGLE_ACTIVE_CHAIN_ASSET" not in text
    assert "CREATE TABLE" not in text


def test_token_symbol_search_tail_sweep_migration_preserves_address_exact_targets() -> None:
    text = TOKEN_SYMBOL_SEARCH_TAIL_SWEEP_MIGRATION.read_text()

    assert 'revision = "20260509_0020"' in text
    assert 'down_revision = "20260509_0019"' in text
    assert "status = 'demoted_search'" in text
    assert "primary_source = 'okx_dex_search'" in text
    assert "protected_address_targets" in text
    assert "CHAIN_ADDRESS_EXACT" in text
    assert "ADDRESS_UNIQUE_ACROSS_TRACKED_CHAINS" in text
    assert "chain_symbol_rank > 3" in text
    assert "CREATE TABLE" not in text


def test_asset_identity_evidence_hard_cut_migration_adds_identity_tables() -> None:
    text = ASSET_IDENTITY_EVIDENCE_MIGRATION.read_text()

    assert 'revision = "20260510_0021"' in text
    assert 'down_revision = "20260509_0020"' in text
    assert "CREATE TABLE IF NOT EXISTS asset_identity_evidence" in text
    assert "CREATE TABLE IF NOT EXISTS asset_identity_current" in text
    assert "evidence_kind TEXT NOT NULL" in text
    assert "lookup_mode TEXT NOT NULL" in text
    assert "identity_confidence TEXT NOT NULL" in text
    assert "selected_evidence_id TEXT" in text
    assert "selection_reason_codes_json JSONB NOT NULL" in text
    assert "idx_asset_identity_evidence_asset" in text
    assert "idx_asset_identity_evidence_provider_lookup" in text
    assert "idx_asset_identity_current_symbol" in text
    assert "ALTER TABLE registry_assets DROP COLUMN IF EXISTS symbol" in text
    assert "ALTER TABLE registry_assets DROP COLUMN IF EXISTS primary_source" in text
