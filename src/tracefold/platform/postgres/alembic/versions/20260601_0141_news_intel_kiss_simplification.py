"""Simplify News Intel read-model lifecycle columns."""

from __future__ import annotations

from alembic import op

revision = "20260601_0141"
down_revision = "20260601_0140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN source_watermark_ms")
    op.execute("ALTER TABLE news_source_quality_rows DROP COLUMN source_watermark_ms")
    op.execute("ANALYZE news_page_rows")
    op.execute("ANALYZE news_source_quality_rows")


def downgrade() -> None:
    """No downgrade for hard-cut removal of unused News serving watermarks."""
