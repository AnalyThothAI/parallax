"""Hard-cut agent execution audit defaults to LiteLLM vocabulary."""

from __future__ import annotations

from alembic import op

revision = "20260529_0128"
down_revision = "20260529_0127"
branch_labels = None
depends_on = None


TRACE_TABLES = ("model_runs", "pulse_agent_runs", "news_item_agent_runs")


def upgrade() -> None:
    for table_name in TRACE_TABLES:
        _rename_trace_column(table_name)
        op.execute(f"ALTER TABLE {table_name} ALTER COLUMN backend SET DEFAULT 'litellm_sdk'")
        op.execute(
            f"""
            UPDATE {table_name}
            SET backend = 'litellm_sdk'
            WHERE backend = 'openai_agents_sdk'
            """
        )
        op.execute(
            f"""
            UPDATE {table_name}
            SET provider = 'litellm'
            WHERE provider = 'openai'
            """
        )

    op.execute("DROP INDEX IF EXISTS idx_model_runs_trace")
    op.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_trace ON model_runs(execution_trace_id)")
    op.execute("DROP INDEX IF EXISTS idx_news_item_agent_runs_sdk_trace")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_item_agent_runs_execution_trace
        ON news_item_agent_runs(execution_trace_id)
        """
    )


def downgrade() -> None:
    """No compatibility downgrade for the LiteLLM execution-plane hard cut."""


def _rename_trace_column(table_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = '{table_name}'
              AND column_name = 'sdk_trace_id'
          ) AND NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = '{table_name}'
              AND column_name = 'execution_trace_id'
          ) THEN
            ALTER TABLE {table_name} RENAME COLUMN sdk_trace_id TO execution_trace_id;
          END IF;
        END $$;
        """
    )
