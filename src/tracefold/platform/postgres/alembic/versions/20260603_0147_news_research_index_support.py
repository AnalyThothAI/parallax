"""Add News research read search indexes."""

from __future__ import annotations

from alembic import op

revision = "20260603_0147"
down_revision = "20260603_0146"
branch_labels = None
depends_on = None


_CREATE_NEWS_RESEARCH_INDEXES_SQL = (
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_token_mentions_symbol_upper_item
      ON news_token_mentions (
        upper(COALESCE(display_symbol, observed_symbol, '')),
        news_item_id
      )
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_news_fact_candidates_claim_trgm_valid
      ON news_fact_candidates USING GIN (claim gin_trgm_ops)
      WHERE validation_status <> 'rejected'
    """,
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        for statement in _CREATE_NEWS_RESEARCH_INDEXES_SQL:
            op.execute(statement)
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_fact_candidates_claim_trgm_valid")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_news_token_mentions_symbol_upper_item")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")
