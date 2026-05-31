"""Add PostgreSQL hot-path indexes and Token Radar rank inputs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260526_0099"
down_revision = "20260525_0098"
branch_labels = None
depends_on = None

_BACKFILL_BATCH_SIZE = 10000
_BACKFILL_CURSOR_COLUMNS = (
    "projection_version",
    "window",
    "scope",
    "lane",
    "target_type_key",
    "identity_id",
)


_ADD_RANK_INPUT_COLUMNS_SQL = """
ALTER TABLE token_radar_target_features
  ADD COLUMN IF NOT EXISTS social_heat_raw_score DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS social_heat_weight DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS social_propagation_raw_score DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS social_propagation_weight DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS semantic_catalyst_raw_score DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS semantic_catalyst_weight DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS timing_risk_raw_score DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS timing_risk_weight DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cohort_high_confidence_mentions INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cohort_kol_mentions INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cohort_public_followup_authors INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS cohort_first_seen_global_24h BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS cohort_symbol TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS social_heat_watched_mentions INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS social_heat_mentions_1h INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS social_propagation_mentions INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS social_heat_latest_seen_ms BIGINT,
  ADD COLUMN IF NOT EXISTS raw_composite_score DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS recommended_decision TEXT NOT NULL DEFAULT 'discard',
  ADD COLUMN IF NOT EXISTS gates_max_decision TEXT NOT NULL DEFAULT 'discard',
  ADD COLUMN IF NOT EXISTS rank_input_version TEXT NOT NULL DEFAULT 'legacy_needs_rebuild'
"""


_BACKFILL_RECOVERABLE_SCALARS_SQL = """
WITH batch AS (
  SELECT
    projection_version,
    "window",
    scope,
    lane,
    target_type_key,
    identity_id
  FROM token_radar_target_features
  WHERE :cursor_projection_version IS NULL
     OR (projection_version, "window", scope, lane, target_type_key, identity_id) >
        (
          :cursor_projection_version,
          :cursor_window,
          :cursor_scope,
          :cursor_lane,
          :cursor_target_type_key,
          :cursor_identity_id
        )
  ORDER BY projection_version, "window", scope, lane, target_type_key, identity_id
  LIMIT :backfill_batch_size
)
UPDATE token_radar_target_features AS target_features
SET
  social_heat_raw_score = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,social_heat,raw_score}', '')::double precision,
    NULLIF(target_features.factor_snapshot_json #>> '{families,social_heat,score}', '')::double precision
  ),
  social_heat_weight = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,social_heat,weight}', '')::double precision,
    0
  ),
  social_propagation_raw_score = COALESCE(
    NULLIF(
      target_features.factor_snapshot_json #>> '{families,social_propagation,raw_score}',
      ''
    )::double precision,
    NULLIF(target_features.factor_snapshot_json #>> '{families,social_propagation,score}', '')::double precision
  ),
  social_propagation_weight = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,social_propagation,weight}', '')::double precision,
    0
  ),
  semantic_catalyst_raw_score = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,semantic_catalyst,raw_score}', '')::double precision,
    NULLIF(target_features.factor_snapshot_json #>> '{families,semantic_catalyst,score}', '')::double precision
  ),
  semantic_catalyst_weight = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,semantic_catalyst,weight}', '')::double precision,
    0
  ),
  timing_risk_raw_score = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,timing_risk,raw_score}', '')::double precision,
    NULLIF(target_features.factor_snapshot_json #>> '{families,timing_risk,score}', '')::double precision
  ),
  timing_risk_weight = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,timing_risk,weight}', '')::double precision,
    0
  ),
  raw_composite_score = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{composite,rank_score}', '')::double precision,
    NULLIF(target_features.factor_snapshot_json #>> '{composite,raw_alpha_score}', '')::double precision
  ),
  recommended_decision = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{composite,recommended_decision}', ''),
    'discard'
  ),
  gates_max_decision = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{gates,max_decision}', ''),
    'discard'
  ),
  cohort_symbol = upper(COALESCE(NULLIF(target_features.factor_snapshot_json #>> '{subject,symbol}', ''), '')),
  social_heat_watched_mentions = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,social_heat,facts,watched_mentions}', '')::integer,
    0
  ),
  social_heat_mentions_1h = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,social_heat,facts,mentions_1h}', '')::integer,
    0
  ),
  social_propagation_mentions = COALESCE(
    NULLIF(target_features.factor_snapshot_json #>> '{families,social_propagation,facts,mentions}', '')::integer,
    0
  ),
  social_heat_latest_seen_ms = NULLIF(
    target_features.factor_snapshot_json #>> '{families,social_heat,facts,latest_seen_ms}',
    ''
  )::bigint
FROM batch
WHERE target_features.projection_version = batch.projection_version
  AND target_features."window" = batch."window"
  AND target_features.scope = batch.scope
  AND target_features.lane = batch.lane
  AND target_features.target_type_key = batch.target_type_key
  AND target_features.identity_id = batch.identity_id
RETURNING target_features.projection_version,
          target_features."window",
          target_features.scope,
          target_features.lane,
          target_features.target_type_key,
          target_features.identity_id
"""


_CREATE_INDEX_SQL = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_lookup_keys_intent_lookup
      ON token_intent_lookup_keys(intent_id, lookup_key)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_rank_v2
      ON token_radar_target_features(
        projection_version,
        "window",
        scope,
        lane DESC,
        rank_score DESC,
        latest_event_received_at_ms DESC,
        identity_id ASC
      )
      WHERE rank_input_version = 'token-radar-rank-input-v1'
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_event_anchor_backfill_jobs_pending_created
      ON event_anchor_backfill_jobs(created_at_ms ASC, event_id ASC, intent_id ASC)
      WHERE status = 'pending'
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_enriched_events_ready_anchor
      ON enriched_events(event_id ASC, intent_id ASC)
      WHERE capture_method <> 'unavailable'
        AND tick_id IS NOT NULL
        AND tick_lag_ms IS NOT NULL
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projection_runs_running_stale
      ON projection_runs(projection_name, projection_version, started_at_ms ASC)
      WHERE status = 'running'
    """,
)


