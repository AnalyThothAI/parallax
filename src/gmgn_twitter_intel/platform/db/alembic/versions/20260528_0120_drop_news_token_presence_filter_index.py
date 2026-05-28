"""Drop retired News token-presence filter index."""

from __future__ import annotations

from alembic import op

revision = "20260528_0120"
down_revision = "20260528_0119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_news_page_rows_token_count_time")


def downgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_page_rows_token_count_time
          ON news_page_rows ((jsonb_array_length(token_lanes_json)), latest_at_ms DESC)
        """
    )
