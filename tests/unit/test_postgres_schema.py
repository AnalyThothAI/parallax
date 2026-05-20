from __future__ import annotations

import re
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
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260508_0011_event_price_" + "observations.py"
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
TOKEN_RADAR_RECOVERY_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0024_price_observation_field_indexes.py"
)
TOKEN_FACTOR_EVAL_DIAGNOSTICS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0026_token_factor_eval_diagnostics.py"
)
TOKEN_FACTOR_PULSE_CLEANUP_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260511_0027_prune_legacy_pulse_factor_snapshots.py"
)
PULSE_FACTOR_CONTRACT_CLEANUP_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260512_0031_prune_legacy_pulse_factor_contracts.py"
)
US_EQUITY_SYMBOL_UNIVERSE_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260512_0034_us_equity_symbol_universe.py"
)
EVENT_ANCHOR_CAPTURE_REDESIGN_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260515_0046_event_anchor_capture_redesign.py"
)
TOKEN_RADAR_RETENTION_WATCHLIST_STATS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/"
    "20260520_0069_token_radar_retention_watchlist_stats.py"
)
TOKEN_NARRATIVE_EPOCHS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260520_0070_token_narrative_epochs.py"
)
ALEMBIC_VERSIONS = Path("src/gmgn_twitter_intel/platform/db/alembic/versions")
LEGACY_PRICE_TABLE = "_".join(("price", "observations"))


def test_initial_postgres_schema_uses_jsonb_boolean_and_tsvector() -> None:
    text = MIGRATION.read_text()

    assert "JSONB" in text
    assert "BOOLEAN" in text
    assert "tsvector" in text
    assert "USING GIN" in text


def test_alembic_revision_ids_are_unique() -> None:
    revisions: dict[str, Path] = {}
    duplicates: dict[str, list[str]] = {}
    for path in sorted(ALEMBIC_VERSIONS.glob("*.py")):
        match = re.search(r'^revision = "([^"]+)"', path.read_text(), flags=re.MULTILINE)
        assert match is not None, f"{path} missing revision"
        revision = match.group(1)
        if revision in revisions:
            duplicates.setdefault(revision, [str(revisions[revision])]).append(str(path))
        revisions[revision] = path
    assert duplicates == {}


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
    assert _legacy_price_index("source", "event") in text
    assert _legacy_price_index("subject", "time", "kind") in text


def test_token_radar_recovery_migration_adds_concurrent_field_indexes_and_coverage() -> None:
    text = TOKEN_RADAR_RECOVERY_MIGRATION.read_text()

    for index_name in (
        _legacy_price_index("current", "price"),
        _legacy_price_index("current", "market", "cap"),
        _legacy_price_index("current", "liquidity"),
        _legacy_price_index("current", "holders"),
        _legacy_price_index("current", "volume", "24h"),
        _legacy_price_index("current", "open", "interest"),
        _legacy_price_index("subject", "first"),
        _legacy_price_index("message", "resolution", "latest"),
    ):
        assert index_name in text
    current_market_cap_index = _legacy_price_index("current", "market", "cap")
    assert f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {current_market_cap_index}" in text
    assert f"DROP INDEX CONCURRENTLY IF EXISTS {current_market_cap_index}" in text
    assert "okx_dex_ws_price_info" in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_projection_coverage" in text
    assert 'PRIMARY KEY(projection_version, "window", scope)' in text


