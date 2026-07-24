"""Allow CryptoPanic news source provider type."""

from __future__ import annotations

from alembic import op

revision = "20260521_0075"
down_revision = "20260521_0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_provider_type_check")
    op.execute(
        """
        ALTER TABLE news_sources
          ADD CONSTRAINT news_sources_provider_type_check
          CHECK (provider_type IN ('rss', 'atom', 'json_feed', 'cryptopanic'))
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM news_sources WHERE provider_type = 'cryptopanic'")
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_provider_type_check")
    op.execute(
        """
        ALTER TABLE news_sources
          ADD CONSTRAINT news_sources_provider_type_check
          CHECK (provider_type IN ('rss', 'atom', 'json_feed'))
        """
    )
