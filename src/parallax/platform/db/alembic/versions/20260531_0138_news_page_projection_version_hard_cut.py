"""Hard cut retired News page projection versions."""

from __future__ import annotations

from alembic import op

revision = "20260531_0138"
down_revision = "20260531_0137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        DELETE FROM news_page_rows
         WHERE projection_version <> 'news_page_rows_v3'
        """
    )
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    """No downgrade for retired News page projection versions."""
