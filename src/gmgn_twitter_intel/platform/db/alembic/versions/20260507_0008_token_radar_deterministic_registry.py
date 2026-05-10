"""Add token radar deterministic registry and price observations."""

from __future__ import annotations

from alembic import op

revision = "20260507_0008"
down_revision = "20260507_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
          project_id TEXT PRIMARY KEY,
          canonical_symbol TEXT,
          display_name TEXT,
          status TEXT NOT NULL,
          evidence_level TEXT NOT NULL,
          primary_source TEXT NOT NULL,
          first_seen_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS registry_assets (
          asset_id TEXT PRIMARY KEY,
          project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
          chain_id TEXT NOT NULL,
          token_standard TEXT NOT NULL,
          address TEXT NOT NULL,
          symbol TEXT,
          name TEXT,
          decimals BIGINT,
          status TEXT NOT NULL,
          evidence_level TEXT NOT NULL,
          primary_source TEXT NOT NULL,
          first_seen_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cex_tokens (
          cex_token_id TEXT PRIMARY KEY,
          project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
          base_symbol TEXT NOT NULL,
          status TEXT NOT NULL,
          evidence_level TEXT NOT NULL,
          first_seen_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS price_feeds (
          pricefeed_id TEXT PRIMARY KEY,
          feed_type TEXT NOT NULL,
          provider TEXT NOT NULL,
          subject_type TEXT NOT NULL,
          subject_id TEXT NOT NULL,
          chain_id TEXT,
          address TEXT,
          native_market_id TEXT,
          base_asset_id TEXT REFERENCES registry_assets(asset_id) ON DELETE SET NULL,
          base_cex_token_id TEXT REFERENCES cex_tokens(cex_token_id) ON DELETE SET NULL,
          base_project_id TEXT REFERENCES projects(project_id) ON DELETE SET NULL,
          base_symbol TEXT,
          quote_symbol TEXT,
          multiplier NUMERIC,
          status TEXT NOT NULL,
          evidence_level TEXT NOT NULL,
          first_seen_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS registry_aliases (
          alias_id TEXT PRIMARY KEY,
          alias_norm TEXT NOT NULL,
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          source TEXT NOT NULL,
          priority BIGINT NOT NULL,
          status TEXT NOT NULL,
          valid_from_ms BIGINT NOT NULL,
          valid_to_ms BIGINT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS price_observations (
          observation_id TEXT PRIMARY KEY,
          pricefeed_id TEXT REFERENCES price_feeds(pricefeed_id) ON DELETE SET NULL,
          provider TEXT NOT NULL,
          observed_at_ms BIGINT NOT NULL,
          subject_type TEXT NOT NULL,
          subject_id TEXT NOT NULL,
          price_usd NUMERIC,
          price_quote NUMERIC,
          quote_symbol TEXT,
          price_basis TEXT NOT NULL DEFAULT 'unavailable',
          market_cap_usd NUMERIC,
          liquidity_usd NUMERIC,
          volume_24h_usd NUMERIC,
          open_interest_usd NUMERIC,
          holders BIGINT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_tasks (
          task_id TEXT PRIMARY KEY,
          task_type TEXT NOT NULL,
          query_key TEXT NOT NULL,
          payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          status TEXT NOT NULL,
          attempt_count BIGINT NOT NULL DEFAULT 0,
          last_error TEXT,
          next_run_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          UNIQUE(task_type, query_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS registry_versions (
          version_id TEXT PRIMARY KEY,
          source TEXT NOT NULL,
          changed_target_type TEXT NOT NULL,
          changed_target_id TEXT NOT NULL,
          affected_lookup_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          changed_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_intent_lookup_keys (
          lookup_key TEXT NOT NULL,
          intent_id TEXT NOT NULL REFERENCES token_intents(intent_id) ON DELETE CASCADE,
          event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
          source_evidence_id TEXT REFERENCES token_evidence(evidence_id) ON DELETE SET NULL,
          created_at_ms BIGINT NOT NULL,
          PRIMARY KEY(lookup_key, intent_id)
        )
        """
    )
    op.execute("ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS target_type TEXT")
    op.execute("ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS target_id TEXT")
    op.execute("ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS pricefeed_id TEXT")
    op.execute(
        "ALTER TABLE token_intent_resolutions "
        "ADD COLUMN IF NOT EXISTS reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE token_intent_resolutions "
        "ADD COLUMN IF NOT EXISTS candidate_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE token_intent_resolutions "
        "ADD COLUMN IF NOT EXISTS lookup_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS registry_version TEXT")
    op.execute(
        "ALTER TABLE token_intent_resolutions "
        "ADD COLUMN IF NOT EXISTS record_status TEXT NOT NULL DEFAULT 'current'"
    )
    op.execute("ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS is_current BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE token_intent_resolutions ADD COLUMN IF NOT EXISTS superseded_at_ms BIGINT")
    op.execute("ALTER TABLE token_intent_resolutions ALTER COLUMN asset_id DROP NOT NULL")
    op.execute("ALTER TABLE token_intent_resolutions ALTER COLUMN primary_venue_id DROP NOT NULL")
    op.execute("ALTER TABLE token_intent_resolutions ALTER COLUMN identity_status DROP NOT NULL")
    op.execute("ALTER TABLE token_intent_resolutions ALTER COLUMN confidence DROP NOT NULL")
    op.execute("ALTER TABLE token_intent_resolutions ALTER COLUMN resolver_policy_version DROP NOT NULL")
    op.execute("DROP INDEX IF EXISTS ux_token_intent_active_resolution")
    op.execute("ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS target_type TEXT")
    op.execute("ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS target_id TEXT")
    op.execute("ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS pricefeed_id TEXT")
    op.execute("ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS target_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS price_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_registry_assets_identity "
        "ON registry_assets(chain_id, lower(address))"
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_cex_tokens_identity ON cex_tokens(base_symbol)")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_price_feeds_native_identity
          ON price_feeds(provider, feed_type, native_market_id)
          WHERE native_market_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_price_feeds_token_identity
          ON price_feeds(provider, feed_type, chain_id, lower(address))
          WHERE address IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_registry_aliases_identity
          ON registry_aliases(alias_norm, target_type, target_id, source)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_token_intent_current_resolution
          ON token_intent_resolutions(intent_id)
          WHERE is_current = true
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_intent_lookup_keys_lookup ON token_intent_lookup_keys(lookup_key)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_intent_resolutions_target_current
          ON token_intent_resolutions(target_type, target_id, decision_time_ms DESC)
          WHERE is_current = true
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_price_observations_feed_latest
          ON price_observations(pricefeed_id, observed_at_ms DESC)
          WHERE pricefeed_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_price_observations_subject_latest
          ON price_observations(subject_type, subject_id, observed_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_price_observations_subject_latest")
    op.execute("DROP INDEX IF EXISTS idx_price_observations_feed_latest")
    op.execute("DROP INDEX IF EXISTS idx_token_intent_resolutions_target_current")
    op.execute("DROP INDEX IF EXISTS idx_token_intent_lookup_keys_lookup")
    op.execute("DROP INDEX IF EXISTS ux_token_intent_current_resolution")
    op.execute("DROP INDEX IF EXISTS ux_registry_aliases_identity")
    op.execute("DROP INDEX IF EXISTS ux_price_feeds_token_identity")
    op.execute("DROP INDEX IF EXISTS ux_price_feeds_native_identity")
    op.execute("DROP INDEX IF EXISTS ux_cex_tokens_identity")
    op.execute("DROP INDEX IF EXISTS ux_registry_assets_identity")
    op.execute("DROP TABLE IF EXISTS token_intent_lookup_keys")
    op.execute("DROP TABLE IF EXISTS registry_versions")
    op.execute("DROP TABLE IF EXISTS discovery_tasks")
    op.execute("DROP TABLE IF EXISTS price_observations")
    op.execute("DROP TABLE IF EXISTS registry_aliases")
    op.execute("DROP TABLE IF EXISTS price_feeds")
    op.execute("DROP TABLE IF EXISTS cex_tokens")
    op.execute("DROP TABLE IF EXISTS registry_assets")
    op.execute("DROP TABLE IF EXISTS projects")
