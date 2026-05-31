"""Add canonical token profile current read model."""

from __future__ import annotations

from alembic import op

revision = "20260517_0052"
down_revision = "20260516_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_profile_current (
          target_type TEXT NOT NULL,
          target_id TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('ready', 'missing', 'unsupported', 'error')),
          profile_provider TEXT,
          source_kind TEXT NOT NULL,
          source_ref TEXT,
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
          quality_flags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          observed_at_ms BIGINT,
          computed_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(target_type, target_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_profile_current_status
          ON token_profile_current(status, updated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_profile_current_provider
          ON token_profile_current(profile_provider, updated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_profile_current_logo
          ON token_profile_current(updated_at_ms DESC)
          WHERE logo_url IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_profile_current_logo")
    op.execute("DROP INDEX IF EXISTS idx_token_profile_current_provider")
    op.execute("DROP INDEX IF EXISTS idx_token_profile_current_status")
    op.execute("DROP TABLE IF EXISTS token_profile_current")
