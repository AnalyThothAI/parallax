"""Fence News fetch completion with one active source claim."""

from __future__ import annotations

from alembic import op

revision = "20260722_0190"
down_revision = "20260722_0189"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '5min'")
    op.execute("ALTER TABLE news_sources ADD COLUMN active_fetch_run_id TEXT")
    op.execute(
        """
        ALTER TABLE news_sources
        ADD CONSTRAINT news_sources_active_fetch_run_id_fkey
        FOREIGN KEY (active_fetch_run_id)
        REFERENCES news_fetch_runs(fetch_run_id)
        ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_news_sources_active_fetch_run_id
        ON news_sources(active_fetch_run_id)
        WHERE active_fetch_run_id IS NOT NULL
        """
    )
    op.execute(
        """
        WITH migration_clock AS (
          SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        UPDATE news_fetch_runs AS runs
        SET finished_at_ms = GREATEST(runs.started_at_ms, migration_clock.now_ms),
            status = 'failed',
            error = 'active_fetch_claim_protocol_migration',
            extra_json = runs.extra_json || '{"outcome":"interrupted_before_active_claim_protocol"}'::jsonb
        FROM migration_clock
        WHERE runs.status = 'running'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_news_sources_active_fetch_run_id")
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT news_sources_active_fetch_run_id_fkey")
    op.execute("ALTER TABLE news_sources DROP COLUMN active_fetch_run_id")
