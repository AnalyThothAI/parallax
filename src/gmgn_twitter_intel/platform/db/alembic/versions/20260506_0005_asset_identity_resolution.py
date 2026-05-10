"""Add asset identity resolution tables."""

from __future__ import annotations

from alembic import op

revision = "20260506_0005"
down_revision = "20260506_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
          asset_id TEXT PRIMARY KEY,
          asset_type TEXT NOT NULL,
          canonical_symbol TEXT NOT NULL,
          display_name TEXT,
          identity_status TEXT NOT NULL,
          confidence DOUBLE PRECISION NOT NULL,
          primary_source TEXT NOT NULL,
          first_seen_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL,
          first_seen_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_assets_symbol_status
          ON assets(canonical_symbol, identity_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_assets_type_symbol
          ON assets(asset_type, canonical_symbol)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_aliases (
          alias_id TEXT PRIMARY KEY,
          asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
          alias_type TEXT NOT NULL,
          alias_value TEXT NOT NULL,
          normalized_alias TEXT NOT NULL,
          source TEXT NOT NULL,
          confidence DOUBLE PRECISION NOT NULL,
          created_at_ms BIGINT NOT NULL,
          UNIQUE(alias_type, normalized_alias, asset_id, source)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_aliases_lookup
          ON asset_aliases(normalized_alias, alias_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_aliases_asset
          ON asset_aliases(asset_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_venues (
          venue_id TEXT PRIMARY KEY,
          asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
          venue_type TEXT NOT NULL,
          provider TEXT NOT NULL,
          exchange TEXT,
          chain TEXT,
          address TEXT,
          inst_id TEXT,
          base_symbol TEXT,
          quote_symbol TEXT,
          inst_type TEXT,
          is_active BOOLEAN NOT NULL DEFAULT true,
          confidence DOUBLE PRECISION NOT NULL,
          source_payload_hash TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_asset_venues_dex_identity
          ON asset_venues(venue_type, chain, lower(address))
          WHERE venue_type = 'dex' AND chain IS NOT NULL AND address IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_asset_venues_cex_identity
          ON asset_venues(venue_type, exchange, inst_type, inst_id)
          WHERE venue_type = 'cex' AND exchange IS NOT NULL AND inst_type IS NOT NULL AND inst_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_venues_asset
          ON asset_venues(asset_id, is_active)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_mentions (
          mention_id TEXT PRIMARY KEY,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          mention_type TEXT NOT NULL,
          raw_value TEXT NOT NULL,
          normalized_symbol TEXT,
          chain_hint TEXT,
          address_hint TEXT,
          source_entity_id TEXT REFERENCES event_entities(entity_id) ON DELETE SET NULL,
          source TEXT NOT NULL,
          mention_confidence DOUBLE PRECISION NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_asset_mentions_event_identity
          ON asset_mentions(
            event_id,
            mention_type,
            COALESCE(normalized_symbol, ''),
            COALESCE(chain_hint, ''),
            COALESCE(lower(address_hint), ''),
            raw_value
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_mentions_symbol
          ON asset_mentions(normalized_symbol, mention_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_mentions_event
          ON asset_mentions(event_id)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_resolution_candidates (
          candidate_id TEXT PRIMARY KEY,
          mention_id TEXT NOT NULL REFERENCES asset_mentions(mention_id) ON DELETE CASCADE,
          asset_id TEXT REFERENCES assets(asset_id) ON DELETE SET NULL,
          venue_id TEXT REFERENCES asset_venues(venue_id) ON DELETE SET NULL,
          provider TEXT NOT NULL,
          candidate_kind TEXT NOT NULL,
          score DOUBLE PRECISION NOT NULL,
          decision TEXT NOT NULL,
          reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          risks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          raw_observation_id TEXT,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_resolution_candidates_mention
          ON asset_resolution_candidates(mention_id, score DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_attributions (
          attribution_id TEXT PRIMARY KEY,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          mention_id TEXT NOT NULL REFERENCES asset_mentions(mention_id) ON DELETE CASCADE,
          asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
          venue_id TEXT REFERENCES asset_venues(venue_id) ON DELETE SET NULL,
          attribution_status TEXT NOT NULL,
          attribution_weight DOUBLE PRECISION NOT NULL,
          confidence DOUBLE PRECISION NOT NULL,
          identity_status TEXT NOT NULL,
          reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          risks_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          decision_time_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_asset_attributions_mention_asset_venue
          ON asset_attributions(mention_id, asset_id, COALESCE(venue_id, ''))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_attributions_event
          ON asset_attributions(event_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_attributions_asset_time
          ON asset_attributions(asset_id, decision_time_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_attributions_status
          ON asset_attributions(attribution_status, identity_status)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_market_snapshots (
          snapshot_id TEXT PRIMARY KEY,
          asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
          venue_id TEXT NOT NULL REFERENCES asset_venues(venue_id) ON DELETE CASCADE,
          provider TEXT NOT NULL,
          observed_at_ms BIGINT NOT NULL,
          price_usd DOUBLE PRECISION,
          market_cap_usd DOUBLE PRECISION,
          liquidity_usd DOUBLE PRECISION,
          volume_24h_usd DOUBLE PRECISION,
          open_interest_usd DOUBLE PRECISION,
          holders BIGINT,
          price_change_5m_pct DOUBLE PRECISION,
          price_change_1h_pct DOUBLE PRECISION,
          price_change_24h_pct DOUBLE PRECISION,
          source_payload_hash TEXT,
          raw_observation_id TEXT,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_market_snapshots_latest
          ON asset_market_snapshots(asset_id, venue_id, observed_at_ms DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_resolution_jobs (
          job_id TEXT PRIMARY KEY,
          job_type TEXT NOT NULL,
          normalized_symbol TEXT,
          chain_hint TEXT,
          address_hint TEXT,
          status TEXT NOT NULL,
          attempt_count BIGINT NOT NULL DEFAULT 0,
          next_run_at_ms BIGINT NOT NULL,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_resolution_jobs_claim
          ON asset_resolution_jobs(status, next_run_at_ms ASC, job_id ASC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_attention_buckets (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          bucket_start_ms BIGINT NOT NULL,
          bucket_size_ms BIGINT NOT NULL,
          asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
          symbol TEXT NOT NULL,
          identity_status TEXT NOT NULL,
          post_count BIGINT NOT NULL DEFAULT 0,
          watched_post_count BIGINT NOT NULL DEFAULT 0,
          unique_author_count BIGINT NOT NULL DEFAULT 0,
          attribution_weight_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
          first_seen_ms BIGINT,
          latest_seen_ms BIGINT,
          top_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          top_authors_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, "window", scope, bucket_start_ms, asset_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_attention_buckets_window
          ON asset_attention_buckets(projection_version, "window", scope, bucket_start_ms DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_attention_bucket_authors (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          bucket_start_ms BIGINT NOT NULL,
          asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
          author_handle TEXT NOT NULL,
          post_count BIGINT NOT NULL DEFAULT 0,
          watched_post_count BIGINT NOT NULL DEFAULT 0,
          followers_max BIGINT,
          first_seen_ms BIGINT,
          latest_seen_ms BIGINT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, "window", scope, bucket_start_ms, asset_id, author_handle)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_attention_bucket_authors_asset
          ON asset_attention_bucket_authors(projection_version, "window", scope, asset_id, bucket_start_ms DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_flow_window_snapshots (
          snapshot_id TEXT PRIMARY KEY,
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          decision_time_ms BIGINT NOT NULL,
          lane TEXT NOT NULL,
          rank BIGINT NOT NULL,
          asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
          asset_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          primary_venue_json JSONB,
          attention_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          resolution_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          market_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          data_health_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          source_max_received_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          UNIQUE(projection_version, "window", scope, lane, decision_time_ms, rank)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_flow_window_snapshots_latest
          ON asset_flow_window_snapshots(projection_version, "window", scope, lane, decision_time_ms DESC, rank ASC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_asset_flow_window_snapshots_latest")
    op.execute("DROP TABLE IF EXISTS asset_flow_window_snapshots")
    op.execute("DROP INDEX IF EXISTS idx_asset_attention_bucket_authors_asset")
    op.execute("DROP TABLE IF EXISTS asset_attention_bucket_authors")
    op.execute("DROP INDEX IF EXISTS idx_asset_attention_buckets_window")
    op.execute("DROP TABLE IF EXISTS asset_attention_buckets")
    op.execute("DROP INDEX IF EXISTS idx_asset_resolution_jobs_claim")
    op.execute("DROP TABLE IF EXISTS asset_resolution_jobs")
    op.execute("DROP INDEX IF EXISTS idx_asset_market_snapshots_latest")
    op.execute("DROP TABLE IF EXISTS asset_market_snapshots")
    op.execute("DROP INDEX IF EXISTS idx_asset_attributions_status")
    op.execute("DROP INDEX IF EXISTS idx_asset_attributions_asset_time")
    op.execute("DROP INDEX IF EXISTS idx_asset_attributions_event")
    op.execute("DROP INDEX IF EXISTS ux_asset_attributions_mention_asset_venue")
    op.execute("DROP TABLE IF EXISTS asset_attributions")
    op.execute("DROP INDEX IF EXISTS idx_asset_resolution_candidates_mention")
    op.execute("DROP TABLE IF EXISTS asset_resolution_candidates")
    op.execute("DROP INDEX IF EXISTS idx_asset_mentions_event")
    op.execute("DROP INDEX IF EXISTS idx_asset_mentions_symbol")
    op.execute("DROP INDEX IF EXISTS ux_asset_mentions_event_identity")
    op.execute("DROP TABLE IF EXISTS asset_mentions")
    op.execute("DROP INDEX IF EXISTS idx_asset_venues_asset")
    op.execute("DROP INDEX IF EXISTS ux_asset_venues_cex_identity")
    op.execute("DROP INDEX IF EXISTS ux_asset_venues_dex_identity")
    op.execute("DROP TABLE IF EXISTS asset_venues")
    op.execute("DROP INDEX IF EXISTS idx_asset_aliases_asset")
    op.execute("DROP INDEX IF EXISTS idx_asset_aliases_lookup")
    op.execute("DROP TABLE IF EXISTS asset_aliases")
    op.execute("DROP INDEX IF EXISTS idx_assets_type_symbol")
    op.execute("DROP INDEX IF EXISTS idx_assets_symbol_status")
    op.execute("DROP TABLE IF EXISTS assets")
