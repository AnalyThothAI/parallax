"""Index the news provider-item fetch-run foreign key."""

from __future__ import annotations

from alembic import op

revision = "20260722_0187"
down_revision = "20260722_0186"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        CREATE INDEX idx_news_provider_items_fetch_run_id
          ON news_provider_items(fetch_run_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_news_provider_items_fetch_run_id")
