"""Add Token Pulse and Equity CPU hard-cut indexes."""

from __future__ import annotations

from alembic import op

revision = "20260529_0124"
down_revision = "20260529_0123"
branch_labels = None
depends_on = None


_CREATE_INDEX_SQL = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intents_event_intent
      ON token_intents(event_id, intent_id)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_resolutions_current_event_target
      ON token_intent_resolutions(
        event_id,
        target_type,
        target_id,
        resolver_policy_version,
        resolution_status,
        confidence DESC,
        decision_time_ms DESC,
        resolution_id DESC
      )
      WHERE is_current = true
        AND target_type IN ('Asset', 'CexToken')
        AND target_id IS NOT NULL
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_feeds_cex_canonical_updated
      ON price_feeds(subject_id, updated_at_ms DESC, native_market_id ASC)
      WHERE subject_type = 'CexToken'
        AND provider = 'binance'
        AND feed_type = 'cex_swap'
        AND quote_symbol = 'USDT'
        AND status = 'canonical'
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_company_timeline_rows_company_row
      ON equity_company_timeline_rows(company_id, row_id)
      INCLUDE (
        company_event_id,
        projection_version,
        payload_hash,
        source_watermark_ms
      )
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_company_timeline_rows_event_row
      ON equity_company_timeline_rows(company_event_id, row_id)
      INCLUDE (
        company_id,
        projection_version,
        payload_hash,
        source_watermark_ms
      )
    """,
)


_DROP_INDEX_SQL = (
    "DROP INDEX CONCURRENTLY IF EXISTS idx_equity_company_timeline_rows_event_row",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_equity_company_timeline_rows_company_row",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_price_feeds_cex_canonical_updated",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_token_intent_resolutions_current_event_target",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_token_intents_event_intent",
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for statement in _CREATE_INDEX_SQL:
            op.execute(statement)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for statement in _DROP_INDEX_SQL:
            op.execute(statement)
