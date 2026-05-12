"""Hard cut search v2 FTS and trigram indexes."""

from __future__ import annotations

from alembic import op

revision = "20260512_0031"
down_revision = "20260511_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("DROP INDEX IF EXISTS idx_events_search_tsv")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS search_tsv")
    op.execute(
        """
        ALTER TABLE events
          ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('simple', coalesce(search_text, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(search_text, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(author_handle, '')), 'D')
          ) STORED
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_search_tsv ON events USING GIN(search_tsv)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_search_text_trgm
          ON events USING GIN(search_text gin_trgm_ops)
          WHERE search_text IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_events_search_text_trgm")
    op.execute("DROP INDEX IF EXISTS idx_events_search_tsv")
    op.execute("ALTER TABLE events DROP COLUMN IF EXISTS search_tsv")
    op.execute(
        """
        ALTER TABLE events
          ADD COLUMN search_tsv tsvector GENERATED ALWAYS AS (
            setweight(to_tsvector('simple', coalesce(author_handle, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(search_text, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(text_clean, '')), 'C')
          ) STORED
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_events_search_tsv ON events USING GIN(search_tsv)")
