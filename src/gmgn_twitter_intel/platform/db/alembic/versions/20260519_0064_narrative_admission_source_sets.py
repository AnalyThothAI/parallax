"""Add source-set metadata to narrative admissions."""

from __future__ import annotations

from alembic import op

revision = "20260519_0064"
down_revision = "20260518_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE narrative_admissions ADD COLUMN IF NOT EXISTS projection_computed_at_ms BIGINT")
    op.execute("ALTER TABLE narrative_admissions ADD COLUMN IF NOT EXISTS source_window_start_ms BIGINT")
    op.execute("ALTER TABLE narrative_admissions ADD COLUMN IF NOT EXISTS source_window_end_ms BIGINT")
    op.execute(
        "ALTER TABLE narrative_admissions "
        "ADD COLUMN IF NOT EXISTS source_event_count BIGINT NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE narrative_admissions "
        "ADD COLUMN IF NOT EXISTS independent_author_count BIGINT NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE narrative_admissions ADD COLUMN IF NOT EXISTS admission_generation TEXT")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_narrative_admissions_projection_frontier
          ON narrative_admissions("window", scope, schema_version, projection_computed_at_ms DESC, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_narrative_admissions_source_fingerprint
          ON narrative_admissions(target_type, target_id, "window", scope, schema_version, source_fingerprint)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_narrative_admissions_source_fingerprint")
    op.execute("DROP INDEX IF EXISTS idx_narrative_admissions_projection_frontier")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN IF EXISTS admission_generation")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN IF EXISTS independent_author_count")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN IF EXISTS source_event_count")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN IF EXISTS source_window_end_ms")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN IF EXISTS source_window_start_ms")
    op.execute("ALTER TABLE narrative_admissions DROP COLUMN IF EXISTS projection_computed_at_ms")
