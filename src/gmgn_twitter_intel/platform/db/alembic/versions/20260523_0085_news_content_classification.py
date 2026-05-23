"""Materialize news content classification fields."""

from __future__ import annotations

from alembic import op

revision = "20260523_0085"
down_revision = "20260523_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS content_class TEXT NOT NULL DEFAULT 'low_signal'")
    op.execute(
        "ALTER TABLE news_items ADD COLUMN IF NOT EXISTS content_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        """
        ALTER TABLE news_items
          ADD COLUMN IF NOT EXISTS content_classification_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute("ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS content_class TEXT NOT NULL DEFAULT 'low_signal'")
    op.execute(
        "ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS content_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_items_content_class_time
          ON news_items(content_class, published_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_content_class_time
          ON news_page_rows(content_class, latest_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_content_class_time")
    op.execute("DROP INDEX IF EXISTS idx_news_items_content_class_time")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS content_tags_json")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS content_class")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS content_classification_json")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS content_tags_json")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS content_class")
