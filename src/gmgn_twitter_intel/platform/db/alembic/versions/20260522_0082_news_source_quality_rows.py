"""Add news source quality read model."""

from __future__ import annotations

from alembic import op

revision = "20260522_0082"
down_revision = "20260522_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS news_source_quality_rows (
          row_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL REFERENCES news_sources(source_id) ON DELETE CASCADE,
          window TEXT NOT NULL,
          computed_at_ms BIGINT NOT NULL,
          fetch_success_rate DOUBLE PRECISION,
          items_fetched INTEGER NOT NULL DEFAULT 0,
          items_inserted INTEGER NOT NULL DEFAULT 0,
          duplicate_rate DOUBLE PRECISION,
          process_success_rate DOUBLE PRECISION,
          resolved_token_rate DOUBLE PRECISION,
          attention_rate DOUBLE PRECISION,
          accepted_fact_rate DOUBLE PRECISION,
          brief_ready_rate DOUBLE PRECISION,
          median_lag_ms BIGINT,
          quality_score DOUBLE PRECISION,
          diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          projection_version TEXT NOT NULL,
          UNIQUE (source_id, window)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_news_source_quality_source_window
          ON news_source_quality_rows(source_id, window)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_news_source_quality_source_window")
    op.execute("DROP TABLE IF EXISTS news_source_quality_rows")