def test_token_factor_eval_diagnostics_migration_adds_nullable_metrics_and_indexes() -> None:
    text = TOKEN_FACTOR_EVAL_DIAGNOSTICS_MIGRATION.read_text()

    assert 'revision = "20260511_0026"' in text
    assert 'down_revision = "20260511_0025"' in text
    for column in (
        "sample_start_ms BIGINT",
        "sample_end_ms BIGINT",
        "spearman_ic DOUBLE PRECISION",
        "icir DOUBLE PRECISION",
        "score_stddev DOUBLE PRECISION",
        "diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    ):
        assert column in text
    assert "score_stddev DOUBLE PRECISION NOT NULL" not in text
    for index_name in (
        "idx_token_score_evaluations_generated",
        "idx_token_radar_rows_settlement",
        _legacy_price_index("subject", "price", "after"),
    ):
        assert index_name in text
    assert 'ON token_score_evaluations(horizon, "window", scope, score_version, generated_at_ms DESC)' in text
    assert 'ON token_radar_rows(factor_version, "window", scope, computed_at_ms, target_type, target_id)' in text
    assert "WHERE price_usd IS NOT NULL" in text
    assert "idx.indisvalid = false" in text
    assert "DROP INDEX IF EXISTS public.{index_name}" in text


def test_token_factor_pulse_cleanup_migration_prunes_legacy_jobs_and_candidates() -> None:
    text = TOKEN_FACTOR_PULSE_CLEANUP_MIGRATION.read_text()

    assert 'revision = "20260511_0027"' in text
    assert 'down_revision = "20260511_0026"' in text
    assert "DELETE FROM pulse_agent_jobs" in text
    assert "DELETE FROM pulse_candidates" in text
    assert "context_json #>> '{factor_snapshot,schema_version}'" in text
    assert "factor_snapshot_json->>'schema_version'" in text
    assert "token_factor_snapshot_v3_social_attention" in text
    assert "UPDATE pulse_agent_jobs" not in text
    assert "mark" not in text.lower()


def test_pulse_factor_contract_cleanup_migration_prunes_non_current_contracts() -> None:
    text = PULSE_FACTOR_CONTRACT_CLEANUP_MIGRATION.read_text()

    assert 'revision = "20260512_0031"' in text
    assert 'down_revision = "20260511_0030"' in text
    assert "DELETE FROM pulse_agent_jobs" in text
    assert "DELETE FROM pulse_candidates" in text
    assert "context_json #>> '{factor_snapshot,schema_version}'" in text
    assert "factor_snapshot_json->>'schema_version'" in text
    assert "token_factor_snapshot_v3_social_attention" in text
    assert "UPDATE pulse_agent_jobs" not in text
    assert "mark" not in text.lower()


def test_us_equity_symbol_universe_migration_adds_market_instrument_lookup_table() -> None:
    text = US_EQUITY_SYMBOL_UNIVERSE_MIGRATION.read_text()

    assert 'revision = "20260512_0034"' in text
    assert 'down_revision = "20260512_0033"' in text
    assert "CREATE TABLE IF NOT EXISTS us_equity_symbols" in text
    assert "market_instrument_id TEXT NOT NULL UNIQUE" in text
    assert "raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb" in text
    assert "idx_us_equity_symbols_active_lookup" in text


def test_event_anchor_capture_redesign_migration_adds_market_tick_tables() -> None:
    text = EVENT_ANCHOR_CAPTURE_REDESIGN_MIGRATION.read_text()
    normalized_text = " ".join(text.split())
    dedupe_index = _extract_sql_statement(text, "CREATE UNIQUE INDEX IF NOT EXISTS idx_market_ticks_dedupe")

    assert 'revision = "20260515_0046"' in text
    assert 'down_revision = "20260514_0045"' in text
    for table_name in ("market_ticks", "token_capture_tier", "enriched_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in text
    for index_name in (
        "idx_market_ticks_target_observed",
        "idx_market_ticks_received",
        "idx_enriched_events_event",
        "idx_enriched_events_target_time",
        "idx_enriched_events_tick",
    ):
        assert index_name in text
    assert "ON market_ticks(target_type, target_id, source_provider, observed_at_ms)" in normalized_text
    assert "received_at_ms" not in dedupe_index
    assert "event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE" in text
    assert "intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE" in text
    assert ("resolution_id TEXT NOT NULL REFERENCES token_intent_resolutions(resolution_id) ON DELETE CASCADE") in text
    assert "capture_reason TEXT NOT NULL" in text
    assert "CREATE OR REPLACE FUNCTION forbid_market_fact_update()" in text
    assert "BEFORE UPDATE ON market_ticks" in text
    assert "BEFORE UPDATE ON enriched_events" in text
    assert "ALTER COLUMN factor_version SET DEFAULT 'token_factor_snapshot_v3_social_attention'" in text
    assert f"DROP TABLE IF EXISTS {LEGACY_PRICE_TABLE} CASCADE" in text
    assert "raise RuntimeError(" in text
    assert "hard-cut migration is not safely reversible" in text
    assert "restoring a pre-migration backup" in text


def test_token_radar_retention_watchlist_stats_migration_adds_bounded_read_models() -> None:
    text = TOKEN_RADAR_RETENTION_WATCHLIST_STATS_MIGRATION.read_text()

    for statement in (
        'revision = "20260520_0069"',
        'down_revision = "20260520_0068"',
        "CREATE TABLE IF NOT EXISTS token_radar_target_first_seen",
        "CREATE TABLE IF NOT EXISTS token_radar_retention_runs",
        "CREATE TABLE IF NOT EXISTS watchlist_handle_signal_stats",
        "CREATE TABLE IF NOT EXISTS watchlist_handle_signal_events",
        "ALTER TABLE social_event_extractions ADD COLUMN IF NOT EXISTS normalized_handle TEXT",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_rows_prune",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_social_event_extractions_signal_normalized_handle_received",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_watchlist_handle_signal_events_handle_received",
        "target_type_key TEXT NOT NULL",
        "identity_id TEXT NOT NULL",
        'PRIMARY KEY (projection_version, "window", scope, target_type_key, identity_id)',
        "event_id TEXT PRIMARY KEY",
    ):
        assert statement in text


def test_token_narrative_epochs_migration_adds_digest_epoch_metadata() -> None:
    text = TOKEN_NARRATIVE_EPOCHS_MIGRATION.read_text()

    for statement in (
        'revision = "20260520_0070"',
        'down_revision = "20260520_0069"',
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_id TEXT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_policy_version TEXT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_event_ids_json JSONB",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_start_ms BIGINT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_end_ms BIGINT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_closed_at_ms BIGINT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS display_current_until_ms BIGINT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS refresh_reason TEXT",
        "idx_token_discussion_digests_epoch_currentness",
        "hard-cut migration is not safely reversible",
    ):
        assert statement in text


def test_projection_migration_adds_pg_only_read_model_tables() -> None:
    text = PROJECTION_MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS projection_offsets" in text
    assert "CREATE TABLE IF NOT EXISTS projection_runs" in text
    assert "CREATE TABLE IF NOT EXISTS projection_dirty_ranges" in text
    assert "FOR UPDATE SKIP LOCKED" not in text
    assert "sqlite" not in text.lower()


def _extract_sql_statement(text: str, statement_start: str) -> str:
    start = text.index(statement_start)
    end = text.index('"""', start)
    return text[start:end]


def _legacy_price_index(*parts: str) -> str:
    return "_".join(("idx", LEGACY_PRICE_TABLE, *parts))


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
        LEGACY_PRICE_TABLE,
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
    assert _legacy_price_index("subject", "latest") in text


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
