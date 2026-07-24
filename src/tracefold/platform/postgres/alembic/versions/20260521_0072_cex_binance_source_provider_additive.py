"""Switch new CEX market tick facts to Binance source provider."""

from __future__ import annotations

from alembic import op

revision = "20260521_0072"
down_revision = "20260521_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE market_ticks
          DROP CONSTRAINT IF EXISTS market_ticks_source_provider_check
        """
    )
    op.execute(
        """
        ALTER TABLE market_ticks
          ADD CONSTRAINT market_ticks_source_provider_check
          CHECK (source_provider IN ('okx_dex_ws', 'okx_dex_rest', 'binance_cex_rest', 'gmgn_dex_quote'))
          NOT VALID
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE market_ticks
          DROP CONSTRAINT IF EXISTS market_ticks_source_provider_check
        """
    )
    op.execute(
        """
        ALTER TABLE market_ticks
          ADD CONSTRAINT market_ticks_source_provider_check
          CHECK (source_provider IN ('okx_dex_ws', 'okx_dex_rest', 'okx_cex_rest', 'gmgn_dex_quote'))
          NOT VALID
        """
    )
