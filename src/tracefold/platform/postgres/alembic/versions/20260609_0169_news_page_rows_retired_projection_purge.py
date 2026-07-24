"""Purge retired News page projection rows."""

from __future__ import annotations

from alembic import op

revision = "20260609_0169"
down_revision = "20260609_0168"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        DELETE FROM news_page_rows
         WHERE projection_version <> 'news_page_rows_v5'
            OR story_key ~ '^news-story:opennews-article:'
        """
    )
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    pass
