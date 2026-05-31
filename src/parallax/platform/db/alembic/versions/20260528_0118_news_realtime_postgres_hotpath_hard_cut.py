"""Hard cut News realtime and PostgreSQL hot paths."""

from __future__ import annotations

from alembic import op

revision = "20260528_0118"
down_revision = "20260528_0117"
branch_labels = None
depends_on = None


_DELETE_NO_START_BACKPRESSURE_RUNS_SQL = """
DELETE FROM news_item_agent_runs AS runs
 WHERE runs.execution_started = false
   AND runs.outcome IN ('backpressure_circuit_open', 'backpressure_capacity_denied')
"""

_DELETE_OPENNEWS_PROVIDER_SIGNAL_BRIEF_TARGETS_SQL = """
DELETE FROM news_projection_dirty_targets AS targets
USING news_items AS items, news_sources AS sources
 WHERE targets.projection_name = 'brief_input'
   AND targets.target_kind = 'news_item'
   AND targets.target_id = items.news_item_id
   AND sources.source_id = items.source_id
   AND sources.provider_type = 'opennews'
   AND items.provider_signal_json ->> 'source' = 'provider'
"""

_CREATE_HOTPATH_INDEXES_SQL = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_unprocessed_claim
      ON news_items(published_at_ms ASC, news_item_id ASC)
      WHERE lifecycle_status IN ('raw', 'process_failed')
         OR (
           lifecycle_status = 'processed'
           AND content_classification_json = '{}'::jsonb
         )
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_page_rows_news_item
      ON news_page_rows(news_item_id)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_projection_dirty_projection_due
      ON news_projection_dirty_targets(
        projection_name,
        due_at_ms,
        leased_until_ms,
        priority,
        updated_at_ms,
        target_kind,
        target_id,
        "window"
      )
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_context_items_source_effective_time
      ON news_context_items(
        source_id,
        (COALESCE(published_at_ms, created_at_ms)),
        parent_news_item_id
      )
    """,
)

_ANALYZE_SQL = (
    "ANALYZE news_item_agent_runs",
    "ANALYZE news_projection_dirty_targets",
    "ANALYZE news_items",
    "ANALYZE news_page_rows",
    "ANALYZE news_context_items",
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(_DELETE_NO_START_BACKPRESSURE_RUNS_SQL)
    op.execute(_DELETE_OPENNEWS_PROVIDER_SIGNAL_BRIEF_TARGETS_SQL)

    for statement in _ANALYZE_SQL:
        op.execute(statement)

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _CREATE_HOTPATH_INDEXES_SQL:
            op.execute(statement)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_context_items_source_effective_time")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_projection_dirty_projection_due")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_page_rows_news_item")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_unprocessed_claim")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")
