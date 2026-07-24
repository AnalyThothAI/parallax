"""Reprocess News items with retired agent admission policy."""

from __future__ import annotations

from alembic import op

revision = "20260609_0170"
down_revision = "20260609_0169"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        CREATE TEMP TABLE news_agent_admission_reprocess_targets ON COMMIT DROP AS
        SELECT news_item_id
          FROM news_items
         WHERE lifecycle_status = 'processed'
           AND (
             agent_admission_version <> 'news_item_agent_admission_market_v2'
             OR COALESCE(agent_admission_json->>'version', '') <> 'news_item_agent_admission_market_v2'
             OR agent_admission_status NOT IN (
               'eligible',
               'eligible_refresh',
               'exact_duplicate',
               'similar_story_covered',
               'similar_story_burst',
               'materially_superseded',
               'source_suppressed',
               'operational_disabled',
               'needs_review'
             )
           )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_news_agent_admission_reprocess_targets
          ON news_agent_admission_reprocess_targets(news_item_id)
        """
    )
    op.execute(
        """
        UPDATE news_items AS items
           SET lifecycle_status = 'raw',
               processing_lease_owner = NULL,
               processing_leased_until_ms = NULL,
               processing_next_due_at_ms = 0,
               processing_attempts = 0,
               processing_error = NULL,
               processing_terminal_error = NULL,
               agent_admission_status = 'needs_review',
               agent_admission_reason = 'agent_admission_policy_reprocess',
               agent_admission_json = '{}'::jsonb,
               agent_admission_version = '',
               agent_representative_news_item_id = '',
               agent_admission_computed_at_ms = NULL,
               updated_at_ms = GREATEST(
                 items.updated_at_ms,
                 (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint
               )
          FROM news_agent_admission_reprocess_targets AS targets
         WHERE items.news_item_id = targets.news_item_id
        """
    )
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets AS dirty
         USING news_agent_admission_reprocess_targets AS targets
         WHERE dirty.target_kind = 'news_item'
           AND dirty.target_id = targets.news_item_id
           AND dirty.projection_name IN ('page', 'brief_input')
        """
    )
    op.execute(
        """
        DELETE FROM news_page_rows AS rows
         USING news_agent_admission_reprocess_targets AS targets
         WHERE rows.news_item_id = targets.news_item_id
        """
    )
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_page_rows")
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    pass
