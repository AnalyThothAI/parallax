"""Drop the retired equity-event intelligence schema."""

from __future__ import annotations

from alembic import op

revision = "20260529_0125"
down_revision = "20260529_0124"
branch_labels = None
depends_on = None


DROP_TABLES = (
    "equity_event_process_jobs",
    "equity_event_evidence_jobs",
    "equity_event_projection_dirty_targets",
    "equity_event_brief_states",
    "equity_event_evidence_artifacts",
    "equity_company_timeline_rows",
    "equity_event_alert_candidates",
    "equity_event_calendar_rows",
    "equity_event_page_rows",
    "equity_event_agent_briefs",
    "equity_event_agent_runs",
    "equity_event_story_members",
    "equity_event_story_groups",
    "equity_event_fact_candidates",
    "equity_event_source_spans",
    "equity_company_events",
    "equity_section_diffs",
    "equity_document_revisions",
    "equity_event_documents",
    "equity_provider_documents",
    "equity_expected_events",
    "equity_event_universe_members",
    "equity_event_fetch_runs",
    "equity_event_sources",
)


def upgrade() -> None:
    for table_name in DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


def downgrade() -> None:
    """No-op: the retired product schema is intentionally not recreated."""
