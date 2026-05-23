"""Split Token Radar current, rank history, and snapshot audit storage."""

from __future__ import annotations

from alembic import op

revision = "20260523_0085"
down_revision = "20260523_0084"
branch_labels = None
depends_on = None


RADAR_ROW_COLUMNS = """
  row_id TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  "window" TEXT NOT NULL,
  scope TEXT NOT NULL,
  computed_at_ms BIGINT NOT NULL,
  source_max_received_at_ms BIGINT NOT NULL,
  lane TEXT NOT NULL,
  rank BIGINT NOT NULL,
  intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  target_type TEXT,
  target_id TEXT,
  pricefeed_id TEXT,
  intent_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  asset_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  primary_venue_json JSONB,
  target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  attention_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  resolution_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  price_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  score_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  factor_version TEXT NOT NULL,
  decision TEXT NOT NULL,
  data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  listed_at_ms BIGINT NOT NULL,
  created_at_ms BIGINT NOT NULL
"""


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS token_radar_current_rows (
          {RADAR_ROW_COLUMNS},
          PRIMARY KEY (row_id),
          UNIQUE (projection_version, "window", scope, lane, rank)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit (
          snapshot_id TEXT NOT NULL,
          {RADAR_ROW_COLUMNS},
          PRIMARY KEY (snapshot_id, computed_at_ms)
        ) PARTITION BY RANGE (computed_at_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_rank_history (
          row_id TEXT NOT NULL,
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          source_max_received_at_ms BIGINT NOT NULL,
          lane TEXT NOT NULL,
          rank BIGINT NOT NULL,
          rank_score DOUBLE PRECISION,
          decision TEXT NOT NULL,
          intent_id TEXT NOT NULL,
          event_id TEXT NOT NULL,
          target_type TEXT,
          target_id TEXT,
          pricefeed_id TEXT,
          target_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          listed_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY (row_id, computed_at_ms)
        ) PARTITION BY RANGE (computed_at_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_snapshot_audit_default
          PARTITION OF token_radar_snapshot_audit DEFAULT
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_rank_history_default
          PARTITION OF token_radar_rank_history DEFAULT
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_storage_maintenance_runs (
          run_id TEXT PRIMARY KEY,
          command TEXT NOT NULL,
          mode TEXT NOT NULL,
          status TEXT NOT NULL,
          dropped_tables_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          truncated_tables_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          deleted_control_rows_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          error TEXT,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_read
          ON token_radar_current_rows(projection_version, "window", scope, lane, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_target
          ON token_radar_current_rows(target_type, target_id, computed_at_ms DESC)
          WHERE target_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_history_read
          ON token_radar_rank_history(projection_version, "window", scope, computed_at_ms DESC, lane, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_history_target
          ON token_radar_rank_history(target_type, target_id, computed_at_ms DESC)
          WHERE target_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_snapshot_audit_read
          ON token_radar_snapshot_audit(projection_version, "window", scope, computed_at_ms DESC, lane, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_snapshot_audit_settlement
          ON token_radar_snapshot_audit(factor_version, "window", scope, computed_at_ms, target_type, target_id)
          WHERE target_id IS NOT NULL
        """
    )
    op.execute("DROP TABLE IF EXISTS token_radar_rows CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_retention_runs")
    op.execute("TRUNCATE TABLE token_radar_target_first_seen RESTART IDENTITY")
    op.execute(
        """
        DELETE FROM token_radar_projection_coverage
        WHERE projection_version LIKE 'token-radar-%'
        """
    )
    op.execute(
        """
        DELETE FROM projection_offsets
        WHERE projection_name = 'token-radar'
        """
    )
    op.execute(
        """
        DELETE FROM projection_runs
        WHERE projection_name = 'token-radar'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_radar_snapshot_audit_settlement")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_snapshot_audit_read")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rank_history_target")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rank_history_read")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_current_rows_target")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_current_rows_read")
    op.execute("DROP TABLE IF EXISTS token_radar_storage_maintenance_runs")
    op.execute("DROP TABLE IF EXISTS token_radar_rank_history")
    op.execute("DROP TABLE IF EXISTS token_radar_snapshot_audit")
    op.execute("DROP TABLE IF EXISTS token_radar_current_rows")
