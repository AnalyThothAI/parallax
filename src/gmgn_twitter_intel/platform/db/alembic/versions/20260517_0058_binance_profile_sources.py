"""Move Binance token profiles into source cache tables."""

from __future__ import annotations

from alembic import op

revision = "20260517_0058"
down_revision = "20260517_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cex_token_profiles (
          cex_token_id TEXT NOT NULL REFERENCES cex_tokens(cex_token_id) ON DELETE CASCADE,
          provider TEXT NOT NULL,
          status TEXT NOT NULL,
          symbol TEXT,
          name TEXT,
          logo_url TEXT,
          source_ref TEXT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          observed_at_ms BIGINT,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(cex_token_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_token_profiles_ready_logo
          ON cex_token_profiles(provider, updated_at_ms DESC, cex_token_id)
          WHERE status = 'ready' AND logo_url IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO cex_token_profiles(
          cex_token_id, provider, status, symbol, name, logo_url, source_ref,
          raw_payload_json, observed_at_ms, last_error, created_at_ms, updated_at_ms
        )
        SELECT
          cex_token_id,
          'binance_cex_profile',
          'ready',
          base_symbol,
          NULL,
          logo_url,
          COALESCE(logo_source || ':' || base_symbol, 'binance_cex_profile:' || base_symbol),
          jsonb_build_object(
            'source_provider', 'binance_cex_profile',
            'migrated_from', 'cex_tokens.logo_url',
            'logo_source', logo_source
          ),
          COALESCE(logo_observed_at_ms, updated_at_ms),
          NULL,
          COALESCE(logo_observed_at_ms, updated_at_ms),
          updated_at_ms
        FROM cex_tokens
        WHERE logo_url IS NOT NULL
        ON CONFLICT(cex_token_id, provider) DO UPDATE SET
          status = excluded.status,
          symbol = excluded.symbol,
          name = excluded.name,
          logo_url = excluded.logo_url,
          source_ref = excluded.source_ref,
          raw_payload_json = excluded.raw_payload_json,
          observed_at_ms = excluded.observed_at_ms,
          last_error = NULL,
          updated_at_ms = excluded.updated_at_ms
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_cex_tokens_logo")
    op.execute("ALTER TABLE cex_tokens DROP COLUMN IF EXISTS logo_observed_at_ms")
    op.execute("ALTER TABLE cex_tokens DROP COLUMN IF EXISTS logo_source")
    op.execute("ALTER TABLE cex_tokens DROP COLUMN IF EXISTS logo_url")


def downgrade() -> None:
    op.execute("ALTER TABLE cex_tokens ADD COLUMN IF NOT EXISTS logo_url TEXT")
    op.execute("ALTER TABLE cex_tokens ADD COLUMN IF NOT EXISTS logo_source TEXT")
    op.execute("ALTER TABLE cex_tokens ADD COLUMN IF NOT EXISTS logo_observed_at_ms BIGINT")
    op.execute(
        """
        UPDATE cex_tokens
        SET logo_url = cex_token_profiles.logo_url,
            logo_source = cex_token_profiles.source_ref,
            logo_observed_at_ms = cex_token_profiles.observed_at_ms,
            updated_at_ms = GREATEST(cex_tokens.updated_at_ms, cex_token_profiles.updated_at_ms)
        FROM cex_token_profiles
        WHERE cex_token_profiles.cex_token_id = cex_tokens.cex_token_id
          AND cex_token_profiles.provider = 'binance_cex_profile'
          AND cex_token_profiles.status = 'ready'
          AND cex_token_profiles.logo_url IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cex_tokens_logo
          ON cex_tokens(updated_at_ms DESC)
          WHERE logo_url IS NOT NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_cex_token_profiles_ready_logo")
    op.execute("DROP TABLE IF EXISTS cex_token_profiles")
