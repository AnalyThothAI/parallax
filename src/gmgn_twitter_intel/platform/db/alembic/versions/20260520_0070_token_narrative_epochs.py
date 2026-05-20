"""Add token narrative epoch metadata to discussion digests."""

from __future__ import annotations

from alembic import op

revision = "20260520_0070"
down_revision = "20260520_0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_id TEXT")
    op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_policy_version TEXT")
    op.execute(
        """
        ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_event_ids_json JSONB
          NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_start_ms BIGINT")
    op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS source_window_end_ms BIGINT")
    op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS epoch_closed_at_ms BIGINT")
    op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS display_current_until_ms BIGINT")
    op.execute("ALTER TABLE token_discussion_digests ADD COLUMN IF NOT EXISTS refresh_reason TEXT")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_discussion_digests_epoch_currentness
          ON token_discussion_digests(
            target_type, target_id, "window", scope, schema_version, status, computed_at_ms DESC
          )
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "hard-cut migration is not safely reversible; restoring a pre-migration backup is required"
    )
