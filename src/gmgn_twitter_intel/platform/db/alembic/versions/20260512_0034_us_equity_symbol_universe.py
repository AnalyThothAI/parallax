"""Add US equity symbol universe for non-crypto cashtag classification."""

from __future__ import annotations

from alembic import op

revision = "20260512_0034"
down_revision = "20260512_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS us_equity_symbols (
          symbol TEXT PRIMARY KEY,
          market_instrument_id TEXT NOT NULL UNIQUE,
          exchange TEXT,
          security_name TEXT,
          instrument_type TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          source TEXT NOT NULL,
          source_updated_at_ms BIGINT NOT NULL,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_us_equity_symbols_active_lookup
          ON us_equity_symbols(symbol)
          WHERE status = 'active'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_us_equity_symbols_source_status
          ON us_equity_symbols(source, status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_us_equity_symbols_source_status")
    op.execute("DROP INDEX IF EXISTS idx_us_equity_symbols_active_lookup")
    op.execute("DROP TABLE IF EXISTS us_equity_symbols")
