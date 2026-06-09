"""Add indexed News admission candidate lookups."""

from __future__ import annotations

from alembic import op

revision = "20260609_0161"
down_revision = "20260609_0160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_items_title_fingerprint_published
          ON news_items(title_fingerprint, published_at_ms DESC, news_item_id)
          WHERE title_fingerprint <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_items_content_hash_published
          ON news_items(content_hash, published_at_ms DESC, news_item_id)
          WHERE content_hash <> ''
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_items_article_url_published
          ON news_items(canonical_url, published_at_ms DESC, news_item_id)
          WHERE canonical_url <> ''
            AND url_identity_kind = 'article'
        """
    )
    op.execute("ANALYZE news_items")


def downgrade() -> None:
    pass
