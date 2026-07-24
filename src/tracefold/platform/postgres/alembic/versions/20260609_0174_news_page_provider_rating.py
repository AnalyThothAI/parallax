"""Expose News provider rating evidence on page rows."""

from __future__ import annotations

from alembic import op

revision = "20260609_0174"
down_revision = "20260609_0173"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS provider_rating_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        UPDATE news_page_rows AS rows
           SET provider_rating_json = jsonb_strip_nulls(
             jsonb_build_object(
               'provider', items.provider_signal_json ->> 'provider',
               'status', items.provider_signal_json ->> 'status',
               'direction', items.provider_signal_json ->> 'direction',
               'signal', items.provider_signal_json ->> 'signal',
               'score',
                 CASE
                   WHEN COALESCE(items.provider_signal_json ->> 'score', '') ~ '^-?[0-9]+$'
                   THEN (items.provider_signal_json ->> 'score')::integer
                   ELSE NULL
                 END,
               'grade', items.provider_signal_json ->> 'grade',
               'method', items.provider_signal_json ->> 'method'
             )
           )
          FROM news_items AS items
         WHERE rows.news_item_id = items.news_item_id
           AND rows.projection_version = 'news_page_rows_v5'
        """
    )
    op.execute("ANALYZE news_page_rows")


def downgrade() -> None:
    pass