_DROP_INDEX_SQL = (
    "DROP INDEX CONCURRENTLY IF EXISTS idx_projection_runs_running_stale",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_enriched_events_ready_anchor",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_event_anchor_backfill_jobs_pending_created",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_features_rank_v2",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_token_intent_lookup_keys_intent_lookup",
)


_RECREATE_OLD_RANK_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_rank
  ON token_radar_target_features(projection_version, "window", scope, lane, rank_score DESC, identity_id)
"""


_INVALID_INDEX_CHECK_SQL = """
DO $$
DECLARE
  invalid_index text;
BEGIN
  SELECT indexrelid::regclass::text
  INTO invalid_index
  FROM pg_index
  WHERE NOT indisvalid
    AND indexrelid::regclass::text = ANY (ARRAY[
      'idx_token_intent_lookup_keys_intent_lookup',
      'idx_token_radar_target_features_rank_v2',
      'idx_event_anchor_backfill_jobs_pending_created',
      'idx_enriched_events_ready_anchor',
      'idx_projection_runs_running_stale'
    ])
  LIMIT 1;

  IF invalid_index IS NOT NULL THEN
    RAISE EXCEPTION 'invalid concurrent index after postgres performance hard cut: %', invalid_index;
  END IF;
END $$;
"""


_DROP_RANK_INPUT_COLUMNS_SQL = """
ALTER TABLE token_radar_target_features
  DROP COLUMN IF EXISTS rank_input_version,
  DROP COLUMN IF EXISTS gates_max_decision,
  DROP COLUMN IF EXISTS recommended_decision,
  DROP COLUMN IF EXISTS raw_composite_score,
  DROP COLUMN IF EXISTS social_heat_latest_seen_ms,
  DROP COLUMN IF EXISTS social_propagation_mentions,
  DROP COLUMN IF EXISTS social_heat_mentions_1h,
  DROP COLUMN IF EXISTS social_heat_watched_mentions,
  DROP COLUMN IF EXISTS cohort_symbol,
  DROP COLUMN IF EXISTS cohort_first_seen_global_24h,
  DROP COLUMN IF EXISTS cohort_public_followup_authors,
  DROP COLUMN IF EXISTS cohort_kol_mentions,
  DROP COLUMN IF EXISTS cohort_high_confidence_mentions,
  DROP COLUMN IF EXISTS timing_risk_weight,
  DROP COLUMN IF EXISTS timing_risk_raw_score,
  DROP COLUMN IF EXISTS semantic_catalyst_weight,
  DROP COLUMN IF EXISTS semantic_catalyst_raw_score,
  DROP COLUMN IF EXISTS social_propagation_weight,
  DROP COLUMN IF EXISTS social_propagation_raw_score,
  DROP COLUMN IF EXISTS social_heat_weight,
  DROP COLUMN IF EXISTS social_heat_raw_score
