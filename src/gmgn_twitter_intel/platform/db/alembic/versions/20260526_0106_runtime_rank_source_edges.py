"""Add compact Token Radar rank source edge read model."""

from __future__ import annotations

from alembic import op

revision = "20260526_0106"
down_revision = "20260526_0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_rank_source_events (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          lane TEXT NOT NULL,
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_id TEXT NOT NULL,
          event_received_at_ms BIGINT NOT NULL,
          source_rank INTEGER NOT NULL DEFAULT 0,
          projected_at_ms BIGINT NOT NULL,
          PRIMARY KEY (
            projection_version,
            "window",
            scope,
            lane,
            target_type_key,
            identity_id,
            source_kind,
            source_id
          ),
          CHECK (source_kind IN ('event', 'intent', 'resolution'))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_target
          ON token_radar_rank_source_events(
            projection_version,
            "window",
            scope,
            target_type_key,
            identity_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_source
          ON token_radar_rank_source_events(source_kind, source_id, event_received_at_ms DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_rank_source_events_recent
          ON token_radar_rank_source_events(
            projection_version,
            "window",
            scope,
            event_received_at_ms DESC
          )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rank_source_events_recent")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rank_source_events_source")
    op.execute("DROP INDEX IF EXISTS idx_token_radar_rank_source_events_target")
    op.execute("DROP TABLE IF EXISTS token_radar_rank_source_events")
