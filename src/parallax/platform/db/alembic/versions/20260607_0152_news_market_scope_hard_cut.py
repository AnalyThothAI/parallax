"""Hard-cut News market scope and drop legacy admission gates."""

from __future__ import annotations

from alembic import op

revision = "20260607_0152"
down_revision = "20260606_0152"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute("ALTER TABLE news_items ADD COLUMN IF NOT EXISTS market_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute(
        "ALTER TABLE news_page_rows ADD COLUMN IF NOT EXISTS market_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_analysis_admission_published")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_page_rows_analysis_admission")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_items_agent_requirement_published")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    for statement in (
        "ALTER TABLE news_items DROP COLUMN IF EXISTS analysis_admission_status",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS analysis_admission_reason",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS analysis_admission_json",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS analysis_admission_version",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS analysis_admission_computed_at_ms",
        "ALTER TABLE news_page_rows DROP COLUMN IF EXISTS analysis_admission_status",
        "ALTER TABLE news_page_rows DROP COLUMN IF EXISTS analysis_admission_reason",
        "ALTER TABLE news_page_rows DROP COLUMN IF EXISTS analysis_admission_json",
        "ALTER TABLE news_page_rows DROP COLUMN IF EXISTS analysis_admission_version",
        "ALTER TABLE news_page_rows DROP COLUMN IF EXISTS analysis_admission_computed_at_ms",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS agent_requirement_status",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS agent_requirement_reason",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS agent_requirement_priority",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS agent_requirement_json",
        "ALTER TABLE news_items DROP COLUMN IF EXISTS agent_requirement_version",
    ):
        op.execute(statement)
    op.execute("ANALYZE news_items")
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    raise RuntimeError(
        "20260607_0152 is a News market-scope hard cut. Downgrade would recreate "
        "legacy crypto-only product gates and is intentionally unsupported."
    )
