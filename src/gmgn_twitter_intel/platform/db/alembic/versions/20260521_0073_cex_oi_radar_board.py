"""Add Binance CEX OI radar board storage."""

from __future__ import annotations

from alembic import op

revision = "20260521_0073"
down_revision = "20260521_0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cex_derivative_series (
          series_id TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          exchange TEXT NOT NULL,
          native_market_id TEXT NOT NULL,
          base_symbol TEXT NOT NULL,
          quote_symbol TEXT NOT NULL,
          metric TEXT NOT NULL,
          period TEXT NOT NULL,
          observed_at_ms BIGINT NOT NULL,
          value_numeric NUMERIC,
          value_usd NUMERIC,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_cex_derivative_series_identity
          ON cex_derivative_series(provider, native_market_id, metric, period, observed_at_ms)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cex_oi_radar_runs (
          run_id TEXT PRIMARY KEY,
          provider TEXT NOT NULL,
          exchange TEXT NOT NULL,
          quote_symbol TEXT NOT NULL,
          contract_type TEXT NOT NULL,
          period TEXT NOT NULL,
          status TEXT NOT NULL,
          started_at_ms BIGINT NOT NULL,
          finished_at_ms BIGINT,
          universe_count BIGINT NOT NULL DEFAULT 0,
          processed_count BIGINT NOT NULL DEFAULT 0,
          failed_count BIGINT NOT NULL DEFAULT 0,
          notes_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_oi_radar_runs_latest
          ON cex_oi_radar_runs(provider, exchange, quote_symbol, contract_type, finished_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cex_oi_radar_rows (
          row_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL REFERENCES cex_oi_radar_runs(run_id) ON DELETE CASCADE,
          rank BIGINT NOT NULL,
          target_id TEXT NOT NULL,
          pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
          native_market_id TEXT NOT NULL,
          base_symbol TEXT NOT NULL,
          quote_symbol TEXT NOT NULL,
          open_interest_usd NUMERIC,
          open_interest_change_pct_1h NUMERIC,
          volume_24h_usd NUMERIC,
          funding_rate NUMERIC,
          mark_price NUMERIC,
          score NUMERIC NOT NULL,
          score_components_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          observed_at_ms BIGINT NOT NULL,
          computed_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_cex_oi_radar_rows_run_target
          ON cex_oi_radar_rows(run_id, target_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_oi_radar_rows_run_rank
          ON cex_oi_radar_rows(run_id, rank)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cex_oi_radar_rows_run_rank")
    op.execute("DROP INDEX IF EXISTS ux_cex_oi_radar_rows_run_target")
    op.execute("DROP TABLE IF EXISTS cex_oi_radar_rows")
    op.execute("DROP INDEX IF EXISTS idx_cex_oi_radar_runs_latest")
    op.execute("DROP TABLE IF EXISTS cex_oi_radar_runs")
    op.execute("DROP INDEX IF EXISTS ux_cex_derivative_series_identity")
    op.execute("DROP TABLE IF EXISTS cex_derivative_series")
