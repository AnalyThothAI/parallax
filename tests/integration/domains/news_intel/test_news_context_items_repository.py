from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_context_items_persist_independently_and_hydrate_detail(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id, provider_item_id = _insert_source_provider_and_item(repo)

        first = repo.upsert_news_context_item(
            context_item_id="context-1",
            source_id="source-1",
            parent_news_item_id=news_item_id,
            provider_item_id=provider_item_id,
            context_type="comment",
            author="alice",
            canonical_url="https://example.com/comment/1",
            body_text="First comment",
            published_at_ms=NOW_MS + 100,
            engagement_json={"likes": 1},
            raw_payload_json={"raw": "first"},
            created_at_ms=NOW_MS + 200,
        )
        repo.upsert_news_context_item(
            context_item_id="context-2",
            source_id="source-1",
            parent_news_item_id=news_item_id,
            provider_item_id=None,
            context_type="reply",
            author="bob",
            canonical_url="https://example.com/comment/2",
            body_text="Second comment",
            published_at_ms=NOW_MS + 200,
            engagement_json={"likes": 2},
            raw_payload_json={"raw": "second"},
            created_at_ms=NOW_MS + 300,
        )
        stored_body = conn.execute(
            "SELECT body_text FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["body_text"]
        detail = repo.get_news_item_detail(news_item_id=news_item_id)
    finally:
        conn.close()

    assert first["context_item_id"] == "context-1"
    assert stored_body == "Primary body"
    assert detail is not None
    assert [row["context_item_id"] for row in detail["context_items"]] == ["context-2", "context-1"]
    assert detail["context_items"][0]["body_text"] == "Second comment"
    assert detail["context_items"][1]["engagement_json"] == {"likes": 1}
    assert all("raw_payload_json" not in row for row in detail["context_items"])
    assert all("provider_item_id" not in row for row in detail["context_items"])


def test_context_item_upsert_updates_mutable_fields_without_touching_news_body(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id, provider_item_id = _insert_source_provider_and_item(repo)

        repo.upsert_news_context_item(
            context_item_id="context-update",
            source_id="source-1",
            parent_news_item_id=news_item_id,
            provider_item_id=provider_item_id,
            context_type="discussion",
            author="alice",
            canonical_url="https://example.com/discussion",
            body_text="Old context",
            published_at_ms=NOW_MS,
            engagement_json={"likes": 1},
            raw_payload_json={"version": 1},
            created_at_ms=NOW_MS,
        )
        updated = repo.upsert_news_context_item(
            context_item_id="context-update",
            source_id="source-1",
            parent_news_item_id=news_item_id,
            provider_item_id=provider_item_id,
            context_type="discussion",
            author="alice-updated",
            canonical_url="https://example.com/discussion-updated",
            body_text="Updated context",
            published_at_ms=NOW_MS + 10,
            engagement_json={"likes": 5, "replies": 2},
            raw_payload_json={"version": 2},
            created_at_ms=NOW_MS + 20,
        )
        rows = repo.list_context_items_for_news_item(news_item_id, limit=25)
        stored_body = conn.execute(
            "SELECT body_text FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["body_text"]
    finally:
        conn.close()

    assert updated["body_text"] == "Updated context"
    assert updated["engagement_json"] == {"likes": 5, "replies": 2}
    assert len(rows) == 1
    assert rows[0]["author"] == "alice-updated"
    assert stored_body == "Primary body"


def test_list_context_items_for_news_item_enforces_limit_and_null_order(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id, _provider_item_id = _insert_source_provider_and_item(repo)
        for index in range(30):
            repo.upsert_news_context_item(
                context_item_id=f"context-{index:02d}",
                source_id="source-1",
                parent_news_item_id=news_item_id,
                provider_item_id=None,
                context_type="related_post",
                body_text=f"Context {index}",
                published_at_ms=None if index == 29 else NOW_MS + index,
                created_at_ms=NOW_MS + index,
                commit=False,
            )
        conn.commit()

        rows = repo.list_context_items_for_news_item(news_item_id, limit=25)
    finally:
        conn.close()

    assert len(rows) == 25
    assert rows[0]["context_item_id"] == "context-28"
    assert rows[-1]["context_item_id"] == "context-04"
    assert "context-29" not in {row["context_item_id"] for row in rows}


def _insert_source_provider_and_item(repo: NewsRepository) -> tuple[str, str]:
    repo.upsert_source(
        source_id="source-1",
        provider_type="rss",
        feed_url="https://example.com/rss.xml",
        source_domain="example.com",
        source_name="Example",
        refresh_interval_seconds=300,
        now_ms=NOW_MS,
    )
    fetch_run_id = repo.start_fetch_run(source_id="source-1", started_at_ms=NOW_MS)
    provider = repo.upsert_provider_item(
        source_id="source-1",
        fetch_run_id=fetch_run_id,
        source_item_key="guid-1",
        canonical_url="https://example.com/guid-1",
        payload_hash="hash-guid-1",
        raw_payload_json={"title": "Primary"},
        fetched_at_ms=NOW_MS,
    )
    news = repo.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url="https://example.com/guid-1",
        title="Primary",
        summary="Primary summary",
        body_text="Primary body",
        language="en",
        published_at_ms=NOW_MS,
        fetched_at_ms=NOW_MS,
        content_hash="content-guid-1",
        title_fingerprint="primary",
        now_ms=NOW_MS,
    )
    return str(news["news_item_id"]), str(provider["provider_item_id"])
