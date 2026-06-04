from __future__ import annotations

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_500_000_000


def test_list_news_page_rows_defaults_to_projected_rows_without_fallback_scan(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        projected_item_id = _insert_source_provider_and_item(repo, source_item_key="projected", title="Projected")
        _insert_source_provider_and_item(repo, source_item_key="raw", title="Raw")
        repo.replace_page_rows_for_items(
            news_item_ids=[projected_item_id],
            rows=[_page_row("row-projected", projected_item_id)],
        )

        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert [row["row_id"] for row in rows] == ["row-projected"]


def test_list_news_page_rows_reads_only_projected_rows_after_hard_cut(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        projected_item_id = _insert_source_provider_and_item(repo, source_item_key="projected", title="Projected")
        _insert_source_provider_and_item(repo, source_item_key="raw", title="Raw")
        repo.replace_page_rows_for_items(
            news_item_ids=[projected_item_id],
            rows=[_page_row("row-projected", projected_item_id)],
        )

        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert [row["row_id"] for row in rows] == ["row-projected"]


def test_news_page_rows_filter_indexes_cover_normal_ui_filters(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        rows = conn.execute(
            """
            SELECT indexname
              FROM pg_indexes
             WHERE schemaname = 'public'
               AND tablename = 'news_page_rows'
            """
        ).fetchall()
    finally:
        conn.close()

    index_names = {str(row["indexname"]) for row in rows}
    assert {
        "ix_news_page_rows_signal_direction",
        "ix_news_page_rows_signal_score",
    } <= index_names
    assert "ix_news_page_rows_token_count_time" not in index_names


def test_page_projection_outputs_one_row_for_public_url_and_material_duplicate(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        _upsert_opennews_source(repo)
        coindesk_url = (
            "https://www.coindesk.com/markets/2026/06/03/"
            "bitcoin-crashes-to-usd62-000-as-billions-of-longs-get-liquidated"
        )
        title = "Bitcoin crashes to $62,000 as billions of longs get liquidated"
        public_news = _upsert_opennews_observation(
            repo,
            article_id="2514740",
            canonical_url=coindesk_url,
            title=title,
            now_ms=NOW_MS,
        )
        fallback_a = _upsert_opennews_observation(
            repo,
            article_id="2514742",
            canonical_url="opennews://item/2514742",
            title=f"COINDESK: {title}",
            now_ms=NOW_MS + 1,
        )
        fallback_b = _upsert_opennews_observation(
            repo,
            article_id="2514744",
            canonical_url="opennews://item/2514744",
            title=title,
            now_ms=NOW_MS + 2,
        )
        representative_id = str(public_news["news_item_id"])
        payload = repo.load_items_for_page_projection(news_item_ids=[representative_id])[0]
        page_row = _page_row("row-coindesk", representative_id)
        page_row["canonical_url"] = coindesk_url
        page_row["headline"] = payload["item"]["title"]
        page_row["source_domain"] = "6551.io"
        page_row["source_json"] = {
            "source_id": "opennews-news",
            "source_role": "observed_source",
            "trust_tier": "standard",
        }
        repo.replace_page_rows_for_items(news_item_ids=[representative_id], rows=[page_row])

        rows = repo.list_news_page_rows(limit=20)
        summary = conn.execute(
            """
            SELECT provider_article_keys_json
              FROM news_page_rows
             WHERE news_item_id = %s
            """,
            (representative_id,),
        ).fetchone()
    finally:
        conn.close()

    assert {str(public_news["news_item_id"]), str(fallback_a["news_item_id"]), str(fallback_b["news_item_id"])} == {
        representative_id
    }
    assert [row["canonical_url"] for row in rows].count(coindesk_url) == 1
    assert rows[0]["news_item_id"] == representative_id
    assert rows[0]["duplicate_count"] == 3
    assert summary["provider_article_keys_json"] == [
        "opennews:2514740",
        "opennews:2514742",
        "opennews:2514744",
    ]


def _insert_source_provider_and_item(
    repo: NewsRepository,
    *,
    source_item_key: str,
    title: str,
) -> str:
    repo.upsert_source(
        source_id="source-1",
        provider_type="rss",
        feed_url="https://example.com/rss.xml",
        source_domain="example.com",
        source_name="Example",
        now_ms=NOW_MS,
    )
    fetch_run_id = repo.start_fetch_run(source_id="source-1", started_at_ms=NOW_MS)
    provider = repo.upsert_provider_item(
        source_id="source-1",
        fetch_run_id=fetch_run_id,
        source_item_key=source_item_key,
        canonical_url=f"https://example.com/{source_item_key}",
        payload_hash=f"hash-{source_item_key}",
        raw_payload_json={"title": title},
        fetched_at_ms=NOW_MS,
    )
    news = repo.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url=f"https://example.com/{source_item_key}",
        title=title,
        summary="Summary",
        body_text="Body",
        language="en",
        published_at_ms=NOW_MS,
        fetched_at_ms=NOW_MS,
        content_hash=f"content-{source_item_key}",
        title_fingerprint=title.lower(),
        now_ms=NOW_MS,
    )
    return str(news["news_item_id"])


def _upsert_opennews_source(repo: NewsRepository) -> None:
    repo.upsert_source(
        source_id="opennews-news",
        provider_type="opennews",
        feed_url="opennews://news",
        source_domain="6551.io",
        source_name="OpenNews News",
        refresh_interval_seconds=60,
        now_ms=NOW_MS,
    )


def _upsert_opennews_observation(
    repo: NewsRepository,
    *,
    article_id: str,
    canonical_url: str,
    title: str,
    now_ms: int,
) -> dict[str, object]:
    provider = repo.upsert_provider_item(
        source_id="opennews-news",
        fetch_run_id=repo.start_fetch_run(source_id="opennews-news", started_at_ms=now_ms),
        source_item_key=article_id,
        canonical_url=canonical_url,
        payload_hash=f"payload-{article_id}",
        raw_payload_json={"id": article_id, "link": canonical_url, "text": title},
        fetched_at_ms=now_ms,
        provider_article_id=article_id,
    )
    return repo.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url=canonical_url,
        title=title,
        summary="",
        body_text=title,
        language="en",
        published_at_ms=now_ms,
        fetched_at_ms=now_ms,
        content_hash=f"content-{article_id}",
        title_fingerprint=title.lower().replace(":", "").replace(",", "").replace("$", "").replace("-", " "),
        now_ms=now_ms,
        provider_token_impacts=[{"symbol": "BTC", "signal": "short", "score": 85}],
    )


def _page_row(row_id: str, news_item_id: str) -> dict[str, object]:
    return {
        "row_id": row_id,
        "news_item_id": news_item_id,
        "latest_at_ms": NOW_MS,
        "lifecycle_status": "processed",
        "headline": row_id,
        "summary": "summary",
        "source_domain": "example.com",
        "canonical_url": f"https://example.com/{row_id}",
        "token_lanes_json": [],
        "fact_lanes_json": [],
        "source_json": {"source_id": "source-1", "source_role": "specialist_media", "trust_tier": "standard"},
        "agent_brief_json": {"status": "ready", "direction": "neutral"},
        "agent_status": "ready",
        "agent_brief_computed_at_ms": NOW_MS,
        "computed_at_ms": NOW_MS,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }
