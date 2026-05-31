"""Add Token Radar target projection coverage."""

from __future__ import annotations

from alembic import op

revision = "20260524_0093"
down_revision = "20260524_0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_radar_target_projection_coverage (
          projection_version TEXT NOT NULL,
          target_type_key TEXT NOT NULL,
          identity_id TEXT NOT NULL,
          latest_market_observed_at_ms BIGINT NOT NULL DEFAULT 0,
          last_projected_at_ms BIGINT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(projection_version, target_type_key, identity_id)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE token_radar_target_projection_coverage SET (
          fillfactor = 70,
          autovacuum_vacuum_scale_factor = 0.02,
          autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_projection_coverage_freshness
              ON token_radar_target_projection_coverage(
                projection_version, target_type_key, identity_id, latest_market_observed_at_ms DESC
              )
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_projection_coverage_freshness")
    op.execute("DROP TABLE IF EXISTS token_radar_target_projection_coverage")
