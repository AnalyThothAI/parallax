"""Add persisted News item agent requirement contract."""

from __future__ import annotations

from alembic import op

revision = "20260605_0150"
down_revision = "20260605_0149"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        ALTER TABLE news_items
          ADD COLUMN IF NOT EXISTS agent_requirement_status TEXT NOT NULL DEFAULT 'not_required',
          ADD COLUMN IF NOT EXISTS agent_requirement_reason TEXT NOT NULL DEFAULT 'item_not_processed',
          ADD COLUMN IF NOT EXISTS agent_requirement_priority INTEGER NOT NULL DEFAULT 100,
          ADD COLUMN IF NOT EXISTS agent_requirement_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS agent_requirement_version TEXT NOT NULL DEFAULT ''
        """
    )
    op.execute(
        """
        UPDATE news_items
           SET agent_requirement_status = 'not_required',
               agent_requirement_reason = CASE
                 WHEN lifecycle_status <> 'processed' THEN 'item_not_processed'
                 WHEN COALESCE(analysis_admission_status, '') <> 'admitted' THEN 'analysis_not_admitted'
                 ELSE agent_requirement_reason
               END,
               agent_requirement_json = CASE
                 WHEN agent_requirement_json = '{}'::jsonb THEN jsonb_build_object(
                   'status', 'not_required',
                   'reason', CASE
                     WHEN lifecycle_status <> 'processed' THEN 'item_not_processed'
                     WHEN COALESCE(analysis_admission_status, '') <> 'admitted' THEN 'analysis_not_admitted'
                     ELSE agent_requirement_reason
                   END,
                   'version', 'news_item_agent_requirement_v1'
                 )
                 ELSE agent_requirement_json
               END,
               agent_requirement_version = CASE
                 WHEN agent_requirement_version = '' THEN 'news_item_agent_requirement_v1'
                 ELSE agent_requirement_version
               END
         WHERE agent_requirement_version = ''
            OR agent_requirement_json = '{}'::jsonb
        """
    )
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_agent_requirement_published
              ON news_items(agent_requirement_status, agent_requirement_reason, published_at_ms DESC, news_item_id)
            """
        )
        op.execute("ANALYZE news_items")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    raise RuntimeError(
        "20260605_0150 News agent requirement contract is not safely reversible; "
        "runtime decisions may already depend on persisted requirement fields"
    )
