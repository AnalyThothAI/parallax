"""Index News source-status hot paths."""

from __future__ import annotations

from alembic import op

revision = "20260528_0119"
down_revision = "20260528_0118"
branch_labels = None
depends_on = None


_CREATE_INDEXES_SQL = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_item_observation_edges_source_item
      ON news_item_observation_edges(source_id, news_item_id)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_fetch_runs_source_started_run
      ON news_fetch_runs(source_id, started_at_ms DESC, fetch_run_id DESC)
    """,
)

_ANALYZE_SQL = (
    "ANALYZE news_item_observation_edges",
    "ANALYZE news_fetch_runs",
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _CREATE_INDEXES_SQL:
            op.execute(statement)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    for statement in _ANALYZE_SQL:
        op.execute(statement)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_fetch_runs_source_started_run")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_item_observation_edges_source_item")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")
