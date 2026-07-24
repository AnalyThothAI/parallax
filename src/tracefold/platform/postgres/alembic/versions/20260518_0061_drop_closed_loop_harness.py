"""Drop SocialEvent shadow harness tables and normalize Pulse runtime names."""

from __future__ import annotations

from alembic import op

revision = "20260518_0061"
down_revision = "20260518_0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _normalize_pulse_runtime_ledger()
    op.execute("DROP TABLE IF EXISTS harness_credits CASCADE")
    op.execute("DROP TABLE IF EXISTS harness_outcomes CASCADE")
    op.execute("DROP TABLE IF EXISTS harness_decisions CASCADE")
    op.execute("DROP TABLE IF EXISTS harness_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS event_clusters CASCADE")
    op.execute("DROP TABLE IF EXISTS attention_seeds CASCADE")
    op.execute("DROP TABLE IF EXISTS harness_weights CASCADE")


def downgrade() -> None:
    # Hard-cut migration: the dropped tables were report-only shadow state.
    # Recreating them here would reintroduce a deleted runtime contract.
    pass


def _normalize_pulse_runtime_ledger() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.pulse_agent_harness_versions') IS NOT NULL
             AND to_regclass('public.pulse_agent_runtime_versions') IS NULL THEN
            ALTER TABLE pulse_agent_harness_versions RENAME TO pulse_agent_runtime_versions;
          END IF;
        END $$;
        """
    )
    _rename_column_if_needed("pulse_agent_runtime_versions", "harness_hash", "runtime_hash")
    _rename_column_if_needed("pulse_agent_runtime_versions", "harness_version", "runtime_version")
    _rename_column_if_needed("pulse_agent_runs", "harness_hash", "runtime_hash")
    _rename_column_if_needed("pulse_agent_runs", "harness_version", "runtime_version")
    _rename_column_if_needed("pulse_agent_eval_cases", "harness_hash", "runtime_hash")
    _rename_column_if_needed("pulse_agent_eval_results", "harness_hash", "runtime_hash")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_runs_harness")
    op.execute("DROP INDEX IF EXISTS idx_pulse_agent_eval_cases_harness")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_runs_runtime
          ON pulse_agent_runs(runtime_hash, started_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_agent_eval_cases_runtime
          ON pulse_agent_eval_cases(runtime_hash, route, recommendation, created_at_ms DESC)
        """
    )


def _rename_column_if_needed(table_name: str, old_name: str, new_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF to_regclass('public.{table_name}') IS NOT NULL
             AND EXISTS (
               SELECT 1
               FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = '{table_name}'
                 AND column_name = '{old_name}'
             )
             AND NOT EXISTS (
               SELECT 1
               FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = '{table_name}'
                 AND column_name = '{new_name}'
             ) THEN
            ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name};
          END IF;
        END $$;
        """
    )
