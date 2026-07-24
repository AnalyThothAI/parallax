"""Index News page member-id lookups."""

from __future__ import annotations

from alembic import op

revision = "20260609_0162"
down_revision = "20260609_0161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_member_news_item_ids_gin
              ON news_page_rows
              USING GIN ((COALESCE(story_json -> 'member_news_item_ids', '[]'::jsonb)))
            """
        )
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    pass
