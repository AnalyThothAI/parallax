from __future__ import annotations

import re
from pathlib import Path

from alembic.script import ScriptDirectory

from gmgn_twitter_intel.platform.db.postgres_migrations import alembic_config

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
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260520_0069_token_radar_retention_watchlist_stats.py"
)
TOKEN_NARRATIVE_EPOCHS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260520_0070_token_narrative_epochs.py"
)
TOKEN_IMAGE_ASSETS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260521_0078_token_image_assets.py"
)
TOKEN_PROFILE_LOCAL_LOGO_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260521_0079_token_profile_local_logo_hard_cut.py"
)
EQUITY_EVENT_INTEL_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0083_equity_event_intel.py"
)
EQUITY_EVENT_FACT_CANDIDATE_SHAPE_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0084_equity_event_fact_candidate_shape.py"
)
TOKEN_RADAR_STORAGE_ROOT_FIX_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0085_token_radar_storage_root_fix.py"
)
EQUITY_EVENT_RUNTIME_INDEXES_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0086_equity_event_runtime_indexes.py"
)
NEWS_CONTENT_CLASSIFICATION_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0087_news_content_classification.py"
)
NEWS_PAGE_FILTER_INDEXES_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0088_news_page_filter_indexes.py"
)
TOKEN_IMAGE_UNSUPPORTED_CLEANUP_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0089_token_image_unsupported_cleanup.py"
)
TOKEN_RADAR_POSTGRES_HARD_CUT_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260523_0090_token_radar_postgres_hard_cut.py"
)
TOKEN_RADAR_TARGET_FEATURE_FRESHNESS_INDEX_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260524_0091_token_radar_target_feature_freshness_index.py"
)
EQUITY_PROJECTION_PAYLOAD_HASHES_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260524_0092_equity_projection_payload_hashes.py"
)
TOKEN_RADAR_TARGET_PROJECTION_COVERAGE_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260524_0093_token_radar_target_projection_coverage.py"
)
RUNTIME_WORKER_DIRTY_TARGETS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260525_0098_runtime_worker_dirty_targets.py"
)
POSTGRES_PERFORMANCE_QUEUE_HARD_CUT_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0099_postgres_performance_queue_hard_cut.py"
)
WORKER_QUEUE_TERMINAL_EVENTS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0100_worker_queue_terminal_events.py"
)
POSTGRES_RUNTIME_ROOT_CAUSE_HARD_CUT_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0101_postgres_runtime_root_cause_hard_cut.py"
)
MACRO_OBSERVATION_SERIES_SOURCE_TS_TEXT_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0102_macro_observation_series_source_ts_text.py"
)
NORMALIZE_TERMINAL_REASON_BUCKETS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0103_normalize_terminal_reason_buckets.py"
)
OPENNEWS_PROVIDER_SIGNAL_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0105_opennews_provider_signal.py"
)
RUNTIME_RANK_SOURCE_EDGES_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0106_runtime_rank_source_edges.py"
)
MACRO_GENERATION_EQUITY_EVIDENCE_JOBS_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/"
    "20260526_0107_macro_generation_equity_evidence_jobs.py"
)
RUNTIME_PERF_LIFECYCLE_INDEXES_MIGRATION = Path(
    "src/gmgn_twitter_intel/platform/db/alembic/versions/20260526_0108_runtime_perf_lifecycle_indexes.py"
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


def test_alembic_revision_graph_has_single_head() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert script.get_heads() == [script.get_current_head()]


def test_runtime_worker_dirty_targets_migration_adds_narrative_control_plane() -> None:
    text = RUNTIME_WORKER_DIRTY_TARGETS_MIGRATION.read_text()

    for table_name in ("narrative_admission_dirty_targets", "discussion_digest_dirty_targets"):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in text
        assert 'PRIMARY KEY (target_type, target_id, "window", scope)' in text
        assert "projection_version TEXT NOT NULL" in text
        assert "schema_version TEXT NOT NULL" in text
        assert f"idx_{table_name.removesuffix('_targets')}_due" in text
        assert f"idx_{table_name.removesuffix('_targets')}_lease" in text

    assert "CREATE TABLE IF NOT EXISTS token_profile_current_dirty_targets" in text
    assert "PRIMARY KEY (target_type, target_id)" in text
    assert "idx_token_profile_current_dirty_due" in text
    assert "idx_token_profile_current_dirty_lease" in text
    assert "CREATE TABLE IF NOT EXISTS token_image_source_dirty_targets" in text
    assert "PRIMARY KEY (source_url_hash, target_type, target_id)" in text
    assert "raw_ref_json JSONB NOT NULL DEFAULT '{}'::jsonb" in text
    assert "idx_token_image_source_dirty_due" in text
    assert "idx_token_image_source_dirty_lease" in text
    assert "CREATE TABLE IF NOT EXISTS asset_profile_refresh_targets" in text
    assert "PRIMARY KEY (provider, target_type, target_id)" in text
    assert "chain_id TEXT NOT NULL" in text
    assert "address TEXT NOT NULL" in text
    assert "idx_asset_profile_refresh_targets_due" in text
    assert "idx_asset_profile_refresh_targets_lease" in text
    assert "CREATE TABLE IF NOT EXISTS token_capture_tier_dirty_targets" in text
    assert "PRIMARY KEY (work_name, partition_key)" in text
    assert "idx_token_capture_tier_dirty_due" in text
    assert "idx_token_capture_tier_dirty_lease" in text

    for column in (
        "leased_until_ms BIGINT",
        "lease_owner TEXT",
        "attempt_count INTEGER NOT NULL DEFAULT 0",
        "claimed_at_ms BIGINT",
        "last_error TEXT",
    ):
        assert f"ALTER TABLE token_mention_semantics ADD COLUMN IF NOT EXISTS {column}" in text
    assert "idx_token_mention_semantics_lease" in text


def test_postgres_performance_queue_hard_cut_indexes() -> None:
    text = POSTGRES_PERFORMANCE_QUEUE_HARD_CUT_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    assert 'revision = "20260526_0099"' in text
    assert 'down_revision = "20260525_0098"' in text
    assert "SET LOCAL lock_timeout" not in text
    assert "SET LOCAL statement_timeout" not in text
    assert "ALTER TABLE token_radar_target_features" in text
    for column in (
        "social_heat_raw_score DOUBLE PRECISION",
        "social_heat_weight DOUBLE PRECISION NOT NULL DEFAULT 0",
        "social_propagation_raw_score DOUBLE PRECISION",
        "semantic_catalyst_weight DOUBLE PRECISION NOT NULL DEFAULT 0",
        "cohort_high_confidence_mentions INTEGER NOT NULL DEFAULT 0",
        "cohort_first_seen_global_24h BOOLEAN NOT NULL DEFAULT FALSE",
        "social_heat_latest_seen_ms BIGINT",
        "raw_composite_score DOUBLE PRECISION",
        "recommended_decision TEXT NOT NULL DEFAULT 'discard'",
        "rank_input_version TEXT NOT NULL DEFAULT 'legacy_needs_rebuild'",
    ):
        assert column in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_lookup_keys_intent_lookup" in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_rank_v2" in text
    assert "WHERE rank_input_version = 'token-radar-rank-input-v1'" in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_event_anchor_backfill_jobs_pending_created" in text
    assert "WHERE status = 'pending'" in text
    assert "idx_event_anchor_backfill_jobs_unfinished_created" not in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_enriched_events_ready_anchor" in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projection_runs_running_stale" in text
    assert text.count("with op.get_context().autocommit_block():") >= 2
    assert "SET lock_timeout = '5s'" in text
    assert "SET statement_timeout = '30min'" in text
    assert "ADD COLUMN IF NOT EXISTS rank_input_version TEXT NOT NULL DEFAULT 'legacy_needs_rebuild'" in text
    assert "_BACKFILL_BATCH_SIZE" in text
    assert "while True:" in text
    assert "LIMIT :backfill_batch_size" in text
    assert '"backfill_batch_size": _BACKFILL_BATCH_SIZE' in text
    assert "RETURNING target_features.projection_version" in text
    assert "len(rows) < _BACKFILL_BATCH_SIZE" in text
    assert re.search(r"UPDATE\s+token_radar_target_features\s+SET", text, re.IGNORECASE) is None
    assert "RAISE EXCEPTION 'invalid concurrent index after postgres performance hard cut" in text
    assert "DROP INDEX CONCURRENTLY IF EXISTS idx_event_anchor_backfill_jobs_pending_created" in text
    assert "DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_features_rank" in text
    assert "DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_features_rank_v2" in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_rank" in text
    assert "ANALYZE token_radar_target_features" in text
    assert "DROP COLUMN IF EXISTS rank_input_version" in text
    assert (
        'ON token_radar_target_features( projection_version, "window", scope, lane DESC, '
        "rank_score DESC, latest_event_received_at_ms DESC, identity_id ASC )"
    ) in normalized_text


def test_worker_queue_terminal_events_migration_contract() -> None:
    text = WORKER_QUEUE_TERMINAL_EVENTS_MIGRATION.read_text()

    assert 'revision = "20260526_0100"' in text
    assert 'down_revision = "20260526_0099"' in text
    assert "CREATE TABLE IF NOT EXISTS worker_queue_terminal_events" in text
    for column in (
        "terminal_id TEXT PRIMARY KEY",
        "worker_name TEXT NOT NULL",
        "source_table TEXT NOT NULL",
        "target_key TEXT NOT NULL",
        "source_row_json JSONB NOT NULL",
        "source_row_hash TEXT NOT NULL",
        "payload_hash TEXT NOT NULL DEFAULT ''",
        "operator_action_at_ms BIGINT",
    ):
        assert column in text
    assert "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_worker_queue_terminal_source_snapshot" in text
    assert "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_worker_queue_terminal_one_unresolved" in text
    assert "worker_name, source_table, target_key, source_row_hash, terminal_generation" in text
    assert "WHERE operator_action IS NULL" in text
    assert "operator_action = 'quarantine'" not in text
    assert "_backfill_existing_terminal_rows()" in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_unresolved" in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_source" in text
    assert text.count("with op.get_context().autocommit_block():") >= 2
    assert "DROP INDEX CONCURRENTLY IF EXISTS uq_worker_queue_terminal_source_snapshot" in text
    assert "DROP INDEX CONCURRENTLY IF EXISTS idx_worker_queue_terminal_source" in text
    assert "DROP TABLE IF EXISTS worker_queue_terminal_events" in text


def test_postgres_runtime_root_cause_hard_cut_migration_contract() -> None:
    text = POSTGRES_RUNTIME_ROOT_CAUSE_HARD_CUT_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    assert 'revision = "20260526_0101"' in text
    assert 'down_revision = "20260526_0100"' in text
    assert "CREATE TABLE IF NOT EXISTS macro_observation_series_rows" in text
    for column in (
        "projection_version TEXT NOT NULL",
        "concept_key TEXT NOT NULL",
        "observed_at TIMESTAMPTZ NOT NULL",
        "series_rank INTEGER NOT NULL",
        "value_numeric DOUBLE PRECISION NOT NULL",
        "source_ts TEXT",
        "raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "projected_at_ms BIGINT NOT NULL",
        "PRIMARY KEY (projection_version, concept_key, observed_at)",
    ):
        assert column in text
    assert "CREATE INDEX IF NOT EXISTS idx_macro_observation_series_rows_lookup" in text
    assert ("ON macro_observation_series_rows ( projection_version, concept_key, series_rank )") in normalized_text
    assert "ALTER TABLE worker_queue_terminal_events" in text
    assert "ADD COLUMN IF NOT EXISTS final_reason_bucket TEXT NOT NULL DEFAULT 'other'" in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_reason_bucket_unresolved" in text
    assert "WHERE operator_action IS NULL" in text
    assert "final_reason_bucket" in text
    assert "THEN 'llm_provider_522'" in text
    assert "THEN 'retry_budget_exhausted'" in text
    assert "THEN 'provider_unavailable'" in text
    assert "THEN 'stale_window_ttl'" in text
    assert text.index("WHEN final_reason ILIKE '%stale%'") < text.index("WHEN final_reason ILIKE '%timeout%'")
    assert "NOT i.indisvalid" in text
    assert "RAISE EXCEPTION 'invalid indexes detected after postgres runtime hard cut migration" in text
    for table_name in (
        "macro_observation_series_rows",
        "worker_queue_terminal_events",
        "token_radar_target_features",
        "token_radar_dirty_targets",
        "pulse_agent_jobs",
    ):
        assert f"ANALYZE {table_name}" in text
    assert "DROP INDEX CONCURRENTLY IF EXISTS idx_worker_queue_terminal_reason_bucket_unresolved" in text


def test_macro_observation_series_source_ts_text_migration_contract() -> None:
    text = MACRO_OBSERVATION_SERIES_SOURCE_TS_TEXT_MIGRATION.read_text()

    assert 'revision = "20260526_0102"' in text
    assert 'down_revision = "20260526_0101"' in text
    assert "ALTER TABLE macro_observation_series_rows" in text
    assert "ALTER COLUMN source_ts TYPE TEXT" in text
    assert "USING source_ts::text" in text
    assert "ANALYZE macro_observation_series_rows" in text


def test_normalize_terminal_reason_buckets_migration_contract() -> None:
    text = NORMALIZE_TERMINAL_REASON_BUCKETS_MIGRATION.read_text()

    assert 'revision = "20260526_0103"' in text
    assert 'down_revision = "20260526_0102"' in text
    assert "UPDATE worker_queue_terminal_events" in text
    for bucket in (
        "llm_provider_522",
        "retry_budget_exhausted",
        "provider_no_quote",
        "provider_unavailable",
        "provider_error",
        "no_market_data",
        "stale_window_ttl",
        "timeout",
        "not_found",
        "semantic_unavailable",
    ):
        assert bucket in text
    assert text.index("WHEN final_reason ILIKE '%stale%'") < text.index("WHEN final_reason ILIKE '%timeout%'")
    assert "ANALYZE worker_queue_terminal_events" in text


def test_runtime_rank_source_edges_migration_contract() -> None:
    text = RUNTIME_RANK_SOURCE_EDGES_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    assert 'revision = "20260526_0106"' in text
    assert 'down_revision = "20260526_0105"' in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_rank_source_events" in text
    for column in (
        "projection_version TEXT NOT NULL",
        '"window" TEXT NOT NULL',
        "scope TEXT NOT NULL",
        "lane TEXT NOT NULL",
        "target_type_key TEXT NOT NULL",
        "identity_id TEXT NOT NULL",
        "source_kind TEXT NOT NULL",
        "source_id TEXT NOT NULL",
        "event_received_at_ms BIGINT NOT NULL",
        "source_rank INTEGER NOT NULL DEFAULT 0",
        "projected_at_ms BIGINT NOT NULL",
    ):
        assert column in text
    for forbidden in ("event_text", "raw_payload_json", "audit_json"):
        assert forbidden not in text
    assert "CHECK (source_kind IN ('event', 'intent', 'resolution'))" in text
    assert "CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_target" in text
    assert "CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_source" in text
    assert "CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_recent" in text
    assert (
        'PRIMARY KEY ( projection_version, "window", scope, lane, target_type_key, identity_id, source_kind, source_id )'
        in normalized_text
    )
    assert (
        'ON token_radar_rank_source_events( projection_version, "window", scope, target_type_key, identity_id )'
        in normalized_text
    )
    assert "DROP TABLE IF EXISTS token_radar_rank_source_events" in text


def test_macro_generation_and_equity_evidence_jobs_migration_contract() -> None:
    text = MACRO_GENERATION_EQUITY_EVIDENCE_JOBS_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    assert 'revision = "20260526_0107"' in text
    assert 'down_revision = "20260526_0106"' in text
    assert "CREATE TABLE IF NOT EXISTS macro_observation_series_active_generation" in text
    assert "CREATE TABLE IF NOT EXISTS macro_observation_series_generations" in text
    assert "ALTER TABLE macro_observation_series_rows" in text
    assert "ADD COLUMN IF NOT EXISTS generation_id TEXT NOT NULL DEFAULT 'initial-active'" in text
    assert "UPDATE macro_observation_series_rows" in text
    assert "SET generation_id = 'initial-active'" in text
    assert (
        "PRIMARY KEY (projection_version, concept_key, observed_at, generation_id)"
        in text
    )
    assert (
        "ON CONFLICT (projection_version, concept_key) DO UPDATE SET generation_id = EXCLUDED.generation_id"
        in normalized_text
    )
    assert "CREATE TABLE IF NOT EXISTS equity_event_evidence_jobs" in text
    for column in (
        "evidence_job_id TEXT PRIMARY KEY",
        "event_document_id TEXT NOT NULL REFERENCES equity_event_documents(event_document_id) ON DELETE CASCADE",
        "status TEXT NOT NULL DEFAULT 'pending'",
        "priority TEXT NOT NULL DEFAULT 'P2'",
        "due_at_ms BIGINT NOT NULL DEFAULT 0",
        "started_at_ms BIGINT",
        "finished_at_ms BIGINT",
        "attempt_count INTEGER NOT NULL DEFAULT 0",
        "max_attempts INTEGER NOT NULL DEFAULT 3",
        "lease_owner TEXT",
        "leased_until_ms BIGINT",
    ):
        assert column in text
    assert "CHECK (status IN ('pending', 'running', 'success', 'failed_retryable', 'failed_terminal'))" in text
    assert "CREATE INDEX IF NOT EXISTS idx_equity_event_evidence_jobs_due" in text
    assert "WHERE status IN ('pending', 'failed_retryable')" in text
    assert "CREATE INDEX IF NOT EXISTS idx_equity_event_evidence_jobs_running" in text
    assert "WHERE status = 'running'" in text
    assert "DROP TABLE IF EXISTS equity_event_evidence_jobs" in text
    assert "DROP TABLE IF EXISTS macro_observation_series_active_generation" in text
    assert "DROP TABLE IF EXISTS macro_observation_series_generations" in text
    assert "DROP COLUMN IF EXISTS generation_id" in text
    assert "DELETE FROM macro_observation_series_rows" in text
    assert "row_number() OVER" in text
    assert (
        "PARTITION BY rows.projection_version, rows.concept_key, rows.observed_at"
        in text
    )
    assert (
        "active.generation_id = rows.generation_id"
        in text
    )
    assert "rows.generation_id = 'initial-active'" in text
    assert "rows.projected_at_ms DESC" in text
    assert "rows.generation_id DESC" in text
    assert text.index("DELETE FROM macro_observation_series_rows") < text.index(
        "ADD CONSTRAINT macro_observation_series_rows_pkey"
    )


def test_runtime_perf_lifecycle_indexes_migration_contract() -> None:
    text = RUNTIME_PERF_LIFECYCLE_INDEXES_MIGRATION.read_text()

    assert 'revision = "20260526_0108"' in text
    assert 'down_revision = "20260526_0107"' in text
    for table_name in (
        "token_radar_rank_source_events",
        "macro_observation_series_active_generation",
        "macro_observation_series_generations",
        "equity_event_evidence_jobs",
    ):
        assert f"COMMENT ON TABLE {table_name}" in text
    for statement in (
        "CREATE INDEX IF NOT EXISTS idx_macro_observation_series_rows_generation_lookup",
        "CREATE INDEX IF NOT EXISTS idx_macro_observation_series_generations_status",
        "CREATE INDEX IF NOT EXISTS idx_macro_observation_series_active_generation_generation",
        "CREATE INDEX IF NOT EXISTS idx_equity_event_evidence_jobs_document",
        "CREATE INDEX IF NOT EXISTS idx_equity_event_fetch_runs_running_started",
        "CREATE INDEX IF NOT EXISTS idx_equity_event_fetch_runs_status_started",
        "DROP INDEX IF EXISTS idx_equity_event_fetch_runs_status_started",
        "DROP INDEX IF EXISTS idx_equity_event_fetch_runs_running_started",
        "COMMENT ON TABLE token_radar_rank_source_events IS NULL",
    ):
        assert statement in text


def test_runtime_performance_hard_cut_revision_chain() -> None:
    migrations = (
        (RUNTIME_RANK_SOURCE_EDGES_MIGRATION, "20260526_0106", "20260526_0105"),
        (MACRO_GENERATION_EQUITY_EVIDENCE_JOBS_MIGRATION, "20260526_0107", "20260526_0106"),
        (RUNTIME_PERF_LIFECYCLE_INDEXES_MIGRATION, "20260526_0108", "20260526_0107"),
    )

    for migration, revision, down_revision in migrations:
        text = migration.read_text()
        assert f'revision = "{revision}"' in text
        assert f'down_revision = "{down_revision}"' in text


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
    normalized_text = " ".join(text.split())

    for statement in (
        'revision = "20260520_0070"',
        'down_revision = "20260520_0069"',
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_id TEXT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_policy_version TEXT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_start_ms BIGINT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_end_ms BIGINT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_closed_at_ms BIGINT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS display_current_until_ms BIGINT",
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS refresh_reason TEXT",
        "idx_token_discussion_digests_epoch_currentness",
        "hard-cut migration is not safely reversible",
    ):
        assert statement in text
    assert (
        "ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_event_ids_json JSONB "
        "NOT NULL DEFAULT '[]'::jsonb"
    ) in normalized_text
    assert (
        'ON token_discussion_digests( target_type, target_id, "window", scope, schema_version, status, '
        "computed_at_ms DESC )"
    ) in normalized_text
    assert "restoring a pre-migration backup" in text


def test_token_image_assets_migration_adds_local_mirror_storage() -> None:
    text = TOKEN_IMAGE_ASSETS_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    for statement in (
        'revision = "20260521_0078"',
        'down_revision = "20260521_0077"',
        "CREATE TABLE IF NOT EXISTS token_image_assets",
        "image_id TEXT PRIMARY KEY",
        "source_url TEXT NOT NULL",
        "source_url_hash TEXT NOT NULL UNIQUE",
        "source_provider TEXT NOT NULL",
        "source_kind TEXT NOT NULL",
        "status TEXT NOT NULL CHECK (status IN ('pending', 'ready', 'error', 'unsupported'))",
        "raw_ref_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "failure_count BIGINT NOT NULL DEFAULT 0",
        "next_refresh_at_ms BIGINT NOT NULL",
        "idx_token_image_assets_due",
        "idx_token_image_assets_ready_source",
        "ALTER TABLE token_profile_current",
        "ADD COLUMN IF NOT EXISTS logo_image_id TEXT",
        "ADD COLUMN IF NOT EXISTS logo_source_provider TEXT",
        "ADD COLUMN IF NOT EXISTS logo_source_url_hash TEXT",
        "idx_token_profile_current_logo_image",
        "with op.get_context().autocommit_block():",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_profile_current_logo_image",
        "WHERE logo_image_id IS NOT NULL",
    ):
        assert statement in text

    for ready_requirement in (
        "media_type IN ('image/gif', 'image/jpeg', 'image/png', 'image/webp')",
        "file_extension IN ('.gif', '.jpg', '.png', '.webp')",
        "content_sha256 IS NOT NULL",
        "byte_size IS NOT NULL",
        "byte_size > 0",
        "storage_path IS NOT NULL",
        "public_url IS NOT NULL",
        "public_url LIKE '/api/token-images/%'",
    ):
        assert ready_requirement in text

    assert "ON token_image_assets(status, next_refresh_at_ms, updated_at_ms)" in normalized_text
    assert "ON token_image_assets(source_url_hash) WHERE status = 'ready'" in normalized_text


def test_token_profile_local_logo_migration_removes_remote_public_logos() -> None:
    text = TOKEN_PROFILE_LOCAL_LOGO_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    for statement in (
        'revision = "20260521_0079"',
        'down_revision = "20260521_0078"',
        "UPDATE token_profile_current",
        "logo_url = NULL",
        "logo_image_id = NULL",
        "logo_source_provider = NULL",
        "logo_source_url_hash = NULL",
        "logo_url NOT LIKE '/api/token-images/%'",
        "token_profile_current_local_logo_url_check",
        "CHECK (logo_url IS NULL OR logo_url LIKE '/api/token-images/%')",
    ):
        assert statement in text

    assert "quality_flags_json || '[\"logo_mirror_pending\"]'::jsonb" in normalized_text


def test_equity_event_intel_migration_adds_domain_tables_and_indexes() -> None:
    text = EQUITY_EVENT_INTEL_MIGRATION.read_text()

    for statement in (
        'revision = "20260523_0083"',
        'down_revision = "20260522_0082"',
        "CREATE TABLE IF NOT EXISTS equity_event_sources",
        "CREATE TABLE IF NOT EXISTS equity_event_fetch_runs",
        "CREATE TABLE IF NOT EXISTS equity_event_universe_members",
        "CREATE TABLE IF NOT EXISTS equity_expected_events",
        "CREATE TABLE IF NOT EXISTS equity_provider_documents",
        "CREATE TABLE IF NOT EXISTS equity_event_documents",
        "CREATE TABLE IF NOT EXISTS equity_document_revisions",
        "CREATE TABLE IF NOT EXISTS equity_section_diffs",
        "CREATE TABLE IF NOT EXISTS equity_company_events",
        "CREATE TABLE IF NOT EXISTS equity_event_source_spans",
        "CREATE TABLE IF NOT EXISTS equity_event_fact_candidates",
        "source_span_id TEXT REFERENCES equity_event_source_spans(span_id) ON DELETE SET NULL",
        "company_id TEXT",
        "ticker TEXT",
        "event_type TEXT",
        "metric_name TEXT",
        "value_numeric DOUBLE PRECISION",
        "value_unit TEXT",
        "period TEXT",
        "direction TEXT",
        "required_slots_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "evidence_span_start INTEGER NOT NULL DEFAULT 0",
        "evidence_span_end INTEGER NOT NULL DEFAULT 0",
        "CREATE TABLE IF NOT EXISTS equity_event_story_groups",
        "CREATE TABLE IF NOT EXISTS equity_event_story_members",
        "CREATE TABLE IF NOT EXISTS equity_event_agent_runs",
        "CREATE TABLE IF NOT EXISTS equity_event_agent_briefs",
        "CREATE TABLE IF NOT EXISTS equity_event_page_rows",
        "CREATE TABLE IF NOT EXISTS equity_event_calendar_rows",
        "CREATE TABLE IF NOT EXISTS equity_event_alert_candidates",
        "CREATE TABLE IF NOT EXISTS equity_company_timeline_rows",
        "CHECK (provider_type IN ('sec_submissions', 'company_ir_rss', 'company_ir_atom', 'configured_calendar'))",
        "CHECK (trust_tier IN ('official', 'high', 'standard', 'low'))",
        "CHECK (priority IN ('P0', 'P1', 'P2', 'P3'))",
        "CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed', 'brief_ready', 'brief_stale'))",
        "CHECK (validation_status IN ('accepted', 'attention', 'rejected', 'pending'))",
        "idx_equity_event_sources_due",
        "idx_equity_expected_events_due",
        "idx_equity_event_documents_company_time",
        "idx_equity_company_events_latest",
        "idx_equity_event_fact_candidates_event",
        "idx_equity_event_story_members_event",
        "idx_equity_event_page_rows_latest",
        "idx_equity_event_calendar_rows_time",
    ):
        assert statement in text

    assert "'official_regulator'" in text
    assert "'official_issuer'" in text
    assert "'calendar'" in text
    assert "'transcript'" in text
    assert "'specialist_media'" in text
    assert "'observed_source'" in text


def test_equity_event_fact_candidate_shape_migration_backfills_feature_branch_schema() -> None:
    text = EQUITY_EVENT_FACT_CANDIDATE_SHAPE_MIGRATION.read_text()

    for statement in (
        'revision = "20260523_0084"',
        'down_revision = "20260523_0083"',
        "ALTER TABLE equity_event_fact_candidates",
        "ADD COLUMN IF NOT EXISTS source_span_id TEXT",
        "ADD COLUMN IF NOT EXISTS company_id TEXT",
        "ADD COLUMN IF NOT EXISTS ticker TEXT",
        "ADD COLUMN IF NOT EXISTS event_type TEXT",
        "ADD COLUMN IF NOT EXISTS metric_name TEXT",
        "ADD COLUMN IF NOT EXISTS value_numeric DOUBLE PRECISION",
        "ADD COLUMN IF NOT EXISTS value_unit TEXT",
        "ADD COLUMN IF NOT EXISTS period TEXT",
        "ADD COLUMN IF NOT EXISTS direction TEXT",
        "ADD COLUMN IF NOT EXISTS required_slots_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ADD COLUMN IF NOT EXISTS evidence_span_start INTEGER NOT NULL DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS evidence_span_end INTEGER NOT NULL DEFAULT 0",
    ):
        assert statement in text


def test_token_radar_storage_root_fix_migration_hard_cuts_old_storage() -> None:
    text = TOKEN_RADAR_STORAGE_ROOT_FIX_MIGRATION.read_text()

    for statement in (
        'revision = "20260523_0085"',
        'down_revision = "20260523_0084"',
        "CREATE TABLE IF NOT EXISTS token_radar_current_rows",
        "CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit",
        "PARTITION BY RANGE (computed_at_ms)",
        "CREATE TABLE IF NOT EXISTS token_radar_rank_history",
        "CREATE TABLE IF NOT EXISTS token_radar_storage_maintenance_runs",
        'UNIQUE (projection_version, "window", scope, lane, rank)',
        "idx_token_radar_current_rows_read",
        "idx_token_radar_rank_history_read",
        "idx_token_radar_snapshot_audit_settlement",
        "DROP TABLE IF EXISTS token_radar_rows CASCADE",
        "DROP TABLE IF EXISTS token_radar_retention_runs",
        "TRUNCATE TABLE token_radar_target_first_seen RESTART IDENTITY",
        "DELETE FROM token_radar_projection_coverage",
        "DELETE FROM projection_offsets",
        "DELETE FROM projection_runs",
    ):
        assert statement in text


def test_equity_event_runtime_indexes_cover_page_projection_latest_lookups() -> None:
    text = EQUITY_EVENT_RUNTIME_INDEXES_MIGRATION.read_text()

    for statement in (
        'revision = "20260523_0086"',
        'down_revision = "20260523_0085"',
        "idx_equity_event_page_rows_event_latest",
        "ON equity_event_page_rows(company_event_id, computed_at_ms DESC, row_id ASC)",
        "idx_equity_company_timeline_rows_event_latest",
        "ON equity_company_timeline_rows(company_event_id, computed_at_ms DESC, row_id ASC)",
        "idx_equity_event_alert_candidates_event_latest",
        "ON equity_event_alert_candidates(company_event_id, computed_at_ms DESC, alert_candidate_id ASC)",
    ):
        assert statement in text


def test_news_content_classification_migration_follows_runtime_indexes() -> None:
    text = NEWS_CONTENT_CLASSIFICATION_MIGRATION.read_text()

    for statement in (
        'revision = "20260523_0087"',
        'down_revision = "20260523_0086"',
        "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS content_class",
        "ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS content_class",
        "idx_news_items_content_class_time",
        "idx_news_page_rows_content_class_time",
    ):
        assert statement in text


def test_news_page_filter_indexes_follow_content_classification() -> None:
    text = NEWS_PAGE_FILTER_INDEXES_MIGRATION.read_text()

    for statement in (
        'revision = "20260523_0088"',
        'down_revision = "20260523_0087"',
        "idx_news_page_rows_provider_type_time",
        "idx_news_page_rows_source_role_time",
        "idx_news_page_rows_trust_tier_time",
        "idx_news_page_rows_direction_time",
        "idx_news_page_rows_decision_class_time",
        "idx_news_page_rows_coverage_tags_gin",
        "idx_news_page_rows_content_tags_gin",
    ):
        assert statement in text


def test_opennews_provider_signal_migration_adds_jsonb_fact_columns() -> None:
    text = OPENNEWS_PROVIDER_SIGNAL_MIGRATION.read_text()

    for statement in (
        'revision = "20260526_0105"',
        'down_revision = "20260526_0104"',
        "provider_signal_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "provider_token_impacts_json JSONB NOT NULL DEFAULT '[]'::jsonb",
        "signal_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "token_impacts_json JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ix_news_items_provider_signal_direction",
        "ix_news_page_rows_signal_direction",
        "'opennews'",
    ):
        assert statement in text


def test_token_image_unsupported_cleanup_follows_news_filter_indexes() -> None:
    text = TOKEN_IMAGE_UNSUPPORTED_CLEANUP_MIGRATION.read_text()

    for statement in (
        'revision = "20260523_0089"',
        'down_revision = "20260523_0088"',
        "UPDATE token_image_assets",
        "status = 'unsupported'",
        "last_error LIKE 'unsupported\\\\_%' ESCAPE '\\\\'",
        "last_error LIKE 'image_too_large:%'",
    ):
        assert statement in text


def test_token_radar_postgres_hard_cut_revision_is_in_alembic_graph() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    revision = script.get_revision("20260523_0090")

    assert revision is not None
    assert revision.down_revision == "20260523_0089"
    assert revision.module.__file__ is not None
    assert revision.module.__file__.endswith("20260523_0090_token_radar_postgres_hard_cut.py")


def test_token_radar_postgres_hard_cut_migration_partitions_hot_tables() -> None:
    text = TOKEN_RADAR_POSTGRES_HARD_CUT_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    assert 'revision = "20260523_0090"' in text
    assert 'down_revision = "20260523_0089"' in text
    assert "DROP TABLE IF EXISTS token_radar_rows CASCADE" in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_rows" not in text

    assert "CREATE TABLE IF NOT EXISTS market_ticks" in text
    assert "PRIMARY KEY (observed_at_ms, tick_id)" in text
    assert "PARTITION BY RANGE (observed_at_ms)" in text
    assert "CREATE TABLE IF NOT EXISTS market_ticks_default" in text
    assert "PARTITION OF market_ticks DEFAULT" in text
    assert "ON market_ticks(observed_at_ms, target_type, target_id, source_provider)" in normalized_text
    assert "ON market_ticks(target_type, target_id, observed_at_ms DESC, tick_id DESC)" in normalized_text

    assert "CREATE TABLE IF NOT EXISTS enriched_events" in text
    assert "tick_observed_at_ms BIGINT" in text
    assert (
        "FOREIGN KEY (tick_observed_at_ms, tick_id) REFERENCES market_ticks(observed_at_ms, tick_id) ON DELETE RESTRICT"
    ) in normalized_text
    assert "CREATE INDEX IF NOT EXISTS idx_enriched_events_tick" in text
    assert "ON enriched_events(tick_observed_at_ms, tick_id)" in normalized_text

    for table_name in (
        "market_tick_current",
        "token_radar_dirty_targets",
        "token_radar_target_features",
        "token_radar_current_rows",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in text

    for table_name in (
        "market_tick_current",
        "token_radar_dirty_targets",
        "token_radar_current_rows",
    ):
        table_statement = _extract_sql_statement(text, f"CREATE TABLE IF NOT EXISTS {table_name}")
        assert "payload_hash TEXT NOT NULL" in table_statement or (
            table_name == "token_radar_current_rows" and "payload_hash TEXT NOT NULL" in text
        )
        assert f"ALTER TABLE {table_name} SET (" in text
        assert "fillfactor" in text[text.index(f"ALTER TABLE {table_name} SET (") :]
        assert "autovacuum_vacuum_scale_factor" in text[text.index(f"ALTER TABLE {table_name} SET (") :]

    target_features_statement = _extract_sql_statement(
        text,
        "CREATE TABLE IF NOT EXISTS token_radar_target_features",
    )
    assert "payload_hash TEXT NOT NULL" in target_features_statement

    assert "CREATE TABLE IF NOT EXISTS token_radar_rank_history" in text
    assert "recorded_at_ms BIGINT NOT NULL" in text
    assert "PARTITION BY RANGE (recorded_at_ms)" in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_rank_history_default" in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit" in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit_default" in text


def test_token_radar_target_feature_freshness_index_migration_matches_dirty_enqueue_lookup() -> None:
    text = TOKEN_RADAR_TARGET_FEATURE_FRESHNESS_INDEX_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    assert 'revision = "20260524_0091"' in text
    assert 'down_revision = "20260523_0090"' in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_freshness" in text
    assert (
        "ON token_radar_target_features( projection_version, target_type_key, "
        "identity_id, latest_market_observed_at_ms DESC )"
    ) in normalized_text
    assert "DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_features_freshness" in text


def test_equity_projection_payload_hashes_migration_follows_token_radar_freshness_index() -> None:
    text = EQUITY_PROJECTION_PAYLOAD_HASHES_MIGRATION.read_text()

    assert 'revision = "20260524_0092"' in text
    assert 'down_revision = "20260524_0091"' in text
    for table_name, index_name in (
        ("equity_event_page_rows", "idx_equity_event_page_rows_payload_hash"),
        ("equity_company_timeline_rows", "idx_equity_company_timeline_rows_payload_hash"),
        ("equity_event_alert_candidates", "idx_equity_event_alert_candidates_payload_hash"),
        ("equity_event_calendar_rows", "idx_equity_event_calendar_rows_payload_hash"),
    ):
        assert f"ALTER TABLE {table_name}" in text
        assert "ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''" in text
        assert "ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0" in text
        assert f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}" in text
        assert f"ON {table_name}(payload_hash)" in text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_event_calendar_rows_expected_event" in text
    assert "ON equity_event_calendar_rows(expected_event_id)" in text


def test_token_radar_target_projection_coverage_migration_follows_equity_projection_hashes() -> None:
    text = TOKEN_RADAR_TARGET_PROJECTION_COVERAGE_MIGRATION.read_text()
    normalized_text = " ".join(text.split())

    assert 'revision = "20260524_0093"' in text
    assert 'down_revision = "20260524_0092"' in text
    assert "CREATE TABLE IF NOT EXISTS token_radar_target_projection_coverage" in text
    assert "latest_market_observed_at_ms BIGINT NOT NULL DEFAULT 0" in text
    assert "PRIMARY KEY(projection_version, target_type_key, identity_id)" in normalized_text
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_projection_coverage_freshness" in text
    assert (
        "ON token_radar_target_projection_coverage( projection_version, target_type_key, "
        "identity_id, latest_market_observed_at_ms DESC )"
    ) in normalized_text
    assert "DROP TABLE IF EXISTS token_radar_target_projection_coverage" in text


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
