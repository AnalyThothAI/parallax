"""Index News page alert-ready latest rows."""

from __future__ import annotations

from alembic import op

revision = "20260609_0163"
down_revision = "20260609_0162"
branch_labels = None
depends_on = None


def upgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_alert_ready_latest
              ON news_page_rows(
                projection_version,
                latest_at_ms DESC,
                agent_brief_computed_at_ms DESC,
                row_id DESC
              )
              WHERE agent_status = 'ready'
                AND COALESCE(agent_brief_json ->> 'status', '') = 'ready'
                AND COALESCE(
                  (signal_json -> 'alert_eligibility' ->> 'in_app_eligible')::boolean,
                  false
                ) = true
            """
        )
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    pass
