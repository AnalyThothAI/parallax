"""Index stale running notification delivery cleanup."""

from __future__ import annotations

from alembic import op

revision = "20260612_0178"
down_revision = "20260612_0177"
branch_labels = None
depends_on = None


_CREATE_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notification_deliveries_running_stale
  ON notification_deliveries(updated_at_ms ASC, delivery_id ASC)
  WHERE status = 'running'
"""

_DROP_INDEX_SQL = "DROP INDEX CONCURRENTLY IF EXISTS idx_notification_deliveries_running_stale"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_CREATE_INDEX_SQL)
        op.execute("ANALYZE notification_deliveries")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(_DROP_INDEX_SQL)
