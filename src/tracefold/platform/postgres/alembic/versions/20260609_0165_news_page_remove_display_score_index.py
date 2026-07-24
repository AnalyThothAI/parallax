"""Remove retired News page display-score index."""

from __future__ import annotations

from alembic import op

revision = "20260609_0165"
down_revision = "20260609_0164"
branch_labels = None
depends_on = None


def upgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_page_rows_display_score80_latest")
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    pass
