"""Add asset identity evidence ledger and current identity read model."""

from __future__ import annotations

from alembic import op

revision = "20260510_0021"
down_revision = "20260509_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_identity_evidence (
          evidence_id TEXT PRIMARY KEY,
          asset_id TEXT NOT NULL REFERENCES registry_assets(asset_id) ON DELETE CASCADE,
          evidence_kind TEXT NOT NULL,
          provider TEXT NOT NULL,
          lookup_mode TEXT NOT NULL,
          chain_id TEXT NOT NULL,
          address TEXT NOT NULL,
          symbol TEXT,
          name TEXT,
          decimals BIGINT,
          confidence TEXT NOT NULL,
          source_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL,
          source_intent_id TEXT REFERENCES token_intents(intent_id) ON DELETE SET NULL,
          source_resolution_id TEXT REFERENCES token_intent_resolutions(resolution_id) ON DELETE SET NULL,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          observed_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_identity_current (
          asset_id TEXT PRIMARY KEY REFERENCES registry_assets(asset_id) ON DELETE CASCADE,
          canonical_symbol TEXT,
          canonical_name TEXT,
          decimals BIGINT,
          identity_confidence TEXT NOT NULL,
          selected_evidence_id TEXT REFERENCES asset_identity_evidence(evidence_id) ON DELETE SET NULL,
          selection_reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          conflict_count BIGINT NOT NULL DEFAULT 0,
          verified_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_asset_identity_evidence_asset ON asset_identity_evidence(asset_id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_identity_evidence_kind_time
          ON asset_identity_evidence(evidence_kind, observed_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_identity_evidence_provider_lookup
          ON asset_identity_evidence(provider, lookup_mode, observed_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_identity_current_confidence
          ON asset_identity_current(identity_confidence)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_identity_current_symbol
          ON asset_identity_current(canonical_symbol)
          WHERE canonical_symbol IS NOT NULL
        """
    )

    # One-time conversion from the legacy registry identity columns. Runtime code
    # must write explicit identity evidence and must not keep this mapping.
    op.execute(
        """
        INSERT INTO asset_identity_evidence(
          evidence_id, asset_id, evidence_kind, provider, lookup_mode, chain_id, address,
          symbol, name, decimals, confidence, raw_payload_json, observed_at_ms, created_at_ms, updated_at_ms
        )
        SELECT
          'legacy-registry-identity:' || md5(
            registry_assets.asset_id || '|' || registry_assets.primary_source || '|' ||
            COALESCE(registry_assets.symbol, '') || '|' || COALESCE(registry_assets.name, '')
          ) AS evidence_id,
          registry_assets.asset_id,
          CASE registry_assets.primary_source
            WHEN 'tweet_ca' THEN 'tweet_contract_mention'
            WHEN 'gmgn_payload' THEN 'gmgn_payload_exact'
            WHEN 'gmgn_token_payload' THEN 'gmgn_payload_exact'
            WHEN 'gmgn_openapi' THEN 'gmgn_openapi_exact'
            WHEN 'okx_dex_address_search' THEN 'okx_dex_exact_address'
            WHEN 'okx_dex_search' THEN 'okx_dex_symbol_candidate'
            ELSE 'legacy_registry_identity'
          END AS evidence_kind,
          CASE
            WHEN registry_assets.primary_source LIKE 'gmgn%' THEN 'gmgn'
            WHEN registry_assets.primary_source LIKE 'okx%' THEN 'okx'
            WHEN registry_assets.primary_source = 'tweet_ca' THEN 'twitter'
            ELSE registry_assets.primary_source
          END AS provider,
          CASE registry_assets.primary_source
            WHEN 'tweet_ca' THEN 'tweet_mention'
            WHEN 'okx_dex_address_search' THEN 'exact_address'
            WHEN 'okx_dex_search' THEN 'symbol_search'
            WHEN 'gmgn_payload' THEN 'provider_payload'
            WHEN 'gmgn_token_payload' THEN 'provider_payload'
            WHEN 'gmgn_openapi' THEN 'exact_address'
            ELSE 'legacy_registry'
          END AS lookup_mode,
          registry_assets.chain_id,
          registry_assets.address,
          registry_assets.symbol,
          registry_assets.name,
          registry_assets.decimals,
          CASE registry_assets.primary_source
            WHEN 'tweet_ca' THEN 'mention_only'
            WHEN 'okx_dex_search' THEN 'provider_candidate'
            WHEN 'okx_dex_address_search' THEN 'provider_exact'
            WHEN 'gmgn_payload' THEN 'provider_exact'
            WHEN 'gmgn_token_payload' THEN 'provider_exact'
            WHEN 'gmgn_openapi' THEN 'provider_exact'
            ELSE 'unknown'
          END AS confidence,
          jsonb_build_object('legacy_primary_source', registry_assets.primary_source),
          registry_assets.updated_at_ms,
          registry_assets.first_seen_at_ms,
          registry_assets.updated_at_ms
        FROM registry_assets
        WHERE registry_assets.symbol IS NOT NULL OR registry_assets.name IS NOT NULL
        ON CONFLICT(evidence_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO asset_identity_current(
          asset_id, canonical_symbol, canonical_name, decimals, identity_confidence,
          selected_evidence_id, selection_reason_codes_json, conflict_count, verified_at_ms, updated_at_ms
        )
        SELECT DISTINCT ON (asset_identity_evidence.asset_id)
          asset_identity_evidence.asset_id,
          asset_identity_evidence.symbol,
          asset_identity_evidence.name,
          asset_identity_evidence.decimals,
          asset_identity_evidence.confidence,
          asset_identity_evidence.evidence_id,
          jsonb_build_array(
            CASE asset_identity_evidence.confidence
              WHEN 'provider_exact' THEN 'SELECTED_PROVIDER_EXACT'
              WHEN 'provider_candidate' THEN 'SELECTED_PROVIDER_CANDIDATE'
              WHEN 'mention_only' THEN 'MENTION_ONLY_IDENTITY'
              ELSE 'SELECTED_UNKNOWN_IDENTITY'
            END
          ),
          0,
          asset_identity_evidence.observed_at_ms,
          asset_identity_evidence.updated_at_ms
        FROM asset_identity_evidence
        ORDER BY
          asset_identity_evidence.asset_id,
          CASE asset_identity_evidence.evidence_kind
            WHEN 'manual_identity_repair' THEN 0
            WHEN 'gmgn_openapi_exact' THEN 1
            WHEN 'gmgn_payload_exact' THEN 2
            WHEN 'okx_dex_exact_address' THEN 3
            WHEN 'okx_cex_instrument' THEN 4
            WHEN 'okx_dex_symbol_candidate' THEN 5
            WHEN 'tweet_contract_mention' THEN 6
            ELSE 99
          END,
          asset_identity_evidence.observed_at_ms DESC,
          asset_identity_evidence.evidence_id
        ON CONFLICT(asset_id) DO NOTHING
        """
    )
    op.execute("ALTER TABLE registry_assets DROP COLUMN IF EXISTS symbol")
    op.execute("ALTER TABLE registry_assets DROP COLUMN IF EXISTS name")
    op.execute("ALTER TABLE registry_assets DROP COLUMN IF EXISTS decimals")
    op.execute("ALTER TABLE registry_assets DROP COLUMN IF EXISTS primary_source")
    op.execute("ALTER TABLE registry_assets DROP COLUMN IF EXISTS evidence_level")


def downgrade() -> None:
    op.execute("ALTER TABLE registry_assets ADD COLUMN IF NOT EXISTS evidence_level TEXT")
    op.execute("UPDATE registry_assets SET evidence_level = 'address_observation' WHERE evidence_level IS NULL")
    op.execute("ALTER TABLE registry_assets ALTER COLUMN evidence_level SET NOT NULL")
    op.execute("ALTER TABLE registry_assets ADD COLUMN IF NOT EXISTS primary_source TEXT")
    op.execute("UPDATE registry_assets SET primary_source = 'identity_evidence' WHERE primary_source IS NULL")
    op.execute("ALTER TABLE registry_assets ALTER COLUMN primary_source SET NOT NULL")
    op.execute("ALTER TABLE registry_assets ADD COLUMN IF NOT EXISTS decimals BIGINT")
    op.execute("ALTER TABLE registry_assets ADD COLUMN IF NOT EXISTS name TEXT")
    op.execute("ALTER TABLE registry_assets ADD COLUMN IF NOT EXISTS symbol TEXT")
    op.execute("DROP INDEX IF EXISTS idx_asset_identity_current_symbol")
    op.execute("DROP INDEX IF EXISTS idx_asset_identity_current_confidence")
    op.execute("DROP INDEX IF EXISTS idx_asset_identity_evidence_provider_lookup")
    op.execute("DROP INDEX IF EXISTS idx_asset_identity_evidence_kind_time")
    op.execute("DROP INDEX IF EXISTS idx_asset_identity_evidence_asset")
    op.execute("DROP TABLE IF EXISTS asset_identity_current")
    op.execute("DROP TABLE IF EXISTS asset_identity_evidence")
