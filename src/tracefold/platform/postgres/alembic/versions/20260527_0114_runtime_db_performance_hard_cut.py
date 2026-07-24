"""Hard cut runtime DB performance read-model lifecycle."""

from __future__ import annotations

from alembic import op

revision = "20260527_0114"
down_revision = "20260527_0113"
branch_labels = None
depends_on = None


_CREATE_TOKEN_RADAR_TARGET_FEATURE_FRESHNESS_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_window_freshness
  ON token_radar_target_features(
    projection_version,
    "window",
    scope,
    latest_event_received_at_ms DESC
  )
"""


_DROP_TOKEN_RADAR_TARGET_FEATURE_FRESHNESS_INDEX_SQL = (
    "DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_features_window_freshness"
)

_CREATE_MACRO_COMPACT_TABLE_SQL = """
CREATE TABLE macro_observation_series_rows_compact (
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
  projected_at_ms BIGINT NOT NULL
)
"""

_COPY_ACTIVE_MACRO_ROWS_SQL = """
INSERT INTO macro_observation_series_rows_compact (
  projection_version,
  concept_key,
  observed_at,
  series_rank,
  value_numeric,
  source_name,
  series_key,
  source_priority,
  unit,
  frequency,
  data_quality,
  source_ts,
  raw_payload_json,
  ingested_at_ms,
  projected_at_ms
)
SELECT
  rows.projection_version,
  rows.concept_key,
  rows.observed_at,
  rows.series_rank,
  rows.value_numeric,
  rows.source_name,
  rows.series_key,
  rows.source_priority,
  rows.unit,
  rows.frequency,
  rows.data_quality,
  rows.source_ts,
  rows.raw_payload_json,
  rows.ingested_at_ms,
  rows.projected_at_ms
FROM macro_observation_series_rows AS rows
JOIN macro_observation_series_active_generation AS active
  ON active.projection_version = rows.projection_version
 AND active.concept_key = rows.concept_key
 AND active.generation_id = rows.generation_id
"""

_CREATE_MACRO_PUBLICATION_STATE_SQL = """
CREATE TABLE IF NOT EXISTS macro_observation_series_publication_state (
  projection_version TEXT PRIMARY KEY,
  source_signature TEXT,
  row_count BIGINT NOT NULL DEFAULT 0,
  latest_attempt_status TEXT NOT NULL DEFAULT 'pending',
  latest_attempt_started_at_ms BIGINT,
  latest_attempt_finished_at_ms BIGINT,
  latest_attempt_error TEXT,
  updated_at_ms BIGINT NOT NULL
)
"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_CREATE_TOKEN_RADAR_TARGET_FEATURE_FRESHNESS_INDEX_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")

    # Stop macro_view_projection before applying this migration. This is a hard
    # cut: runtime code no longer reads legacy physical generations.
    op.execute("DROP TABLE IF EXISTS macro_observation_series_rows_compact")
    op.execute(_CREATE_MACRO_COMPACT_TABLE_SQL)
    op.execute(_COPY_ACTIVE_MACRO_ROWS_SQL)
    op.execute(_CREATE_MACRO_PUBLICATION_STATE_SQL)
    op.execute(
        """
        ALTER TABLE macro_observation_series_rows_compact
          ADD CONSTRAINT macro_observation_series_rows_compact_pkey
          PRIMARY KEY (projection_version, concept_key, observed_at)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_macro_observation_series_rows_compact_lookup
          ON macro_observation_series_rows_compact(projection_version, concept_key, series_rank, observed_at DESC)
        """
    )
    op.execute("ALTER TABLE macro_observation_series_rows RENAME TO macro_observation_series_rows_legacy_20260527_0114")
    op.execute("ALTER TABLE macro_observation_series_rows_compact RENAME TO macro_observation_series_rows")
    op.execute("DROP TABLE IF EXISTS macro_observation_series_active_generation")
    op.execute("DROP TABLE IF EXISTS macro_observation_series_generations")
    op.execute("ANALYZE macro_observation_series_rows")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_DROP_TOKEN_RADAR_TARGET_FEATURE_FRESHNESS_INDEX_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")
    raise RuntimeError(
        "20260527_0114 runtime DB performance hard cut is not safely reversible; "
        "restore from backup or rebuild current read models from facts."
    )
