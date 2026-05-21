"""Add token image local mirror asset storage."""

from __future__ import annotations

from alembic import op

revision = "20260521_0077"
down_revision = "20260521_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_image_assets (
          image_id TEXT PRIMARY KEY,
          source_url TEXT NOT NULL,
          source_url_hash TEXT NOT NULL UNIQUE,
          source_provider TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          status TEXT NOT NULL CHECK (status IN ('pending', 'ready', 'error', 'unsupported')),
          media_type TEXT,
          file_extension TEXT,
          content_sha256 TEXT,
          byte_size BIGINT,
          storage_path TEXT,
          public_url TEXT,
          raw_ref_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          failure_count BIGINT NOT NULL DEFAULT 0,
          last_error TEXT,
          observed_at_ms BIGINT,
          next_refresh_at_ms BIGINT NOT NULL,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          CHECK (
            status <> 'ready'
            OR (
              media_type IN ('image/gif', 'image/jpeg', 'image/png', 'image/webp')
              AND file_extension IN ('.gif', '.jpg', '.png', '.webp')
              AND content_sha256 IS NOT NULL
              AND byte_size IS NOT NULL
              AND byte_size > 0
              AND storage_path IS NOT NULL
              AND public_url IS NOT NULL
              AND public_url LIKE '/api/token-images/%'
            )
          )
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_image_assets_due
          ON token_image_assets(status, next_refresh_at_ms, updated_at_ms)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_image_assets_ready_source
          ON token_image_assets(source_url_hash)
          WHERE status = 'ready'
        """
    )
    op.execute(
        """
        ALTER TABLE token_profile_current
          ADD COLUMN IF NOT EXISTS logo_image_id TEXT,
          ADD COLUMN IF NOT EXISTS logo_source_provider TEXT,
          ADD COLUMN IF NOT EXISTS logo_source_url_hash TEXT
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_profile_current_logo_image
          ON token_profile_current(logo_image_id)
          WHERE logo_image_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_profile_current_logo_image")
    op.execute(
        """
        ALTER TABLE token_profile_current
          DROP COLUMN IF EXISTS logo_image_id,
          DROP COLUMN IF EXISTS logo_source_provider,
          DROP COLUMN IF EXISTS logo_source_url_hash
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_token_image_assets_ready_source")
    op.execute("DROP INDEX IF EXISTS idx_token_image_assets_due")
    op.execute("DROP TABLE IF EXISTS token_image_assets")
