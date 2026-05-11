"""Hard-cut Token Radar anchor/live market boundary."""

from __future__ import annotations

from alembic import op

revision = "20260511_0029"
down_revision = "20260511_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE price_observations, token_market_price_baselines")
    with op.get_context().autocommit_block():
        for name in (
            "idx_current_market_field_facts_latest",
            "idx_price_observations_current_price",
            "idx_price_observations_current_market_cap",
            "idx_price_observations_current_liquidity",
            "idx_price_observations_current_holders",
            "idx_price_observations_current_volume_24h",
            "idx_price_observations_current_open_interest",
            "idx_price_observations_message_resolution_latest",
        ):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_price_observations_message_anchor_resolution
            ON price_observations(source_resolution_id)
            WHERE observation_kind = 'message_anchor' AND source_resolution_id IS NOT NULL
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_anchor_subject_time
            ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_id DESC)
            WHERE observation_kind = 'message_anchor'
            """
        )
    op.execute("DROP TABLE IF EXISTS current_market_field_facts")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS current_market_field_facts (
          subject_type TEXT NOT NULL,
          subject_id TEXT NOT NULL,
          field_key TEXT NOT NULL,
          value_json JSONB NOT NULL,
          observed_at_ms BIGINT NOT NULL,
          provider TEXT NOT NULL,
          source_observation_id TEXT NOT NULL,
          updated_at_ms BIGINT NOT NULL,
          PRIMARY KEY(subject_type, subject_id, field_key, source_observation_id)
        )
        """
    )
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_anchor_subject_time")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_price_observations_message_anchor_resolution")
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_current_market_field_facts_latest
            ON current_market_field_facts(
              subject_type, subject_id, field_key, observed_at_ms DESC, source_observation_id DESC
            )
            """
        )
