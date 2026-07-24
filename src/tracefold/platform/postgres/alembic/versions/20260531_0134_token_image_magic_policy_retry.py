"""Retry token images blocked by the retired header/media mismatch policy."""

from __future__ import annotations

from alembic import op

revision = "20260531_0134"
down_revision = "20260531_0133"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        UPDATE token_image_assets
        SET status = 'error',
            media_type = NULL,
            file_extension = NULL,
            content_sha256 = NULL,
            byte_size = NULL,
            storage_path = NULL,
            public_url = NULL,
            last_error = 'image_magic_media_type_policy_repaired: prior_media_type_mismatch',
            next_refresh_at_ms = 0
        WHERE status = 'unsupported'
          AND last_error = 'unsupported_image_bytes: media_type_mismatch'
        """
    )
    op.execute("ANALYZE token_image_assets")


def downgrade() -> None:
    """No downgrade for restoring rows wrongly marked terminal by the old policy."""
