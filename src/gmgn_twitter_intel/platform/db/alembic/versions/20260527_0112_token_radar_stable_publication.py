"""Make Token Radar current rows content-stable and quality-explicit."""

from __future__ import annotations

from alembic import op

revision = "20260527_0112"
down_revision = "20260527_0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM token_radar_current_rows;")

    op.execute("ALTER TABLE token_radar_current_rows DROP COLUMN IF EXISTS asset_json")
    op.execute("ALTER TABLE token_radar_current_rows DROP COLUMN IF EXISTS primary_venue_json")
    op.execute("ALTER TABLE token_radar_current_rows DROP COLUMN IF EXISTS target_json")
    op.execute("ALTER TABLE token_radar_current_rows DROP COLUMN IF EXISTS attention_json")
    op.execute("ALTER TABLE token_radar_current_rows DROP COLUMN IF EXISTS market_json")
    op.execute("ALTER TABLE token_radar_current_rows DROP COLUMN IF EXISTS price_json")
    op.execute("ALTER TABLE token_radar_current_rows DROP COLUMN IF EXISTS score_json")

    op.execute("ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS rank_score DOUBLE PRECISION")
    op.execute("ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS quality_status TEXT")
    op.execute(
        "ALTER TABLE token_radar_current_rows "
        "ADD COLUMN IF NOT EXISTS degraded_reasons_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE token_radar_current_rows ALTER COLUMN rank_score SET NOT NULL")
    op.execute("ALTER TABLE token_radar_current_rows ALTER COLUMN quality_status SET NOT NULL")
    op.execute(
        """
        ALTER TABLE token_radar_current_rows
        DROP CONSTRAINT IF EXISTS ck_token_radar_current_rows_quality_status
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_current_rows
        ADD CONSTRAINT ck_token_radar_current_rows_quality_status
        CHECK (quality_status IN ('ready', 'degraded', 'insufficient', 'failed'))
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260527_0112 token-radar stable-publication hard-cut migration is not safely reversible; "
        "rollback requires restoring a pre-migration backup."
    )
