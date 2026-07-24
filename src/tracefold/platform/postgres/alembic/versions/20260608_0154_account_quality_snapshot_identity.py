"""Hard-cut account quality snapshots to stable current identity."""

from __future__ import annotations

from alembic import op

revision = "20260608_0154"
down_revision = "20260608_0153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '10min'")
    op.execute(
        """
        UPDATE account_quality_snapshots
           SET handle = lower(ltrim(btrim(handle), '@')),
               "window" = lower(btrim("window"))
        """
    )
    op.execute(
        """
        WITH ranked AS (
          SELECT
            snapshot_id,
            row_number() OVER (
              PARTITION BY handle, "window"
              ORDER BY updated_at_ms DESC, snapshot_id DESC
            ) AS rank
          FROM account_quality_snapshots
        )
        DELETE FROM account_quality_snapshots AS snapshots
        USING ranked
        WHERE snapshots.snapshot_id = ranked.snapshot_id
          AND ranked.rank > 1
        """
    )
    op.execute(
        """
        UPDATE account_quality_snapshots
           SET snapshot_id = concat('account-quality', chr(58), handle, chr(58), "window", chr(58), 'current')
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_account_quality_snapshots_handle_window
          ON account_quality_snapshots(handle, "window")
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_account_quality_snapshots_handle_window")
