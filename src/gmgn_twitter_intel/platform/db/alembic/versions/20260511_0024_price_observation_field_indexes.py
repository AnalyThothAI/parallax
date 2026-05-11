"""Add field-aware price observation indexes and radar coverage."""

from __future__ import annotations

from alembic import op

revision = "20260511_0024"
down_revision = "20260510_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_projection_coverage (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          status TEXT NOT NULL,
          reason TEXT,
          source_rows BIGINT NOT NULL DEFAULT 0,
          row_count BIGINT NOT NULL DEFAULT 0,
          computed_at_ms BIGINT,
          started_at_ms BIGINT,
          finished_at_ms BIGINT,
          error TEXT,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, "window", scope)
        )
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_price
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_price', 'okx_dex_ws_price_info', 'okx_cex')
              AND (price_usd IS NOT NULL OR price_quote IS NOT NULL)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_market_cap
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_ws_price_info')
              AND market_cap_usd IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_liquidity
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_ws_price_info')
              AND liquidity_usd IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_holders
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('gmgn_payload', 'okx_dex_search', 'okx_dex_ws_price_info')
              AND holders IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_volume_24h
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider IN ('okx_cex', 'gmgn_payload', 'okx_dex_search', 'okx_dex_ws_price_info')
              AND volume_24h_usd IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_current_open_interest
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE provider = 'okx_cex'
              AND open_interest_usd IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_subject_first
            ON price_observations(subject_type, subject_id, observed_at_ms ASC, observation_id ASC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_message_resolution_latest
            ON price_observations(
              source_resolution_id, subject_type, subject_id, observation_kind, observed_at_ms DESC, observation_id DESC
            )
            WHERE observation_kind IN ('message_payload', 'message_quote')
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_message_resolution_latest")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_subject_first")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_open_interest")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_volume_24h")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_holders")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_liquidity")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_market_cap")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_current_price")
    op.execute("DROP TABLE IF EXISTS token_radar_projection_coverage")
