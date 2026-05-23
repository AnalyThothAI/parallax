from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
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


def test_list_news_page_rows_can_include_unprojected_fallback_when_requested(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        projected_item_id = _insert_source_provider_and_item(repo, source_item_key="projected", title="Projected")
        raw_item_id = _insert_source_provider_and_item(repo, source_item_key="raw", title="Raw")
        repo.replace_page_rows_for_items(
            news_item_ids=[projected_item_id],
            rows=[_page_row("row-projected", projected_item_id)],
        )

        rows = repo.list_news_page_rows(limit=10, include_unprojected=True)
    finally:
        conn.close()

    assert {row["row_id"] for row in rows} == {"row-projected", raw_item_id}
    raw = next(row for row in rows if row["row_id"] == raw_item_id)
    assert raw["headline"] == "Raw"
    assert raw["agent_status"] == "pending"


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
        "idx_news_page_rows_provider_type_time",
        "idx_news_page_rows_source_role_time",
        "idx_news_page_rows_trust_tier_time",
        "idx_news_page_rows_coverage_tags_gin",
        "idx_news_page_rows_content_tags_gin",
        "idx_news_page_rows_direction_time",
        "idx_news_page_rows_decision_class_time",
    } <= index_names


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
    news = repo.upsert_news_item(
        provider_item_id=provider["provider_item_id"],
        source_id="source-1",
        source_domain="example.com",
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


def _page_row(row_id: str, news_item_id: str) -> dict[str, object]:
    return {
        "row_id": row_id,
        "news_item_id": news_item_id,
        "story_id": None,
        "latest_at_ms": NOW_MS,
        "lifecycle_status": "processed",
        "headline": row_id,
        "summary": "summary",
        "source_domain": "example.com",
        "canonical_url": f"https://example.com/{row_id}",
        "token_lanes_json": [],
        "fact_lanes_json": [],
        "story_json": {},
        "source_json": {"source_id": "source-1", "source_role": "specialist_media", "trust_tier": "standard"},
        "agent_brief_json": {"status": "ready", "direction": "neutral"},
        "agent_status": "ready",
        "agent_brief_computed_at_ms": NOW_MS,
        "computed_at_ms": NOW_MS,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }
