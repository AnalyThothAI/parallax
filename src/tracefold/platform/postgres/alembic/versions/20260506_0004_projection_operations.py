"""Add PostgreSQL projection operation tables."""

from __future__ import annotations

from alembic import op

revision = "20260506_0004"
down_revision = "20260506_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projection_offsets (
          projection_name TEXT PRIMARY KEY,
          projection_version TEXT NOT NULL,
          source_table TEXT NOT NULL,
          source_max_received_at_ms BIGINT NOT NULL DEFAULT 0,
          source_max_id TEXT NOT NULL DEFAULT '',
          last_run_id TEXT,
          status TEXT NOT NULL,
          lag_ms BIGINT NOT NULL DEFAULT 0,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projection_runs (
          run_id TEXT PRIMARY KEY,
          projection_name TEXT NOT NULL,
          projection_version TEXT NOT NULL,
          mode TEXT NOT NULL,
          status TEXT NOT NULL,
          source_start_ms BIGINT,
          source_end_ms BIGINT,
          rows_read BIGINT NOT NULL DEFAULT 0,
          rows_written BIGINT NOT NULL DEFAULT 0,
          dirty_ranges_written BIGINT NOT NULL DEFAULT 0,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT,
          error TEXT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_projection_runs_lookup
          ON projection_runs(projection_name, projection_version, started_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projection_dirty_ranges (
          dirty_id TEXT PRIMARY KEY,
          projection_name TEXT NOT NULL,
          projection_version TEXT NOT NULL,
          entity_type TEXT NOT NULL,
          entity_key TEXT NOT NULL,
          "window" TEXT,
          scope TEXT,
          start_ms BIGINT NOT NULL,
          end_ms BIGINT NOT NULL,
          reason TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_projection_dirty_ranges_dedup
          ON projection_dirty_ranges(
            projection_name, projection_version, entity_type, entity_key,
            "window", scope, start_ms, end_ms, reason
          ) NULLS NOT DISTINCT
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_projection_dirty_ranges_claim
          ON projection_dirty_ranges(projection_name, projection_version, created_at_ms ASC, dirty_id ASC)
          WHERE status = 'pending'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_social_buckets (
          projection_version TEXT NOT NULL,
          scope TEXT NOT NULL,
          bucket_size_ms BIGINT NOT NULL,
          bucket_start_ms BIGINT NOT NULL,
          token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE,
          identity_key TEXT NOT NULL,
          chain TEXT,
          address TEXT,
          symbol TEXT,
          post_count BIGINT NOT NULL DEFAULT 0,
          direct_mention_count BIGINT NOT NULL DEFAULT 0,
          selected_symbol_mention_count BIGINT NOT NULL DEFAULT 0,
          weighted_mention_count DOUBLE PRECISION NOT NULL DEFAULT 0,
          attribution_confidence_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
          watched_post_count BIGINT NOT NULL DEFAULT 0,
          unique_author_count BIGINT NOT NULL DEFAULT 0,
          watched_author_count BIGINT NOT NULL DEFAULT 0,
          weighted_reach DOUBLE PRECISION NOT NULL DEFAULT 0,
          first_seen_ms BIGINT,
          latest_seen_ms BIGINT,
          top_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          top_authors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_attribution_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, scope, bucket_size_ms, bucket_start_ms, token_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_social_buckets_window
          ON token_social_buckets(projection_version, scope, bucket_size_ms, bucket_start_ms)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_social_buckets_token_window
          ON token_social_buckets(projection_version, scope, token_id, bucket_start_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_social_bucket_authors (
          projection_version TEXT NOT NULL,
          scope TEXT NOT NULL,
          bucket_size_ms BIGINT NOT NULL,
          bucket_start_ms BIGINT NOT NULL,
          token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE,
          author_handle TEXT NOT NULL,
          post_count BIGINT NOT NULL DEFAULT 0,
          watched_post_count BIGINT NOT NULL DEFAULT 0,
          followers_max BIGINT,
          first_seen_ms BIGINT,
          latest_seen_ms BIGINT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, scope, bucket_size_ms, bucket_start_ms, token_id, author_handle)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_social_bucket_authors_token
          ON token_social_bucket_authors(
            projection_version, scope, bucket_size_ms, bucket_start_ms, token_id, author_handle
          )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_flow_window_snapshots (
          snapshot_id TEXT PRIMARY KEY,
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          decision_time_ms BIGINT NOT NULL,
          rank BIGINT NOT NULL,
          token_id TEXT NOT NULL REFERENCES tokens(token_id) ON DELETE CASCADE,
          identity_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          flow_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          timeline_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          score_versions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          component_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_bucket_range_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_max_received_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          UNIQUE(projection_version, "window", scope, decision_time_ms, rank)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_flow_window_snapshots_latest
          ON token_flow_window_snapshots(projection_version, "window", scope, decision_time_ms DESC, rank ASC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_flow_window_snapshots_latest")
    op.execute("DROP TABLE IF EXISTS token_flow_window_snapshots")
    op.execute("DROP INDEX IF EXISTS idx_token_social_bucket_authors_token")
    op.execute("DROP TABLE IF EXISTS token_social_bucket_authors")
    op.execute("DROP INDEX IF EXISTS idx_token_social_buckets_token_window")
    op.execute("DROP INDEX IF EXISTS idx_token_social_buckets_window")
    op.execute("DROP TABLE IF EXISTS token_social_buckets")
    op.execute("DROP INDEX IF EXISTS idx_projection_dirty_ranges_claim")
    op.execute("DROP INDEX IF EXISTS ux_projection_dirty_ranges_dedup")
    op.execute("DROP TABLE IF EXISTS projection_dirty_ranges")
    op.execute("DROP INDEX IF EXISTS idx_projection_runs_lookup")
    op.execute("DROP TABLE IF EXISTS projection_runs")
    op.execute("DROP TABLE IF EXISTS projection_offsets")
