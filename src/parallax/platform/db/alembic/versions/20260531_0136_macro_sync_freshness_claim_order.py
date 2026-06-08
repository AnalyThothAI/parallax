"""Root-fix macro sync freshness queue identity and claim order."""

from __future__ import annotations

from alembic import op

revision = "20260531_0136"
down_revision = "20260531_0135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM macro_sync_windows
        WHERE trigger_reason LIKE 'steady_overlap:%'
          AND status IN ('pending', 'retryable')
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_macro_sync_windows_due")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_sync_windows_due
          ON macro_sync_windows(priority ASC, window_end DESC, due_at_ms ASC, updated_at_ms ASC, sync_window_id)
          WHERE status IN ('pending', 'retryable')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_macro_sync_windows_due")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_sync_windows_due
          ON macro_sync_windows(priority ASC, due_at_ms ASC, updated_at_ms ASC, sync_window_id)
          WHERE status IN ('pending', 'retryable')
        """
    )
