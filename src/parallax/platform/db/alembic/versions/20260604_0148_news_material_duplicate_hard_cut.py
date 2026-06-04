"""Allow News material duplicate observation edges."""

from __future__ import annotations

from alembic import op

revision = "20260604_0148"
down_revision = "20260603_0142"
branch_labels = None
depends_on = None


_RELAX_EDGE_MATCH_TYPE_CONSTRAINT_SQL = """
ALTER TABLE news_item_observation_edges
  DROP CONSTRAINT IF EXISTS news_item_observation_edges_match_type_check;

ALTER TABLE news_item_observation_edges
  ADD CONSTRAINT news_item_observation_edges_match_type_check
  CHECK (
    match_type = ANY (
      ARRAY[
        'same_provider_article_id',
        'same_article_url',
        'same_canonical_url',
        'same_content_hash',
        'same_material_title',
        'weak_title_time_source'
      ]::text[]
    )
  )
"""

_CREATE_MATERIAL_LOOKUP_INDEX_SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_items_source_published_material_lookup
  ON news_items(source_id, published_at_ms DESC, news_item_id)
"""


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(_RELAX_EDGE_MATCH_TYPE_CONSTRAINT_SQL)

    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        op.execute("SET statement_timeout = '30min'")
        op.execute(_CREATE_MATERIAL_LOOKUP_INDEX_SQL)
        op.execute("ANALYZE news_items")
        op.execute("RESET lock_timeout")
        op.execute("RESET statement_timeout")


def downgrade() -> None:
    raise RuntimeError(
        "20260604_0148 News material duplicate hard cut is not safely reversible; "
        "same_material_title edges may already exist"
    )
