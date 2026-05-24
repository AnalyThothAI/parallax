"""Add payload hashes to equity projection read models."""

from __future__ import annotations

from alembic import op

revision = "20260524_0092"
down_revision = "20260524_0091"
branch_labels = None
depends_on = None


_ADD_COLUMN_SQL = (
    """
    ALTER TABLE equity_event_page_rows
      ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE equity_event_page_rows
      ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE equity_company_timeline_rows
      ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE equity_company_timeline_rows
      ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE equity_event_alert_candidates
      ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE equity_event_alert_candidates
      ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE equity_event_calendar_rows
      ADD COLUMN IF NOT EXISTS payload_hash TEXT NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE equity_event_calendar_rows
      ADD COLUMN IF NOT EXISTS source_watermark_ms BIGINT NOT NULL DEFAULT 0
    """,
)

_CREATE_INDEX_SQL = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_event_calendar_rows_expected_event
      ON equity_event_calendar_rows(expected_event_id)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_event_page_rows_payload_hash
      ON equity_event_page_rows(payload_hash)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_company_timeline_rows_payload_hash
      ON equity_company_timeline_rows(payload_hash)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_event_alert_candidates_payload_hash
      ON equity_event_alert_candidates(payload_hash)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_equity_event_calendar_rows_payload_hash
      ON equity_event_calendar_rows(payload_hash)
    """,
)

_DROP_INDEX_SQL = (
    "DROP INDEX CONCURRENTLY IF EXISTS idx_equity_event_calendar_rows_payload_hash",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_equity_event_calendar_rows_expected_event",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_equity_event_alert_candidates_payload_hash",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_equity_company_timeline_rows_payload_hash",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_equity_event_page_rows_payload_hash",
)

_DROP_COLUMN_SQL = (
    """
    ALTER TABLE equity_event_calendar_rows
      DROP COLUMN IF EXISTS payload_hash
    """,
    """
    ALTER TABLE equity_event_calendar_rows
      DROP COLUMN IF EXISTS source_watermark_ms
    """,
    """
    ALTER TABLE equity_event_alert_candidates
      DROP COLUMN IF EXISTS payload_hash
    """,
    """
    ALTER TABLE equity_event_alert_candidates
      DROP COLUMN IF EXISTS source_watermark_ms
    """,
    """
    ALTER TABLE equity_company_timeline_rows
      DROP COLUMN IF EXISTS payload_hash
    """,
    """
    ALTER TABLE equity_company_timeline_rows
      DROP COLUMN IF EXISTS source_watermark_ms
    """,
    """
    ALTER TABLE equity_event_page_rows
      DROP COLUMN IF EXISTS payload_hash
    """,
    """
    ALTER TABLE equity_event_page_rows
      DROP COLUMN IF EXISTS source_watermark_ms
    """,
)


def upgrade() -> None:
    for statement in _ADD_COLUMN_SQL:
        op.execute(statement)

    with op.get_context().autocommit_block():
        for statement in _CREATE_INDEX_SQL:
            op.execute(statement)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for statement in _DROP_INDEX_SQL:
            op.execute(statement)

    for statement in _DROP_COLUMN_SQL:
        op.execute(statement)
