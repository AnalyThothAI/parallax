"""Add token radar factor snapshot hard-cut storage."""

from __future__ import annotations

from alembic import op

revision = "20260510_0022"
down_revision = "20260510_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE token_radar_rows
          ADD COLUMN IF NOT EXISTS factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_rows
          ADD COLUMN IF NOT EXISTS factor_version TEXT NOT NULL DEFAULT 'token_factor_snapshot_v3_social_attention'
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_candidates
          ADD COLUMN IF NOT EXISTS factor_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_candidates
          ADD COLUMN IF NOT EXISTS agent_recommendation_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE pulse_candidates
          ADD COLUMN IF NOT EXISTS gate_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rows_factor_version
          ON token_radar_rows(projection_version, factor_version, "window", scope, computed_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pulse_candidates_factor_snapshot_gate
          ON pulse_candidates(pulse_version, "window", scope, updated_at_ms DESC)
          WHERE factor_snapshot_json <> '{}'::jsonb
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pulse_candidates_factor_snapshot_gate")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rows_factor_version")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS gate_json")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS agent_recommendation_json")
    op.execute("ALTER TABLE pulse_candidates DROP COLUMN IF EXISTS factor_snapshot_json")
    op.execute("ALTER TABLE token_radar_rows DROP COLUMN IF EXISTS factor_version")
    op.execute("ALTER TABLE token_radar_rows DROP COLUMN IF EXISTS factor_snapshot_json")
