"""Add equity event runtime projection indexes."""

from __future__ import annotations

from alembic import op

revision = "20260523_0086"
down_revision = "20260523_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_page_rows_event_latest
          ON equity_event_page_rows(company_event_id, computed_at_ms DESC, row_id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_company_timeline_rows_event_latest
          ON equity_company_timeline_rows(company_event_id, computed_at_ms DESC, row_id ASC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_alert_candidates_event_latest
          ON equity_event_alert_candidates(company_event_id, computed_at_ms DESC, alert_candidate_id ASC)
        """
    )


def downgrade() -> None:
    for index_name in (
        "idx_equity_event_alert_candidates_event_latest",
        "idx_equity_company_timeline_rows_event_latest",
        "idx_equity_event_page_rows_event_latest",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
