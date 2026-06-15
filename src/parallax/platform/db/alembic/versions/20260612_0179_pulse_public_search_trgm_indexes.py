"""Add Signal Pulse public search trigram indexes."""

from __future__ import annotations

from alembic import op

revision = "20260612_0179"
down_revision = "20260612_0178"
branch_labels = None
depends_on = None


_CREATE_INDEXES_SQL = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pulse_candidates_symbol_trgm
      ON pulse_candidates USING GIN (symbol gin_trgm_ops)
      WHERE symbol IS NOT NULL
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pulse_candidates_subject_key_trgm
      ON pulse_candidates USING GIN (subject_key gin_trgm_ops)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pulse_candidates_target_id_trgm
      ON pulse_candidates USING GIN (target_id gin_trgm_ops)
      WHERE target_id IS NOT NULL
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pulse_agent_jobs_subject_key_trgm
      ON pulse_agent_jobs USING GIN (subject_key gin_trgm_ops)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pulse_agent_jobs_target_id_trgm
      ON pulse_agent_jobs USING GIN (target_id gin_trgm_ops)
      WHERE target_id IS NOT NULL
    """,
)

_DROP_INDEXES_SQL = (
    "DROP INDEX CONCURRENTLY IF EXISTS idx_pulse_agent_jobs_target_id_trgm",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_pulse_agent_jobs_subject_key_trgm",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_pulse_candidates_target_id_trgm",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_pulse_candidates_subject_key_trgm",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_pulse_candidates_symbol_trgm",
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for sql in _CREATE_INDEXES_SQL:
            op.execute(sql)
        op.execute("ANALYZE pulse_candidates")
        op.execute("ANALYZE pulse_agent_jobs")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for sql in _DROP_INDEXES_SQL:
            op.execute(sql)
