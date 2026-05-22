from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
from gmgn_twitter_intel.domains.news_intel.types import NewsSourceConfig
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_reconcile_configured_sources_persists_classification_and_disables_removed_sources(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="removed-source",
            provider_type="rss",
            feed_url="https://removed.example/rss.xml",
            source_domain="removed.example",
            source_name="Removed",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        repo.upsert_source(
            source_id="configured-source",
            provider_type="rss",
            feed_url="https://old.example/rss.xml",
            source_domain="old.example",
            source_name="Old Configured",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        conn.execute(
            "UPDATE news_sources SET source_quality_status = 'verified' WHERE source_id = 'configured-source'"
        )

        rows = repo.reconcile_configured_sources(
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
                    fetch_policy={"kind": "releases"},
                    context_policy={"thread_depth": 2},
                    cost_policy={"budget": "low"},
                ),
                {
                    "source_id": "community-source",
                    "provider_type": "reddit",
                    "feed_url": "https://www.reddit.com/r/ethfinance/new.json",
                    "source_domain": "reddit.com",
                    "source_name": "r/ethfinance",
                    "source_role": "community",
                    "trust_tier": "standard",
                    "coverage_tags": "ethereum, community",
                    "asset_universe": ["eth"],
                    "authority_scope": {"community": "ethfinance"},
                    "fetch_policy": {"kind": "poll"},
                    "context_policy": {"include_comments": True},
                    "cost_policy": {"budget": "free"},
                },
            ],
            now_ms=NOW_MS + 10,
        )
        stored = {
            row["source_id"]: row
            for row in conn.execute("SELECT * FROM news_sources ORDER BY source_id").fetchall()
        }
    finally:
        conn.close()

    assert [row["source_id"] for row in rows] == ["configured-source", "community-source"]
    assert stored["configured-source"]["enabled"] is True
    assert stored["removed-source"]["enabled"] is False
    assert stored["configured-source"]["provider_type"] == "github"
    assert stored["configured-source"]["source_role"] == "developer_signal"
    assert stored["configured-source"]["coverage_tags_json"] == ["ethereum", "protocol"]
    assert stored["configured-source"]["asset_universe_json"] == ["eth"]
    assert stored["configured-source"]["authority_scope_json"] == {"project": "ethereum"}
    assert stored["configured-source"]["fetch_policy_json"] == {"kind": "releases"}
    assert stored["configured-source"]["context_policy_json"] == {"thread_depth": 2}
    assert stored["configured-source"]["cost_policy_json"] == {"budget": "low"}
    assert stored["configured-source"]["source_quality_status"] == "verified"
    assert stored["community-source"]["coverage_tags_json"] == ["ethereum", "community"]
    assert stored["community-source"]["source_quality_status"] == "unknown"
