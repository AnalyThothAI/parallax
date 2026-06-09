"""Require eligible News agent admission for page serving rows."""

from __future__ import annotations

from alembic import op

revision = "20260609_0172"
down_revision = "20260609_0171"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets AS dirty
         USING news_items AS items
         WHERE dirty.projection_name = 'page'
           AND dirty.target_kind = 'news_item'
           AND dirty.target_id = items.news_item_id
           AND (
             items.agent_admission_version <> 'news_item_agent_admission_market_v2'
             OR items.agent_admission_status NOT IN ('eligible', 'eligible_refresh')
           )
        """
    )
    op.execute(
        """
        DELETE FROM news_page_rows AS rows
         USING news_items AS items
         WHERE rows.news_item_id = items.news_item_id
           AND rows.projection_version = 'news_page_rows_v5'
           AND (
             rows.agent_admission_status NOT IN ('eligible', 'eligible_refresh')
             OR items.agent_admission_version <> 'news_item_agent_admission_market_v2'
             OR items.agent_admission_status NOT IN ('eligible', 'eligible_refresh')
           )
        """
    )
    op.execute("ANALYZE news_projection_dirty_targets")
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    pass
