from __future__ import annotations

from parallax.app.runtime.repository_session import repositories_for_connection
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_canonical_item_identity_collapses_two_provider_observations(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = _repositories(conn)
        canonical_url = "https://example.com/news/stable-story"
        with repos.transaction():
            repos.news_sources.upsert_source(
                source_id="source-1",
                provider_type="rss",
                feed_url="https://example.com/rss.xml",
                source_domain="example.com",
                source_name="Example",
                now_ms=NOW_MS,
            )
            fetch_run_id = repos.news_sources.start_fetch_run(source_id="source-1", started_at_ms=NOW_MS)
            first_provider = repos.news_sources.upsert_provider_item(
                source_id="source-1",
                fetch_run_id=fetch_run_id,
                source_item_key="provider-observation-1",
                canonical_url=canonical_url,
                payload_hash="payload-1",
                raw_payload={"title": "Stable story"},
                fetched_at_ms=NOW_MS,
            )
            second_provider = repos.news_sources.upsert_provider_item(
                source_id="source-1",
                fetch_run_id=fetch_run_id,
                source_item_key="provider-observation-2",
                canonical_url=canonical_url,
                payload_hash="payload-2",
                raw_payload={"title": "Stable story update"},
                fetched_at_ms=NOW_MS + 1,
            )
            first = _upsert_item(repos, first_provider["provider_item_id"], canonical_url, "content-1")
            second = _upsert_item(repos, second_provider["provider_item_id"], canonical_url, "content-2")
        edge_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_item_observation_edges WHERE news_item_id = %s",
            (first["news_item_id"],),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert first["news_item_id"] == second["news_item_id"]
    assert edge_count == 2


def _upsert_item(repos, provider_item_id: str, canonical_url: str, content_hash: str):
    return repos.news_items.upsert_canonical_news_item(
        provider_item_id=provider_item_id,
        canonical_url=canonical_url,
        title="Stable story",
        summary="Summary",
        body_text="Body",
        language="en",
        published_at_ms=NOW_MS,
        fetched_at_ms=NOW_MS,
        content_hash=content_hash,
        title_fingerprint="stable story",
        now_ms=NOW_MS,
    )


def _repositories(conn):
    return repositories_for_connection(
        conn,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )
