"""Hard cut retired runtime lifecycle storage."""

from __future__ import annotations

from alembic import op

revision = "20260527_0115"
down_revision = "20260527_0114"
branch_labels = None
depends_on = None


_DROP_OBSOLETE_MACRO_LOOKUP_INDEX_SQL = (
    "DROP INDEX CONCURRENTLY IF EXISTS idx_macro_observation_series_rows_compact_lookup"
)

_CREATE_MACRO_HISTORY_ORDER_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_macro_observation_series_rows_history_order
  ON macro_observation_series_rows(projection_version, concept_key, observed_at DESC, series_rank)
"""


_CREATE_MACRO_VIEW_SNAPSHOTS_COMPACT_SQL = """
CREATE TABLE IF NOT EXISTS macro_view_snapshots_compact (
  snapshot_id TEXT PRIMARY KEY,
  projection_version TEXT NOT NULL,
  asof_date DATE NOT NULL,
  status TEXT NOT NULL,
  regime TEXT NOT NULL,
  overall_score NUMERIC,
  panels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  indicators_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  triggers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  data_gaps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_coverage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  computed_at_ms BIGINT NOT NULL,
  features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  chain_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  scenario_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  scorecard_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload_hash TEXT NOT NULL
)
"""

_COPY_LATEST_MACRO_VIEW_SNAPSHOTS_SQL = """
INSERT INTO macro_view_snapshots_compact (
  snapshot_id,
  projection_version,
  asof_date,
  status,
  regime,
  overall_score,
  panels_json,
  indicators_json,
  triggers_json,
  data_gaps_json,
  source_coverage_json,
  computed_at_ms,
  features_json,
  chain_json,
  scenario_json,
  scorecard_json,
  payload_hash
)
WITH ranked AS (
  SELECT
    snapshot_id,
    projection_version,
    asof_date,
    status,
    regime,
    overall_score,
    panels_json,
    indicators_json,
    triggers_json,
    data_gaps_json,
    source_coverage_json,
    computed_at_ms,
    features_json,
    chain_json,
    scenario_json,
    scorecard_json,
    row_number() OVER (
      PARTITION BY projection_version
      ORDER BY computed_at_ms DESC, snapshot_id DESC
    ) AS snapshot_rank
  FROM macro_view_snapshots
)
SELECT
  'macro-view:' || projection_version || ':' || 'current' AS snapshot_id,
  projection_version,
  asof_date,
  status,
  regime,
  overall_score,
  panels_json,
  indicators_json,
  triggers_json,
  data_gaps_json,
  source_coverage_json,
  computed_at_ms,
  features_json,
  chain_json,
  scenario_json,
  scorecard_json,
  'md5:' || md5(
    jsonb_build_object(
      'projection_version', projection_version,
      'asof_date', asof_date,
      'status', status,
      'regime', regime,
      'overall_score', overall_score,
      'panels_json', panels_json,
      'indicators_json', indicators_json,
      'triggers_json', triggers_json,
      'data_gaps_json', data_gaps_json,
      'source_coverage_json', source_coverage_json,
      'features_json', features_json,
      'chain_json', chain_json,
      'scenario_json', scenario_json,
      'scorecard_json', scorecard_json
    )::text
  ) AS payload_hash
FROM ranked
WHERE snapshot_rank = 1
"""

_CREATE_MACRO_PROJECTION_DIRTY_TARGETS_SQL = """
CREATE TABLE IF NOT EXISTS macro_projection_dirty_targets (
  projection_name TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  target_kind TEXT NOT NULL,
  target_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  dirty_reason TEXT NOT NULL,
  source_watermark_ms BIGINT NOT NULL DEFAULT 0,
  priority INTEGER NOT NULL DEFAULT 100,
  due_at_ms BIGINT NOT NULL,
  leased_until_ms BIGINT,
  lease_owner TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at_ms BIGINT NOT NULL,
  updated_at_ms BIGINT NOT NULL,
  PRIMARY KEY (projection_name, projection_version, target_kind, target_id)
)
"""

_SEED_MACRO_VIEW_DIRTY_TARGET_SQL = """
INSERT INTO macro_projection_dirty_targets (
  projection_name,
  projection_version,
  target_kind,
  target_id,
  payload_hash,
  dirty_reason,
  source_watermark_ms,
  priority,
  due_at_ms,
  created_at_ms,
  updated_at_ms
)
SELECT
  'macro_view',
  'macro_regime_v4',
  'current',
  'current',
  'seed:20260527_0115:macro_view:macro_regime_v4:current',
  'migration_hard_cut_rebuild',
  0,
  0,
  0,
  now_ms.value,
  now_ms.value
