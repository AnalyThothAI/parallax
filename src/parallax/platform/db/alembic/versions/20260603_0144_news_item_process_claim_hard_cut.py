"""Hard cut News item processing claim and retry lifecycle."""

from __future__ import annotations

from alembic import op

revision = "20260603_0144"
down_revision = "20260603_0143"
branch_labels = None
depends_on = None


_DROP_LEGACY_LIFECYCLE_CHECK_SQL = """
DO $$
DECLARE
  lifecycle_constraint_name TEXT;
BEGIN
  ALTER TABLE news_items DROP CONSTRAINT IF EXISTS news_items_lifecycle_status_check;

  SELECT constraints.conname
    INTO lifecycle_constraint_name
    FROM pg_constraint AS constraints
    JOIN pg_class AS tables
      ON tables.oid = constraints.conrelid
    JOIN pg_namespace AS namespaces
      ON namespaces.oid = tables.relnamespace
   WHERE namespaces.nspname = current_schema()
     AND tables.relname = 'news_items'
     AND constraints.contype = 'c'
     AND pg_get_constraintdef(constraints.oid) LIKE '%lifecycle_status%'
     AND pg_get_constraintdef(constraints.oid) LIKE '%raw%'
     AND pg_get_constraintdef(constraints.oid) LIKE '%processed%'
     AND pg_get_constraintdef(constraints.oid) LIKE '%process_failed%'
   LIMIT 1;

  IF lifecycle_constraint_name IS NOT NULL THEN
    EXECUTE format(
      'ALTER TABLE news_items DROP CONSTRAINT %I',
      lifecycle_constraint_name
    );
  END IF;
END
$$;
"""

_ADD_NEW_LIFECYCLE_CHECK_SQL = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_constraint
     WHERE conrelid = 'news_items'::regclass
       AND conname = 'news_items_lifecycle_status_check'
  ) THEN
    ALTER TABLE news_items
      ADD CONSTRAINT news_items_lifecycle_status_check
      CHECK (
        lifecycle_status IN (
          'raw',
          'processing',
          'processed',
          'process_retryable',
          'process_terminal_failed'
        )
      );
  END IF;
END
$$;
"""

_ADD_OLD_LIFECYCLE_CHECK_SQL = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_constraint
     WHERE conrelid = 'news_items'::regclass
       AND conname = 'news_items_lifecycle_status_check'
  ) THEN
    ALTER TABLE news_items
      ADD CONSTRAINT news_items_lifecycle_status_check
      CHECK (lifecycle_status IN ('raw', 'processed', 'process_failed'));
  END IF;
END
$$;
"""

_CREATE_CLAIM_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_unprocessed_claim
  ON news_items(lifecycle_status, processing_next_due_at_ms, published_at_ms, news_item_id)
  WHERE lifecycle_status = 'raw'
     OR lifecycle_status = 'process_retryable'
"""

_CREATE_PROCESSING_LEASE_EXPIRY_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_processing_lease_expiry
  ON news_items(processing_leased_until_ms, news_item_id)
  WHERE lifecycle_status = 'processing'
"""

_CREATE_OLD_CLAIM_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_unprocessed_claim
  ON news_items(published_at_ms ASC, news_item_id ASC)
  WHERE lifecycle_status IN ('raw', 'process_failed')
     OR (
       lifecycle_status = 'processed'
       AND content_classification_json = '{}'::jsonb
     )
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS processing_lease_owner TEXT")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS processing_leased_until_ms BIGINT")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS processing_next_due_at_ms BIGINT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS processing_terminal_error TEXT")
    op.execute(_DROP_LEGACY_LIFECYCLE_CHECK_SQL)
    op.execute(
        """
        UPDATE news_items
           SET lifecycle_status = 'process_retryable',
               processing_lease_owner = NULL,
               processing_leased_until_ms = NULL,
               processing_next_due_at_ms = 0,
               processing_terminal_error = NULL
         WHERE lifecycle_status = 'process_failed'
        """
    )
    op.execute(
        """
        UPDATE news_items
           SET lifecycle_status = 'raw',
               processing_attempts = 0,
               processing_lease_owner = NULL,
               processing_leased_until_ms = NULL,
               processing_next_due_at_ms = 0,
               processing_error = NULL,
               processing_terminal_error = NULL,
               processed_at_ms = NULL
         WHERE lifecycle_status = 'processed'
           AND COALESCE(content_classification_json::text, '{}') = '{}'
        """
    )
    op.execute(_ADD_NEW_LIFECYCLE_CHECK_SQL)
    op.execute("ANALYZE news_items")

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_unprocessed_claim")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_processing_lease_expiry")
        op.execute(_CREATE_CLAIM_INDEX_SQL)
        op.execute(_CREATE_PROCESSING_LEASE_EXPIRY_INDEX_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute("ALTER TABLE news_items DROP CONSTRAINT IF EXISTS news_items_lifecycle_status_check")
    op.execute(
        """
        UPDATE news_items
           SET lifecycle_status = CASE
                 WHEN lifecycle_status = 'raw' THEN 'raw'
                 WHEN lifecycle_status = 'processed' THEN 'processed'
                 ELSE 'process_failed'
               END,
               processing_error = CASE
                 WHEN lifecycle_status = 'process_terminal_failed' THEN processing_terminal_error
                 ELSE processing_error
               END,
               processed_at_ms = CASE
                 WHEN lifecycle_status = 'processed' THEN processed_at_ms
                 ELSE NULL
               END
         WHERE lifecycle_status IN ('processing', 'process_retryable', 'process_terminal_failed')
            OR processing_lease_owner IS NOT NULL
            OR processing_leased_until_ms IS NOT NULL
            OR processing_terminal_error IS NOT NULL
        """
    )
    op.execute(_ADD_OLD_LIFECYCLE_CHECK_SQL)

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_unprocessed_claim")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_processing_lease_expiry")
        op.execute(_CREATE_OLD_CLAIM_INDEX_SQL)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")

    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS processing_terminal_error")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS processing_next_due_at_ms")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS processing_leased_until_ms")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS processing_lease_owner")
