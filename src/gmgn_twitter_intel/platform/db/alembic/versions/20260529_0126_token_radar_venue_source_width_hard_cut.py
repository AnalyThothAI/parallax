"""Hard-cut Token Radar venue identity and narrow source edges."""

from __future__ import annotations

from alembic import op

revision = "20260529_0126"
down_revision = "20260529_0125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM token_radar_current_rows")
    op.execute("DELETE FROM token_radar_target_first_seen")
    op.execute("DROP TABLE IF EXISTS token_radar_publication_state CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_rank_source_events CASCADE")

    op.execute("ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS venue TEXT NOT NULL DEFAULT 'all'")
    op.execute(
        """
        ALTER TABLE token_radar_current_rows
          DROP CONSTRAINT IF EXISTS token_radar_current_rows_projection_version_window_scope_lane_rank_key
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_current_rows
          DROP CONSTRAINT IF EXISTS
          token_radar_current_rows_projection_version_window_scope_lane_target_type_key_identity_id_key
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_token_radar_current_rows_generation")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_token_radar_current_rows_venue_rank
          ON token_radar_current_rows(projection_version, "window", scope, venue, lane, rank)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_token_radar_current_rows_venue_target
          ON token_radar_current_rows(projection_version, "window", scope, venue, lane, target_type_key, identity_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_generation
          ON token_radar_current_rows(projection_version, "window", scope, venue, generation_id, lane, rank)
        """
    )

    op.execute(
        """
        CREATE TABLE token_radar_publication_state (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
          venue TEXT NOT NULL DEFAULT 'all',
          current_generation_id TEXT,
          current_published_at_ms BIGINT,
          current_source_frontier_ms BIGINT,
          current_row_count BIGINT NOT NULL DEFAULT 0,
          current_source_rows BIGINT NOT NULL DEFAULT 0,
          latest_attempt_generation_id TEXT,
          latest_attempt_status TEXT NOT NULL CHECK (latest_attempt_status IN ('ready', 'failed')),
          latest_attempt_started_at_ms BIGINT,
          latest_attempt_finished_at_ms BIGINT,
          latest_attempt_error TEXT,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, "window", scope, venue),
          CHECK (latest_attempt_status = 'failed' OR current_generation_id = latest_attempt_generation_id)
        )
        """
    )

    op.execute("ALTER TABLE token_radar_target_first_seen ADD COLUMN IF NOT EXISTS venue TEXT NOT NULL DEFAULT 'all'")
    op.execute("ALTER TABLE token_radar_target_first_seen DROP CONSTRAINT IF EXISTS token_radar_target_first_seen_pkey")
    op.execute(
        """
        ALTER TABLE token_radar_target_first_seen
          ADD PRIMARY KEY(projection_version, "window", scope, venue, target_type_key, identity_id)
        """
    )

    op.execute(
        """
        CREATE TABLE token_radar_rank_source_events (
          projection_version TEXT NOT NULL,
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          source_id TEXT NOT NULL,
          event_received_at_ms BIGINT NOT NULL,
          projected_at_ms BIGINT NOT NULL,
          source_payload_hash TEXT NOT NULL,
          intent_id TEXT,
          event_id TEXT,
          resolution_id TEXT,
          target_type TEXT,
          target_id TEXT,
          pricefeed_id TEXT,
          resolution_status TEXT,
          is_watched BOOLEAN NOT NULL DEFAULT false,
          PRIMARY KEY(projection_version, target_type_key, identity_id, source_kind, source_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_token_radar_rank_source_events_target_time
          ON token_radar_rank_source_events(
            projection_version,
            target_type_key,
            identity_id,
            event_received_at_ms DESC,
            source_id
          )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_token_radar_rank_source_events_watched
          ON token_radar_rank_source_events(projection_version, event_received_at_ms DESC)
          WHERE is_watched = true
        """
    )

    op.execute("ALTER TABLE token_radar_dirty_targets DROP COLUMN IF EXISTS source_event_ids_json")
    op.execute("ALTER TABLE token_radar_dirty_targets DROP COLUMN IF EXISTS source_dirty")
    op.execute(
        """
        CREATE TABLE token_radar_source_dirty_events (
          projection_version TEXT NOT NULL,
          source_event_id TEXT NOT NULL,
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          dirty_reason TEXT NOT NULL,
          payload_hash TEXT NOT NULL,
          due_at_ms BIGINT NOT NULL,
          leased_until_ms BIGINT,
          lease_owner TEXT,
          attempt_count BIGINT NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
          last_error TEXT,
          first_dirty_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, source_event_id, target_type_key, identity_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_token_radar_source_dirty_events_claim
          ON token_radar_source_dirty_events(
            due_at_ms ASC, updated_at_ms ASC, source_event_id, target_type_key, identity_id
          )
        """
    )


def downgrade() -> None:
    """No compatibility downgrade for the hard-cut derived read models."""
