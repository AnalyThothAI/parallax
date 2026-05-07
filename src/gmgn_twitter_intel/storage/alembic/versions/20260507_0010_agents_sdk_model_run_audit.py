"""Add OpenAI Agents SDK run audit columns."""

from __future__ import annotations

from alembic import op

revision = "20260507_0010"
down_revision = "20260507_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_enrichment_labels CASCADE")
    op.execute(
        """
        UPDATE enrichment_jobs
        SET status = 'dead',
            last_error = 'legacy_job_type_retired',
            updated_at_ms = EXTRACT(EPOCH FROM NOW())::bigint * 1000
        WHERE job_type <> 'watched_social_event_extraction'
          AND status IN ('pending', 'failed', 'running')
        """
    )
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS backend TEXT NOT NULL DEFAULT 'openai_agents_sdk'")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS sdk_trace_id TEXT")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS workflow_name TEXT")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS agent_name TEXT")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS artifact_version_hash TEXT")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS prompt_version TEXT")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS schema_version TEXT")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS input_hash TEXT")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS output_hash TEXT")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS trace_metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS usage_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE model_runs ADD COLUMN IF NOT EXISTS latency_ms BIGINT NOT NULL DEFAULT 0")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_trace ON model_runs(sdk_trace_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_backend_finished ON model_runs(backend, finished_at_ms)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_model_runs_backend_finished")
    op.execute("DROP INDEX IF EXISTS idx_model_runs_trace")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS latency_ms")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS usage_json")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS trace_metadata_json")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS output_hash")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS input_hash")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS schema_version")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS prompt_version")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS artifact_version_hash")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS agent_name")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS workflow_name")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS sdk_trace_id")
    op.execute("ALTER TABLE model_runs DROP COLUMN IF EXISTS backend")
