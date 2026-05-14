"""Add watchlist handle intel summary tables."""

from __future__ import annotations

from alembic import op

revision = "20260514_0045"
down_revision = "20260514_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_handle_summary_jobs (
          handle TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          next_run_at_ms BIGINT NOT NULL,
          pending_signal_count BIGINT NOT NULL DEFAULT 0,
          trigger_reason TEXT NOT NULL,
          lease_expires_at_ms BIGINT,
          lease_token TEXT,
          attempt_count BIGINT NOT NULL DEFAULT 0,
          max_attempts BIGINT NOT NULL DEFAULT 3,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_watchlist_handle_summary_jobs_due
          ON watchlist_handle_summary_jobs(status, next_run_at_ms, updated_at_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_handle_summaries (
          handle TEXT PRIMARY KEY,
          generated_at_ms BIGINT NOT NULL,
          input_window_start_ms BIGINT NOT NULL,
          input_window_end_ms BIGINT NOT NULL,
          input_event_count BIGINT NOT NULL,
          signal_count_at_generation BIGINT NOT NULL,
          model TEXT NOT NULL,
          summary_zh TEXT NOT NULL,
          topics_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          raw_response_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist_handle_summary_runs (
          run_id TEXT PRIMARY KEY,
          handle TEXT NOT NULL,
          status TEXT NOT NULL,
          model TEXT NOT NULL,
          request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          response_json JSONB,
          input_event_count BIGINT NOT NULL DEFAULT 0,
          usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          error TEXT,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_watchlist_handle_summary_runs_handle_started
          ON watchlist_handle_summary_runs(handle, started_at_ms DESC)
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_author_received_event_lower_desc
              ON events(lower(author_handle), received_at_ms DESC, event_id DESC)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_events_author_received_event_lower_desc")
    op.execute("DROP INDEX IF EXISTS idx_watchlist_handle_summary_runs_handle_started")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_summary_runs")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_summaries")
    op.execute("DROP INDEX IF EXISTS idx_watchlist_handle_summary_jobs_due")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_summary_jobs")
