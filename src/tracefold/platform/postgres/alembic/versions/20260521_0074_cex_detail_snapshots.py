"""Add CEX detail snapshot read model."""

from __future__ import annotations

from alembic import op

revision = "20260521_0074"
down_revision = "20260521_0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cex_detail_snapshots (
          snapshot_id TEXT PRIMARY KEY,
          target_type TEXT NOT NULL DEFAULT 'CexToken',
          target_id TEXT NOT NULL,
          exchange TEXT NOT NULL DEFAULT 'binance',
          native_market_id TEXT NOT NULL,
          base_symbol TEXT NOT NULL,
          quote_symbol TEXT NOT NULL DEFAULT 'USDT',
          status TEXT NOT NULL,
          baseline_status TEXT NOT NULL,
          coinglass_status TEXT NOT NULL,
          price_usd NUMERIC,
          mark_price NUMERIC,
          funding_rate NUMERIC,
          volume_24h_usd NUMERIC,
          open_interest_usd NUMERIC,
          oi_change_pct_1h NUMERIC,
          oi_change_pct_4h NUMERIC,
          oi_change_pct_24h NUMERIC,
          cvd_delta_1h NUMERIC,
          cvd_delta_4h NUMERIC,
          cvd_delta_24h NUMERIC,
          long_short_ratio NUMERIC,
          top_trader_position_ratio NUMERIC,
          level_bands_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          degraded_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          observed_at_ms BIGINT,
          computed_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_cex_detail_snapshots_market
          ON cex_detail_snapshots(exchange, native_market_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_detail_snapshots_target
          ON cex_detail_snapshots(target_type, target_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_detail_snapshots_computed_at
          ON cex_detail_snapshots(computed_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cex_detail_snapshots_computed_at")
    op.execute("DROP INDEX IF EXISTS idx_cex_detail_snapshots_target")
    op.execute("DROP INDEX IF EXISTS ux_cex_detail_snapshots_market")
    op.execute("DROP TABLE IF EXISTS cex_detail_snapshots")
