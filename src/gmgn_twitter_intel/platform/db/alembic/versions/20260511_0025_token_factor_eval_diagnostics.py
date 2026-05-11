"""Add token factor evaluation diagnostics columns and indexes."""

from __future__ import annotations

from alembic import op

revision = "20260511_0025"
down_revision = "20260511_0024"
branch_labels = None
depends_on = None

SETTLEMENT_INDEXES = (
    "idx_token_score_evaluations_generated",
    "idx_token_radar_rows_settlement",
    "idx_price_observations_subject_price_after",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE token_score_evaluations
          ADD COLUMN IF NOT EXISTS sample_start_ms BIGINT,
          ADD COLUMN IF NOT EXISTS sample_end_ms BIGINT,
          ADD COLUMN IF NOT EXISTS spearman_ic DOUBLE PRECISION,
          ADD COLUMN IF NOT EXISTS icir DOUBLE PRECISION,
          ADD COLUMN IF NOT EXISTS score_stddev DOUBLE PRECISION,
          ADD COLUMN IF NOT EXISTS diagnostics_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    for index_name in SETTLEMENT_INDEXES:
        _drop_invalid_index(index_name)
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_score_evaluations_generated
              ON token_score_evaluations(horizon, "window", scope, score_version, generated_at_ms DESC)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_radar_rows_settlement
              ON token_radar_rows(factor_version, "window", scope, computed_at_ms, target_type, target_id)
            """
        )
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_observations_subject_price_after
              ON price_observations(subject_type, subject_id, observed_at_ms ASC, observation_id ASC)
              WHERE price_usd IS NOT NULL
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_price_observations_subject_price_after")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_radar_rows_settlement")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_token_score_evaluations_generated")
    op.execute(
        """
        ALTER TABLE token_score_evaluations
          DROP COLUMN IF EXISTS diagnostics_json,
          DROP COLUMN IF EXISTS score_stddev,
          DROP COLUMN IF EXISTS icir,
          DROP COLUMN IF EXISTS spearman_ic,
          DROP COLUMN IF EXISTS sample_end_ms,
          DROP COLUMN IF EXISTS sample_start_ms
        """
    )


def _drop_invalid_index(index_name: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM pg_class cls
            JOIN pg_namespace ns ON ns.oid = cls.relnamespace
            JOIN pg_index idx ON idx.indexrelid = cls.oid
            WHERE ns.nspname = 'public'
              AND cls.relname = '{index_name}'
              AND idx.indisvalid = false
          ) THEN
            EXECUTE 'DROP INDEX IF EXISTS public.{index_name}';
          END IF;
        END $$;
        """
    )
