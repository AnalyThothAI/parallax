"""Replace discovery task queue with discovery result facts."""

from __future__ import annotations

from alembic import op

revision = "20260507_0009"
down_revision = "20260507_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discovery_tasks")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_discovery_results (
          provider TEXT NOT NULL,
          lookup_key TEXT NOT NULL,
          lookup_type TEXT NOT NULL,
          status TEXT NOT NULL,
          candidate_count INTEGER NOT NULL DEFAULT 0,
          candidate_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          result_hash TEXT,
          last_lookup_at_ms BIGINT,
          next_refresh_at_ms BIGINT NOT NULL DEFAULT 0,
          last_error TEXT,
          error_count INTEGER NOT NULL DEFAULT 0,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(provider, lookup_key),
          CONSTRAINT ck_token_discovery_results_status
            CHECK(status IN ('running', 'found', 'not_found', 'error'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_discovery_results_due
          ON token_discovery_results(provider, status, next_refresh_at_ms, updated_at_ms)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_discovery_results_lookup_type
          ON token_discovery_results(lookup_type, status, next_refresh_at_ms)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_discovery_results_lookup_type")
    op.execute("DROP INDEX IF EXISTS idx_token_discovery_results_due")
    op.execute("DROP TABLE IF EXISTS token_discovery_results")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_tasks (
          task_id TEXT PRIMARY KEY,
          task_type TEXT NOT NULL,
          query_key TEXT NOT NULL UNIQUE,
          payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          status TEXT NOT NULL DEFAULT 'pending',
          attempt_count INTEGER NOT NULL DEFAULT 0,
          next_run_at_ms BIGINT NOT NULL,
          last_error TEXT,
          created_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL
        )
        """
    )
