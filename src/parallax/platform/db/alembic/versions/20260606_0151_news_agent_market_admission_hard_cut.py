"""Add News agent admission market hard-cut storage."""

from __future__ import annotations

from alembic import op

revision = "20260606_0151"
down_revision = "20260605_0151"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        ALTER TABLE news_items
          ADD COLUMN IF NOT EXISTS agent_admission_status TEXT NOT NULL DEFAULT 'needs_review',
          ADD COLUMN IF NOT EXISTS agent_admission_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS agent_admission_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS agent_admission_version TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS agent_representative_news_item_id TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS agent_admission_computed_at_ms BIGINT
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS agent_admission_status TEXT NOT NULL DEFAULT 'needs_review',
          ADD COLUMN IF NOT EXISTS agent_admission_reason TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS agent_admission_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS agent_representative_news_item_id TEXT NOT NULL DEFAULT ''
        """
    )

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_agent_admission_published
              ON news_items(agent_admission_status, published_at_ms DESC, news_item_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_agent_admission
              ON news_page_rows(agent_admission_status, latest_at_ms DESC, row_id DESC)
            """
        )
        op.execute("ANALYZE news_items")
        op.execute("ANALYZE news_page_rows")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    raise RuntimeError(
        "20260606_0151 News agent admission market hard cut is not safely reversible; "
        "agent admission state may already be consumed by runtime rows"
    )
