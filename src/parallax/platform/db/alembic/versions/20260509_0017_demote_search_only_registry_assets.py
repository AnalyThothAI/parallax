"""Demote unretained OKX DEX search-only registry assets."""

from __future__ import annotations

from alembic import op

revision = "20260509_0017"
down_revision = "20260509_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH latest_price AS (
          SELECT DISTINCT ON (subject_id)
            subject_id,
            price_usd,
            market_cap_usd,
            liquidity_usd,
            holders,
            observed_at_ms
          FROM price_observations
          WHERE subject_type = 'Asset'
          ORDER BY subject_id, observed_at_ms DESC, observation_id DESC
        ),
        protected_assets(asset_id) AS (
          SELECT target_id
          FROM token_intent_resolutions
          WHERE is_current = true
            AND record_status = 'current'
            AND target_type = 'Asset'
            AND target_id IS NOT NULL
          UNION
          SELECT jsonb_array_elements_text(candidate_ids_json)
          FROM token_intent_resolutions
          WHERE is_current = true
            AND record_status = 'current'
            AND candidate_ids_json IS NOT NULL
        ),
        ranked_search_assets AS (
          SELECT
            registry_assets.asset_id,
            ROW_NUMBER() OVER (
              PARTITION BY registry_assets.symbol, registry_assets.chain_id
              ORDER BY
                (
                  0.5 * log(GREATEST(COALESCE(latest_price.market_cap_usd, 0)::double precision, 0.0) + 1.0)
                  + 0.3 * log(GREATEST(COALESCE(latest_price.liquidity_usd, 0)::double precision, 0.0) + 1.0)
                  + 0.2 * log(GREATEST(COALESCE(latest_price.holders, 0)::double precision, 0.0) + 1.0)
                ) DESC,
                (latest_price.price_usd IS NOT NULL) DESC,
                registry_assets.updated_at_ms DESC,
                registry_assets.asset_id ASC
            ) AS chain_symbol_rank
          FROM registry_assets
          LEFT JOIN latest_price ON latest_price.subject_id = registry_assets.asset_id
          WHERE registry_assets.primary_source = 'okx_dex_search'
            AND registry_assets.status = 'candidate'
            AND registry_assets.symbol IS NOT NULL
        ),
        demotion_targets AS (
          SELECT ranked_search_assets.asset_id
          FROM ranked_search_assets
          WHERE ranked_search_assets.chain_symbol_rank > 3
            AND NOT EXISTS (
              SELECT 1
              FROM protected_assets
              WHERE protected_assets.asset_id = ranked_search_assets.asset_id
            )
        )
        UPDATE registry_assets
        SET status = 'demoted_search'
        WHERE registry_assets.asset_id IN (
          SELECT asset_id
          FROM demotion_targets
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE registry_assets
        SET status = 'candidate'
        WHERE status = 'demoted_search'
          AND primary_source = 'okx_dex_search'
        """
    )
