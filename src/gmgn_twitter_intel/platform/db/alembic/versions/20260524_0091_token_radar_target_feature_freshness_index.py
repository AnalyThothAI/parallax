"""Add Token Radar target feature freshness lookup index."""

from __future__ import annotations

from alembic import op

revision = "20260524_0091"
down_revision = "20260523_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_target_features_freshness
            ON token_radar_target_features(
              projection_version,
              target_type_key,
              identity_id,
              latest_market_observed_at_ms DESC
            )
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_target_features_freshness")
