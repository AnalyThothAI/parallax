"""Add indexed public read path lookups."""

from __future__ import annotations

from alembic import op

revision = "20260517_0055"
down_revision = "20260517_0054"
branch_labels = None
depends_on = None


INDEXES = (
    "idx_token_intent_resolutions_public_event_current",
    "idx_price_feeds_cex_subject_preferred",
)


def upgrade() -> None:
    for index_name in INDEXES:
        _drop_invalid_index(index_name)
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_intent_resolutions_public_event_current
              ON token_intent_resolutions(event_id, decision_time_ms, resolution_id)
              WHERE is_current = true
                AND target_type IN ('Asset', 'CexToken')
                AND target_id IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_feeds_cex_subject_preferred
              ON price_feeds(
                subject_type,
                subject_id,
                feed_type,
                status,
                updated_at_ms DESC,
                native_market_id
              )
              WHERE subject_type = 'CexToken'
                AND status IN ('candidate', 'canonical')
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_feeds_cex_subject_preferred")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_intent_resolutions_public_event_current")


def _drop_invalid_index(index_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM pg_class cls
            JOIN pg_namespace ns ON ns.oid = cls.relnamespace
            JOIN pg_index idx ON idx.indexrelid = cls.oid
            WHERE ns.nspname = 'public'
              AND cls.relname = '{index_name}'
              AND idx.indisvalid = false
          ) THEN
            EXECUTE 'DROP INDEX IF EXISTS public.{index_name}';
          END IF;
        END $$;
        """
    )
