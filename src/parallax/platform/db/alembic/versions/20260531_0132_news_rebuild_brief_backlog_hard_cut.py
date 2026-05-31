"""Hard cut historical News rebuild brief backlog."""

from __future__ import annotations

from alembic import op

revision = "20260531_0132"
down_revision = "20260531_0131"
branch_labels = None
depends_on = None


_DELETE_REBUILD_BRIEF_TARGETS_SQL = """
DELETE FROM news_projection_dirty_targets
 WHERE projection_name = 'brief_input'
   AND dirty_reason IN (
     'news_public_url_hard_identity_rebuild',
     'news_canonical_url_hard_identity_rebuild'
   )
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(_DELETE_REBUILD_BRIEF_TARGETS_SQL)
    op.execute("ANALYZE news_projection_dirty_targets")


def downgrade() -> None:
    """No downgrade for deleting obsolete historical LLM backfill targets."""
