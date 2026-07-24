"""Route agent brief inputs through dirty target queues."""

from __future__ import annotations

from alembic import op

revision = "20260525_0097"
down_revision = "20260525_0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          DROP CONSTRAINT IF EXISTS news_projection_dirty_targets_projection_name_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          DROP CONSTRAINT IF EXISTS news_projection_dirty_targets_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          ADD CONSTRAINT news_projection_dirty_targets_projection_name_check
          CHECK (projection_name IN ('story', 'brief_input', 'page', 'source_quality'))
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          ADD CONSTRAINT news_projection_dirty_targets_check
          CHECK (
            (projection_name = 'source_quality' AND target_kind = 'source' AND "window" <> '')
            OR (
              projection_name IN ('story', 'brief_input', 'page')
              AND target_kind = 'news_item'
              AND "window" = ''
            )
          )
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_company_events_brief_candidates
              ON equity_company_events(event_time_ms DESC, company_event_id)
              WHERE validation_status <> 'rejected'
                AND lifecycle_status IN ('raw', 'processed', 'brief_ready', 'brief_stale')
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_event_agent_runs_brief_attempts
              ON equity_event_agent_runs(
                company_event_id,
                artifact_version_hash,
                execution_started,
                status,
                started_at_ms DESC
              )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_event_agent_runs_latest
              ON equity_event_agent_runs(company_event_id, finished_at_ms DESC, run_id DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_items_processed_published
              ON news_items(published_at_ms DESC, news_item_id DESC)
              WHERE lifecycle_status = 'processed'
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_item_agent_runs_started_attempts
              ON news_item_agent_runs(news_item_id, artifact_version_hash)
              WHERE execution_started = true
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_item_agent_runs_recent_backpressure
              ON news_item_agent_runs(news_item_id, finished_at_ms DESC)
              WHERE execution_started = false AND status = 'backpressure'
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_story_members_story_created
              ON news_story_members(story_id, created_at_ms DESC, news_item_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_context_items_source_effective_time
              ON news_context_items(source_id, (COALESCE(published_at_ms, created_at_ms)) DESC)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_context_items_source_effective_time")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_story_members_story_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_item_agent_runs_recent_backpressure")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_item_agent_runs_started_attempts")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_items_processed_published")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_equity_event_agent_runs_latest")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_equity_event_agent_runs_brief_attempts")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_equity_company_events_brief_candidates")

    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          DROP CONSTRAINT IF EXISTS news_projection_dirty_targets_projection_name_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          DROP CONSTRAINT IF EXISTS news_projection_dirty_targets_check
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          ADD CONSTRAINT news_projection_dirty_targets_projection_name_check
          CHECK (projection_name IN ('story', 'page', 'source_quality'))
        """
    )
    op.execute(
        """
        ALTER TABLE news_projection_dirty_targets
          ADD CONSTRAINT news_projection_dirty_targets_check
          CHECK (
            (projection_name = 'source_quality' AND target_kind = 'source' AND "window" <> '')
            OR (projection_name <> 'source_quality' AND target_kind = 'news_item' AND "window" = '')
          )
        """
    )
