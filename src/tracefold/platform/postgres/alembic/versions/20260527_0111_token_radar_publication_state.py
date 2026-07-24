"""Hard-cut Token Radar online service state to current rows plus publication state."""

from __future__ import annotations

from alembic import op

revision = "20260527_0111"
down_revision = "20260526_0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM token_radar_current_rows")
    op.execute("DROP TABLE IF EXISTS token_radar_rank_history CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_snapshot_audit CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_publication_state CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_projection_coverage CASCADE")
    op.execute("DROP TABLE IF EXISTS token_radar_target_projection_coverage CASCADE")

    op.execute("ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS generation_id TEXT")
    op.execute("ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS published_at_ms BIGINT")
    op.execute("ALTER TABLE token_radar_current_rows ADD COLUMN IF NOT EXISTS source_frontier_ms BIGINT")
    op.execute("ALTER TABLE token_radar_current_rows ALTER COLUMN generation_id SET NOT NULL")
    op.execute("ALTER TABLE token_radar_current_rows ALTER COLUMN published_at_ms SET NOT NULL")
    op.execute("ALTER TABLE token_radar_current_rows ALTER COLUMN source_frontier_ms SET NOT NULL")
    op.execute("ALTER TABLE token_radar_target_features DROP COLUMN IF EXISTS rank_input_version")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_current_rows_generation
          ON token_radar_current_rows(
            projection_version, "window", scope, generation_id, lane, rank
          )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_publication_state (
          projection_version TEXT NOT NULL,
          "window" TEXT NOT NULL,
          scope TEXT NOT NULL,
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
          PRIMARY KEY(projection_version, "window", scope),
          CHECK (latest_attempt_status = 'failed' OR current_generation_id = latest_attempt_generation_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_publication_state SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_radar_publication_state_current
          ON token_radar_publication_state(
            projection_version, "window", scope, latest_attempt_status, current_generation_id
          )
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "20260527_0111 token-radar publication-state hard-cut migration is not safely reversible; "
        "rollback requires restoring a pre-migration backup."
    )
