"""Harden equity fetch run terminal states and reap stale running runs."""

from __future__ import annotations

from alembic import op

revision = "20260526_0110"
down_revision = "20260526_0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE equity_event_fetch_runs DROP CONSTRAINT IF EXISTS equity_event_fetch_runs_status_check")
    op.execute(
        """
        WITH now_value AS (
          SELECT (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint AS now_ms
        )
        UPDATE equity_event_fetch_runs AS runs
           SET status = 'failed_retryable',
               error = COALESCE(runs.error, 'legacy_failed_fetch_run'),
               extra_json = COALESCE(runs.extra_json, '{}'::jsonb)
                 || jsonb_build_object(
                      'migrated_from_status', 'failed',
                      'migrated_at_ms', now_value.now_ms
                    )
          FROM now_value
         WHERE runs.status = 'failed'
        """
    )
    op.execute(
        """
        WITH now_value AS (
          SELECT (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::bigint AS now_ms
        ),
        stale AS (
          UPDATE equity_event_fetch_runs AS runs
             SET status = 'failed_retryable',
                 finished_at_ms = now_value.now_ms,
                 error = 'stale_fetch_run_timeout',
                 extra_json = COALESCE(runs.extra_json, '{}'::jsonb)
                   || jsonb_build_object(
                        'failure_reason', 'stale_fetch_run_timeout',
                        'stale_before_ms', now_value.now_ms - 900000,
                        'reaped_at_ms', now_value.now_ms,
                        'migration_revision', '20260526_0110'
                      )
            FROM now_value
           WHERE runs.status = 'running'
             AND runs.finished_at_ms = 0
             AND runs.started_at_ms < now_value.now_ms - 900000
          RETURNING runs.source_id
        )
        UPDATE equity_event_sources AS sources
           SET consecutive_failures = consecutive_failures + 1,
               last_error = 'stale_fetch_run_timeout',
               next_fetch_after_ms = LEAST(next_fetch_after_ms, now_value.now_ms),
               updated_at_ms = now_value.now_ms
          FROM now_value
         WHERE sources.source_id IN (SELECT DISTINCT source_id FROM stale)
        """
    )
    op.execute(
        """
        ALTER TABLE equity_event_fetch_runs
          ADD CONSTRAINT equity_event_fetch_runs_status_check
          CHECK (status IN ('running', 'success', 'failed_retryable', 'failed_terminal'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE equity_event_fetch_runs DROP CONSTRAINT IF EXISTS equity_event_fetch_runs_status_check")
    op.execute(
        """
        UPDATE equity_event_fetch_runs
           SET status = 'failed'
         WHERE status IN ('failed_retryable', 'failed_terminal')
        """
    )
    op.execute(
        """
        ALTER TABLE equity_event_fetch_runs
          ADD CONSTRAINT equity_event_fetch_runs_status_check
          CHECK (status IN ('running', 'success', 'failed'))
        """
    )
