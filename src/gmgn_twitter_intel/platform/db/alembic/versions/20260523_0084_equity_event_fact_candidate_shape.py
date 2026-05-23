"""Backfill equity event fact candidate typed fields."""

from __future__ import annotations

from alembic import op

revision = "20260523_0084"
down_revision = "20260523_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in (
        "ADD COLUMN IF NOT EXISTS source_span_id TEXT",
        "ADD COLUMN IF NOT EXISTS company_id TEXT",
        "ADD COLUMN IF NOT EXISTS ticker TEXT",
        "ADD COLUMN IF NOT EXISTS event_type TEXT",
        "ADD COLUMN IF NOT EXISTS metric_name TEXT",
        "ADD COLUMN IF NOT EXISTS value_numeric DOUBLE PRECISION",
        "ADD COLUMN IF NOT EXISTS value_unit TEXT",
        "ADD COLUMN IF NOT EXISTS period TEXT",
        "ADD COLUMN IF NOT EXISTS direction TEXT",
        "ADD COLUMN IF NOT EXISTS required_slots_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ADD COLUMN IF NOT EXISTS evidence_span_start INTEGER NOT NULL DEFAULT 0",
        "ADD COLUMN IF NOT EXISTS evidence_span_end INTEGER NOT NULL DEFAULT 0",
    ):
        op.execute(f"ALTER TABLE equity_event_fact_candidates {statement}")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM pg_constraint
             WHERE conname = 'equity_event_fact_candidates_source_span_id_fkey'
          ) THEN
            ALTER TABLE equity_event_fact_candidates
              ADD CONSTRAINT equity_event_fact_candidates_source_span_id_fkey
              FOREIGN KEY (source_span_id)
              REFERENCES equity_event_source_spans(span_id)
              ON DELETE SET NULL;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE equity_event_fact_candidates
          DROP CONSTRAINT IF EXISTS equity_event_fact_candidates_source_span_id_fkey
        """
    )
    for column in (
        "evidence_span_end",
        "evidence_span_start",
        "required_slots_json",
        "direction",
        "period",
        "value_unit",
        "value_numeric",
        "metric_name",
        "event_type",
        "ticker",
        "company_id",
        "source_span_id",
    ):
        op.execute(f"ALTER TABLE equity_event_fact_candidates DROP COLUMN IF EXISTS {column}")
