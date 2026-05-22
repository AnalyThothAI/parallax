"""Add news source chain classification fields."""

from __future__ import annotations

from alembic import op

revision = "20260522_0081"
down_revision = "20260521_0080"
branch_labels = None
depends_on = None

PROVIDER_TYPES = (
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
)
PREVIOUS_PROVIDER_TYPES = ("rss", "atom", "json_feed", "cryptopanic")
SOURCE_ROLES = (
    "official_exchange",
    "official_regulator",
    "official_protocol",
    "official_issuer",
    "specialist_media",
    "aggregator",
    "social",
    "community",
    "developer_signal",
    "observed_source",
)
PREVIOUS_SOURCE_ROLES = (
    "official_exchange",
    "official_regulator",
    "official_protocol",
    "official_issuer",
    "specialist_media",
    "aggregator",
    "social",
    "observed_source",
)


def upgrade() -> None:
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_provider_type_check")
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_source_role_check")
    op.execute(
        "ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS coverage_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS asset_universe_json JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS authority_scope_json JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute("ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS fetch_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute(
        "ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS context_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute("ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS cost_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute(
        "ALTER TABLE news_sources ADD COLUMN IF NOT EXISTS source_quality_status TEXT NOT NULL DEFAULT 'unknown'"
    )
    _add_provider_type_constraint(PROVIDER_TYPES)
    _add_source_role_constraint(SOURCE_ROLES)


def downgrade() -> None:
    # Rows with new provider/source-role values must be removed before restoring old constraints.
    op.execute(f"DELETE FROM news_sources WHERE provider_type NOT IN ({_quoted_list(PREVIOUS_PROVIDER_TYPES)})")
    op.execute(f"DELETE FROM news_sources WHERE source_role NOT IN ({_quoted_list(PREVIOUS_SOURCE_ROLES)})")
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_provider_type_check")
    op.execute("ALTER TABLE news_sources DROP CONSTRAINT IF EXISTS news_sources_source_role_check")
    op.execute("ALTER TABLE news_sources DROP COLUMN IF EXISTS source_quality_status")
    op.execute("ALTER TABLE news_sources DROP COLUMN IF EXISTS cost_policy_json")
    op.execute("ALTER TABLE news_sources DROP COLUMN IF EXISTS context_policy_json")
    op.execute("ALTER TABLE news_sources DROP COLUMN IF EXISTS fetch_policy_json")
    op.execute("ALTER TABLE news_sources DROP COLUMN IF EXISTS authority_scope_json")
    op.execute("ALTER TABLE news_sources DROP COLUMN IF EXISTS asset_universe_json")
    op.execute("ALTER TABLE news_sources DROP COLUMN IF EXISTS coverage_tags_json")
    _add_provider_type_constraint(PREVIOUS_PROVIDER_TYPES)
    _add_source_role_constraint(PREVIOUS_SOURCE_ROLES)


def _add_provider_type_constraint(values: tuple[str, ...]) -> None:
    op.execute(
        f"""
        ALTER TABLE news_sources
          ADD CONSTRAINT news_sources_provider_type_check
          CHECK (provider_type IN ({_quoted_list(values)}))
        """
    )


def _add_source_role_constraint(values: tuple[str, ...]) -> None:
    op.execute(
        f"""
        ALTER TABLE news_sources
          ADD CONSTRAINT news_sources_source_role_check
          CHECK (source_role IN ({_quoted_list(values)}))
        """
    )


def _quoted_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)