"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_ADD_RANK_INPUT_COLUMNS_SQL)
        _backfill_recoverable_scalars_in_chunks()
        op.execute("ANALYZE token_radar_target_features")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _CREATE_INDEX_SQL:
            op.execute(statement)
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_features_rank")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute(_INVALID_INDEX_CHECK_SQL)

    op.execute("ANALYZE token_intent_lookup_keys")
    op.execute("ANALYZE event_anchor_backfill_jobs")
    op.execute("ANALYZE enriched_events")
    op.execute("ANALYZE projection_runs")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _DROP_INDEX_SQL:
            op.execute(statement)
        op.execute(_RECREATE_OLD_RANK_INDEX_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute(_DROP_RANK_INPUT_COLUMNS_SQL)


def _backfill_recoverable_scalars_in_chunks() -> None:
    bind = op.get_bind()
    statement = _backfill_statement()
    cursor: tuple[str, ...] | None = None
    while True:
        params = _backfill_cursor_params(cursor)
        rows = bind.execute(statement, params).mappings().all()
        if not rows:
            break
        cursor = max(tuple(str(row[column]) for column in _BACKFILL_CURSOR_COLUMNS) for row in rows)
        if len(rows) < _BACKFILL_BATCH_SIZE:
            break


def _backfill_statement() -> sa.TextClause:
    return sa.text(_BACKFILL_RECOVERABLE_SCALARS_SQL).bindparams(
        sa.bindparam("backfill_batch_size", type_=sa.Integer()),
        sa.bindparam("cursor_projection_version", type_=sa.Text()),
        sa.bindparam("cursor_window", type_=sa.Text()),
        sa.bindparam("cursor_scope", type_=sa.Text()),
        sa.bindparam("cursor_lane", type_=sa.Text()),
        sa.bindparam("cursor_target_type_key", type_=sa.Text()),
        sa.bindparam("cursor_identity_id", type_=sa.Text()),
    )


def _backfill_cursor_params(cursor: tuple[str, ...] | None) -> dict[str, object]:
    if cursor is None:
        return {
            "backfill_batch_size": _BACKFILL_BATCH_SIZE,
            "cursor_projection_version": None,
            "cursor_window": None,
            "cursor_scope": None,
            "cursor_lane": None,
            "cursor_target_type_key": None,
            "cursor_identity_id": None,
        }
    return {
        "backfill_batch_size": _BACKFILL_BATCH_SIZE,
        "cursor_projection_version": cursor[0],
        "cursor_window": cursor[1],
        "cursor_scope": cursor[2],
        "cursor_lane": cursor[3],
        "cursor_target_type_key": cursor[4],
        "cursor_identity_id": cursor[5],
    }
