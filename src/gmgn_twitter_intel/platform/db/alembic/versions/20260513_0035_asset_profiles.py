"""Add current asset profile facts."""

from __future__ import annotations

from alembic import op

revision = "20260513_0035"
down_revision = "20260512_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_profiles (
          asset_id TEXT NOT NULL REFERENCES registry_assets(asset_id) ON DELETE CASCADE,
          provider TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('ready', 'missing', 'unsupported', 'error')),
          symbol TEXT,
          name TEXT,
          logo_url TEXT,
          banner_url TEXT,
          website_url TEXT,
          twitter_username TEXT,
          twitter_url TEXT,
          telegram_url TEXT,
          gmgn_url TEXT,
          geckoterminal_url TEXT,
          description TEXT,
          raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          observed_at_ms BIGINT,
          next_refresh_at_ms BIGINT NOT NULL,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(asset_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_profiles_due
          ON asset_profiles(provider, next_refresh_at_ms, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_asset_profiles_status
          ON asset_profiles(status, updated_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_asset_profiles_status")
    op.execute("DROP INDEX IF EXISTS idx_asset_profiles_due")
    op.execute("DROP TABLE IF EXISTS asset_profiles")
