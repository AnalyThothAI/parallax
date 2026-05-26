"""Add runtime performance lifecycle comments and supporting indexes."""

from __future__ import annotations

from alembic import op

revision = "20260526_0108"
down_revision = "20260526_0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        COMMENT ON TABLE token_radar_rank_source_events IS
          'Compact Token Radar rank-source edge read model. Stores source ids only; event text and raw payload stay in material fact tables.'
        """
    )
    op.execute(
        """
        COMMENT ON TABLE macro_observation_series_generations IS
          'Macro observation projection generations for hard-cut generation swap rebuilds.'
        """
    )
    op.execute(
        """
        COMMENT ON TABLE macro_observation_series_active_generation IS
          'Current macro observation generation pointer per projection and concept.'
        """
    )
    op.execute(
        """
        COMMENT ON TABLE equity_event_evidence_jobs IS
          'Bounded equity document evidence hydration queue owned by the evidence hydration worker.'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_observation_series_rows_generation_lookup
          ON macro_observation_series_rows(
            projection_version,
            concept_key,
            generation_id,
            series_rank,
            observed_at DESC
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_observation_series_generations_status
          ON macro_observation_series_generations(projection_version, status, created_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_macro_observation_series_active_generation_generation
          ON macro_observation_series_active_generation(projection_version, generation_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_evidence_jobs_document
          ON equity_event_evidence_jobs(event_document_id, status, updated_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_fetch_runs_running_started
          ON equity_event_fetch_runs(started_at_ms, fetch_run_id)
          WHERE status = 'running'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_equity_event_fetch_runs_status_started
          ON equity_event_fetch_runs(status, started_at_ms DESC, fetch_run_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_equity_event_fetch_runs_status_started")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_fetch_runs_running_started")
    op.execute("DROP INDEX IF EXISTS idx_equity_event_evidence_jobs_document")
    op.execute("DROP INDEX IF EXISTS idx_macro_observation_series_active_generation_generation")
    op.execute("DROP INDEX IF EXISTS idx_macro_observation_series_generations_status")
    op.execute("DROP INDEX IF EXISTS idx_macro_observation_series_rows_generation_lookup")
    op.execute("COMMENT ON TABLE equity_event_evidence_jobs IS NULL")
    op.execute("COMMENT ON TABLE macro_observation_series_active_generation IS NULL")
    op.execute("COMMENT ON TABLE macro_observation_series_generations IS NULL")
    op.execute("COMMENT ON TABLE token_radar_rank_source_events IS NULL")
