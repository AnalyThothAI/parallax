"""Keep News source status bounded after a cold PostgreSQL start."""

from __future__ import annotations

from alembic import op

revision = "20260724_0196"
down_revision = "20260724_0195"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        CREATE INDEX ix_news_items_source_status_cover
          ON news_items(news_item_id)
          INCLUDE (published_at_ms, fetched_at_ms)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_news_items_source_status_cover")
