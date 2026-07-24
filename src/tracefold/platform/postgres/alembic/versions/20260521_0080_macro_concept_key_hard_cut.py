"""Hard-cut macro observations to canonical concept keys."""

from __future__ import annotations

from alembic import op

revision = "20260521_0080"
down_revision = "20260521_0079"
branch_labels = None
depends_on = None


_CONCEPT_CASE = """
CASE series_key
  WHEN 'fred:WALCL' THEN 'liquidity:fed_assets'
  WHEN 'fred:WRBWFRBL' THEN 'liquidity:reserve_balances'
  WHEN 'fred:RRPONTSYD' THEN 'liquidity:on_rrp'
  WHEN 'nyfed:SOFR' THEN 'liquidity:sofr'
  WHEN 'treasury_fiscal:operating_cash_balance' THEN 'liquidity:tga'
  WHEN 'fred:DGS2' THEN 'rates:dgs2'
  WHEN 'fred:DGS5' THEN 'rates:dgs5'
  WHEN 'fred:DGS10' THEN 'rates:dgs10'
  WHEN 'fred:DGS30' THEN 'rates:dgs30'
  WHEN 'fred:T10Y2Y' THEN 'rates:10y2y'
  WHEN 'fred:T10Y3M' THEN 'rates:10y3m'
  WHEN 'fred:DFII10' THEN 'rates:real_10y'
  WHEN 'fred:T10YIE' THEN 'inflation:10y_breakeven'
  WHEN 'fred:T5YIFR' THEN 'inflation:5y5y_forward'
  WHEN 'fred:DFEDTARU' THEN 'fed:target_upper'
  WHEN 'fred:DFEDTARL' THEN 'fed:target_lower'
  WHEN 'fred:EFFR' THEN 'fed:effr'
  WHEN 'fred:IORB' THEN 'fed:iorb'
  WHEN 'fred:BAMLC0A0CM' THEN 'credit:ig_oas'
  WHEN 'fred:BAMLH0A0HYM2' THEN 'credit:hy_oas'
  WHEN 'fred:VIXCLS' THEN 'vol:vix'
  WHEN 'fred:SP500' THEN 'asset:spx'
  WHEN 'fred:DCOILWTICO' THEN 'commodity:wti'
  WHEN 'fred:DTWEXBGS' THEN 'fx:broad_dollar'
  WHEN 'stooq:spy.us' THEN 'asset:spy'
  WHEN 'stooq:qqq.us' THEN 'asset:qqq'
  WHEN 'stooq:iwm.us' THEN 'asset:iwm'
  WHEN 'stooq:tlt.us' THEN 'asset:tlt'
  WHEN 'stooq:hyg.us' THEN 'asset:hyg'
  WHEN 'stooq:lqd.us' THEN 'asset:lqd'
  WHEN 'stooq:gld.us' THEN 'asset:gld'
  WHEN 'stooq:uso.us' THEN 'asset:uso'
  WHEN 'stooq:btc.us' THEN 'crypto:btc'
  WHEN 'stooq:eth.us' THEN 'crypto:eth'
  WHEN 'stooq:dxy.us' THEN 'fx:dxy'
  WHEN 'yahoo:SPY' THEN 'asset:spy'
  WHEN 'yahoo:QQQ' THEN 'asset:qqq'
  WHEN 'yahoo:IWM' THEN 'asset:iwm'
  WHEN 'yahoo:TLT' THEN 'asset:tlt'
  WHEN 'yahoo:HYG' THEN 'asset:hyg'
  WHEN 'yahoo:LQD' THEN 'asset:lqd'
  WHEN 'yahoo:GLD' THEN 'asset:gld'
  WHEN 'yahoo:USO' THEN 'asset:uso'
  WHEN 'yahoo:DX-Y.NYB' THEN 'fx:dxy'
  WHEN 'yahoo:BTC-USD' THEN 'crypto:btc'
  WHEN 'yahoo:ETH-USD' THEN 'crypto:eth'
  WHEN 'cftc:financial_futures:sp500_net_noncommercial' THEN 'positioning:sp500_net_noncommercial'
END
"""


def upgrade() -> None:
    op.execute("ALTER TABLE macro_observations ADD COLUMN IF NOT EXISTS concept_key TEXT")
    op.execute("ALTER TABLE macro_observations ADD COLUMN IF NOT EXISTS source_priority INTEGER")
    op.execute(f"UPDATE macro_observations SET concept_key = {_CONCEPT_CASE} WHERE concept_key IS NULL")
    op.execute(
        """
        UPDATE macro_observations
        SET source_priority = CASE
          WHEN source_name = 'stooq' OR series_key LIKE 'stooq:%' THEN 10
          ELSE 100
        END
        WHERE source_priority IS NULL
          AND concept_key IS NOT NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_macro_observations_latest")
    op.execute("DROP INDEX IF EXISTS ux_macro_observations_identity")
    op.execute(
        """
        ALTER TABLE macro_observations
          ALTER COLUMN concept_key SET NOT NULL,
          ALTER COLUMN source_priority SET NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_observations_identity
          ON macro_observations(concept_key, observed_at, source_name, series_key)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_observations_latest
          ON macro_observations(concept_key, observed_at DESC, source_priority DESC, ingested_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_macro_observations_latest")
    op.execute("DROP INDEX IF EXISTS ux_macro_observations_identity")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_macro_observations_identity
          ON macro_observations(source_name, series_key, observed_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_observations_latest
          ON macro_observations(series_key, observed_at DESC, ingested_at_ms DESC)
        """
    )
    op.execute("ALTER TABLE macro_observations DROP COLUMN IF EXISTS source_priority")
    op.execute("ALTER TABLE macro_observations DROP COLUMN IF EXISTS concept_key")
