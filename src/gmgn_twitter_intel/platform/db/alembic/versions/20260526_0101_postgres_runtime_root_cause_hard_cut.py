"""Add runtime PostgreSQL read models and terminal reason buckets."""

from __future__ import annotations

from alembic import op

revision = "20260526_0101"
down_revision = "20260526_0100"
branch_labels = None
depends_on = None


_CREATE_MACRO_OBSERVATION_SERIES_ROWS_SQL = """
CREATE TABLE IF NOT EXISTS macro_observation_series_rows(
  projection_version TEXT NOT NULL,
  concept_key TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  series_rank INTEGER NOT NULL,
  value_numeric DOUBLE PRECISION NOT NULL,
  source_name TEXT NOT NULL,
  series_key TEXT NOT NULL,
  source_priority INTEGER NOT NULL,
  unit TEXT,
  frequency TEXT,
  data_quality TEXT,
  source_ts TEXT,
  raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ingested_at_ms BIGINT NOT NULL,
  projected_at_ms BIGINT NOT NULL,
  PRIMARY KEY (projection_version, concept_key, observed_at)
)
"""


_CREATE_MACRO_OBSERVATION_SERIES_ROWS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_macro_observation_series_rows_lookup
  ON macro_observation_series_rows (
    projection_version,
    concept_key,
    series_rank
  )
"""


_ADD_TERMINAL_REASON_BUCKET_SQL = """
ALTER TABLE worker_queue_terminal_events
  ADD COLUMN IF NOT EXISTS final_reason_bucket TEXT NOT NULL DEFAULT 'other'
"""


_BACKFILL_TERMINAL_REASON_BUCKET_SQL = """
UPDATE worker_queue_terminal_events
SET final_reason_bucket = CASE
  WHEN final_reason ILIKE '%522%' THEN 'provider_llm_522'
  WHEN final_reason ILIKE '%provider_no_quote%' THEN 'provider_no_quote'
  WHEN final_reason ILIKE '%provider_error%' THEN 'provider_error'
  WHEN final_reason ILIKE '%no_market_data%' THEN 'no_market_data'
  WHEN final_reason ILIKE '%stale%' THEN 'stale_window'
  WHEN final_reason ILIKE '%timeout%' THEN 'timeout'
  WHEN final_reason ILIKE '%not_found%' THEN 'not_found'
  WHEN final_reason ILIKE '%semantic%' THEN 'semantic_unavailable'
  ELSE 'other'
END
WHERE final_reason_bucket = 'other'
"""


_CREATE_CONCURRENT_INDEX_SQL = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_worker_queue_terminal_reason_bucket_unresolved
      ON worker_queue_terminal_events (
        worker_name,
        source_table,
        final_reason_bucket,
        terminalized_at_ms DESC
      )
      WHERE operator_action IS NULL
    """,
)


_DROP_CONCURRENT_INDEX_SQL = ("DROP INDEX CONCURRENTLY IF EXISTS idx_worker_queue_terminal_reason_bucket_unresolved",)


_INVALID_INDEX_CHECK_SQL = """
DO $$
DECLARE
  invalid_count integer;
BEGIN
  SELECT count(*)
  INTO invalid_count
  FROM pg_index i
  JOIN pg_class c ON c.oid = i.indexrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = current_schema()
    AND c.relname IN (
      'idx_worker_queue_terminal_reason_bucket_unresolved'
    )
    AND NOT i.indisvalid;

  IF invalid_count > 0 THEN
    RAISE EXCEPTION 'invalid indexes detected after postgres runtime hard cut migration: %', invalid_count;
  END IF;
END $$;
"""


_ANALYZE_TABLES_SQL = (
    "ANALYZE macro_observation_series_rows",
    "ANALYZE worker_queue_terminal_events",
    "ANALYZE token_radar_target_features",
    "ANALYZE token_radar_dirty_targets",
    "ANALYZE pulse_agent_jobs",
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute(_CREATE_MACRO_OBSERVATION_SERIES_ROWS_SQL)
    op.execute(_CREATE_MACRO_OBSERVATION_SERIES_ROWS_INDEX_SQL)
    op.execute(_ADD_TERMINAL_REASON_BUCKET_SQL)
    op.execute(_BACKFILL_TERMINAL_REASON_BUCKET_SQL)

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _CREATE_CONCURRENT_INDEX_SQL:
            op.execute(statement)
        op.execute(_INVALID_INDEX_CHECK_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    for statement in _ANALYZE_TABLES_SQL:
        op.execute(statement)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _DROP_CONCURRENT_INDEX_SQL:
            op.execute(statement)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute("ALTER TABLE worker_queue_terminal_events DROP COLUMN IF EXISTS final_reason_bucket")
    op.execute("DROP TABLE IF EXISTS macro_observation_series_rows")
