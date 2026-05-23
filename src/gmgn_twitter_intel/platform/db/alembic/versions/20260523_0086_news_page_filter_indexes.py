"""Add indexed news page filter paths."""

from __future__ import annotations

from alembic import op

revision = "20260523_0086"
down_revision = "20260523_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_provider_type_time
          ON news_page_rows ((source_json ->> 'provider_type'), latest_at_ms DESC, row_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_source_role_time
          ON news_page_rows ((source_json ->> 'source_role'), latest_at_ms DESC, row_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_trust_tier_time
          ON news_page_rows ((source_json ->> 'trust_tier'), latest_at_ms DESC, row_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_direction_time
          ON news_page_rows (LOWER(agent_brief_json ->> 'direction'), latest_at_ms DESC, row_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_decision_class_time
          ON news_page_rows ((agent_brief_json ->> 'decision_class'), latest_at_ms DESC, row_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_coverage_tags_gin
          ON news_page_rows USING GIN ((source_json -> 'coverage_tags'))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_page_rows_content_tags_gin
          ON news_page_rows USING GIN (content_tags_json)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_content_tags_gin")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_coverage_tags_gin")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_decision_class_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_direction_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_trust_tier_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_source_role_time")
    op.execute("DROP INDEX IF EXISTS idx_news_page_rows_provider_type_time")
