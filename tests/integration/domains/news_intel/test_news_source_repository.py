from __future__ import annotations

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.news_intel.repositories.news_item_repository import NewsItemRepository
from parallax.domains.news_intel.repositories.news_page_repository import NewsPageRepository
from parallax.domains.news_intel.repositories.news_source_repository import NewsSourceRepository
from parallax.domains.news_intel.repositories.news_story_agent_repository import NewsStoryAgentRepository
from parallax.domains.news_intel.types import NewsSourceConfig
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_repository_session_binds_four_concrete_news_repositories(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = _repositories(conn)
    finally:
        conn.close()

    assert isinstance(repos.news_sources, NewsSourceRepository)
    assert isinstance(repos.news_items, NewsItemRepository)
    assert isinstance(repos.news_story_agents, NewsStoryAgentRepository)
    assert isinstance(repos.news_pages, NewsPageRepository)
    assert not hasattr(repos, "news")


def test_reconcile_configured_sources_updates_and_disables_by_source_id(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = _repositories(conn)
        with repos.transaction():
            repos.news_sources.upsert_source(
                source_id="removed-source",
                provider_type="rss",
                feed_url="https://removed.example/rss.xml",
                source_domain="removed.example",
                source_name="Removed",
                now_ms=NOW_MS,
            )
            repos.news_sources.upsert_source(
                source_id="configured-source",
                provider_type="rss",
                feed_url="https://old.example/rss.xml",
                source_domain="old.example",
                source_name="Old Configured",
                now_ms=NOW_MS,
            )
            changes = repos.news_sources.reconcile_configured_sources(
                [
                    NewsSourceConfig(
                        source_id="configured-source",
                        provider_type="github",
                        feed_url="https://api.github.com/repos/ethereum/go-ethereum/releases",
                        source_domain="github.com",
                        source_name="go-ethereum releases",
                        source_role="developer_signal",
                        trust_tier="official",
                        refresh_interval_seconds=120,
                        coverage_tags=("ethereum", "protocol"),
                        asset_universe=("eth",),
                        authority_scope={"project": "ethereum"},
                    ),
                    NewsSourceConfig(
                        source_id="new-source",
                        provider_type="reddit",
                        feed_url="https://www.reddit.com/r/ethfinance/new.json",
                        source_domain="reddit.com",
                        source_name="r/ethfinance",
                        source_role="community",
                        trust_tier="standard",
                        refresh_interval_seconds=300,
                    ),
                ],
                now_ms=NOW_MS + 10,
            )
        stored = {
            str(row["source_id"]): row
            for row in conn.execute("SELECT * FROM news_sources ORDER BY source_id").fetchall()
        }
    finally:
        conn.close()

    assert [(row["source_id"], row["status"]) for row in changes] == [
        ("configured-source", "updated"),
        ("new-source", "inserted"),
        ("removed-source", "disabled"),
    ]
    assert stored["configured-source"]["enabled"] is True
    assert stored["configured-source"]["provider_type"] == "github"
    assert stored["configured-source"]["coverage_tags_json"] == ["ethereum", "protocol"]
    assert stored["removed-source"]["enabled"] is False


def _repositories(conn):
    return repositories_for_connection(
        conn,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )
