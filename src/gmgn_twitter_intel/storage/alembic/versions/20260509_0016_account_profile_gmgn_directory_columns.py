"""Add GMGN account directory columns to account_profiles."""

from __future__ import annotations

from alembic import op

revision = "20260509_0016"
down_revision = "20260508_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE account_profiles
          ADD COLUMN IF NOT EXISTS gmgn_user_id TEXT,
          ADD COLUMN IF NOT EXISTS gmgn_user_tags TEXT[],
          ADD COLUMN IF NOT EXISTS gmgn_platform_followers BIGINT,
          ADD COLUMN IF NOT EXISTS gmgn_directory_observed_at_ms BIGINT
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS account_profiles_gmgn_followers_idx
          ON account_profiles (gmgn_platform_followers DESC NULLS LAST)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS account_profiles_gmgn_followers_idx")
    op.execute(
        """
        ALTER TABLE account_profiles
          DROP COLUMN IF EXISTS gmgn_directory_observed_at_ms,
          DROP COLUMN IF EXISTS gmgn_platform_followers,
          DROP COLUMN IF EXISTS gmgn_user_tags,
          DROP COLUMN IF EXISTS gmgn_user_id
        """
    )
