"""Hard cut inactive News story projection."""

from __future__ import annotations

from alembic import op

revision = "20260531_0131"
down_revision = "20260530_0130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM news_projection_dirty_targets
         WHERE projection_name = 'story'
            OR dirty_reason = 'news_story_projected'
        """
    )
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS story_json")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS story_id")
    op.execute("DROP TABLE IF EXISTS news_story_members CASCADE")
    op.execute("DROP TABLE IF EXISTS news_story_groups CASCADE")


def downgrade() -> None:
    """No downgrade for the hard-cut removal of inactive News story projection."""
