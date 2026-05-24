"""Add Equity and News projection dirty target queues."""

from __future__ import annotations

from alembic import op

revision = "20260524_0094"
down_revision = "20260524_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equity_event_projection_dirty_targets (
          projection_name TEXT NOT NULL,
          target_kind TEXT NOT NULL,
          target_id TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (projection_name, target_kind, target_id),
          CHECK (projection_name IN ('story', 'brief_input', 'page', 'timeline', 'alert', 'calendar')),
          CHECK (target_kind IN ('company_event', 'expected_event', 'company'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_projection_dirty_targets (
          projection_name TEXT NOT NULL,
          target_kind TEXT NOT NULL,
          target_id TEXT NOT NULL,
          "window" TEXT NOT NULL DEFAULT '',
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 100,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0,
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (projection_name, target_kind, target_id, "window"),
          CHECK (projection_name IN ('story', 'page', 'source_quality')),
          CHECK (target_kind IN ('news_item', 'source')),
          CHECK (
            (projection_name = 'source_quality' AND target_kind = 'source' AND "window" <> '')
            OR (projection_name <> 'source_quality' AND target_kind = 'news_item' AND "window" = '')
          )
        )
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        ALTER TABLE news_source_quality_rows
          ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        ALTER TABLE news_source_quality_rows
          ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_projection_dirty_due
              ON equity_event_projection_dirty_targets(
                due_at_ms,
                leased_until_ms,
                priority,
                updated_at_ms,
                projection_name,
                target_kind,
                target_id
              )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_projection_dirty_lease
              ON equity_event_projection_dirty_targets(leased_until_ms, due_at_ms)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_projection_dirty_due
              ON news_projection_dirty_targets(
                due_at_ms,
                leased_until_ms,
                priority,
                updated_at_ms,
                projection_name,
                target_kind,
                target_id,
                "window"
              )
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_projection_dirty_lease
              ON news_projection_dirty_targets(leased_until_ms, due_at_ms)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_projection_dirty_lease")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_projection_dirty_due")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_equity_projection_dirty_lease")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_equity_projection_dirty_due")

    op.execute("DROP TABLE IF EXISTS news_projection_dirty_targets")
    op.execute("DROP TABLE IF EXISTS equity_event_projection_dirty_targets")
    op.execute(
        """
        ALTER TABLE news_source_quality_rows
          DROP COLUMN IF EXISTS source_watermark_ms
        """
    )
    op.execute(
        """
        ALTER TABLE news_source_quality_rows
          DROP COLUMN IF EXISTS payload_hash
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          DROP COLUMN IF EXISTS source_watermark_ms
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          DROP COLUMN IF EXISTS payload_hash
        """
    )
