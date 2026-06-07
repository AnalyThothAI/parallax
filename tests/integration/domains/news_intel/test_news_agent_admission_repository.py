from __future__ import annotations

from psycopg.types.json import Jsonb

from parallax.domains.news_intel._constants import NEWS_ITEM_AGENT_ADMISSION_VERSION, NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_update_item_agent_admission_persists_without_touching_market_scope(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _seed_processed_news_item(conn, primary_scope="us_equity")

        updated = repo.update_item_agent_admission(
            news_item_id=news_item_id,
            admission=_agent_admission_fixture(status="eligible", reason="provider_score_high"),
            now_ms=NOW_MS + 1_000,
        )
        row = repo.get_news_item_detail(news_item_id=news_item_id)
    finally:
        conn.close()

    assert updated == 1
    assert row is not None
    assert row["agent_admission_status"] == "eligible"
    assert row["agent_admission_reason"] == "provider_score_high"
    assert row["agent_admission"]["status"] == "eligible"
    assert row["agent_representative_news_item_id"] == news_item_id
    assert row["market_scope"]["primary"] == "us_equity"


def test_page_row_persists_agent_admission_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _seed_processed_news_item(conn)
        row = _page_row_fixture(news_item_id=news_item_id, agent_admission_status="similar_story_covered")

        repo.replace_page_rows_for_items(news_item_ids=[news_item_id], rows=[row])
        listed = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert [item["row_id"] for item in listed] == ["row-agent-admission"]
    assert listed[0]["agent_admission_status"] == "similar_story_covered"
    assert listed[0]["agent_admission_reason"] == "same_story_key_current_brief"
    assert listed[0]["agent_admission"]["status"] == "similar_story_covered"
    assert listed[0]["agent_representative_news_item_id"] == "news-representative"


def test_load_agent_admission_contexts_returns_exact_duplicate_by_provider_article_key(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        representative_id = _seed_processed_news_item(conn)
        conn.execute(
            "UPDATE news_items SET provider_article_keys_json = %s WHERE news_item_id = %s",
            (Jsonb(["opennews:shared-agent-admission"]), representative_id),
        )
        duplicate_id = _insert_second_processed_news_item(
            conn,
            provider_article_keys=["opennews:shared-agent-admission"],
        )
        conn.commit()

        contexts = repo.load_agent_admission_contexts(news_item_ids=[duplicate_id], now_ms=NOW_MS)
    finally:
        conn.close()

    assert len(contexts) == 1
    assert contexts[0]["exact_duplicate"] == {
        "exact_duplicate": True,
        "match_type": "same_provider_article_id",
        "matched_news_item_id": representative_id,
        "representative_news_item_id": representative_id,
        "matched_story_key": "",
    }


def _seed_processed_news_item(conn, *, primary_scope: str = "crypto") -> str:
    conn.execute(
        """
        INSERT INTO news_sources (
          source_id, provider_type, feed_url, source_domain, source_name,
          source_role, trust_tier, enabled, created_at_ms, updated_at_ms
        )
        VALUES (
          'source-agent-admission', 'rss', 'https://example.com/rss.xml', 'example.com', 'Example',
          'observed_source', 'standard', true, %s, %s
        )
        """,
        (NOW_MS, NOW_MS),
    )
    conn.execute(
        """
        INSERT INTO news_provider_items (
          provider_item_id, source_id, source_item_key, canonical_url, payload_hash,
          raw_payload_json, fetched_at_ms
        )
        VALUES (
          'provider-agent-admission', 'source-agent-admission', 'guid-agent-admission',
          'https://example.com/agent-admission', 'hash-agent-admission',
          '{"title":"Agent admission"}'::jsonb, %s
        )
        """,
        (NOW_MS,),
    )
    conn.execute(
        """
        INSERT INTO news_items (
          news_item_id, provider_item_id, source_id, source_domain, canonical_url,
          title, summary, body_text, language, published_at_ms, fetched_at_ms,
          content_hash, title_fingerprint, provider_signal_json, lifecycle_status,
          content_class, content_classification_json, market_scope_json, created_at_ms, updated_at_ms
        )
        VALUES (
          'news-agent-admission', 'provider-agent-admission', 'source-agent-admission', 'example.com',
          'https://example.com/agent-admission', 'Agent admission', 'Summary', '', 'en', %s, %s,
          'content-agent-admission', 'agent admission',
          %s, 'processed', 'us_equity', '{"policy_version":"test"}'::jsonb,
          %s, %s, %s
        )
        """,
        (
            NOW_MS,
            NOW_MS,
            Jsonb({"source": "provider", "status": "ready", "score": 95}),
            Jsonb(_market_scope_fixture(primary=primary_scope)),
            NOW_MS,
            NOW_MS,
        ),
    )
    conn.execute(
        """
        INSERT INTO news_item_observation_edges (
          provider_item_id, news_item_id, source_id, provider_article_key, match_type,
          match_confidence, policy_version, evidence_json, first_seen_at_ms, last_seen_at_ms
        )
        VALUES (
          'provider-agent-admission', 'news-agent-admission', 'source-agent-admission',
          'rss:agent-admission', 'same_provider_article_id', 'strong', 'test',
          '{"item_payload": {"title": "Agent admission"}}'::jsonb, %s, %s
        )
        """,
        (NOW_MS, NOW_MS),
    )
    conn.commit()
    return "news-agent-admission"


def _insert_second_processed_news_item(conn, *, provider_article_keys: list[str]) -> str:
    conn.execute(
        """
        INSERT INTO news_provider_items (
          provider_item_id, source_id, source_item_key, canonical_url, payload_hash,
          raw_payload_json, fetched_at_ms
        )
        VALUES (
          'provider-agent-admission-2', 'source-agent-admission', 'guid-agent-admission-2',
          'https://example.com/agent-admission-2', 'hash-agent-admission-2',
          '{"title":"Agent admission duplicate"}'::jsonb, %s
        )
        """,
        (NOW_MS,),
    )
    conn.execute(
        """
        INSERT INTO news_items (
          news_item_id, provider_item_id, source_id, source_domain, canonical_url,
          title, summary, body_text, language, published_at_ms, fetched_at_ms,
          content_hash, title_fingerprint, provider_signal_json, lifecycle_status,
          content_class, content_classification_json, provider_article_keys_json,
          created_at_ms, updated_at_ms
        )
        VALUES (
          'news-agent-admission-2', 'provider-agent-admission-2', 'source-agent-admission', 'example.com',
          'https://example.com/agent-admission-2', 'Agent admission duplicate', 'Summary', '', 'en', %s, %s,
          'content-agent-admission-2', 'agent admission duplicate',
          %s, 'processed', 'us_equity', '{"policy_version":"test"}'::jsonb, %s, %s, %s
        )
        """,
        (
            NOW_MS + 1,
            NOW_MS + 1,
            Jsonb({"source": "provider", "status": "ready", "score": 94}),
            Jsonb(provider_article_keys),
            NOW_MS + 1,
            NOW_MS + 1,
        ),
    )
    return "news-agent-admission-2"


def _agent_admission_fixture(*, status: str, reason: str) -> dict[str, object]:
    return {
        "eligible": status in {"eligible", "eligible_refresh"},
        "status": status,
        "reason": reason,
        "representative_news_item_id": "news-agent-admission",
        "basis": {"provider_signal": {"score": 95}},
        "version": NEWS_ITEM_AGENT_ADMISSION_VERSION,
    }


def _page_row_fixture(*, news_item_id: str, agent_admission_status: str) -> dict[str, object]:
    return {
        "row_id": "row-agent-admission",
        "news_item_id": news_item_id,
        "representative_news_item_id": news_item_id,
        "story_key": "news-story:test-agent-admission",
        "story": {"story_key": "news-story:test-agent-admission", "member_count": 1},
        "latest_at_ms": NOW_MS,
        "lifecycle_status": "processed",
        "headline": "Agent admission",
        "summary": "Summary",
        "source_domain": "example.com",
        "canonical_url": "https://example.com/agent-admission",
        "token_lanes": [],
        "fact_lanes": [],
        "signal": {"display_signal": {"source": "provider", "status": "ready", "score": 95}},
        "token_impacts": [],
        "source": {"source_id": "source-agent-admission"},
        "agent_brief": {"status": "pending"},
        "agent_status": "pending",
        "market_scope": _market_scope_fixture(primary="us_equity"),
        "agent_admission_status": agent_admission_status,
        "agent_admission_reason": "same_story_key_current_brief",
        "agent_admission": {
            "eligible": False,
            "status": agent_admission_status,
            "reason": "same_story_key_current_brief",
            "representative_news_item_id": "news-representative",
            "basis": {"similar_story": {"story_key": "news-story:test-agent-admission"}},
            "version": NEWS_ITEM_AGENT_ADMISSION_VERSION,
        },
        "agent_representative_news_item_id": "news-representative",
        "computed_at_ms": NOW_MS,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }


def _market_scope_fixture(*, primary: str) -> dict[str, object]:
    return {
        "scope": [primary],
        "primary": primary,
        "status": "classified",
        "reason": "market_scope_classified",
        "basis": {"test": True},
        "version": "news_market_scope_v1",
    }
