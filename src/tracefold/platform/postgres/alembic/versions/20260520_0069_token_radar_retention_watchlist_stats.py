"""Add Token Radar retention and watchlist signal stats read models."""

from __future__ import annotations

from alembic import op

revision = "20260520_0069"
down_revision = "20260520_0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE social_event_extractions ADD COLUMN IF NOT EXISTS normalized_handle TEXT")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_target_first_seen (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          first_seen_ms BIGINT NOT NULL,
          last_seen_ms BIGINT NOT NULL,
          first_row_id TEXT,
          latest_row_id TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (projection_version, "window", scope, target_type_key, identity_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_retention_runs (
          run_id TEXT PRIMARY KEY,
          mode TEXT NOT NULL,
          retention_days INTEGER NOT NULL,
          cutoff_ms BIGINT NOT NULL,
          batch_size INTEGER NOT NULL,
          max_batches INTEGER,
          rows_planned BIGINT NOT NULL DEFAULT 0,
          rows_deleted BIGINT NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          error TEXT,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_handle_signal_stats (
          handle TEXT PRIMARY KEY,
          total_signal_count BIGINT NOT NULL DEFAULT 0,
          latest_signal_at_ms BIGINT,
          latest_signal_event_id TEXT,
          first_signal_at_ms BIGINT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_handle_signal_events (
          event_id TEXT PRIMARY KEY,
          handle TEXT NOT NULL,
          received_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_rows_prune
              ON token_radar_rows(computed_at_ms ASC, row_id ASC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_first_seen_updated
              ON token_radar_target_first_seen(updated_at_ms DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_social_event_extractions_signal_normalized_handle_received
              ON social_event_extractions(normalized_handle, received_at_ms DESC, event_id DESC)
              WHERE is_signal_event = TRUE AND normalized_handle IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_watchlist_handle_signal_stats_latest
              ON watchlist_handle_signal_stats(latest_signal_at_ms DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_watchlist_handle_signal_events_handle_received
              ON watchlist_handle_signal_events(handle, received_at_ms DESC, event_id DESC)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_watchlist_handle_signal_events_handle_received")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_watchlist_handle_signal_stats_latest")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_social_event_extractions_signal_normalized_handle_received")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_first_seen_updated")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_rows_prune")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_signal_events")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_signal_stats")
    op.execute("DROP TABLE IF EXISTS token_radar_retention_runs")
    op.execute("DROP TABLE IF EXISTS token_radar_target_first_seen")
    op.execute("ALTER TABLE social_event_extractions DROP COLUMN IF EXISTS normalized_handle")
