"""Stop retrying terminal token image mirror failures."""

from __future__ import annotations

from alembic import op

revision = "20260523_0089"
down_revision = "20260523_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE token_image_assets
        SET status = 'unsupported',
            next_refresh_at_ms = updated_at_ms
        WHERE status IN ('pending', 'error')
          AND (
            last_error LIKE 'unsupported\\_%' ESCAPE '\\'
            OR last_error LIKE 'image_too_large:%'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE token_image_assets
        SET status = 'error'
        WHERE status = 'unsupported'
          AND (
            last_error LIKE 'unsupported\\_%' ESCAPE '\\'
            OR last_error LIKE 'image_too_large:%'
          )
        """
    )
