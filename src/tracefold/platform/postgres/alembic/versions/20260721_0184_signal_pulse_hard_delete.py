"""Remove the Signal Pulse projection, queues, audit ledger, and notification residue."""

from __future__ import annotations

from alembic import op

revision = "20260721_0184"
down_revision = "20260713_0183"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")

    # Notifications and terminal rows contain logical source references rather
    # than foreign keys. Remove that retired product evidence before its source
    # tables disappear; generic notification and queue audit infrastructure stays.
    op.execute(
        """
        DELETE FROM notifications
        WHERE rule_id = 'signal_pulse_candidate'
           OR source_table = 'pulse_candidates'
           OR entity_type = 'pulse_candidate'
        """
    )
    op.execute(
        """
        DELETE FROM worker_queue_terminal_events
        WHERE worker_name = 'pulse_candidate'
           OR source_table IN ('pulse_agent_jobs', 'pulse_trigger_dirty_targets')
        """
    )

    # Drop children before parents. Deliberately avoid CASCADE and IF EXISTS so
    # schema drift fails closed instead of silently removing unknown dependents.
    op.execute("DROP TABLE pulse_agent_eval_results")
    op.execute("DROP TABLE pulse_agent_eval_cases")
    op.execute("DROP TABLE pulse_evidence_packets")
    op.execute("DROP TABLE pulse_agent_run_steps")
    op.execute("DROP TABLE pulse_playbook_snapshots")
    op.execute("DROP TABLE pulse_candidates")
    op.execute("DROP TABLE pulse_agent_runs")
    op.execute("DROP TABLE pulse_agent_jobs")
    op.execute("DROP TABLE pulse_agent_runtime_versions")
    op.execute("DROP TABLE pulse_candidate_edge_state")
    op.execute("DROP TABLE pulse_candidate_run_budget")
    op.execute("DROP TABLE pulse_target_run_budget")
    op.execute("DROP TABLE pulse_trigger_dirty_targets")


def downgrade() -> None:
    raise RuntimeError("20260721_0184 is an irreversible hard cut; restore a pre-migration backup to downgrade")
