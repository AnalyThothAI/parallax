"""Hard-cut token profile logos to local image URLs only."""

from __future__ import annotations

from alembic import op

revision = "20260521_0079"
down_revision = "20260521_0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE token_profile_current
        SET logo_url = NULL,
            logo_image_id = NULL,
            logo_source_provider = NULL,
            logo_source_url_hash = NULL,
            quality_flags_json = CASE
              WHEN jsonb_typeof(quality_flags_json) = 'array'
                AND quality_flags_json ? 'logo_mirror_pending'
                THEN quality_flags_json
              WHEN jsonb_typeof(quality_flags_json) = 'array'
                THEN quality_flags_json || '["logo_mirror_pending"]'::jsonb
              ELSE '["logo_mirror_pending"]'::jsonb
            END
        WHERE logo_url IS NOT NULL
          AND logo_url NOT LIKE '/api/token-images/%'
        """
    )
    op.execute(
        """
        ALTER TABLE token_profile_current
          DROP CONSTRAINT IF EXISTS token_profile_current_local_logo_url_check
        """
    )
    op.execute(
        """
        ALTER TABLE token_profile_current
          ADD CONSTRAINT token_profile_current_local_logo_url_check
          CHECK (logo_url IS NULL OR logo_url LIKE '/api/token-images/%')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE token_profile_current
          DROP CONSTRAINT IF EXISTS token_profile_current_local_logo_url_check
        """
    )
