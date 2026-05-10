"""Add message attribution to price observations."""

from __future__ import annotations

from alembic import op

revision = "20260508_0011"
down_revision = "20260507_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE price_observations
        ADD COLUMN IF NOT EXISTS source_event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE price_observations
        ADD COLUMN IF NOT EXISTS source_intent_id TEXT REFERENCES token_intents(intent_id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE price_observations
        ADD COLUMN IF NOT EXISTS source_resolution_id TEXT
          REFERENCES token_intent_resolutions(resolution_id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS observation_kind TEXT
        """
    )
    op.execute("ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS event_received_at_ms BIGINT")
    op.execute("ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS observation_lag_ms BIGINT")
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_source_event
              ON price_observations(source_event_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_source_intent
              ON price_observations(source_intent_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_source_resolution
              ON price_observations(source_resolution_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_subject_time_kind
              ON price_observations(subject_type, subject_id, observed_at_ms DESC, observation_kind)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_subject_time_kind")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_source_resolution")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_source_intent")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_source_event")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS observation_lag_ms")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS event_received_at_ms")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS observation_kind")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS source_resolution_id")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS source_intent_id")
    op.execute("ALTER TABLE price_observations DROP COLUMN IF EXISTS source_event_id")
