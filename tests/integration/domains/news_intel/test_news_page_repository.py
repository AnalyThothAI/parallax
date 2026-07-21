from __future__ import annotations

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_unchanged_page_projection_writes_zero_serving_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = _repositories(conn)
        with repos.transaction():
            news_item_id = _seed_item(repos)
            row = _page_row(news_item_id)
            first = repos.news_pages.replace_page_rows_for_items(
                news_item_ids=[news_item_id],
                rows=[row],
            )
            second = repos.news_pages.replace_page_rows_for_items(
                news_item_ids=[news_item_id],
                rows=[row],
            )
        listed = repos.news_pages.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert first == {"inserted": 1, "updated": 0, "unchanged": 0, "deleted": 0}
    assert second == {"inserted": 0, "updated": 0, "unchanged": 1, "deleted": 0}
    assert [row["news_item_id"] for row in listed] == [news_item_id]


def _seed_item(repos) -> str:
    repos.news_sources.upsert_source(
        source_id="page-source",
        provider_type="rss",
        feed_url="https://example.com/page.xml",
        source_domain="example.com",
        source_name="Page source",
        now_ms=NOW_MS,
    )
    fetch_run_id = repos.news_sources.start_fetch_run(source_id="page-source", started_at_ms=NOW_MS)
    provider = repos.news_sources.upsert_provider_item(
        source_id="page-source",
        fetch_run_id=fetch_run_id,
        source_item_key="page-observation-1",
        canonical_url="https://example.com/page-1",
        payload_hash="page-payload-1",
        raw_payload={"title": "Projected story"},
        fetched_at_ms=NOW_MS,
    )
    item = repos.news_items.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url="https://example.com/page-1",
        title="Projected story",
        summary="Summary",
        body_text="Body",
        language="en",
        published_at_ms=NOW_MS,
        fetched_at_ms=NOW_MS,
        content_hash="page-content-1",
        title_fingerprint="projected story",
        now_ms=NOW_MS,
    )
    return str(item["news_item_id"])


def _page_row(news_item_id: str) -> dict[str, object]:
    story_key = f"story:{news_item_id}"
    return {
        "row_id": f"row-{news_item_id}",
        "news_item_id": news_item_id,
        "representative_news_item_id": news_item_id,
        "story_key": story_key,
        "latest_at_ms": NOW_MS,
        "lifecycle_status": "processed",
        "headline": "Projected story",
        "summary": "Summary",
        "source_domain": "example.com",
        "canonical_url": "https://example.com/page-1",
        "token_lanes": [],
        "fact_lanes": [],
        "story": {
            "story_key": story_key,
            "representative_news_item_id": news_item_id,
            "member_news_item_ids": [news_item_id],
            "member_count": 1,
            "source_domains": ["example.com"],
        },
        "token_impacts": [],
        "content_class": "market_moving",
        "content_tags": ["market"],
        "content_classification": {"policy_version": "news_content_classification_v1"},
        "source": {"source_id": "page-source", "source_role": "specialist_media", "trust_tier": "standard"},
        "signal": {"display_signal": {"direction": "neutral", "status": "partial"}},
        "provider_rating": {"status": "ready", "score": 80},
        "agent_brief": {"status": "pending"},
        "agent_status": "pending",
        "agent_brief_computed_at_ms": None,
        "market_scope": {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "market_scope_classified",
            "basis": {"subject": "fixture"},
            "version": "news_market_scope_v1",
        },
        "macro_event_flow": None,
        "agent_admission": {
            "eligible": True,
            "status": "eligible",
            "reason": "eligible",
            "basis": {"market_scope": ["crypto"]},
            "version": "news_item_agent_admission_market_v2",
            "representative_news_item_id": news_item_id,
        },
        "agent_admission_status": "eligible",
        "agent_admission_reason": "eligible",
        "agent_representative_news_item_id": news_item_id,
        "computed_at_ms": NOW_MS,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }


def _repositories(conn):
    return repositories_for_connection(
        conn,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )
