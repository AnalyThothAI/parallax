"""Materialize Token Radar listed-at time."""

from __future__ import annotations

from alembic import op

revision = "20260517_0054"
down_revision = "20260517_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE token_radar_rows ADD COLUMN IF NOT EXISTS listed_at_ms BIGINT")
    op.execute(
        """
        WITH latest_sets AS (
          SELECT projection_version, "window", scope, MAX(computed_at_ms) AS computed_at_ms
          FROM token_radar_rows
          GROUP BY projection_version, "window", scope
        ),
        current_rows AS (
          SELECT
            rows.row_id,
            rows.projection_version,
            rows."window",
            rows.scope,
            COALESCE(rows.target_type, '') AS target_type_key,
            COALESCE(rows.target_id, rows.intent_id) AS identity_id
          FROM token_radar_rows rows
          JOIN latest_sets
            ON latest_sets.projection_version = rows.projection_version
           AND latest_sets."window" = rows."window"
           AND latest_sets.scope = rows.scope
           AND latest_sets.computed_at_ms = rows.computed_at_ms
          WHERE rows.listed_at_ms IS NULL
        ),
        listed AS (
          SELECT current_rows.row_id, MIN(history.computed_at_ms) AS first_seen_ms
          FROM current_rows
          JOIN token_radar_rows history
            ON history.projection_version = current_rows.projection_version
           AND history."window" = current_rows."window"
           AND history.scope = current_rows.scope
           AND COALESCE(history.target_type, '') = current_rows.target_type_key
           AND COALESCE(history.target_id, history.intent_id) = current_rows.identity_id
          GROUP BY current_rows.row_id
        )
        UPDATE token_radar_rows rows
        SET listed_at_ms = listed.first_seen_ms
        FROM listed
        WHERE rows.row_id = listed.row_id
          AND rows.listed_at_ms IS NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE token_radar_rows DROP COLUMN IF EXISTS listed_at_ms")
