"""Add token discovery dirty lookup queue."""

from __future__ import annotations

from alembic import op

revision = "20260525_0096"
down_revision = "20260524_0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_discovery_dirty_lookup_keys (
          provider TEXT NOT NULL,
          lookup_key TEXT NOT NULL,
          lookup_type TEXT NOT NULL CHECK (lookup_type IN ('dex_symbol_lookup', 'address_lookup')),
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          due_at_ms BIGINT NOT NULL,
          latest_seen_ms BIGINT NOT NULL DEFAULT 0,
          intent_count BIGINT NOT NULL DEFAULT 0,
          refresh_priority INTEGER NOT NULL DEFAULT 9,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY (provider, lookup_key)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE token_discovery_dirty_lookup_keys SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_discovery_dirty_due
          ON token_discovery_dirty_lookup_keys(
            provider,
            refresh_priority ASC,
            due_at_ms ASC,
            latest_seen_ms DESC,
            updated_at_ms ASC,
            lookup_key ASC
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_discovery_dirty_lease
          ON token_discovery_dirty_lookup_keys(provider, leased_until_ms, due_at_ms)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_discovery_dirty_lease")
    op.execute("DROP INDEX IF EXISTS idx_token_discovery_dirty_due")
    op.execute("DROP TABLE IF EXISTS token_discovery_dirty_lookup_keys")
