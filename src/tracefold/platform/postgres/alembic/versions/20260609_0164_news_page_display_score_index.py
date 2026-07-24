"""Index News page default display-score reads."""

from __future__ import annotations

from alembic import op

revision = "20260609_0164"
down_revision = "20260609_0163"
branch_labels = None
depends_on = None


def upgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_display_score80_latest
              ON news_page_rows(projection_version, latest_at_ms DESC, row_id DESC)
              WHERE COALESCE(NULLIF(signal_json -> 'display_signal' ->> 'score', '')::int, -1) >= 80
            """
        )
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    pass
