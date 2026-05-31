"""Add compact Token Radar rank source edge read model."""

from __future__ import annotations

from alembic import op

revision = "20260526_0106"
down_revision = "20260526_0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_rank_source_events (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          lane TEXT NOT NULL,
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_id TEXT NOT NULL,
          event_received_at_ms BIGINT NOT NULL,
          source_rank INTEGER NOT NULL DEFAULT 0,
          projected_at_ms BIGINT NOT NULL,
          intent_id TEXT NOT NULL,
          event_id TEXT NOT NULL,
          intent_key TEXT,
          construction_policy TEXT,
          primary_evidence_id TEXT,
          display_symbol TEXT,
          display_name TEXT,
          chain_hint TEXT,
          address_hint TEXT,
          intent_status TEXT,
          intent_created_at_ms BIGINT,
          intent_updated_at_ms BIGINT,
          resolution_id TEXT,
          target_type TEXT,
          target_id TEXT,
          pricefeed_id TEXT,
          resolution_status TEXT,
          reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          candidate_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          lookup_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          decision_time_ms BIGINT,
          author_handle TEXT,
          is_watched BOOLEAN NOT NULL DEFAULT false,
          text_fingerprint TEXT,
          post_quality_score INTEGER,
          post_informative BOOLEAN,
          post_has_market_context BOOLEAN,
          ws_author_followers BIGINT,
          gmgn_platform_followers BIGINT,
          gmgn_user_tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
          account_profile_first_seen_ms BIGINT,
          llm_direction_hint TEXT,
          llm_impact_hint DOUBLE PRECISION,
          llm_semantic_novelty_hint DOUBLE PRECISION,
          llm_label_confidence DOUBLE PRECISION,
          asset_chain_id TEXT,
          asset_token_standard TEXT,
          asset_address TEXT,
          asset_symbol TEXT,
          asset_name TEXT,
          asset_identity_confidence TEXT,
          asset_identity_reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
          asset_identity_conflict_count INTEGER NOT NULL DEFAULT 0,
          asset_registry_status TEXT,
          cex_base_symbol TEXT,
          cex_token_status TEXT,
          feed_type TEXT,
          pricefeed_provider TEXT,
          native_market_id TEXT,
          pricefeed_base_symbol TEXT,
          pricefeed_quote_symbol TEXT,
          pricefeed_status TEXT,
          first_price_observed_at_ms BIGINT,
          first_price_usd NUMERIC,
          first_price_quote NUMERIC,
          first_price_quote_symbol TEXT,
          first_price_basis TEXT,
          event_price_capture_id TEXT,
          event_price_capture_method TEXT,
          event_price_capture_reason TEXT,
          event_price_tick_lag_ms BIGINT,
          event_price_provider TEXT,
          event_price_source_tier TEXT,
          event_price_pricefeed_id TEXT,
          event_price_observed_at_ms BIGINT,
          event_price_received_at_ms BIGINT,
          event_price_usd NUMERIC,
          event_price_quote NUMERIC,
          event_price_quote_symbol TEXT,
          event_price_basis TEXT,
          event_price_market_cap_usd NUMERIC,
          event_price_liquidity_usd NUMERIC,
          event_price_volume_24h_usd NUMERIC,
          event_price_open_interest_usd NUMERIC,
          event_price_holders BIGINT,
          latest_price_tick_id TEXT,
          latest_price_provider TEXT,
          latest_price_source_tier TEXT,
          latest_price_pricefeed_id TEXT,
          latest_price_observed_at_ms BIGINT,
          latest_price_received_at_ms BIGINT,
          latest_price_usd NUMERIC,
          latest_price_quote NUMERIC,
          latest_price_quote_symbol TEXT,
          latest_price_basis TEXT,
          latest_price_market_cap_usd NUMERIC,
          latest_price_liquidity_usd NUMERIC,
          latest_price_volume_24h_usd NUMERIC,
          latest_price_open_interest_usd NUMERIC,
          latest_price_holders BIGINT,
          before_event_price_observed_at_ms BIGINT,
          before_event_price_usd NUMERIC,
          before_event_price_quote NUMERIC,
          before_event_price_quote_symbol TEXT,
          before_event_price_basis TEXT,
          first_seen_global_24h BOOLEAN NOT NULL DEFAULT false,
          PRIMARY KEY (
            projection_version,
            "window",
            scope,
            lane,
            target_type_key,
            identity_id,
            source_kind,
            source_id
          ),
          CHECK (source_kind IN ('event', 'intent', 'resolution'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_target
          ON token_radar_rank_source_events(
            projection_version,
            "window",
            scope,
            target_type_key,
            identity_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_source
          ON token_radar_rank_source_events(source_kind, source_id, event_received_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_recent
          ON token_radar_rank_source_events(
            projection_version,
            "window",
            scope,
            event_received_at_ms DESC
          )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rank_source_events_recent")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rank_source_events_source")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rank_source_events_target")
    op.execute("DROP TABLE IF EXISTS token_radar_rank_source_events")