FROM (
  SELECT floor(extract(epoch from clock_timestamp()) * 1000)::bigint AS value
) AS now_ms
ON CONFLICT (projection_name, projection_version, target_kind, target_id) DO UPDATE
SET
  payload_hash = EXCLUDED.payload_hash,
  dirty_reason = EXCLUDED.dirty_reason,
  due_at_ms = LEAST(macro_projection_dirty_targets.due_at_ms, EXCLUDED.due_at_ms),
  updated_at_ms = EXCLUDED.updated_at_ms
"""

_CREATE_CEX_OI_PUBLICATION_STATE_SQL = """
CREATE TABLE IF NOT EXISTS cex_oi_radar_publication_state (
  board_key TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  exchange TEXT NOT NULL,
  quote_symbol TEXT NOT NULL,
  contract_type TEXT NOT NULL,
  period TEXT NOT NULL,
  current_published_at_ms BIGINT,
  current_source_frontier_ms BIGINT,
  current_row_count BIGINT NOT NULL DEFAULT 0,
  latest_attempt_status TEXT NOT NULL DEFAULT 'pending',
  latest_attempt_started_at_ms BIGINT,
  latest_attempt_finished_at_ms BIGINT,
  latest_attempt_error TEXT,
  updated_at_ms BIGINT NOT NULL,
  UNIQUE (provider, exchange, quote_symbol, contract_type, period)
)
"""

_CREATE_CEX_OI_ROWS_SQL = """
CREATE TABLE IF NOT EXISTS cex_oi_radar_rows (
  row_id TEXT PRIMARY KEY,
  period TEXT NOT NULL,
  board_provider TEXT NOT NULL,
  board_exchange TEXT NOT NULL,
  board_quote_symbol TEXT NOT NULL,
  board_contract_type TEXT NOT NULL,
  rank BIGINT NOT NULL,
  target_id TEXT NOT NULL,
  pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
  native_market_id TEXT NOT NULL,
  base_symbol TEXT NOT NULL,
  quote_symbol TEXT NOT NULL,
  open_interest_usd NUMERIC,
  open_interest_change_pct_1h NUMERIC,
  volume_24h_usd NUMERIC,
  funding_rate NUMERIC,
  mark_price NUMERIC,
  score NUMERIC NOT NULL,
  score_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  observed_at_ms BIGINT NOT NULL,
  computed_at_ms BIGINT NOT NULL
)
"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_DROP_OBSOLETE_MACRO_LOOKUP_INDEX_SQL)
        op.execute(_CREATE_MACRO_HISTORY_ORDER_INDEX_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")

    op.execute("DROP TABLE IF EXISTS macro_observation_series_rows_legacy_20260527_0114")
    _rebuild_macro_view_snapshots()
    _create_macro_projection_dirty_targets()
    _rebuild_cex_oi_radar_current_tables()
    _add_payload_hash_columns()

    for table_name in (
        "macro_observation_series_rows",
        "macro_view_snapshots",
        "macro_projection_dirty_targets",
        "cex_oi_radar_publication_state",
        "cex_oi_radar_rows",
        "news_page_rows",
        "news_source_quality_rows",
        "token_profile_current",
    ):
        op.execute(f"ANALYZE {table_name}")


def downgrade() -> None:
    raise RuntimeError(
        "20260527_0115 next runtime lifecycle hard cut is not safely reversible; "
        "restore from backup or rebuild current read models from material facts."
    )


def _rebuild_macro_view_snapshots() -> None:
    op.execute("DROP TABLE IF EXISTS macro_view_snapshots_compact")
    op.execute(_CREATE_MACRO_VIEW_SNAPSHOTS_COMPACT_SQL)
    op.execute(_COPY_LATEST_MACRO_VIEW_SNAPSHOTS_SQL)
    op.execute("DROP TABLE macro_view_snapshots")
    op.execute("ALTER TABLE macro_view_snapshots_compact RENAME TO macro_view_snapshots")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_view_snapshots_current
          ON macro_view_snapshots(projection_version)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_view_snapshots_latest_current
          ON macro_view_snapshots(projection_version, computed_at_ms DESC)
        """
    )


def _create_macro_projection_dirty_targets() -> None:
    op.execute(_CREATE_MACRO_PROJECTION_DIRTY_TARGETS_SQL)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_projection_dirty_targets_due
          ON macro_projection_dirty_targets(priority ASC, due_at_ms ASC, updated_at_ms ASC)
          WHERE leased_until_ms IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_projection_dirty_targets_lease
          ON macro_projection_dirty_targets(leased_until_ms)
          WHERE leased_until_ms IS NOT NULL
        """
    )
    op.execute(_SEED_MACRO_VIEW_DIRTY_TARGET_SQL)


