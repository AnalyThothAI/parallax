"""Drop retired social/watchlist agent tables."""

from __future__ import annotations

from alembic import op

revision = "20260530_0130"
down_revision = "20260530_0129"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS watchlist_handle_summary_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_summary_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_summaries CASCADE")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_signal_events CASCADE")
    op.execute("DROP TABLE IF EXISTS watchlist_handle_signal_stats CASCADE")
    op.execute("DROP TABLE IF EXISTS social_event_extraction_evidence CASCADE")
    op.execute("DROP TABLE IF EXISTS social_event_extractions CASCADE")
    op.execute("DROP TABLE IF EXISTS enrichment_results CASCADE")
    op.execute("DROP TABLE IF EXISTS enrichment_jobs CASCADE")


def downgrade() -> None:
    """No downgrade for hard-cut removal of retired social/watchlist agents."""
