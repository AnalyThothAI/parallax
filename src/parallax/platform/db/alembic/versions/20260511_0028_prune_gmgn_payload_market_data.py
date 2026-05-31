"""Hard-cut GMGN payload market data."""

from __future__ import annotations

from alembic import op

revision = "20260511_0028"
down_revision = "20260511_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM current_market_field_facts WHERE provider = 'gmgn_payload'")
    op.execute(
        """
        DELETE FROM token_market_price_baselines
        WHERE event_price_provider = 'gmgn_payload'
           OR event_price_observation_kind = 'message_payload'
        """
    )
    op.execute(
        """
        DELETE FROM price_observations
        WHERE provider = 'gmgn_payload'
           OR observation_kind = 'message_payload'
        """
    )
    op.execute("DELETE FROM price_feeds WHERE provider = 'gmgn_payload'")
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_price")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_market_cap")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_liquidity")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_holders")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_volume_24h")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_message_resolution_latest")
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_price
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('okx_dex_search', 'okx_dex_price', 'okx_dex_ws_price_info', 'okx_cex')
              AND (price_usd IS NOT NULL OR price_quote IS NOT NULL)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_market_cap
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('okx_dex_search', 'okx_dex_ws_price_info')
              AND market_cap_usd IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_liquidity
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('okx_dex_search', 'okx_dex_ws_price_info')
              AND liquidity_usd IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_holders
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('okx_dex_search', 'okx_dex_ws_price_info')
              AND holders IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_volume_24h
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('okx_cex', 'okx_dex_search', 'okx_dex_ws_price_info')
              AND volume_24h_usd IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_message_resolution_latest
            ON price_observations(
              source_resolution_id, subject_type, subject_id, observation_kind, observed_at_ms DESC, observation_id DESC
            )
            WHERE observation_kind = 'message_quote'
            """
        )


def downgrade() -> None:
    pass
