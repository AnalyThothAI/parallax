"""Add market tick current dirty target queue."""

from __future__ import annotations

from alembic import op

revision = "20260524_0095"
down_revision = "20260524_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS market_tick_current_dirty_targets (
          target_type TEXT NOT NULL CHECK (target_type IN ('chain_token', 'cex_symbol')),
          target_id TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          due_at_ms BIGINT NOT NULL,
          source_watermark_ms BIGINT NOT NULL DEFAULT 0,
          priority INTEGER NOT NULL DEFAULT 0,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (target_type, target_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE market_tick_current_dirty_targets SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_tick_current_dirty_due
          ON market_tick_current_dirty_targets(
            priority DESC,
            due_at_ms ASC,
            updated_at_ms ASC,
            target_type,
            target_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_market_tick_current_dirty_lease
          ON market_tick_current_dirty_targets(leased_until_ms, due_at_ms)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_market_tick_current_dirty_lease")
    op.execute("DROP INDEX IF EXISTS idx_market_tick_current_dirty_due")
    op.execute("DROP TABLE IF EXISTS market_tick_current_dirty_targets")