def _rebuild_cex_oi_radar_current_tables() -> None:
    op.execute("DROP TABLE IF EXISTS cex_oi_radar_rows")
    op.execute("DROP TABLE IF EXISTS cex_oi_radar_runs")
    op.execute(_CREATE_CEX_OI_PUBLICATION_STATE_SQL)
    op.execute(_CREATE_CEX_OI_ROWS_SQL)
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_cex_oi_radar_rows_current_target
          ON cex_oi_radar_rows(
            board_provider,
            board_exchange,
            board_quote_symbol,
            board_contract_type,
            period,
            target_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_oi_radar_rows_current_rank
          ON cex_oi_radar_rows(
            board_provider,
            board_exchange,
            board_quote_symbol,
            board_contract_type,
            period,
            rank
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_oi_radar_publication_state_current
          ON cex_oi_radar_publication_state(
            provider,
            exchange,
            quote_symbol,
            contract_type,
            period
          )
        """
    )


def _add_payload_hash_columns() -> None:
    op.execute("ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS payload_hash TEXT")
    op.execute(
        """
        UPDATE news_page_rows
        SET payload_hash = COALESCE(NULLIF(payload_hash, ''), 'legacy:' || md5(row_to_json(news_page_rows)::text))
        WHERE payload_hash IS NULL OR payload_hash = ''
        """
    )
    op.execute("ALTER TABLE news_page_rows ALTER COLUMN payload_hash SET NOT NULL")

    op.execute("ALTER TABLE news_source_quality_rows ADD COLUMN IF NOT EXISTS payload_hash TEXT")
    op.execute(
        """
        UPDATE news_source_quality_rows
        SET payload_hash = COALESCE(
          NULLIF(payload_hash, ''),
          'legacy:' || md5(row_to_json(news_source_quality_rows)::text)
        )
        WHERE payload_hash IS NULL OR payload_hash = ''
        """
    )
    op.execute("ALTER TABLE news_source_quality_rows ALTER COLUMN payload_hash SET NOT NULL")

    op.execute("ALTER TABLE token_profile_current ADD COLUMN IF NOT EXISTS payload_hash TEXT")
    op.execute(
        """
        UPDATE token_profile_current
        SET payload_hash = COALESCE(
          NULLIF(payload_hash, ''),
          'legacy:' || md5(row_to_json(token_profile_current)::text)
        )
        WHERE payload_hash IS NULL OR payload_hash = ''
        """
    )
    op.execute("ALTER TABLE token_profile_current ALTER COLUMN payload_hash SET NOT NULL")
