"""Add News analysis admission and story identity columns."""

from __future__ import annotations

from alembic import op

revision = "20260605_0149"
down_revision = "20260604_0148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        ALTER TABLE news_items
          ADD COLUMN IF NOT EXISTS analysis_admission_status TEXT NOT NULL DEFAULT 'needs_review',
          ADD COLUMN IF NOT EXISTS analysis_admission_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS analysis_admission_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS analysis_admission_version TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS story_key TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS story_identity_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS story_identity_version TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS representative_news_item_id TEXT,
          ADD COLUMN IF NOT EXISTS story_key TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS story_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS analysis_admission_status TEXT NOT NULL DEFAULT 'needs_review',
          ADD COLUMN IF NOT EXISTS analysis_admission_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS analysis_admission_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_story_key_published
              ON news_items(story_key, published_at_ms DESC, news_item_id)
              WHERE story_key <> ''
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_analysis_admission_published
              ON news_items(analysis_admission_status, published_at_ms DESC, news_item_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_story_key
              ON news_page_rows(story_key, latest_at_ms DESC, row_id DESC)
              WHERE story_key <> ''
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_analysis_admission
              ON news_page_rows(analysis_admission_status, latest_at_ms DESC, row_id DESC)
            """
        )
        op.execute("ANALYZE news_items")
        op.execute("ANALYZE news_page_rows")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    raise RuntimeError(
        "20260605_0149 News analysis/story hard cut is not safely reversible; "
        "admission and story identity columns may already be consumed by runtime rows"
    )
