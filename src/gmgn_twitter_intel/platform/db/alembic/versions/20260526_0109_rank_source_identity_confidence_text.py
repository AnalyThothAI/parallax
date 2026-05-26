"""Align Token Radar rank-source identity confidence with asset identity facts."""

from __future__ import annotations

from alembic import op

revision = "20260526_0109"
down_revision = "20260526_0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE token_radar_rank_source_events
          ALTER COLUMN asset_identity_confidence TYPE TEXT
          USING asset_identity_confidence::text
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE token_radar_rank_source_events
          ALTER COLUMN asset_identity_confidence TYPE DOUBLE PRECISION
          USING CASE
            WHEN asset_identity_confidence IS NULL OR asset_identity_confidence = '' THEN NULL
            WHEN asset_identity_confidence ~ '^-?[0-9]+(\\.[0-9]+)?$'
              THEN asset_identity_confidence::double precision
            ELSE NULL
          END
        """
    )
