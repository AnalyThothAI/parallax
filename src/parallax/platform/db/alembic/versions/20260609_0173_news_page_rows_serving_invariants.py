"""Enforce News page row serving invariants."""

from __future__ import annotations

from alembic import op

revision = "20260609_0173"
down_revision = "20260609_0172"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets AS dirty
         WHERE dirty.projection_name = 'page'
           AND dirty.target_kind = 'news_item'
           AND NOT EXISTS (
             SELECT 1
               FROM news_items AS items
              WHERE items.news_item_id = dirty.target_id
                AND items.lifecycle_status = 'processed'
                AND items.story_key <> ''
                AND items.story_identity_version = 'news_story_identity_v2'
                AND items.agent_admission_version = 'news_item_agent_admission_market_v2'
                AND items.agent_admission_status IN ('eligible', 'eligible_refresh')
           )
        """
    )
    op.execute(
        """
        DELETE FROM news_page_rows AS rows
         WHERE rows.projection_version = 'news_page_rows_v5'
           AND (
             rows.story_key = ''
             OR rows.agent_admission_status NOT IN ('eligible', 'eligible_refresh')
             OR NOT EXISTS (
               SELECT 1
                 FROM news_items AS items
                WHERE items.news_item_id = rows.news_item_id
                  AND items.lifecycle_status = 'processed'
                  AND items.story_key <> ''
                  AND items.story_identity_version = 'news_story_identity_v2'
                  AND items.agent_admission_version = 'news_item_agent_admission_market_v2'
                  AND items.agent_admission_status IN ('eligible', 'eligible_refresh')
             )
           )
        """
    )
    op.execute("ANALYZE news_projection_dirty_targets")
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    pass
