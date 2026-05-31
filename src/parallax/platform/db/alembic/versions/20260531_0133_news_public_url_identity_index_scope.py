"""Scope News public URL uniqueness to hard canonical URL identities."""

from __future__ import annotations

from alembic import op

revision = "20260531_0133"
down_revision = "20260531_0132"
branch_labels = None
depends_on = None


_DROP_PUBLIC_CANONICAL_URL_INDEX_SQL = """
DROP INDEX CONCURRENTLY IF EXISTS ux_news_items_public_canonical_url
"""

_CREATE_PUBLIC_CANONICAL_URL_INDEX_SQL = """
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_news_items_public_canonical_url
  ON news_items(canonical_url)
  WHERE canonical_url ~* '^https?://'
    AND canonical_item_key = ('canonical-url:' || canonical_url)
"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_DROP_PUBLIC_CANONICAL_URL_INDEX_SQL)
        op.execute(_CREATE_PUBLIC_CANONICAL_URL_INDEX_SQL)
        op.execute("ANALYZE news_items")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    raise RuntimeError(
        "20260531_0133 News public URL identity index scope is not safely reversible; "
        "restore from backup or apply an explicit forward repair migration"
    )
