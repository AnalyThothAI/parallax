"""Add event indexes for batched recent payload hydration."""

from __future__ import annotations

from alembic import op

revision = "20260517_0056"
down_revision = "20260517_0055"
branch_labels = None
depends_on = None


INDEXES = (
    "idx_attention_seeds_event",
    "idx_event_clusters_event_seen",
)


def upgrade() -> None:
    for index_name in INDEXES:
        _drop_invalid_index(index_name)
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_attention_seeds_event
              ON attention_seeds(event_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_event_clusters_event_seen
              ON event_clusters(event_id, first_seen_at_ms DESC)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_event_clusters_event_seen")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_attention_seeds_event")


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
