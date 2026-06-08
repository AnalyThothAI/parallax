"""Rekey Pulse candidate serving rows to product/window identity."""

from __future__ import annotations

from alembic import op

revision = "20260608_0156"
down_revision = "20260608_0155"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    op.execute("DROP INDEX IF EXISTS ux_pulse_candidates_product_window_key")
    op.execute(
        "ALTER TABLE pulse_playbook_snapshots "
        "DROP CONSTRAINT IF EXISTS pulse_playbook_snapshots_candidate_id_fkey"
    )
    op.execute(
        """
        CREATE TEMP TABLE pulse_candidate_product_identity_rekey ON COMMIT DROP AS
        WITH keyed AS (
          SELECT
            candidate_id AS old_id,
            'pulse-' || substring(
              encode(
                sha256(
                  convert_to(
                    candidate_type || '|' || "window" || '|' || scope || '|' || target_type || '|' || target_id,
                    'UTF8'
                  )
                ),
                'hex'
              )
              FROM 1 FOR 40
            ) AS new_id,
            candidate_type,
            "window",
            scope,
            target_type,
            target_id,
            created_at_ms,
            updated_at_ms
          FROM pulse_candidates
          WHERE target_type IS NOT NULL
            AND target_id IS NOT NULL
        ),
        ranked AS (
          SELECT
            *,
            row_number() OVER (
              PARTITION BY candidate_type, "window", scope, target_type, target_id
              ORDER BY updated_at_ms DESC, created_at_ms DESC, old_id DESC
            ) AS product_rank
          FROM keyed
        )
        SELECT * FROM ranked
        """
    )
    op.execute(
        """
        UPDATE pulse_agent_jobs AS job
        SET candidate_id = rekey.new_id,
            context_json = CASE
              WHEN jsonb_typeof(job.context_json) = 'object'
                THEN jsonb_set(job.context_json, '{candidate_id}', to_jsonb(rekey.new_id), true)
              ELSE job.context_json
            END
        FROM pulse_candidate_product_identity_rekey AS rekey
        WHERE job.candidate_id = rekey.old_id
          AND rekey.old_id <> rekey.new_id
        """
    )
    op.execute(
        """
        UPDATE pulse_agent_runs AS run
        SET candidate_id = rekey.new_id
        FROM pulse_candidate_product_identity_rekey AS rekey
        WHERE run.candidate_id = rekey.old_id
          AND rekey.old_id <> rekey.new_id
        """
    )
    op.execute(
        """
        UPDATE pulse_evidence_packets AS packet
        SET candidate_id = rekey.new_id
        FROM pulse_candidate_product_identity_rekey AS rekey
        WHERE packet.candidate_id = rekey.old_id
          AND rekey.old_id <> rekey.new_id
        """
    )
    op.execute(
        """
        DELETE FROM pulse_candidate_edge_state AS edge
        USING pulse_candidate_product_identity_rekey AS rekey
        WHERE edge.candidate_id = rekey.old_id
          AND rekey.product_rank > 1
        """
    )
    op.execute(
        """
        UPDATE pulse_candidate_edge_state AS edge
        SET candidate_id = rekey.new_id
        FROM pulse_candidate_product_identity_rekey AS rekey
        WHERE edge.candidate_id = rekey.old_id
          AND rekey.product_rank = 1
          AND rekey.old_id <> rekey.new_id
        """
    )
    op.execute(
        """
        DELETE FROM pulse_candidate_run_budget AS budget
        USING pulse_candidate_product_identity_rekey AS rekey
        WHERE budget.candidate_id = rekey.old_id
          AND rekey.product_rank > 1
        """
    )
    op.execute(
        """
        UPDATE pulse_candidate_run_budget AS budget
        SET candidate_id = rekey.new_id
        FROM pulse_candidate_product_identity_rekey AS rekey
        WHERE budget.candidate_id = rekey.old_id
          AND rekey.product_rank = 1
          AND rekey.old_id <> rekey.new_id
        """
    )
    op.execute(
        """
        WITH ranked_playbooks AS (
          SELECT
            playbook.ctid AS row_ctid,
            row_number() OVER (
              PARTITION BY rekey.new_id, playbook.horizon, playbook.playbook_version
              ORDER BY playbook.created_at_ms DESC, playbook.playbook_id DESC
            ) AS playbook_rank
          FROM pulse_playbook_snapshots AS playbook
          JOIN pulse_candidate_product_identity_rekey AS rekey
            ON rekey.old_id = playbook.candidate_id
        )
        DELETE FROM pulse_playbook_snapshots AS playbook
        USING ranked_playbooks
        WHERE playbook.ctid = ranked_playbooks.row_ctid
          AND ranked_playbooks.playbook_rank > 1
        """
    )
    op.execute(
        """
        UPDATE pulse_playbook_snapshots AS playbook
        SET candidate_id = rekey.new_id
        FROM pulse_candidate_product_identity_rekey AS rekey
        WHERE playbook.candidate_id = rekey.old_id
          AND rekey.old_id <> rekey.new_id
        """
    )
    op.execute(
        """
        DELETE FROM pulse_candidates AS candidate
        USING pulse_candidate_product_identity_rekey AS rekey
        WHERE candidate.candidate_id = rekey.old_id
          AND rekey.product_rank > 1
        """
    )
    op.execute(
        """
        UPDATE pulse_candidates AS candidate
        SET candidate_id = rekey.new_id
        FROM pulse_candidate_product_identity_rekey AS rekey
        WHERE candidate.candidate_id = rekey.old_id
          AND rekey.product_rank = 1
          AND rekey.old_id <> rekey.new_id
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_playbook_snapshots
          ADD CONSTRAINT pulse_playbook_snapshots_candidate_id_fkey
          FOREIGN KEY (candidate_id)
          REFERENCES pulse_candidates(candidate_id)
          ON DELETE CASCADE
          ON UPDATE CASCADE
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_pulse_candidates_product_window_key
          ON pulse_candidates(candidate_type, "window", scope, target_type, target_id)
          WHERE target_type IS NOT NULL
            AND target_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_pulse_candidates_product_window_key")
    op.execute(
        "ALTER TABLE pulse_playbook_snapshots "
        "DROP CONSTRAINT IF EXISTS pulse_playbook_snapshots_candidate_id_fkey"
    )
    op.execute(
        """
        ALTER TABLE pulse_playbook_snapshots
          ADD CONSTRAINT pulse_playbook_snapshots_candidate_id_fkey
          FOREIGN KEY (candidate_id)
          REFERENCES pulse_candidates(candidate_id)
          ON DELETE CASCADE
        """
    )
