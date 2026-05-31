"""Allow GMGN DEX quote market tick provider facts."""

from __future__ import annotations

from alembic import op

revision = "20260516_0047"
down_revision = "20260515_0046"
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
          CHECK (source_provider IN ('okx_dex_ws', 'okx_dex_rest', 'okx_cex_rest', 'gmgn_dex_quote'))
        """
    )


def downgrade() -> None:
    raise RuntimeError("20260516_0047 is not safely reversible while gmgn_dex_quote market tick facts may exist.")
