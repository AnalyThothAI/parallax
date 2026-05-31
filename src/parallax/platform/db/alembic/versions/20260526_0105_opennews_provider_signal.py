"""Add OpenNews provider signal material facts."""

from __future__ import annotations

from alembic import op

revision = "20260526_0105"
down_revision = "20260526_0104"
branch_labels = None
depends_on = None

_PROVIDER_TYPES = (
    "rss",
    "atom",
    "json_feed",
    "cryptopanic",
    "openbb",
    "telegram_public",
    "twitter_profile",
    "twitter_thread_context",
    "reddit",
    "hackernews",
    "github",
    "ossinsight",
    "manual_api",
    "opennews",
)
_PREVIOUS_PROVIDER_TYPES = tuple(value for value in _PROVIDER_TYPES if value != "opennews")


def upgrade() -> None:
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_provider_type_check")
    _add_provider_type_constraint(_PROVIDER_TYPES)
    op.execute(
        """
        ALTER TABLE news_items
          ADD COLUMN IF NOT EXISTS provider_signal_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE news_items
          ADD COLUMN IF NOT EXISTS provider_token_impacts_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS signal_json JSONB NOT NULL DEFAULT '{}'::jsonb
        """
    )
    op.execute(
        """
        ALTER TABLE news_page_rows
          ADD COLUMN IF NOT EXISTS token_impacts_json JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    op.execute(
        """
        UPDATE news_page_rows
           SET signal_json = CASE
                 WHEN agent_brief_json ->> 'status' = 'ready' THEN
                   jsonb_build_object(
                     'source', 'agent',
                     'status', 'ready',
                     'direction', COALESCE(NULLIF(agent_brief_json ->> 'direction', ''), 'neutral'),
                     'method', 'news_item_brief'
                   )
                 ELSE
                   jsonb_build_object(
                     'source', 'partial',
                     'status', 'partial',
                     'direction', 'neutral',
                     'method', 'pending'
                   )
               END
         WHERE signal_json = '{}'::jsonb
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_items_provider_signal_direction
          ON news_items ((provider_signal_json ->> 'direction'))
          WHERE provider_signal_json <> '{}'::jsonb
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_page_rows_signal_direction
          ON news_page_rows ((signal_json ->> 'direction'), latest_at_ms DESC)
          WHERE signal_json <> '{}'::jsonb
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_page_rows_signal_score
          ON news_page_rows (((signal_json ->> 'score')::int), latest_at_ms DESC)
          WHERE signal_json ? 'score'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_news_page_rows_token_count_time
          ON news_page_rows ((jsonb_array_length(token_lanes_json)), latest_at_ms DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_news_page_rows_token_count_time")
    op.execute("DROP INDEX IF EXISTS ix_news_page_rows_signal_score")
    op.execute("DROP INDEX IF EXISTS ix_news_page_rows_signal_direction")
    op.execute("DROP INDEX IF EXISTS ix_news_items_provider_signal_direction")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS token_impacts_json")
    op.execute("ALTER TABLE news_page_rows DROP COLUMN IF EXISTS signal_json")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS provider_token_impacts_json")
    op.execute("ALTER TABLE news_items DROP COLUMN IF EXISTS provider_signal_json")
    op.execute("DELETE FROM news_sources WHERE provider_type = 'opennews'")
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_provider_type_check")
    _add_provider_type_constraint(_PREVIOUS_PROVIDER_TYPES)


def _add_provider_type_constraint(values: tuple[str, ...]) -> None:
    op.execute(
        f"""
        ALTER TABLE news_sources
          ADD CONSTRAINT news_sources_provider_type_check
          CHECK (provider_type IN ({_quoted_list(values)}))
        """
    )


def _quoted_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)
