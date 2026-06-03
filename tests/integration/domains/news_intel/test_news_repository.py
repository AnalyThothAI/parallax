from __future__ import annotations

import inspect
from contextlib import contextmanager
from types import SimpleNamespace

from alembic import command
from psycopg.types.json import Jsonb

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
    NEWS_PAGE_PROJECTION_VERSION,
)
from parallax.domains.news_intel.repositories.news_repository import NewsRepository, news_page_cursor
from parallax.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NewsContextTargetRef,
)
from parallax.platform.db.postgres_migrations import alembic_config
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.postgres_test_utils import test_postgres_dsn as _test_postgres_dsn

NOW_MS = 1_779_000_000_000


def test_source_fetch_provider_and_news_item_round_trip(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="coindesk-rss",
            provider_type="rss",
            feed_url="https://www.coindesk.com/arc/outboundfeeds/rss/",
            source_domain="coindesk.com",
            source_name="CoinDesk",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        due = repo.claim_due_sources(now_ms=NOW_MS, limit=10)
        fetch_run_id = repo.start_fetch_run(source_id="coindesk-rss", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="coindesk-rss",
            fetch_run_id=fetch_run_id,
            source_item_key="guid-1",
            canonical_url="https://www.coindesk.com/news/sol-etf",
            payload_hash="payload-hash-1",
            raw_payload_json={"id": "guid-1", "title": "SOL ETF filing"},
            fetched_at_ms=NOW_MS,
        )
        news = repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://www.coindesk.com/news/sol-etf",
            title="SOL ETF filing",
            summary="Issuer files for a SOL ETF.",
            body_text="Issuer files for a SOL ETF.",
            language="en",
            published_at_ms=NOW_MS - 60_000,
            fetched_at_ms=NOW_MS,
            content_hash="content-hash-1",
            title_fingerprint="sol etf filing",
            now_ms=NOW_MS,
        )
        repo.finish_fetch_run(
            fetch_run_id=fetch_run_id,
            source_id="coindesk-rss",
            status="success",
            finished_at_ms=NOW_MS + 100,
            fetched_count=1,
            inserted_count=1,
            updated_count=0,
            duplicate_count=0,
            http_status=200,
        )
        repo.replace_page_rows_for_items(
            news_item_ids=[news["news_item_id"]],
            rows=[
                {
                    "row_id": "row-1",
                    "news_item_id": news["news_item_id"],
                    "latest_at_ms": NOW_MS - 60_000,
                    "lifecycle_status": "raw",
                    "headline": "SOL ETF filing",
                    "summary": "Issuer files for a SOL ETF.",
                    "source_domain": "coindesk.com",
                    "canonical_url": "https://www.coindesk.com/news/sol-etf",
                    "token_lanes": [],
                    "fact_lanes": [],
                    "signal": {
                        "source": "partial",
                        "status": "partial",
                        "direction": "neutral",
                        "label_zh": "中性",
                    },
                    "token_impacts": [],
                    "source": {
                        "source_id": "coindesk-rss",
                        "provider_type": "rss",
                        "source_domain": "coindesk.com",
                        "source_name": "CoinDesk",
                        "source_role": "observed_source",
                        "trust_tier": "standard",
                        "coverage_tags": [],
                        "source_quality_status": "unknown",
                    },
                    "computed_at_ms": NOW_MS,
                    "projection_version": NEWS_PAGE_PROJECTION_VERSION,
                }
            ],
        )

        rows = repo.list_news_page_rows(limit=10)
        source = conn.execute("SELECT * FROM news_sources WHERE source_id = %s", ("coindesk-rss",)).fetchone()
        run = conn.execute("SELECT * FROM news_fetch_runs WHERE fetch_run_id = %s", (fetch_run_id,)).fetchone()
    finally:
        conn.close()

    assert due[0]["source_id"] == "coindesk-rss"
    assert provider["status"] == "inserted"
    assert news["status"] == "inserted"
    assert source["last_success_at_ms"] == NOW_MS + 100
    assert run["status"] == "success"
    assert run["fetched_count"] == 1
    assert run["inserted_count"] == 1
    assert rows[0]["news_item_id"] == news["news_item_id"]
    assert rows[0]["headline"] == "SOL ETF filing"
    assert rows[0]["latest_at_ms"] == NOW_MS - 60_000
    assert rows[0]["canonical_url"] == "https://www.coindesk.com/news/sol-etf"
    assert "story" not in rows[0]
    assert "story_id" not in rows[0]
    assert rows[0]["source"] == {
        "source_id": "coindesk-rss",
        "provider_type": "rss",
        "source_domain": "coindesk.com",
        "source_name": "CoinDesk",
        "source_role": "observed_source",
        "trust_tier": "standard",
        "coverage_tags": [],
        "source_quality_status": "unknown",
    }


def test_upsert_news_item_persists_provider_signal_and_token_impacts(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-realtime",
            provider_type="opennews",
            feed_url="opennews://subscribe",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=fetch_run_id,
            source_item_key="2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="hash",
            raw_payload={"id": 2367422},
            fetched_at_ms=NOW_MS,
        )

        row = repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="BTC headline",
            fetched_at_ms=NOW_MS,
            content_hash="content-hash",
            title_fingerprint="btc-headline",
            now_ms=NOW_MS,
            provider_signal={
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
            },
            provider_token_impacts=[{"symbol": "BTC", "score": 82, "signal": "long", "grade": "A"}],
        )

        loaded = repo.get_news_item_detail(news_item_id=row["news_item_id"])
    finally:
        conn.close()

    assert loaded is not None
    assert loaded["provider_signal"] == {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
        "direction": "bullish",
    }
    assert loaded["provider_token_impacts"] == [{"symbol": "BTC", "score": 82, "signal": "long", "grade": "A"}]


def test_provider_and_news_item_upserts_are_idempotent_and_update_content(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
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
        first_provider = repo.upsert_provider_item(
            source_id="source-1",
            fetch_run_id=fetch_run_id,
            source_item_key="same-guid",
            canonical_url="https://example.com/news/a",
            payload_hash="hash-old",
            raw_payload_json={"title": "Old"},
            fetched_at_ms=NOW_MS,
        )
        first_news = repo.upsert_canonical_news_item(
            provider_item_id=first_provider["provider_item_id"],
            canonical_url="https://example.com/news/a",
            title="Old title",
            summary="Old summary",
            body_text="Old body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-old",
            title_fingerprint="old title",
            now_ms=NOW_MS,
        )

        second_provider = repo.upsert_provider_item(
            source_id="source-1",
            fetch_run_id=fetch_run_id,
            source_item_key="same-guid",
            canonical_url="https://example.com/news/a",
            payload_hash="hash-new",
            raw_payload_json={"title": "New"},
            fetched_at_ms=NOW_MS + 1_000,
        )
        second_news = repo.upsert_canonical_news_item(
            provider_item_id=second_provider["provider_item_id"],
            canonical_url="https://example.com/news/a",
            title="New title",
            summary="New summary",
            body_text="New body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-new",
            title_fingerprint="new title",
            now_ms=NOW_MS + 1_000,
        )

        provider_count = conn.execute("SELECT COUNT(*) AS count FROM news_provider_items").fetchone()["count"]
        news_count = conn.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()["count"]
        stored_provider = conn.execute(
            "SELECT * FROM news_provider_items WHERE source_item_key = %s",
            ("same-guid",),
        ).fetchone()
        stored_news = conn.execute(
            "SELECT * FROM news_items WHERE provider_item_id = %s",
            (first_provider["provider_item_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert first_provider["provider_item_id"] == second_provider["provider_item_id"]
    assert first_news["news_item_id"] == second_news["news_item_id"]
    assert second_provider["status"] == "updated"
    assert second_news["status"] == "updated"
    assert provider_count == 1
    assert news_count == 1
    assert stored_provider["payload_hash"] == "hash-new"
    assert stored_provider["raw_payload_json"] == {"title": "New"}
    assert stored_news["title"] == "New title"
    assert stored_news["content_hash"] == "content-new"


def test_source_local_item_keys_do_not_merge_across_feed_sources(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        for source_id, domain, name in (
            ("rss-alpha", "alpha.example.com", "Alpha"),
            ("rss-beta", "beta.example.com", "Beta"),
        ):
            repo.upsert_source(
                source_id=source_id,
                provider_type="rss",
                feed_url=f"https://{domain}/rss.xml",
                source_domain=domain,
                source_name=name,
                refresh_interval_seconds=300,
                now_ms=NOW_MS,
            )

        news_rows: list[dict[str, object]] = []
        for index, (source_id, domain, slug) in enumerate(
            (
                ("rss-alpha", "alpha.example.com", "alpha-exclusive"),
                ("rss-beta", "beta.example.com", "beta-exclusive"),
            )
        ):
            fetched_at_ms = NOW_MS + index * 1_000
            fetch_run_id = repo.start_fetch_run(source_id=source_id, started_at_ms=fetched_at_ms)
            provider = repo.upsert_provider_item(
                source_id=source_id,
                fetch_run_id=fetch_run_id,
                source_item_key="shared-guid",
                canonical_url=f"https://{domain}/news/{slug}",
                payload_hash=f"payload-{slug}",
                raw_payload_json={"guid": "shared-guid", "title": f"{slug} title"},
                fetched_at_ms=fetched_at_ms,
            )
            news_rows.append(
                repo.upsert_canonical_news_item(
                    provider_item_id=provider["provider_item_id"],
                    canonical_url=f"https://{domain}/news/{slug}",
                    title=f"{slug} title",
                    summary=f"{slug} summary",
                    body_text=f"{slug} body",
                    language="en",
                    published_at_ms=fetched_at_ms,
                    fetched_at_ms=fetched_at_ms,
                    content_hash=f"content-{slug}",
                    title_fingerprint=f"{slug} title",
                    now_ms=fetched_at_ms,
                )
            )

        providers = conn.execute(
            """
            SELECT source_id, source_item_key, provider_article_id, provider_article_key
              FROM news_provider_items
             ORDER BY source_id
            """
        ).fetchall()
        items = conn.execute(
            """
            SELECT canonical_url, duplicate_observation_count, source_ids_json,
                   provider_article_keys_json
              FROM news_items
             ORDER BY canonical_url
            """
        ).fetchall()
        edges = conn.execute(
            """
            SELECT source_id, provider_article_key
              FROM news_item_observation_edges
             ORDER BY source_id
            """
        ).fetchall()
    finally:
        conn.close()

    assert len({str(row["news_item_id"]) for row in news_rows}) == 2
    assert [dict(row) for row in providers] == [
        {
            "source_id": "rss-alpha",
            "source_item_key": "shared-guid",
            "provider_article_id": "",
            "provider_article_key": "",
        },
        {
            "source_id": "rss-beta",
            "source_item_key": "shared-guid",
            "provider_article_id": "",
            "provider_article_key": "",
        },
    ]
    assert [dict(row) for row in items] == [
        {
            "canonical_url": "https://alpha.example.com/news/alpha-exclusive",
            "duplicate_observation_count": 1,
            "source_ids_json": ["rss-alpha"],
            "provider_article_keys_json": [],
        },
        {
            "canonical_url": "https://beta.example.com/news/beta-exclusive",
            "duplicate_observation_count": 1,
            "source_ids_json": ["rss-beta"],
            "provider_article_keys_json": [],
        },
    ]
    assert [dict(row) for row in edges] == [
        {"source_id": "rss-alpha", "provider_article_key": ""},
        {"source_id": "rss-beta", "provider_article_key": ""},
    ]


def test_explicit_rss_provider_article_key_is_not_global_identity(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="rss-explicit",
            provider_type="rss",
            feed_url="https://explicit.example.com/rss.xml",
            source_domain="explicit.example.com",
            source_name="Explicit RSS",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="rss-explicit", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="rss-explicit",
            fetch_run_id=fetch_run_id,
            source_item_key="source-local-guid",
            canonical_url="https://explicit.example.com/news/source-local-guid",
            payload_hash="payload-explicit",
            raw_payload_json={
                "id": "payload-id",
                "article_id": "payload-article-id",
                "provider_article_id": "payload-provider-id",
                "provider_article_key": "rss:payload-key",
                "guid": "payload-guid",
                "title": "Explicit RSS",
            },
            provider_article_id="explicit-provider-id",
            provider_article_key="rss:explicit-provider-id",
            fetched_at_ms=NOW_MS,
        )
        news = repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://explicit.example.com/news/source-local-guid",
            title="Explicit RSS",
            summary="Explicit RSS summary",
            body_text="Explicit RSS body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-explicit-rss",
            title_fingerprint="explicit rss",
            now_ms=NOW_MS,
        )

        stored_provider = conn.execute(
            "SELECT provider_article_id, provider_article_key FROM news_provider_items"
        ).fetchone()
        edge = conn.execute(
            "SELECT provider_article_key, match_type FROM news_item_observation_edges"
        ).fetchone()
        stored_news = conn.execute(
            "SELECT canonical_item_key, provider_article_keys_json FROM news_items"
        ).fetchone()
    finally:
        conn.close()

    assert provider["provider_article_id"] == ""
    assert provider["provider_article_key"] == ""
    assert dict(stored_provider) == {"provider_article_id": "", "provider_article_key": ""}
    assert dict(edge) == {"provider_article_key": "", "match_type": "same_canonical_url"}
    assert news["canonical_item_key"] == "canonical-url:https://explicit.example.com/news/source-local-guid"
    assert dict(stored_news) == {
        "canonical_item_key": "canonical-url:https://explicit.example.com/news/source-local-guid",
        "provider_article_keys_json": [],
    }


def test_old_rss_provider_article_key_is_cleared_on_upsert(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="rss-old",
            provider_type="rss",
            feed_url="https://old.example.com/rss.xml",
            source_domain="old.example.com",
            source_name="Old RSS",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        old_run_id = repo.start_fetch_run(source_id="rss-old", started_at_ms=NOW_MS - 1_000)
        conn.execute(
            """
            INSERT INTO news_provider_items (
              provider_item_id, source_id, fetch_run_id, source_item_key, canonical_url,
              payload_hash, raw_payload_json, fetched_at_ms, provider_article_id,
              provider_article_key, provider_payload_status, provider_published_at_ms,
              provider_observed_at_ms
            )
            VALUES (
              'provider-item-old-rss', 'rss-old', %s, 'old-guid',
              'https://old.example.com/news/old-guid', 'payload-old',
              %s, %s, 'old-guid', 'rss:old-guid', 'partial', %s, %s
            )
            """,
            (
                old_run_id,
                Jsonb({"guid": "old-guid", "title": "Old RSS"}),
                NOW_MS - 1_000,
                NOW_MS - 1_000,
                NOW_MS - 1_000,
            ),
        )
        conn.commit()

        new_run_id = repo.start_fetch_run(source_id="rss-old", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="rss-old",
            fetch_run_id=new_run_id,
            source_item_key="old-guid",
            canonical_url="https://old.example.com/news/old-guid",
            payload_hash="payload-new",
            raw_payload_json={"guid": "old-guid", "title": "New RSS"},
            fetched_at_ms=NOW_MS,
        )
        news = repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://old.example.com/news/old-guid",
            title="New RSS",
            summary="New RSS summary",
            body_text="New RSS body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-new-rss",
            title_fingerprint="new rss",
            now_ms=NOW_MS,
        )

        stored_provider = conn.execute(
            """
            SELECT provider_item_id, provider_article_id, provider_article_key, payload_hash
              FROM news_provider_items
            """
        ).fetchone()
        edge = conn.execute(
            "SELECT provider_article_key, match_type FROM news_item_observation_edges"
        ).fetchone()
        stored_news = conn.execute(
            "SELECT provider_article_keys_json FROM news_items WHERE news_item_id = %s",
            (news["news_item_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert provider["provider_item_id"] == "provider-item-old-rss"
    assert provider["provider_article_id"] == ""
    assert provider["provider_article_key"] == ""
    assert dict(stored_provider) == {
        "provider_item_id": "provider-item-old-rss",
        "provider_article_id": "",
        "provider_article_key": "",
        "payload_hash": "payload-new",
    }
    assert dict(edge) == {"provider_article_key": "", "match_type": "same_canonical_url"}
    assert stored_news["provider_article_keys_json"] == []


def test_legacy_rss_provider_article_key_is_not_written_to_canonical_edge(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="rss-legacy-edge",
            provider_type="rss",
            feed_url="https://legacy-edge.example.com/rss.xml",
            source_domain="legacy-edge.example.com",
            source_name="Legacy Edge RSS",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="rss-legacy-edge", started_at_ms=NOW_MS)
        conn.execute(
            """
            INSERT INTO news_provider_items (
              provider_item_id, source_id, fetch_run_id, source_item_key, canonical_url,
              payload_hash, raw_payload_json, fetched_at_ms, provider_article_id,
              provider_article_key, provider_payload_status, provider_published_at_ms,
              provider_observed_at_ms
            )
            VALUES (
              'provider-item-legacy-edge-rss', 'rss-legacy-edge', %s, 'legacy-edge-guid',
              'https://legacy-edge.example.com/news/legacy-edge-guid', 'payload-legacy-edge',
              %s, %s, 'legacy-edge-guid', 'rss:legacy-edge-guid', 'ready', %s, %s
            )
            """,
            (
                fetch_run_id,
                Jsonb({"guid": "legacy-edge-guid", "title": "Legacy Edge RSS"}),
                NOW_MS,
                NOW_MS,
                NOW_MS,
            ),
        )
        conn.commit()

        news = repo.upsert_canonical_news_item(
            provider_item_id="provider-item-legacy-edge-rss",
            canonical_url="https://legacy-edge.example.com/news/legacy-edge-guid",
            title="Legacy Edge RSS",
            summary="Legacy edge RSS summary",
            body_text="Legacy edge RSS body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-legacy-edge-rss",
            title_fingerprint="legacy edge rss",
            now_ms=NOW_MS,
            provider_payload_status="ready",
        )

        edge = conn.execute(
            """
            SELECT provider_article_key,
                   evidence_json ->> 'provider_article_key' AS evidence_provider_article_key
              FROM news_item_observation_edges
             WHERE provider_item_id = 'provider-item-legacy-edge-rss'
            """
        ).fetchone()
        stored_news = conn.execute(
            "SELECT provider_article_keys_json FROM news_items WHERE news_item_id = %s",
            (news["news_item_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert dict(edge) == {"provider_article_key": "", "evidence_provider_article_key": None}
    assert stored_news["provider_article_keys_json"] == []


def test_opennews_article_id_collapses_across_sources_into_observation_edges(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        for source_id in ("opennews-news", "opennews-listing"):
            repo.upsert_source(
                source_id=source_id,
                provider_type="opennews",
                feed_url=f"opennews://{source_id}",
                source_domain="6551.io",
                source_name=source_id,
                refresh_interval_seconds=10,
                now_ms=NOW_MS,
            )

        first_run_id = repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS)
        first_provider = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=first_run_id,
            source_item_key="news-2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-news",
            raw_payload_json={"id": 2367422, "title": "BTC headline", "aiRating": {"status": "done"}, "ts": NOW_MS},
            fetched_at_ms=NOW_MS,
        )
        first_news = repo.upsert_canonical_news_item(
            provider_item_id=first_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="BTC headline",
            summary="First source summary",
            body_text="First source body",
            language="en",
            published_at_ms=NOW_MS - 60_000,
            fetched_at_ms=NOW_MS,
            content_hash="content-btc-headline",
            title_fingerprint="btc headline",
            now_ms=NOW_MS,
        )

        second_run_id = repo.start_fetch_run(source_id="opennews-listing", started_at_ms=NOW_MS + 1_000)
        second_provider = repo.upsert_provider_item(
            source_id="opennews-listing",
            fetch_run_id=second_run_id,
            source_item_key="listing-2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-listing",
            raw_payload_json={"id": 2367422, "title": "BTC headline", "aiRating": {"status": "done"}, "ts": NOW_MS},
            fetched_at_ms=NOW_MS + 1_000,
        )
        second_news = repo.upsert_canonical_news_item(
            provider_item_id=second_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="BTC headline",
            summary="Second source summary",
            body_text="Second source body",
            language="en",
            published_at_ms=NOW_MS - 60_000,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-btc-headline",
            title_fingerprint="btc headline",
            now_ms=NOW_MS + 1_000,
        )

        news_count = conn.execute("SELECT COUNT(*) AS count FROM news_items").fetchone()["count"]
        edge_count = conn.execute("SELECT COUNT(*) AS count FROM news_item_observation_edges").fetchone()["count"]
        stored_news = conn.execute(
            "SELECT * FROM news_items WHERE canonical_item_key = %s",
            ("canonical-url:https://example.com/news/2367422",),
        ).fetchone()
        edges = conn.execute(
            """
            SELECT provider_item_id, news_item_id, source_id, provider_article_key, match_type, match_confidence
              FROM news_item_observation_edges
             ORDER BY source_id
            """
        ).fetchall()
        providers = conn.execute(
            """
            SELECT source_id, provider_article_id, provider_article_key, provider_payload_status,
                   provider_published_at_ms, provider_observed_at_ms
              FROM news_provider_items
             ORDER BY source_id
            """
        ).fetchall()
    finally:
        conn.close()

    assert first_provider["provider_article_id"] == "2367422"
    assert second_provider["provider_article_id"] == "2367422"
    assert first_provider["provider_article_key"] == second_provider["provider_article_key"] == "opennews:2367422"
    assert [dict(row) for row in providers] == [
        {
            "source_id": "opennews-listing",
            "provider_article_id": "2367422",
            "provider_article_key": "opennews:2367422",
            "provider_payload_status": "ready",
            "provider_published_at_ms": NOW_MS,
            "provider_observed_at_ms": NOW_MS + 1_000,
        },
        {
            "source_id": "opennews-news",
            "provider_article_id": "2367422",
            "provider_article_key": "opennews:2367422",
            "provider_payload_status": "ready",
            "provider_published_at_ms": NOW_MS,
            "provider_observed_at_ms": NOW_MS,
        },
    ]
    assert first_news["status"] == "inserted"
    assert second_news["status"] == "updated"
    assert first_news["news_item_id"] == second_news["news_item_id"] == stored_news["news_item_id"]
    assert news_count == 1
    assert edge_count == 2
    assert stored_news["canonical_item_key"] == "canonical-url:https://example.com/news/2367422"
    assert stored_news["duplicate_observation_count"] == 2
    assert stored_news["source_ids_json"] == ["opennews-listing", "opennews-news"]
    assert stored_news["source_domains_json"] == ["6551.io"]
    assert stored_news["provider_article_keys_json"] == ["opennews:2367422"]
    assert [dict(row) for row in edges] == [
        {
            "provider_item_id": second_provider["provider_item_id"],
            "news_item_id": stored_news["news_item_id"],
            "source_id": "opennews-listing",
            "provider_article_key": "opennews:2367422",
            "match_type": "same_canonical_url",
            "match_confidence": "strong",
        },
        {
            "provider_item_id": first_provider["provider_item_id"],
            "news_item_id": stored_news["news_item_id"],
            "source_id": "opennews-news",
            "provider_article_key": "opennews:2367422",
            "match_type": "same_canonical_url",
            "match_confidence": "strong",
        },
    ]


def test_opennews_provider_global_ids_do_not_collapse_by_exact_content_hash(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-news",
            provider_type="opennews",
            feed_url="opennews://news",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )
        news_ids: list[str] = []
        for article_id in ("2367422", "2367423"):
            run_id = repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS)
            provider = repo.upsert_provider_item(
                source_id="opennews-news",
                fetch_run_id=run_id,
                source_item_key=f"source-key-{article_id}",
                canonical_url=f"opennews://item/{article_id}",
                payload_hash=f"payload-{article_id}",
                raw_payload_json={"id": article_id, "title": "Shared body", "aiRating": {"status": "done"}},
                fetched_at_ms=NOW_MS,
            )
            news = repo.upsert_canonical_news_item(
                provider_item_id=provider["provider_item_id"],
                canonical_url=f"opennews://item/{article_id}",
                title="Shared body",
                summary="Shared summary",
                body_text="Shared body",
                language="en",
                published_at_ms=NOW_MS,
                fetched_at_ms=NOW_MS,
                content_hash="content-shared-opennews-body",
                title_fingerprint="shared body",
                now_ms=NOW_MS,
            )
            news_ids.append(str(news["news_item_id"]))

        rows = conn.execute(
            """
            SELECT canonical_item_key, duplicate_observation_count
              FROM news_items
             ORDER BY canonical_item_key
            """
        ).fetchall()
        edges = conn.execute(
            """
            SELECT provider_article_key, match_type
              FROM news_item_observation_edges
             ORDER BY provider_article_key
            """
        ).fetchall()
    finally:
        conn.close()

    assert len(set(news_ids)) == 2
    assert [dict(row) for row in rows] == [
        {"canonical_item_key": "provider:opennews:2367422", "duplicate_observation_count": 1},
        {"canonical_item_key": "provider:opennews:2367423", "duplicate_observation_count": 1},
    ]
    assert [dict(row) for row in edges] == [
        {"provider_article_key": "opennews:2367422", "match_type": "same_provider_article_id"},
        {"provider_article_key": "opennews:2367423", "match_type": "same_provider_article_id"},
    ]


def test_opennews_provider_article_key_survives_source_item_key_drift(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-news",
            provider_type="opennews",
            feed_url="opennews://news",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )
        first_run_id = repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS)
        first = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=first_run_id,
            source_item_key="transient-a",
            canonical_url="opennews://item/2367422",
            payload_hash="payload-a",
            raw_payload_json={"id": 2367422, "title": "Ready", "aiRating": {"status": "done"}},
            fetched_at_ms=NOW_MS,
        )
        first_news = repo.upsert_canonical_news_item(
            provider_item_id=first["provider_item_id"],
            canonical_url="opennews://item/2367422",
            title="Ready",
            summary="First OpenNews summary",
            body_text="First OpenNews body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-opennews-first",
            title_fingerprint="ready",
            now_ms=NOW_MS,
            provider_payload_status=first["incoming_provider_payload_status"],
        )
        second_run_id = repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS + 1_000)
        second = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=second_run_id,
            source_item_key="transient-b",
            canonical_url="https://example.com/",
            payload_hash="payload-b",
            raw_payload_json={"id": 2367422, "title": "Ready updated", "aiRating": {"status": "done"}},
            fetched_at_ms=NOW_MS + 1_000,
        )
        second_news = repo.upsert_canonical_news_item(
            provider_item_id=second["provider_item_id"],
            canonical_url="https://example.com/",
            title="Ready updated",
            summary="Second OpenNews summary",
            body_text="Second OpenNews body",
            language="en",
            published_at_ms=NOW_MS + 1_000,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-opennews-second",
            title_fingerprint="ready updated",
            now_ms=NOW_MS + 1_000,
            provider_payload_status=second["incoming_provider_payload_status"],
        )
        providers = conn.execute(
            """
            SELECT provider_item_id, source_item_key, provider_article_id, provider_article_key, payload_hash
              FROM news_provider_items
            """
        ).fetchall()
        items = conn.execute(
            """
            SELECT news_item_id, canonical_url, canonical_item_key, content_hash,
                   duplicate_observation_count, provider_article_keys_json
              FROM news_items
            """
        ).fetchall()
        edges = conn.execute(
            "SELECT news_item_id, provider_article_key, match_type FROM news_item_observation_edges"
        ).fetchall()
    finally:
        conn.close()

    assert first["provider_item_id"] == second["provider_item_id"]
    assert first_news["news_item_id"] == second_news["news_item_id"]
    assert [dict(row) for row in providers] == [
        {
            "provider_item_id": first["provider_item_id"],
            "source_item_key": "transient-a",
            "provider_article_id": "2367422",
            "provider_article_key": "opennews:2367422",
            "payload_hash": "payload-b",
        }
    ]
    assert [dict(row) for row in items] == [
        {
            "news_item_id": first_news["news_item_id"],
            "canonical_url": "https://example.com/",
            "canonical_item_key": "provider:opennews:2367422",
            "content_hash": "content-opennews-second",
            "duplicate_observation_count": 1,
            "provider_article_keys_json": ["opennews:2367422"],
        }
    ]
    assert [dict(row) for row in edges] == [
        {
            "news_item_id": first_news["news_item_id"],
            "provider_article_key": "opennews:2367422",
            "match_type": "same_provider_article_id",
        }
    ]


def test_duplicate_observation_edge_returns_updated_for_projection_refresh(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        for source_id in ("opennews-news", "opennews-onchain"):
            repo.upsert_source(
                source_id=source_id,
                provider_type="opennews",
                feed_url=f"opennews://{source_id}",
                source_domain="6551.io",
                source_name=source_id,
                refresh_interval_seconds=10,
                now_ms=NOW_MS,
            )

        first_run_id = repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS)
        first_provider = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=first_run_id,
            source_item_key="news-2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-news",
            raw_payload_json={"id": 2367422, "title": "BTC headline", "ts": NOW_MS},
            fetched_at_ms=NOW_MS,
        )
        repo.upsert_canonical_news_item(
            provider_item_id=first_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="BTC headline",
            summary="Same summary",
            body_text="Same body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-btc-headline",
            title_fingerprint="btc headline",
            now_ms=NOW_MS,
        )

        second_run_id = repo.start_fetch_run(source_id="opennews-onchain", started_at_ms=NOW_MS + 1_000)
        second_provider = repo.upsert_provider_item(
            source_id="opennews-onchain",
            fetch_run_id=second_run_id,
            source_item_key="onchain-2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-onchain",
            raw_payload_json={"id": 2367422, "title": "BTC headline", "ts": NOW_MS},
            fetched_at_ms=NOW_MS + 1_000,
        )
        duplicate_edge_news = repo.upsert_canonical_news_item(
            provider_item_id=second_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="BTC headline",
            summary="Same summary",
            body_text="Same body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-btc-headline",
            title_fingerprint="btc headline",
            now_ms=NOW_MS + 1_000,
        )
        repeated_duplicate = repo.upsert_canonical_news_item(
            provider_item_id=second_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="BTC headline",
            summary="Same summary",
            body_text="Same body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-btc-headline",
            title_fingerprint="btc headline",
            now_ms=NOW_MS + 2_000,
        )
    finally:
        conn.close()

    assert duplicate_edge_news["status"] == "updated"
    assert repeated_duplicate["status"] == "duplicate"


def test_partial_duplicate_does_not_replace_ready_canonical_representative(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        for source_id in ("opennews-news", "opennews-listing"):
            repo.upsert_source(
                source_id=source_id,
                provider_type="opennews",
                feed_url=f"opennews://{source_id}",
                source_domain="6551.io",
                source_name=source_id,
                refresh_interval_seconds=10,
                now_ms=NOW_MS,
            )

        ready_run_id = repo.start_fetch_run(source_id="opennews-news", started_at_ms=NOW_MS)
        ready_provider = repo.upsert_provider_item(
            source_id="opennews-news",
            fetch_run_id=ready_run_id,
            source_item_key="ready-2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-ready",
            raw_payload_json={"id": 2367422, "title": "Ready headline", "aiRating": {"status": "done"}, "ts": NOW_MS},
            fetched_at_ms=NOW_MS,
        )
        ready_news = repo.upsert_canonical_news_item(
            provider_item_id=ready_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="Ready headline",
            summary="Ready summary",
            body_text="Ready body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-ready",
            title_fingerprint="ready headline",
            now_ms=NOW_MS,
            provider_signal={
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "score": 82,
            },
        )

        partial_run_id = repo.start_fetch_run(source_id="opennews-listing", started_at_ms=NOW_MS + 1_000)
        partial_provider = repo.upsert_provider_item(
            source_id="opennews-listing",
            fetch_run_id=partial_run_id,
            source_item_key="partial-2367422",
            canonical_url="opennews://item/2367422",
            payload_hash="payload-partial",
            raw_payload_json={"id": 2367422, "title": "Partial headline", "ts": NOW_MS + 1_000},
            fetched_at_ms=NOW_MS + 1_000,
        )
        partial_news = repo.upsert_canonical_news_item(
            provider_item_id=partial_provider["provider_item_id"],
            canonical_url="opennews://item/2367422",
            title="Partial headline",
            summary="Partial summary",
            body_text="Partial body",
            language="en",
            published_at_ms=NOW_MS + 1_000,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-partial",
            title_fingerprint="partial headline",
            now_ms=NOW_MS + 1_000,
            provider_signal={
                "source": "partial",
                "status": "partial",
                "direction": "neutral",
            },
        )

        stored_news = conn.execute(
            "SELECT * FROM news_items WHERE news_item_id = %s",
            (ready_news["news_item_id"],),
        ).fetchone()
        edge_count = conn.execute("SELECT COUNT(*) AS count FROM news_item_observation_edges").fetchone()["count"]
    finally:
        conn.close()

    assert ready_news["status"] == "inserted"
    assert partial_news["status"] == "updated"
    assert ready_news["news_item_id"] == partial_news["news_item_id"]
    assert edge_count == 2
    assert stored_news["duplicate_observation_count"] == 2
    assert stored_news["canonical_url"] == "https://example.com/news/2367422"
    assert stored_news["title"] == "Ready headline"
    assert stored_news["summary"] == "Ready summary"
    assert stored_news["body_text"] == "Ready body"
    assert stored_news["content_hash"] == "content-ready"
    assert stored_news["provider_signal_json"] == {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
        "direction": "bullish",
        "score": 82,
    }
    assert stored_news["source_ids_json"] == ["opennews-listing", "opennews-news"]
    assert stored_news["provider_article_keys_json"] == ["opennews:2367422"]


def test_ready_representative_tie_breaker_is_order_independent(tmp_path) -> None:
    def write_pair(order: tuple[str, str], db_name: str) -> dict[str, object]:
        conn = connect_postgres_test(tmp_path / db_name, read_only=False)
        try:
            migrate(conn)
            repo = NewsRepository(conn)
            for label in ("alpha", "beta"):
                repo.upsert_source(
                    source_id=f"opennews-{label}",
                    provider_type="opennews",
                    feed_url=f"opennews://{label}",
                    source_domain="6551.io",
                    source_name=f"OpenNews {label}",
                    refresh_interval_seconds=10,
                    now_ms=NOW_MS,
                )

            for index, label in enumerate(order):
                run_id = repo.start_fetch_run(source_id=f"opennews-{label}", started_at_ms=NOW_MS + index)
                provider = repo.upsert_provider_item(
                    source_id=f"opennews-{label}",
                    fetch_run_id=run_id,
                    source_item_key=f"{label}-2367422",
                    canonical_url="https://example.com/news/2367422",
                    payload_hash=f"payload-{label}",
                    raw_payload_json={"id": 2367422, "title": f"{label} headline", "aiRating": {"status": "done"}},
                    fetched_at_ms=NOW_MS + index * 1_000,
                )
                repo.upsert_canonical_news_item(
                    provider_item_id=provider["provider_item_id"],
                    canonical_url="https://example.com/news/2367422",
                    title=f"{label.title()} headline",
                    summary=f"{label.title()} summary",
                    body_text=f"{label.title()} body",
                    language="en",
                    published_at_ms=NOW_MS,
                    fetched_at_ms=NOW_MS + index * 1_000,
                    content_hash=f"content-{label}",
                    title_fingerprint=f"{label} headline",
                    now_ms=NOW_MS + index * 1_000,
                    provider_signal={"source": "provider", "provider": "opennews", "status": "ready"},
                )

            row = conn.execute(
                """
                SELECT source_id, title, summary, body_text, provider_item_id, canonical_item_key
                  FROM news_items
                 WHERE provider_article_keys_json ? 'opennews:2367422'
                """
            ).fetchone()
        finally:
            conn.close()
        return dict(row)

    alpha_then_beta = write_pair(("alpha", "beta"), "alpha-then-beta")
    beta_then_alpha = write_pair(("beta", "alpha"), "beta-then-alpha")

    expected = {
        "source_id": "opennews-alpha",
        "title": "Alpha headline",
        "summary": "Alpha summary",
        "body_text": "Alpha body",
    }
    assert {key: alpha_then_beta[key] for key in expected} == expected
    assert {key: beta_then_alpha[key] for key in expected} == expected
    assert alpha_then_beta["canonical_item_key"] == "canonical-url:https://example.com/news/2367422"
    assert beta_then_alpha["canonical_item_key"] == "canonical-url:https://example.com/news/2367422"


def test_provider_item_identity_and_ready_status_do_not_downgrade_on_later_partial(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-realtime",
            provider_type="opennews",
            feed_url="opennews://realtime",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )
        ready_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS)
        ready_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=ready_run_id,
            source_item_key="same-provider-item",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-ready",
            raw_payload_json={"id": 2367422, "title": "Ready headline", "aiRating": {"status": "done"}},
            fetched_at_ms=NOW_MS,
        )
        ready_news = repo.upsert_canonical_news_item(
            provider_item_id=ready_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="Ready headline",
            summary="Ready summary",
            body_text="Ready body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-ready",
            title_fingerprint="ready headline",
            now_ms=NOW_MS,
            provider_signal={"source": "provider", "provider": "opennews", "status": "ready"},
            provider_payload_status=ready_provider["incoming_provider_payload_status"],
        )

        partial_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS + 1_000)
        partial_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=partial_run_id,
            source_item_key="same-provider-item",
            canonical_url="opennews://item/2367422",
            payload_hash="payload-partial",
            raw_payload_json={"title": "Partial headline"},
            fetched_at_ms=NOW_MS + 1_000,
        )
        partial_news = repo.upsert_canonical_news_item(
            provider_item_id=partial_provider["provider_item_id"],
            canonical_url="opennews://item/2367422",
            title="Partial headline",
            summary="Partial summary",
            body_text="Partial body",
            language="en",
            published_at_ms=NOW_MS + 1_000,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-partial",
            title_fingerprint="partial headline",
            now_ms=NOW_MS + 1_000,
            provider_signal={"source": "partial", "status": "partial"},
            provider_payload_status=partial_provider["incoming_provider_payload_status"],
        )

        provider_row = conn.execute(
            """
            SELECT provider_article_id, provider_article_key, provider_payload_status,
                   canonical_url, payload_hash, raw_payload_json, fetched_at_ms
              FROM news_provider_items
            """
        ).fetchone()
        stored_news = conn.execute("SELECT * FROM news_items").fetchone()
        edge = conn.execute(
            "SELECT news_item_id, provider_article_key, match_type FROM news_item_observation_edges"
        ).fetchone()
    finally:
        conn.close()

    assert ready_provider["provider_item_id"] == partial_provider["provider_item_id"]
    assert ready_news["news_item_id"] == partial_news["news_item_id"]
    assert provider_row["provider_article_id"] == "2367422"
    assert provider_row["provider_article_key"] == "opennews:2367422"
    assert provider_row["provider_payload_status"] == "ready"
    assert provider_row["canonical_url"] == "https://example.com/news/2367422"
    assert provider_row["payload_hash"] == "payload-ready"
    assert provider_row["raw_payload_json"]["aiRating"] == {"status": "done"}
    assert provider_row["fetched_at_ms"] == NOW_MS
    assert stored_news["canonical_item_key"] == "canonical-url:https://example.com/news/2367422"
    assert stored_news["title"] == "Ready headline"
    assert stored_news["canonical_url"] == "https://example.com/news/2367422"
    assert edge["news_item_id"] == stored_news["news_item_id"]
    assert edge["provider_article_key"] == "opennews:2367422"
    assert edge["match_type"] == "same_provider_article_id"


def test_provider_item_identity_promotion_remaps_edge_and_removes_zero_edge_item(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-realtime",
            provider_type="opennews",
            feed_url="opennews://realtime",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )
        first_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS)
        first_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=first_run_id,
            source_item_key="pending-2367422",
            canonical_url="opennews://item/pending-2367422",
            payload_hash="payload-pending",
            raw_payload_json={"title": "Pending headline"},
            provider_article_id="",
            fetched_at_ms=NOW_MS,
        )
        first_news = repo.upsert_canonical_news_item(
            provider_item_id=first_provider["provider_item_id"],
            canonical_url="opennews://item/pending-2367422",
            title="Pending headline",
            summary="Pending summary",
            body_text="Pending body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-pending-2367422",
            title_fingerprint="pending headline",
            now_ms=NOW_MS,
        )

        second_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS + 1_000)
        second_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=second_run_id,
            source_item_key="pending-2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-ready",
            raw_payload_json={"id": 2367422, "title": "Ready headline", "aiRating": {"status": "done"}},
            provider_article_id="2367422",
            fetched_at_ms=NOW_MS + 1_000,
        )
        second_news = repo.upsert_canonical_news_item(
            provider_item_id=second_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="Ready headline",
            summary="Ready summary",
            body_text="Ready body",
            language="en",
            published_at_ms=NOW_MS + 1_000,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-ready-2367422",
            title_fingerprint="ready headline",
            now_ms=NOW_MS + 1_000,
            provider_payload_status=second_provider["incoming_provider_payload_status"],
        )

        old_item_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_items WHERE news_item_id = %s",
            (first_news["news_item_id"],),
        ).fetchone()["count"]
        rows = conn.execute(
            """
            SELECT news_item_id, canonical_item_key, duplicate_observation_count,
                   source_ids_json, provider_article_keys_json
              FROM news_items
             ORDER BY canonical_item_key
            """
        ).fetchall()
        edges = conn.execute(
            """
            SELECT provider_item_id, news_item_id, provider_article_key, match_type
              FROM news_item_observation_edges
             ORDER BY provider_item_id
            """
        ).fetchall()
    finally:
        conn.close()

    assert first_provider["provider_item_id"] == second_provider["provider_item_id"]
    assert first_provider["provider_article_id"] == ""
    pending_identity_key = (
        f"weak-title-source-window:opennews-realtime:{NOW_MS - (NOW_MS % 3_600_000)}:pending headline"
    )
    assert first_news["canonical_item_key"] == pending_identity_key
    assert second_news["status"] == "updated"
    assert second_news["canonical_item_key"] == "canonical-url:https://example.com/news/2367422"
    assert old_item_count == 0
    assert [dict(row) for row in rows] == [
        {
            "news_item_id": second_news["news_item_id"],
            "canonical_item_key": "canonical-url:https://example.com/news/2367422",
            "duplicate_observation_count": 1,
            "source_ids_json": ["opennews-realtime"],
            "provider_article_keys_json": ["opennews:2367422"],
        }
    ]
    assert [dict(row) for row in edges] == [
        {
            "provider_item_id": second_provider["provider_item_id"],
            "news_item_id": second_news["news_item_id"],
            "provider_article_key": "opennews:2367422",
            "match_type": "same_canonical_url",
        }
    ]


def test_opennews_partial_first_promotes_to_ready_content_hash_and_collapses_mirror_source(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-realtime",
            provider_type="opennews",
            feed_url="opennews://realtime",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )
        repo.upsert_source(
            source_id="rss-mirror",
            provider_type="rss",
            feed_url="https://example.com/rss.xml",
            source_domain="example.com",
            source_name="Mirror",
            refresh_interval_seconds=60,
            now_ms=NOW_MS,
        )
        partial_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS)
        partial_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=partial_run_id,
            source_item_key="ws-2367422",
            canonical_url="opennews://item/2367422",
            payload_hash="payload-partial",
            raw_payload_json={"title": "Partial headline"},
            provider_article_id="2367422",
            fetched_at_ms=NOW_MS,
        )
        partial_news = repo.upsert_canonical_news_item(
            provider_item_id=partial_provider["provider_item_id"],
            canonical_url="opennews://item/2367422",
            title="Partial headline",
            summary="Partial summary",
            body_text="Partial body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-partial-2367422",
            title_fingerprint="partial headline",
            now_ms=NOW_MS,
            provider_payload_status=partial_provider["incoming_provider_payload_status"],
        )

        ready_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS + 1_000)
        ready_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=ready_run_id,
            source_item_key="rest-2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-ready",
            raw_payload_json={"id": 2367422, "title": "Ready headline", "aiRating": {"status": "done"}},
            fetched_at_ms=NOW_MS + 1_000,
        )
        ready_news = repo.upsert_canonical_news_item(
            provider_item_id=ready_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="Ready headline",
            summary="Shared summary",
            body_text="Shared body",
            language="en",
            published_at_ms=NOW_MS + 1_000,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-ready-2367422",
            title_fingerprint="ready headline",
            now_ms=NOW_MS + 1_000,
            provider_payload_status=ready_provider["incoming_provider_payload_status"],
        )
        mirror_run_id = repo.start_fetch_run(source_id="rss-mirror", started_at_ms=NOW_MS + 2_000)
        mirror_provider = repo.upsert_provider_item(
            source_id="rss-mirror",
            fetch_run_id=mirror_run_id,
            source_item_key="mirror-2367422",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-mirror",
            raw_payload_json={"guid": "mirror-2367422", "title": "Ready headline"},
            fetched_at_ms=NOW_MS + 2_000,
        )
        mirror_news = repo.upsert_canonical_news_item(
            provider_item_id=mirror_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="Ready headline",
            summary="Shared summary",
            body_text="Shared body",
            language="en",
            published_at_ms=NOW_MS + 2_000,
            fetched_at_ms=NOW_MS + 2_000,
            content_hash="content-ready-2367422",
            title_fingerprint="ready headline",
            now_ms=NOW_MS + 2_000,
        )

        rows = conn.execute(
            """
            SELECT news_item_id, canonical_item_key, duplicate_observation_count,
                   source_ids_json, provider_article_keys_json
              FROM news_items
             ORDER BY canonical_item_key
            """
        ).fetchall()
        edges = conn.execute(
            """
            SELECT source_id, news_item_id, provider_article_key, match_type
              FROM news_item_observation_edges
             ORDER BY source_id
            """
        ).fetchall()
        old_item_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_items WHERE news_item_id = %s",
            (partial_news["news_item_id"],),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert partial_provider["provider_item_id"] == ready_provider["provider_item_id"]
    assert ready_news["news_item_id"] == mirror_news["news_item_id"]
    assert old_item_count == 0
    assert [dict(row) for row in rows] == [
        {
            "news_item_id": ready_news["news_item_id"],
            "canonical_item_key": "canonical-url:https://example.com/news/2367422",
            "duplicate_observation_count": 2,
            "source_ids_json": ["opennews-realtime", "rss-mirror"],
            "provider_article_keys_json": ["opennews:2367422"],
        }
    ]
    assert [dict(row) for row in edges] == [
        {
            "source_id": "opennews-realtime",
            "news_item_id": ready_news["news_item_id"],
            "provider_article_key": "opennews:2367422",
            "match_type": "same_canonical_url",
        },
        {
            "source_id": "rss-mirror",
            "news_item_id": ready_news["news_item_id"],
            "provider_article_key": "",
            "match_type": "same_canonical_url",
        },
    ]


def test_opennews_provider_id_wins_when_url_is_not_article_identity(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-realtime",
            provider_type="opennews",
            feed_url="opennews://realtime",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )
        partial_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS)
        partial_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=partial_run_id,
            source_item_key="ws-2367422",
            canonical_url="opennews://item/2367422",
            payload_hash="payload-partial",
            raw_payload_json={"title": "Partial headline"},
            provider_article_id="2367422",
            fetched_at_ms=NOW_MS,
        )
        partial_news = repo.upsert_canonical_news_item(
            provider_item_id=partial_provider["provider_item_id"],
            canonical_url="opennews://item/2367422",
            title="Partial headline",
            summary="Partial summary",
            body_text="Partial body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-partial-homepage",
            title_fingerprint="partial headline",
            now_ms=NOW_MS,
            provider_payload_status=partial_provider["incoming_provider_payload_status"],
        )
        ready_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS + 1_000)
        ready_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=ready_run_id,
            source_item_key="rest-2367422",
            canonical_url="https://example.com/",
            payload_hash="payload-ready",
            raw_payload_json={"id": 2367422, "title": "Ready headline", "aiRating": {"status": "done"}},
            fetched_at_ms=NOW_MS + 1_000,
        )
        ready_news = repo.upsert_canonical_news_item(
            provider_item_id=ready_provider["provider_item_id"],
            canonical_url="https://example.com/",
            title="Ready headline",
            summary="Ready summary",
            body_text="Ready body",
            language="en",
            published_at_ms=NOW_MS + 1_000,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-ready-homepage",
            title_fingerprint="ready headline",
            now_ms=NOW_MS + 1_000,
            provider_payload_status=ready_provider["incoming_provider_payload_status"],
        )

        rows = conn.execute("SELECT news_item_id, canonical_item_key, url_identity_kind FROM news_items").fetchall()
        edges = conn.execute(
            """
            SELECT provider_item_id, news_item_id, provider_article_key, match_type
              FROM news_item_observation_edges
             ORDER BY provider_item_id
            """
        ).fetchall()
        old_item_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_items WHERE news_item_id = %s",
            (partial_news["news_item_id"],),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert partial_news["news_item_id"] == ready_news["news_item_id"]
    assert old_item_count == 1
    assert [dict(row) for row in rows] == [
        {
            "news_item_id": ready_news["news_item_id"],
            "canonical_item_key": "provider:opennews:2367422",
            "url_identity_kind": "homepage",
        }
    ]
    assert [dict(row) for row in edges] == [
        {
            "provider_item_id": ready_provider["provider_item_id"],
            "news_item_id": ready_news["news_item_id"],
            "provider_article_key": "opennews:2367422",
            "match_type": "same_provider_article_id",
        },
    ]


def test_identity_promotion_reselects_old_representative_when_edges_remain(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-realtime",
            provider_type="opennews",
            feed_url="opennews://realtime",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS)
        first_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=fetch_run_id,
            source_item_key="pending-a",
            canonical_url="opennews://item/pending-a",
            payload_hash="payload-a",
            raw_payload_json={"title": "Pending A"},
            provider_article_id="",
            fetched_at_ms=NOW_MS,
        )
        first_news = repo.upsert_canonical_news_item(
            provider_item_id=first_provider["provider_item_id"],
            canonical_url="opennews://item/pending-a",
            title="Pending A",
            summary="Pending A summary",
            body_text="Pending A body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-shared-cluster",
            title_fingerprint="pending shared",
            now_ms=NOW_MS,
        )
        second_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=fetch_run_id,
            source_item_key="pending-b",
            canonical_url="opennews://item/pending-b",
            payload_hash="payload-b",
            raw_payload_json={"title": "Pending B"},
            provider_article_id="",
            fetched_at_ms=NOW_MS + 1,
        )
        repo.upsert_canonical_news_item(
            provider_item_id=second_provider["provider_item_id"],
            canonical_url="opennews://item/pending-b",
            title="Pending B",
            summary="Pending B summary",
            body_text="Pending B body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS + 1,
            content_hash="content-shared-cluster",
            title_fingerprint="pending shared",
            now_ms=NOW_MS + 1,
        )
        repo.mark_item_processed(news_item_id=first_news["news_item_id"], processed_at_ms=NOW_MS + 100)
        conn.execute(
            """
            INSERT INTO news_item_entities (
              entity_id, news_item_id, entity_type, raw_value, normalized_value, chain,
              span_start, span_end, text_surface, confidence, extraction_policy_version, created_at_ms
            )
            VALUES (%s, %s, 'symbol', '$STALE', 'STALE', NULL, 0, 6, 'title', 0.8, 'test', %s)
            """,
            ("entity-stale-remap", first_news["news_item_id"], NOW_MS),
        )
        conn.commit()

        promoted_run_id = repo.start_fetch_run(source_id="opennews-realtime", started_at_ms=NOW_MS + 2_000)
        promoted_provider = repo.upsert_provider_item(
            source_id="opennews-realtime",
            fetch_run_id=promoted_run_id,
            source_item_key="pending-a",
            canonical_url="https://example.com/news/2367422",
            payload_hash="payload-a-ready",
            raw_payload_json={"id": 2367422, "title": "Ready A", "aiRating": {"status": "done"}},
            provider_article_id="2367422",
            fetched_at_ms=NOW_MS + 2_000,
        )
        promoted_news = repo.upsert_canonical_news_item(
            provider_item_id=promoted_provider["provider_item_id"],
            canonical_url="https://example.com/news/2367422",
            title="Ready A",
            summary="Ready A summary",
            body_text="Ready A body",
            language="en",
            published_at_ms=NOW_MS + 2_000,
            fetched_at_ms=NOW_MS + 2_000,
            content_hash="content-ready-a",
            title_fingerprint="ready a",
            now_ms=NOW_MS + 2_000,
        )

        old_item = conn.execute(
            "SELECT * FROM news_items WHERE news_item_id = %s",
            (first_news["news_item_id"],),
        ).fetchone()
        old_entity_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_item_entities WHERE news_item_id = %s",
            (first_news["news_item_id"],),
        ).fetchone()["count"]
        old_edges = conn.execute(
            """
            SELECT provider_item_id, news_item_id, provider_article_key
              FROM news_item_observation_edges
             WHERE news_item_id = %s
            """,
            (first_news["news_item_id"],),
        ).fetchall()
        new_edges = conn.execute(
            """
            SELECT provider_item_id, news_item_id, provider_article_key
              FROM news_item_observation_edges
             WHERE news_item_id = %s
            """,
            (promoted_news["news_item_id"],),
        ).fetchall()
    finally:
        conn.close()

    assert old_item is not None
    pending_identity_key = f"weak-title-source-window:opennews-realtime:{NOW_MS - (NOW_MS % 3_600_000)}:pending shared"
    assert old_item["canonical_item_key"] == pending_identity_key
    assert old_item["provider_item_id"] == second_provider["provider_item_id"]
    assert old_item["canonical_url"] == "opennews://item/pending-b"
    assert old_item["title"] == "Pending B"
    assert old_item["summary"] == "Pending B summary"
    assert old_item["body_text"] == "Pending B body"
    assert old_item["content_hash"] == "content-shared-cluster"
    assert old_item["title_fingerprint"] == "pending shared"
    assert old_item["lifecycle_status"] == "raw"
    assert old_item["duplicate_observation_count"] == 1
    assert old_item["provider_article_keys_json"] == []
    assert old_entity_count == 0
    assert set(promoted_news["affected_news_item_ids"]) == {
        first_news["news_item_id"],
        promoted_news["news_item_id"],
    }
    assert [dict(row) for row in old_edges] == [
        {
            "provider_item_id": second_provider["provider_item_id"],
            "news_item_id": first_news["news_item_id"],
            "provider_article_key": "",
        }
    ]
    assert [dict(row) for row in new_edges] == [
        {
            "provider_item_id": promoted_provider["provider_item_id"],
            "news_item_id": promoted_news["news_item_id"],
            "provider_article_key": "opennews:2367422",
        }
    ]


def test_fetch_run_deletion_does_not_delete_provider_or_news_facts(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        fetch_run_id = conn.execute("SELECT fetch_run_id FROM news_provider_items").fetchone()["fetch_run_id"]

        conn.execute("DELETE FROM news_fetch_runs WHERE fetch_run_id = %s", (fetch_run_id,))
        conn.commit()
        provider = conn.execute("SELECT fetch_run_id FROM news_provider_items").fetchone()
        news_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert provider["fetch_run_id"] is None
    assert news_count == 1


def test_claim_due_sources_leases_claimed_sources(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="lease-source",
            provider_type="rss",
            feed_url="https://lease.example/rss.xml",
            source_domain="lease.example",
            source_name="Lease",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )

        first = repo.claim_due_sources(now_ms=NOW_MS, limit=10, claim_lease_ms=60_000)
        second = repo.claim_due_sources(now_ms=NOW_MS + 1_000, limit=10, claim_lease_ms=60_000)
        third = repo.claim_due_sources(now_ms=NOW_MS + 60_001, limit=10, claim_lease_ms=60_000)
    finally:
        conn.close()

    assert [row["source_id"] for row in first] == ["lease-source"]
    assert second == []
    assert [row["source_id"] for row in third] == ["lease-source"]


def test_disable_unconfigured_sources_preserves_manual_sources(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="managed-active",
            provider_type="rss",
            feed_url="https://active.example/rss.xml",
            source_domain="active.example",
            source_name="Active",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        repo.upsert_source(
            source_id="managed-missing",
            provider_type="rss",
            feed_url="https://missing.example/rss.xml",
            source_domain="missing.example",
            source_name="Missing",
            refresh_interval_seconds=300,
            now_ms=NOW_MS,
        )
        repo.upsert_source(
            source_id="manual-source",
            provider_type="rss",
            feed_url="https://manual.example/rss.xml",
            source_domain="manual.example",
            source_name="Manual",
            refresh_interval_seconds=300,
            managed_by_config=False,
            now_ms=NOW_MS,
        )

        disabled = repo.disable_unconfigured_sources(configured_source_ids=["managed-active"], now_ms=NOW_MS + 10)
        states = {
            row["source_id"]: row["enabled"]
            for row in conn.execute("SELECT source_id, enabled FROM news_sources ORDER BY source_id").fetchall()
        }
    finally:
        conn.close()

    assert disabled == 1
    assert states == {
        "managed-active": True,
        "managed-missing": False,
        "manual-source": True,
    }


def test_reconcile_configured_sources_materializes_and_disables_removed_managed_sources(tmp_path) -> None:
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

        rows = repo.reconcile_configured_sources(
            [
                {
                    "source_id": "configured-source",
                    "provider_type": "rss",
                    "feed_url": "https://configured.example/rss.xml",
                    "source_domain": "configured.example",
                    "source_name": "Configured",
                    "source_role": "specialist_media",
                    "trust_tier": "standard",
                    "refresh_interval_seconds": 120,
                }
            ],
            now_ms=NOW_MS + 10,
        )
        states = {
            row["source_id"]: row["enabled"]
            for row in conn.execute("SELECT source_id, enabled FROM news_sources ORDER BY source_id").fetchall()
        }
    finally:
        conn.close()

    assert [(row["source_id"], row["status"]) for row in rows] == [
        ("configured-source", "inserted"),
        ("removed-source", "disabled"),
    ]
    assert states == {"configured-source": True, "removed-source": False}


def test_replace_page_rows_for_items_removes_stale_rows_in_item_scope(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        other_news_item_id = _insert_source_provider_and_item(repo, source_item_key="other-guid", title="Other")
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id, other_news_item_id],
            rows=[
                {
                    "row_id": "row-stale",
                    "news_item_id": news_item_id,
                    "latest_at_ms": NOW_MS,
                    "source_domain": "example.com",
                    "headline": "Stale",
                    "summary": "Old summary",
                    "canonical_url": "https://example.com/stale",
                    "lifecycle_status": "raw",
                    "token_lanes_json": [],
                    "fact_lanes_json": [],
                    "source_json": {"source_id": "source-1"},
                    "projection_version": "test-v1",
                    "computed_at_ms": NOW_MS,
                },
                {
                    "row_id": "row-other",
                    "news_item_id": other_news_item_id,
                    "latest_at_ms": NOW_MS,
                    "source_domain": "example.com",
                    "headline": "Other",
                    "summary": "Other summary",
                    "canonical_url": "https://example.com/other",
                    "lifecycle_status": "raw",
                    "token_lanes_json": [],
                    "fact_lanes_json": [],
                    "source_json": {"source_id": "source-1"},
                    "projection_version": "test-v1",
                    "computed_at_ms": NOW_MS,
                },
            ],
        )

        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[
                {
                    "row_id": "row-fresh",
                    "news_item_id": news_item_id,
                    "latest_at_ms": NOW_MS + 1,
                    "source_domain": "example.com",
                    "headline": "Fresh",
                    "summary": "New summary",
                    "canonical_url": "https://example.com/fresh",
                    "lifecycle_status": "processed",
                    "token_lanes_json": [{"lane": "resolved", "symbol": "SOL"}],
                    "fact_lanes_json": [],
                    "source_json": {"source_id": "source-1"},
                    "projection_version": "test-v1",
                    "computed_at_ms": NOW_MS + 1,
                }
            ],
        )

        rows = conn.execute("SELECT row_id, news_item_id FROM news_page_rows ORDER BY row_id").fetchall()
    finally:
        conn.close()

    assert [(row["row_id"], row["news_item_id"]) for row in rows] == [
        ("row-fresh", news_item_id),
        ("row-other", other_news_item_id),
    ]


def test_replace_page_rows_for_items_keeps_unchanged_row_without_delete_reinsert(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        row = _page_row(
            "row-stable",
            news_item_id,
            source_id="source-1",
            computed_at_ms=NOW_MS,
        )

        first = repo.replace_page_rows_for_items(news_item_ids=[news_item_id], rows=[row], commit=True)
        inserted = conn.execute("SELECT ctid, xmin, computed_at_ms, payload_hash FROM news_page_rows").fetchone()
        second = repo.replace_page_rows_for_items(news_item_ids=[news_item_id], rows=[row], commit=True)
        unchanged = conn.execute("SELECT ctid, xmin, computed_at_ms, payload_hash FROM news_page_rows").fetchone()
    finally:
        conn.close()

    assert first == {"inserted": 1, "updated": 0, "unchanged": 0, "deleted": 0}
    assert second == {"inserted": 0, "updated": 0, "unchanged": 1, "deleted": 0}
    assert unchanged == inserted


def test_replace_source_quality_rows_skips_unchanged_payload_hash(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="source-1",
            provider_type="rss",
            feed_url="https://source-1.example.com/rss.xml",
            source_domain="example.com",
            source_name="Example",
            now_ms=NOW_MS,
        )
        row = _source_quality_row(source_id="source-1", computed_at_ms=NOW_MS)

        repo.replace_source_quality_rows(rows=[row], status_window="24h", commit=True)
        inserted = conn.execute(
            """
            SELECT ctid, xmin, computed_at_ms, payload_hash
              FROM news_source_quality_rows
             WHERE source_id = 'source-1'
            """
        ).fetchone()
        repo.replace_source_quality_rows(
            rows=[{**row, "computed_at_ms": NOW_MS + 10_000}],
            status_window="24h",
            commit=True,
        )
        unchanged = conn.execute(
            """
            SELECT ctid, xmin, computed_at_ms, payload_hash
              FROM news_source_quality_rows
             WHERE source_id = 'source-1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert unchanged == inserted


def test_delete_page_rows_for_sources_removes_disabled_source_scope(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_id="source-1")
        other_news_item_id = _insert_source_provider_and_item(
            repo,
            source_id="source-2",
            source_item_key="other-guid",
            title="Other",
        )
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id, other_news_item_id],
            rows=[
                _page_row("row-1", news_item_id, source_id="source-1"),
                _page_row("row-2", other_news_item_id, source_id="source-2"),
            ],
        )
        conn.execute("UPDATE news_sources SET enabled = false WHERE source_id = 'source-1'")
        conn.commit()

        deleted = repo.delete_page_rows_for_sources(source_ids=["source-1"])
        rows = conn.execute("SELECT row_id FROM news_page_rows ORDER BY row_id").fetchall()
    finally:
        conn.close()

    assert deleted == 1
    assert [row["row_id"] for row in rows] == ["row-2"]


def test_list_news_item_ids_for_sources_uses_observation_edges_not_representative_source(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_id="source-1", source_item_key="shared")
        repo.upsert_source(
            source_id="source-2",
            provider_type="rss",
            feed_url="https://source-2.example.com/rss.xml",
            source_domain="source-2.example.com",
            source_name="Source Two",
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="source-2", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="source-2",
            fetch_run_id=fetch_run_id,
            source_item_key="shared-copy",
            canonical_url="https://example.com/news/shared",
            payload_hash="hash-shared-copy",
            raw_payload_json={"title": "Shared"},
            fetched_at_ms=NOW_MS,
        )
        repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://example.com/news/shared",
            title="Shared",
            summary="Summary",
            body_text="Body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-shared",
            title_fingerprint="shared",
            now_ms=NOW_MS,
        )

        source_two_items = repo.list_news_item_ids_for_sources(source_ids=["source-2"])
    finally:
        conn.close()

    assert source_two_items == [news_item_id]


def test_page_projection_loader_uses_enabled_edge_source_metadata_for_disabled_representative(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_id="source-disabled", source_item_key="shared")
        repo.upsert_source(
            source_id="source-enabled",
            provider_type="rss",
            feed_url="https://enabled.example/rss.xml",
            source_domain="enabled.example",
            source_name="Enabled",
            source_role="official_exchange",
            trust_tier="high",
            coverage_tags=("breaking",),
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="source-enabled", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="source-enabled",
            fetch_run_id=fetch_run_id,
            source_item_key="shared-enabled",
            canonical_url="https://example.com/news/shared",
            payload_hash="hash-shared-enabled",
            raw_payload_json={"title": "Enabled Shared"},
            fetched_at_ms=NOW_MS + 1_000,
        )
        repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://example.com/news/shared",
            title="Enabled Shared",
            summary="Enabled Summary",
            body_text="Enabled Body",
            language="zh",
            published_at_ms=NOW_MS + 1_000,
            fetched_at_ms=NOW_MS + 1_000,
            content_hash="content-shared-enabled",
            title_fingerprint="enabled shared",
            now_ms=NOW_MS + 1_000,
            provider_signal={"display_signal": {"direction": "bullish", "score": 81}},
            provider_token_impacts=[{"symbol": "BTC", "score": 81}],
        )
        conn.execute("UPDATE news_sources SET enabled = false WHERE source_id = 'source-disabled'")
        conn.commit()

        payloads = repo.load_items_for_page_projection(news_item_ids=[news_item_id])
    finally:
        conn.close()

    assert payloads[0]["item"]["source_id"] == "source-enabled"
    assert payloads[0]["item"]["source_domain"] == "enabled.example"
    assert payloads[0]["item"]["provider_item_id"] == provider["provider_item_id"]
    assert payloads[0]["item"]["canonical_url"] == "https://example.com/news/shared"
    assert payloads[0]["item"]["title"] == "Enabled Shared"
    assert payloads[0]["item"]["summary"] == "Enabled Summary"
    assert payloads[0]["item"]["body_text"] == "Enabled Body"
    assert payloads[0]["item"]["language"] == "zh"
    assert payloads[0]["item"]["published_at_ms"] == NOW_MS + 1_000
    assert payloads[0]["item"]["fetched_at_ms"] == NOW_MS + 1_000
    assert payloads[0]["item"]["content_hash"] == "content-shared-enabled"
    assert payloads[0]["item"]["title_fingerprint"] == "enabled shared"
    assert payloads[0]["item"]["provider_signal_json"] == {"display_signal": {"direction": "bullish", "score": 81}}
    assert payloads[0]["item"]["provider_token_impacts_json"] == [{"symbol": "BTC", "score": 81}]
    assert payloads[0]["item"]["source_role"] == "official_exchange"
    assert payloads[0]["item"]["trust_tier"] == "high"
    assert payloads[0]["item"]["coverage_tags_json"] == ["breaking"]


def test_list_news_page_rows_only_returns_projected_items_after_fallback_hard_cut(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        projected_item_id = _insert_source_provider_and_item(repo, source_item_key="projected", title="Projected")
        _insert_source_provider_and_item(repo, source_item_key="raw", title="Raw")
        repo.replace_page_rows_for_items(
            news_item_ids=[projected_item_id],
            rows=[_page_row("row-projected", projected_item_id, source_id="source-1")],
        )

        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert {row["row_id"] for row in rows} == {"row-projected"}


def test_list_news_page_rows_filters_to_current_projection_version(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        current_item_id = _insert_source_provider_and_item(
            repo,
            source_item_key="current-projection",
            title="Current projection",
        )
        stale_item_id = _insert_source_provider_and_item(
            repo,
            source_item_key="stale-projection",
            title="Stale projection",
        )
        repo.replace_page_rows_for_items(
            news_item_ids=[current_item_id, stale_item_id],
            rows=[
                _page_row("row-current-version", current_item_id, source_id="source-1"),
                _page_row(
                    "row-stale-version",
                    stale_item_id,
                    source_id="source-1",
                    projection_version="news_page_rows_v2",
                ),
            ],
        )

        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert [row["row_id"] for row in rows] == ["row-current-version"]


def test_list_news_page_rows_requires_enabled_observation_edge(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_item_key="disabled-source", title="Disabled")
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[_page_row("row-disabled-source", news_item_id, source_id="source-1")],
        )
        conn.execute("UPDATE news_sources SET enabled = false WHERE source_id = 'source-1'")
        conn.commit()

        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert rows == []


def test_list_news_page_rows_hides_stale_disabled_projected_source_before_reprojection(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(
            repo,
            source_id="source-disabled",
            source_item_key="shared-stale",
            title="Shared stale",
        )
        repo.upsert_source(
            source_id="source-enabled",
            provider_type="rss",
            feed_url="https://enabled-stale.example/rss.xml",
            source_domain="enabled-stale.example",
            source_name="Enabled Stale",
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="source-enabled", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="source-enabled",
            fetch_run_id=fetch_run_id,
            source_item_key="shared-stale-enabled",
            canonical_url="https://example.com/news/shared-stale",
            payload_hash="hash-shared-stale-enabled",
            raw_payload_json={"title": "Shared stale"},
            fetched_at_ms=NOW_MS,
        )
        repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://example.com/news/shared-stale",
            title="Shared stale",
            summary="Summary",
            body_text="Body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-shared-stale",
            title_fingerprint="shared stale",
            now_ms=NOW_MS,
        )
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[_page_row("row-stale-disabled-source", news_item_id, source_id="source-disabled")],
        )
        conn.execute("UPDATE news_sources SET enabled = false WHERE source_id = 'source-disabled'")
        conn.commit()

        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert rows == []


def test_replace_page_rows_for_items_writes_canonical_duplicate_summary_columns(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_item_key="summary", title="Summary")
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[_page_row("row-summary", news_item_id, source_id="source-1")],
        )

        row = conn.execute(
            """
            SELECT canonical_item_key, duplicate_count, source_ids_json,
                   source_domains_json, provider_article_keys_json
              FROM news_page_rows
             WHERE row_id = 'row-summary'
            """
        ).fetchone()
        item = conn.execute(
            """
            SELECT canonical_item_key, duplicate_observation_count, source_ids_json,
                   source_domains_json, provider_article_keys_json
              FROM news_items
             WHERE news_item_id = %s
            """,
            (news_item_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row["canonical_item_key"] == item["canonical_item_key"]
    assert row["duplicate_count"] == item["duplicate_observation_count"]
    assert row["source_ids_json"] == item["source_ids_json"] == ["source-1"]
    assert row["source_domains_json"] == item["source_domains_json"] == ["example.com"]
    assert row["provider_article_keys_json"] == item["provider_article_keys_json"] == []


def test_replace_page_rows_summary_counts_enabled_edges_only(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_item_key="summary", title="Summary")
        repo.upsert_source(
            source_id="source-disabled",
            provider_type="rss",
            feed_url="https://disabled.example/rss.xml",
            source_domain="disabled.example",
            source_name="Disabled",
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="source-disabled", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="source-disabled",
            fetch_run_id=fetch_run_id,
            source_item_key="summary-disabled",
            canonical_url="https://example.com/news/summary",
            payload_hash="hash-summary-disabled",
            raw_payload_json={"title": "Summary"},
            fetched_at_ms=NOW_MS,
        )
        duplicate_news = repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://example.com/news/summary",
            title="Summary",
            summary="Summary",
            body_text="Body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-summary",
            title_fingerprint="summary",
            now_ms=NOW_MS,
        )
        conn.execute("UPDATE news_sources SET enabled = false WHERE source_id = 'source-disabled'")
        conn.commit()

        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[_page_row("row-summary-enabled", news_item_id, source_id="source-1")],
        )
        row = conn.execute(
            """
            SELECT duplicate_count, source_ids_json, source_domains_json, provider_article_keys_json
              FROM news_page_rows
             WHERE row_id = 'row-summary-enabled'
            """
        ).fetchone()
        item = conn.execute(
            """
            SELECT duplicate_observation_count, source_ids_json
              FROM news_items
             WHERE news_item_id = %s
            """,
            (news_item_id,),
        ).fetchone()
    finally:
        conn.close()

    assert duplicate_news["news_item_id"] == news_item_id
    assert item["duplicate_observation_count"] == 2
    assert set(item["source_ids_json"]) == {"source-1", "source-disabled"}
    assert row["duplicate_count"] == 1
    assert row["source_ids_json"] == ["source-1"]
    assert row["source_domains_json"] == ["example.com"]
    assert row["provider_article_keys_json"] == []


def test_news_item_agent_brief_migration_backfills_pending_page_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260519_0066")

        news_item_id = _insert_legacy_source_provider_and_item(conn)
        conn.execute(
            """
            INSERT INTO news_page_rows (
              row_id, news_item_id, story_id, latest_at_ms, lifecycle_status,
              headline, summary, source_domain, canonical_url, token_lanes_json,
              fact_lanes_json, story_json, source_json, computed_at_ms, projection_version
            )
            VALUES (
              %s, %s, NULL, %s, 'raw',
              'old projected row', 'summary', 'example.com', 'https://example.com/old',
              '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb, %s, %s
            )
            """,
            ("row-old-default", news_item_id, NOW_MS, NOW_MS, NEWS_PAGE_PROJECTION_VERSION),
        )
        conn.commit()
        command.upgrade(config, "head")

        repo = NewsRepository(conn)
        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert rows[0]["agent_status"] == "pending"
    assert rows[0]["agent_brief_computed_at_ms"] is None
    assert "agent_brief_json" not in rows[0]
    assert rows[0]["agent_brief"]["status"] == "pending"
    assert rows[0]["signal"]["status"] == "partial"


def test_canonical_dedup_migration_backfills_identity_and_observation_edges(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260527_0115")

        _insert_legacy_canonical_source(conn)
        _insert_legacy_canonical_provider_and_item(
            conn,
            suffix="a",
            canonical_url="https://example.com/news/shared",
            content_hash="content-shared",
        )
        _insert_legacy_canonical_provider_and_item(
            conn,
            suffix="b",
            canonical_url="https://example.com/news/shared",
            content_hash="content-shared",
        )
        conn.commit()

        command.upgrade(config, "head")

        rows = conn.execute(
            """
            SELECT news_item_id, canonical_item_key, duplicate_observation_count,
                   source_ids_json, source_domains_json, provider_article_keys_json
              FROM news_items
             ORDER BY news_item_id
            """
        ).fetchall()
        edge_rows = conn.execute(
            """
            SELECT provider_item_id, news_item_id, source_id, provider_article_key,
                   match_type, match_confidence
              FROM news_item_observation_edges
             ORDER BY provider_item_id
            """
        ).fetchall()
        empty_key_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_items WHERE canonical_item_key = ''"
        ).fetchone()["count"]
        zero_edge_count = conn.execute(
            """
            SELECT COUNT(*) AS count
              FROM news_items AS items
             WHERE NOT EXISTS (
               SELECT 1
                 FROM news_item_observation_edges AS edges
                WHERE edges.news_item_id = items.news_item_id
             )
            """
        ).fetchone()["count"]
        duplicate_key_count = conn.execute(
            """
            SELECT COUNT(*) AS count
              FROM (
                SELECT canonical_item_key
                  FROM news_items
                 WHERE canonical_item_key <> ''
                 GROUP BY canonical_item_key
                HAVING COUNT(*) > 1
              ) AS duplicate_keys
            """
        ).fetchone()["count"]
        canonical_index_exists = conn.execute(
            "SELECT to_regclass('public.ux_news_items_canonical_item_key') IS NOT NULL AS exists"
        ).fetchone()["exists"]
    finally:
        conn.close()

    assert empty_key_count == 0
    assert zero_edge_count == 0
    assert duplicate_key_count == 0
    assert canonical_index_exists is True
    assert len(rows) == 1
    assert len(edge_rows) == 2
    assert [dict(row) for row in rows] == [
        {
            "news_item_id": "news-item-legacy-a",
            "canonical_item_key": "canonical-url:https://example.com/news/shared",
            "duplicate_observation_count": 2,
            "source_ids_json": ["source-legacy"],
            "source_domains_json": ["example.com"],
            "provider_article_keys_json": [],
        }
    ]
    assert {tuple(row["source_ids_json"]) for row in rows} == {("source-legacy",)}
    assert {tuple(row["source_domains_json"]) for row in rows} == {("example.com",)}
    assert [dict(row) for row in edge_rows] == [
        {
            "provider_item_id": "provider-item-legacy-a",
            "news_item_id": "news-item-legacy-a",
            "source_id": "source-legacy",
            "provider_article_key": "",
            "match_type": "same_canonical_url",
            "match_confidence": "strong",
        },
        {
            "provider_item_id": "provider-item-legacy-b",
            "news_item_id": "news-item-legacy-a",
            "source_id": "source-legacy",
            "provider_article_key": "",
            "match_type": "same_canonical_url",
            "match_confidence": "strong",
        },
    ]


def test_canonical_dedup_migration_promotes_public_urls_to_hard_identity(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260527_0115")

        _insert_legacy_canonical_source(conn, source_id="source-url", provider_type="rss")
        for suffix, url in (
            ("news-root", "https://example.com/news"),
            ("nyt-live", "https://www.nytimes.com/live/2026/05/28/business/markets-fed"),
            ("tass-world", "https://tass.com/world"),
            ("afp-news", "https://www.afp.com/en/news"),
        ):
            _insert_legacy_canonical_provider_and_item(
                conn,
                suffix=suffix,
                source_id="source-url",
                canonical_url=url,
                content_hash=f"content-{suffix}",
            )
        conn.commit()

        command.upgrade(config, "head")

        rows = conn.execute(
            """
            SELECT canonical_url, canonical_item_key, dedup_key_kind, url_identity_kind
              FROM news_items
             ORDER BY canonical_url
            """
        ).fetchall()
        edges = conn.execute(
            """
            SELECT items.canonical_url, edges.match_type
              FROM news_item_observation_edges AS edges
              JOIN news_items AS items ON items.news_item_id = edges.news_item_id
             ORDER BY items.canonical_url
            """
        ).fetchall()
    finally:
        conn.close()

    assert [row["canonical_item_key"] for row in rows] == [
        "canonical-url:https://example.com/news",
        "canonical-url:https://tass.com/world",
        "canonical-url:https://www.afp.com/en/news",
        "canonical-url:https://www.nytimes.com/live/2026/05/28/business/markets-fed",
    ]
    assert {row["dedup_key_kind"] for row in rows} == {"canonical_url"}
    assert {row["url_identity_kind"] for row in rows} == {"aggregator", "live_page"}
    assert {row["match_type"] for row in edges} == {"same_canonical_url"}


def test_canonical_dedup_migration_backfills_opennews_provider_id_only_from_payload(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute("GRANT ALL ON SCHEMA public TO public")
        conn.commit()
        config = alembic_config()
        config.attributes["database_url"] = _test_postgres_dsn()
        command.upgrade(config, "20260527_0115")

        _insert_legacy_canonical_source(
            conn,
            source_id="opennews-legacy",
            provider_type="opennews",
            source_domain="6551.io",
        )
        _insert_legacy_canonical_provider_and_item(
            conn,
            suffix="opennews-missing",
            source_id="opennews-legacy",
            source_domain="6551.io",
            source_item_key="source-key-is-not-article-id",
            canonical_url="opennews://item/source-key-is-not-article-id",
            content_hash="content-opennews-missing",
            raw_payload={"sourceItemKey": "source-key-is-not-article-id", "title": "Missing provider id"},
        )
        _insert_legacy_canonical_provider_and_item(
            conn,
            suffix="opennews-real",
            source_id="opennews-legacy",
            source_domain="6551.io",
            source_item_key="transient-source-key",
            canonical_url="opennews://item/2367422",
            content_hash="content-opennews-real",
            raw_payload={"id": 2367422, "title": "Real provider id"},
        )
        conn.commit()

        command.upgrade(config, "head")

        providers = conn.execute(
            """
            SELECT source_item_key, provider_article_id, provider_article_key
              FROM news_provider_items
             ORDER BY source_item_key
            """
        ).fetchall()
        rows = conn.execute(
            """
            SELECT canonical_url, canonical_item_key, provider_article_keys_json
              FROM news_items
             ORDER BY canonical_url
            """
        ).fetchall()
    finally:
        conn.close()

    assert [dict(row) for row in providers] == [
        {
            "source_item_key": "source-key-is-not-article-id",
            "provider_article_id": "",
            "provider_article_key": "",
        },
        {
            "source_item_key": "transient-source-key",
            "provider_article_id": "2367422",
            "provider_article_key": "opennews:2367422",
        },
    ]
    assert [dict(row) for row in rows] == [
        {
            "canonical_url": "opennews://item/2367422",
            "canonical_item_key": "content-hash:content-opennews-real",
            "provider_article_keys_json": ["opennews:2367422"],
        },
        {
            "canonical_url": "opennews://item/source-key-is-not-article-id",
            "canonical_item_key": "content-hash:content-opennews-missing",
            "provider_article_keys_json": [],
        },
    ]


def test_page_projection_rebuilds_and_lists_agent_brief_columns_when_brief_updates(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[
                _page_row(
                    "row-1",
                    news_item_id,
                    source_id="source-1",
                    projection_version=NEWS_PAGE_PROJECTION_VERSION,
                    computed_at_ms=NOW_MS + 10,
                )
            ],
        )
        run = _insert_agent_run(repo, news_item_id=news_item_id, run_id="run-brief-1")
        repo.upsert_news_item_agent_brief(
            news_item_id=news_item_id,
            agent_run_id=run["run_id"],
            status="ready",
            direction="bullish",
            decision_class="driver",
            brief_json={
                "summary_zh": "SOL ETF 申请提升关注。",
                "market_read_zh": "叙事催化增强。",
                "bull_view": {"strength": "strong"},
                "bear_view": {"strength": "weak"},
                "data_gaps": [{"kind": "identity"}],
            },
            input_hash="input-brief-1",
            artifact_version_hash="artifact-brief-1",
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 100,
            created_at_ms=NOW_MS + 100,
            updated_at_ms=NOW_MS + 100,
        )

        candidates = repo.load_items_for_page_projection(news_item_ids=[news_item_id])
        row = candidates[0]
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[
                {
                    **_page_row(
                        "row-1",
                        news_item_id,
                        source_id="source-1",
                        projection_version=NEWS_PAGE_PROJECTION_VERSION,
                        computed_at_ms=NOW_MS + 200,
                    ),
                    "agent_brief_json": {
                        "status": "ready",
                        "summary_zh": "SOL ETF 申请提升关注。",
                        "agent_run_id": "run-brief-1",
                    },
                    "agent_status": "ready",
                    "agent_brief_computed_at_ms": NOW_MS + 100,
                }
            ],
        )
        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert [candidate["item"]["news_item_id"] for candidate in candidates] == [news_item_id]
    assert row["current_brief"]["agent_run_id"] == "run-brief-1"
    assert rows[0]["agent_status"] == "ready"
    assert rows[0]["agent_brief_computed_at_ms"] == NOW_MS + 100
    assert "agent_brief_status" not in rows[0]
    assert "agent_brief_json" not in rows[0]
    assert rows[0]["agent_brief"]["summary_zh"] == "SOL ETF 申请提升关注。"
    assert "agent_run_id" not in rows[0]["agent_brief"]
    assert "input_hash" not in rows[0]["agent_brief"]
    assert "artifact_version_hash" not in rows[0]["agent_brief"]


def test_news_high_signal_candidates_do_not_require_ready_agent_status(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[
                {
                    **_page_row("row-provider-high", news_item_id, source_id="source-1"),
                    "signal_json": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "external_push_block_reason": "agent_brief_not_ready",
                            "provider_score": 90,
                            "decision_class": "context",
                        },
                    },
                    "token_impacts_json": [{"symbol": "BTC", "score": 90}],
                    "agent_status": "insufficient",
                    "agent_brief_json": {
                        "status": "insufficient",
                        "direction": "neutral",
                        "decision_class": "context",
                    },
                }
            ],
        )

        rows = repo.list_news_high_signal_notification_candidates(min_score=85, limit=10)
    finally:
        conn.close()

    assert [row["news_item_id"] for row in rows] == [news_item_id]
    assert rows[0]["agent_status"] == "insufficient"
    assert rows[0]["signal"]["alert_eligibility"]["provider_score"] == 90


def test_news_high_signal_candidates_hide_stale_disabled_projected_source_before_reprojection(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(
            repo,
            source_id="source-disabled",
            source_item_key="candidate-stale",
            title="Candidate stale",
        )
        repo.upsert_source(
            source_id="source-enabled",
            provider_type="rss",
            feed_url="https://candidate-enabled.example/rss.xml",
            source_domain="candidate-enabled.example",
            source_name="Candidate Enabled",
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="source-enabled", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="source-enabled",
            fetch_run_id=fetch_run_id,
            source_item_key="candidate-stale-enabled",
            canonical_url="https://example.com/news/candidate-stale",
            payload_hash="hash-candidate-stale-enabled",
            raw_payload_json={"title": "Candidate stale"},
            fetched_at_ms=NOW_MS,
        )
        repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://example.com/news/candidate-stale",
            title="Candidate stale",
            summary="Summary",
            body_text="Body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-candidate-stale",
            title_fingerprint="candidate stale",
            now_ms=NOW_MS,
        )
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[
                {
                    **_page_row("row-candidate-stale", news_item_id, source_id="source-disabled"),
                    "signal": {
                        "display_signal": {"direction": "bullish", "score": 90},
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "provider_score": 90,
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 90}],
                }
            ],
        )
        conn.execute("UPDATE news_sources SET enabled = false WHERE source_id = 'source-disabled'")
        conn.commit()

        rows = repo.list_news_high_signal_notification_candidates(min_score=85, limit=10)
    finally:
        conn.close()

    assert rows == []


def test_news_high_signal_candidates_filter_to_current_projection_version(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        current_item_id = _insert_source_provider_and_item(
            repo,
            source_item_key="current-candidate",
            title="Current candidate",
        )
        stale_item_id = _insert_source_provider_and_item(
            repo,
            source_item_key="stale-candidate",
            title="Stale candidate",
        )
        ready_signal = {
            "direction": "bullish",
            "alert_eligibility": {
                "in_app_eligible": True,
                "external_push_ready": True,
                "provider_score": 91,
                "decision_class": "driver",
            },
        }
        repo.replace_page_rows_for_items(
            news_item_ids=[current_item_id, stale_item_id],
            rows=[
                {
                    **_page_row("row-current-candidate", current_item_id, source_id="source-1"),
                    "signal_json": ready_signal,
                    "token_impacts_json": [{"symbol": "BTC", "score": 91}],
                },
                {
                    **_page_row(
                        "row-stale-candidate",
                        stale_item_id,
                        source_id="source-1",
                        projection_version="news_page_rows_v2",
                    ),
                    "signal_json": ready_signal,
                    "token_impacts_json": [{"symbol": "ETH", "score": 91}],
                },
            ],
        )

        rows = repo.list_news_high_signal_notification_candidates(min_score=85, limit=10)
    finally:
        conn.close()

    assert [row["row_id"] for row in rows] == ["row-current-candidate"]


def test_list_news_page_rows_uses_composite_cursor(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        first_item_id = _insert_source_provider_and_item(repo, source_item_key="first", title="First")
        second_item_id = _insert_source_provider_and_item(repo, source_item_key="second", title="Second")
        third_item_id = _insert_source_provider_and_item(repo, source_item_key="third", title="Third")
        repo.replace_page_rows_for_items(
            news_item_ids=[first_item_id, second_item_id, third_item_id],
            rows=[
                _page_row("row-c", first_item_id, source_id="source-1", latest_at_ms=NOW_MS + 300),
                _page_row("row-a", second_item_id, source_id="source-1", latest_at_ms=NOW_MS + 200),
                _page_row("row-b", third_item_id, source_id="source-1", latest_at_ms=NOW_MS + 100),
            ],
        )

        first_page = repo.list_news_page_rows(limit=1)
        second_page = repo.list_news_page_rows(limit=10, cursor=news_page_cursor(first_page[0]))
    finally:
        conn.close()

    assert [row["row_id"] for row in first_page] == ["row-c"]
    assert [row["row_id"] for row in second_page] == ["row-a", "row-b"]


def test_list_news_page_rows_filters_by_signal(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        bullish_item_id = _insert_source_provider_and_item(repo, source_item_key="bullish", title="Bullish")
        bearish_item_id = _insert_source_provider_and_item(repo, source_item_key="bearish", title="Bearish")
        repo.replace_page_rows_for_items(
            news_item_ids=[bullish_item_id, bearish_item_id],
            rows=[
                {
                    **_page_row("row-bullish", bullish_item_id, source_id="source-1"),
                    "agent_status": "ready",
                    "agent_brief_json": {"status": "ready", "direction": "bullish"},
                    "signal": {"display_signal": {"direction": "bullish", "score": 80}},
                },
                {
                    **_page_row("row-bearish", bearish_item_id, source_id="source-1"),
                    "agent_status": "ready",
                    "agent_brief_json": {"status": "ready", "direction": "bearish"},
                    "signal": {"display_signal": {"direction": "bearish", "score": 88}},
                },
            ],
        )

        rows = repo.list_news_page_rows(limit=10, signal="bearish")
    finally:
        conn.close()

    assert [row["row_id"] for row in rows] == ["row-bearish"]
    assert rows[0]["signal"]["display_signal"]["direction"] == "bearish"


def test_list_news_page_rows_filters_by_query_text(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        matching_item_id = _insert_source_provider_and_item(
            repo,
            source_item_key="matching",
            title="Ethereum ETF approved",
        )
        other_item_id = _insert_source_provider_and_item(repo, source_item_key="other", title="Solana update")
        repo.replace_page_rows_for_items(
            news_item_ids=[matching_item_id, other_item_id],
            rows=[
                {
                    **_page_row("row-matching", matching_item_id, source_id="source-1"),
                    "headline": "Ethereum ETF approved",
                    "summary": "Spot ETF flows are expanding.",
                },
                {
                    **_page_row("row-other", other_item_id, source_id="source-1"),
                    "headline": "Solana update",
                    "summary": "Validator notes and market color.",
                },
            ],
        )

        rows = repo.list_news_page_rows(limit=10, q="ethereum")
    finally:
        conn.close()

    assert [row["row_id"] for row in rows] == ["row-matching"]


def test_page_projection_loader_includes_source_classification_changes(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_id="source-1")
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[
                _page_row(
                    "row-current",
                    news_item_id,
                    source_id="source-1",
                    projection_version=NEWS_PAGE_PROJECTION_VERSION,
                    computed_at_ms=NOW_MS + 10,
                )
            ],
        )
        conn.execute(
            """
            UPDATE news_sources
               SET coverage_tags_json = '["exchange_listing"]'::jsonb,
                   source_quality_status = 'healthy',
                   updated_at_ms = %s
             WHERE source_id = %s
            """,
            (NOW_MS + 100, "source-1"),
        )
        conn.commit()

        candidates = repo.load_items_for_page_projection(news_item_ids=[news_item_id])
    finally:
        conn.close()

    assert [candidate["item"]["news_item_id"] for candidate in candidates] == [news_item_id]
    assert candidates[0]["item"]["coverage_tags_json"] == ["exchange_listing"]
    assert candidates[0]["item"]["source_quality_status"] == "healthy"


def test_updating_news_item_clears_stale_item_facts_and_refreshes_page_projection(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[
                _page_row(
                    "row-1",
                    news_item_id,
                    source_id="source-1",
                    projection_version=NEWS_PAGE_PROJECTION_VERSION,
                    computed_at_ms=NOW_MS,
                )
            ],
        )
        conn.execute(
            """
            INSERT INTO news_item_entities (
              entity_id, news_item_id, entity_type, raw_value, normalized_value, chain,
              span_start, span_end, text_surface, confidence, extraction_policy_version, created_at_ms
            )
            VALUES (%s, %s, 'symbol', '$OLD', 'OLD', NULL, 0, 4, 'title', 0.8, 'test', %s)
            """,
            ("entity-old", news_item_id, NOW_MS),
        )
        conn.execute(
            """
            INSERT INTO news_token_mentions (
              mention_id, news_item_id, entity_id, observed_symbol, resolution_status, target_type,
              target_id, display_symbol, reason_codes_json, candidate_targets_json, evidence_strength,
              confidence, created_at_ms
            )
            VALUES (%s, %s, %s, 'OLD', 'known_symbol', 'CexToken', 'cex:OLD', 'OLD', %s, %s, 'medium', 0.8, %s)
            """,
            ("mention-old", news_item_id, "entity-old", Jsonb(["CONFIRMED_CEX_TOKEN"]), Jsonb([]), NOW_MS),
        )
        conn.execute(
            """
            INSERT INTO news_fact_candidates (
              fact_candidate_id, news_item_id, event_type, claim, realis, evidence_quote,
              evidence_span_start, evidence_span_end, source_role, required_slots_json,
              affected_targets_json, validation_status, rejection_reasons_json, extraction_method,
              policy_version, created_at_ms, updated_at_ms
            )
            VALUES (
              %s, %s, 'listing', 'Old claim', 'reported_claim', 'Old evidence',
              0, 12, 'official_exchange', %s, %s, 'accepted', %s, 'test', 'test', %s, %s
            )
            """,
            ("fact-old", news_item_id, Jsonb({"asset": True}), Jsonb([]), Jsonb([]), NOW_MS, NOW_MS),
        )
        conn.commit()
        provider = conn.execute(
            "SELECT provider_item_id FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()

        repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://example.com/news/guid-1",
            title="Title",
            summary="Summary",
            body_text="Changed body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS + 1,
            content_hash="content-guid-1-v2",
            title_fingerprint="title",
            now_ms=NOW_MS + 1,
        )

        page_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_page_rows WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["count"]
        entity_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_item_entities WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["count"]
        mention_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_token_mentions WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["count"]
        fact_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_fact_candidates WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["count"]
        status = conn.execute(
            "SELECT lifecycle_status FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["lifecycle_status"]
        repos = repositories_for_connection(conn)
        repos.news_projection_dirty_targets.enqueue_targets(
            [{"projection_name": "page", "target_kind": "news_item", "target_id": news_item_id}],
            reason="news_item_written",
            now_ms=NOW_MS + 2,
        )
        page_worker = NewsPageProjectionWorker(
            name="news_page_projection",
            settings=SimpleNamespace(batch_size=10, lease_ms=60_000, retry_ms=30_000, statement_timeout_seconds=30),
            db=_SingleConnectionWorkerDB(conn),
            telemetry=object(),
        )
        page_result = page_worker.run_once_sync(now_ms=NOW_MS + 3)
        refreshed_page = conn.execute(
            """
            SELECT token_lanes_json, fact_lanes_json
              FROM news_page_rows
             WHERE news_item_id = %s
            """,
            (news_item_id,),
        ).fetchone()
    finally:
        conn.close()

    assert page_count == 1
    assert entity_count == 0
    assert mention_count == 0
    assert fact_count == 0
    assert status == "raw"
    assert page_result.processed == 1
    assert refreshed_page["token_lanes_json"] == []
    assert refreshed_page["fact_lanes_json"] == []


def test_update_item_content_classification_persists_materialized_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)

        repo.update_item_content_classification(
            news_item_id=news_item_id,
            content_class="regulation",
            content_tags=["tokenized_stocks", "sec"],
            classification_payload={"policy_version": "test", "matched_rules": ["rule-1"]},
            now_ms=NOW_MS + 1,
        )

        row = conn.execute(
            """
            SELECT content_class, content_tags_json, content_classification_json, updated_at_ms
              FROM news_items
             WHERE news_item_id = %s
            """,
            (news_item_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row["content_class"] == "regulation"
    assert row["content_tags_json"] == ["tokenized_stocks", "sec"]
    assert row["content_classification_json"] == {"policy_version": "test", "matched_rules": ["rule-1"]}
    assert row["updated_at_ms"] == NOW_MS + 1


def test_list_unprocessed_items_claims_processed_unclassified_items(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        classified_id = _insert_source_provider_and_item(repo, source_item_key="classified", title="Classified")
        unclassified_id = _insert_source_provider_and_item(repo, source_item_key="unclassified", title="Unclassified")
        repo.update_item_content_classification(
            news_item_id=classified_id,
            content_class="crypto_market",
            content_tags=["crypto_market"],
            classification_payload={"policy_version": "test"},
            now_ms=NOW_MS + 1,
        )
        repo.mark_item_processed(news_item_id=classified_id, processed_at_ms=NOW_MS + 2)
        repo.mark_item_processed(news_item_id=unclassified_id, processed_at_ms=NOW_MS + 2)

        rows = repo.list_unprocessed_items(limit=10, now_ms=NOW_MS + 3)
    finally:
        conn.close()

    assert [row["news_item_id"] for row in rows] == [unclassified_id]
    assert rows[0]["lifecycle_status"] == "processed"
    assert rows[0]["content_classification_json"] == {}


def test_get_news_item_detail_hydrates_agent_brief_and_latest_run_summary(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        run = _insert_agent_run(repo, news_item_id=news_item_id, run_id="run-detail-1")
        repo.upsert_news_item_agent_brief(
            news_item_id=news_item_id,
            agent_run_id=run["run_id"],
            status="ready",
            direction="mixed",
            decision_class="watch",
            brief_json={
                "summary_zh": "事件仍需观察。",
                "market_read_zh": "短线影响取决于确认信号。",
                "bull_view": {"strength": "moderate"},
                "bear_view": {"strength": "weak"},
            },
            input_hash="input-brief-1",
            artifact_version_hash="artifact-brief-1",
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 100,
            created_at_ms=NOW_MS + 100,
            updated_at_ms=NOW_MS + 100,
        )

        detail = repo.get_news_item_detail(news_item_id=news_item_id)
    finally:
        conn.close()

    assert detail is not None
    assert detail["agent_brief"]["status"] == "ready"
    assert detail["agent_brief"]["direction"] == "mixed"
    assert detail["agent_brief"]["brief_json"]["summary_zh"] == "事件仍需观察。"
    assert "agent_run_id" not in detail["agent_brief"]
    assert "input_hash" not in detail["agent_brief"]
    assert "artifact_version_hash" not in detail["agent_brief"]
    assert detail["agent_run"] == {
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
        "model": "gpt-5-mini",
        "provider": "litellm",
        "lane": NEWS_ITEM_BRIEF_LANE,
        "error_class": None,
        "error": None,
        "started_at_ms": NOW_MS + 90,
        "finished_at_ms": NOW_MS + 100,
    }
    assert "request_json" not in detail["agent_run"]
    assert "response_json" not in detail["agent_run"]


def test_get_news_item_detail_reads_current_projected_signal_and_lanes(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_item_key="detail-projection")
        run = _insert_agent_run(repo, news_item_id=news_item_id, run_id="run-detail-projected")
        repo.upsert_news_item_agent_brief(
            news_item_id=news_item_id,
            agent_run_id=run["run_id"],
            status="ready",
            direction="bearish",
            decision_class="driver",
            brief_json={
                "summary_zh": "原始 agent brief 不应覆盖当前投影。",
                "market_read_zh": "detail 必须与 page projection 一致。",
            },
            input_hash="input-brief-1",
            artifact_version_hash="artifact-brief-1",
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 100,
            created_at_ms=NOW_MS + 100,
            updated_at_ms=NOW_MS + 100,
        )
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[
                {
                    **_page_row("row-detail-current", news_item_id, source_id="source-1"),
                    "signal_json": {
                        "source": "provider",
                        "status": "ready",
                        "direction": "bullish",
                        "score": 88,
                        "method": "projected-page-row",
                    },
                    "token_impacts_json": [{"symbol": "BTC", "score": 88}],
                    "token_lanes_json": [{"lane": "resolved", "symbol": "BTC"}],
                    "fact_lanes_json": [{"status": "accepted", "event_type": "macro"}],
                    "content_tags_json": ["macro"],
                    "content_classification_json": {"policy_version": "projected"},
                }
            ],
        )

        detail = repo.get_news_item_detail(news_item_id=news_item_id)
    finally:
        conn.close()

    assert detail is not None
    assert detail["signal"]["method"] == "projected-page-row"
    assert detail["signal"]["direction"] == "bullish"
    assert detail["token_impacts"] == [{"symbol": "BTC", "score": 88}]
    assert detail["token_lanes"] == [{"lane": "resolved", "symbol": "BTC"}]
    assert detail["fact_lanes"] == [{"status": "accepted", "event_type": "macro"}]
    assert detail["content_tags"] == ["macro"]
    assert detail["content_classification"] == {"policy_version": "projected"}


def test_get_news_item_detail_exposes_canonical_observation_evidence(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_id="source-1", source_item_key="shared")
        repo.upsert_source(
            source_id="source-2",
            provider_type="rss",
            feed_url="https://source-2.example.com/rss.xml",
            source_domain="source-2.example.com",
            source_name="Source Two",
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="source-2", started_at_ms=NOW_MS)
        provider = repo.upsert_provider_item(
            source_id="source-2",
            fetch_run_id=fetch_run_id,
            source_item_key="shared-copy",
            canonical_url="opennews://item/shared-copy",
            payload_hash="hash-shared-copy",
            raw_payload_json={"id": "shared-copy", "title": "Shared"},
            fetched_at_ms=NOW_MS,
        )
        repo.upsert_canonical_news_item(
            provider_item_id=provider["provider_item_id"],
            canonical_url="https://example.com/news/shared",
            title="Shared",
            summary="Summary",
            body_text="Body",
            language="en",
            published_at_ms=NOW_MS,
            fetched_at_ms=NOW_MS,
            content_hash="content-shared",
            title_fingerprint="shared",
            now_ms=NOW_MS,
        )

        detail = repo.get_news_item_detail(news_item_id=news_item_id)
    finally:
        conn.close()

    assert detail is not None
    assert "provider_item_id" not in detail
    assert "canonical_item_key" not in detail
    assert "dedup_key_kind" not in detail
    assert "dedup_key_confidence" not in detail
    assert "url_identity_kind" not in detail
    assert "source_ids_json" not in detail
    assert "source_domains_json" not in detail
    assert "provider_article_keys_json" not in detail
    assert {edge["source_id"] for edge in detail["observation_edges"]} == {"source-1", "source-2"}
    assert {item["source_id"] for item in detail["provider_observations"]} == {"source-1", "source-2"}
    assert all("provider_item_id" not in item for item in detail["provider_observations"])
    assert all("source_item_key" not in item for item in detail["provider_observations"])
    assert all("raw_payload_json" not in item for item in detail["provider_observations"])
    assert {item["canonical_url"] for item in detail["provider_observations"]} == {
        "",
        "https://example.com/news/shared",
    }
    assert "source_item_key" not in detail["provider_item"]
    assert detail["source"]["source_id"] == "source-1"
    assert "feed_url" not in detail["source"]
    assert "fetch_policy_json" not in detail["source"]
    assert "sync_cursor_json" not in detail["source"]
    assert detail["fetch_run"]["source_id"] == "source-1"
    assert detail["fetch_run"]["status"] == "running"
    assert "fetch_run_id" not in detail["fetch_run"]


def test_fact_detail_sanitizes_internal_urls(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_item_key="internal-url")
        conn.execute(
            "UPDATE news_items SET canonical_url = 'opennews://item/internal-url' WHERE news_item_id = %s",
            (news_item_id,),
        )
        conn.execute(
            """
            INSERT INTO news_fact_candidates (
              fact_candidate_id, news_item_id, event_type, claim, realis, evidence_quote,
              evidence_span_start, evidence_span_end, source_role, required_slots_json,
              affected_targets_json, validation_status, rejection_reasons_json, extraction_method,
              policy_version, created_at_ms, updated_at_ms
            )
            VALUES (
              'fact-internal-url', %s, 'listing', 'Claim', 'reported_claim', 'Evidence',
              0, 8, 'observed_source', '{}'::jsonb, '[]'::jsonb, 'accepted', '[]'::jsonb,
              'test', 'test', %s, %s
            )
            """,
            (news_item_id, NOW_MS, NOW_MS),
        )
        fact = repo.get_news_fact_detail(fact_candidate_id="fact-internal-url")
    finally:
        conn.close()

    assert fact is not None
    assert fact["canonical_url"] == ""


def test_research_fact_context_is_item_scoped_bounded_and_rejection_aware(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        _insert_fact_candidate(
            conn,
            news_item_id=news_item_id,
            fact_candidate_id="fact-accepted",
            validation_status="accepted",
            claim="Issuer filed for a SOL ETF.",
        )
        _insert_fact_candidate(
            conn,
            news_item_id=news_item_id,
            fact_candidate_id="fact-attention",
            validation_status="attention",
            claim="Analysts expect a decision window.",
        )
        _insert_fact_candidate(
            conn,
            news_item_id=news_item_id,
            fact_candidate_id="fact-rejected",
            validation_status="rejected",
            claim="Rejected rumor.",
        )
        conn.commit()

        default_rows = repo.get_fact_context(news_item_id=news_item_id, limit=10)
        limited_rows = repo.get_fact_context(news_item_id=news_item_id, limit=1)
        with_rejected = repo.get_fact_context(news_item_id=news_item_id, include_rejected=True, limit=10)
    finally:
        conn.close()

    assert {row["validation_status"] for row in default_rows} == {"accepted", "attention"}
    assert len(limited_rows) == 1
    assert {row["validation_status"] for row in with_rejected} == {"accepted", "attention", "rejected"}
    assert all(row["news_item_id"] == news_item_id for row in with_rejected)
    assert all("raw_payload_json" not in row for row in with_rejected)
    assert with_rejected[0]["result_basis"] == "fact_candidate"
    assert with_rejected[0]["evidence_ref"].startswith("news_fact_candidates:")


def test_research_observation_history_marks_same_domain_sources_not_independent(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_id="source-1", source_item_key="shared")
        _attach_observation_source(
            repo,
            news_item_id=news_item_id,
            source_id="source-2",
            source_domain="example.com",
            source_name="Example Mirror",
            source_item_key="shared-mirror",
        )
        conn.commit()

        history = repo.get_news_observation_history(news_item_id=news_item_id, limit=10)
    finally:
        conn.close()

    assert history["news_item_id"] == news_item_id
    assert history["source_count"] == 2
    assert history["source_domain_count"] == 1
    assert history["observation_count"] == 2
    assert history["duplicate_count"] == 2
    assert history["independent_source_confirmed"] is False
    assert history["independence_class"] == "same_domain_only"
    assert history["source_ids"] == ["source-1", "source-2"]
    assert history["source_domains"] == ["example.com"]
    assert history["same_domain_notes"]
    assert all("provider_item_id" not in row for row in history["observed_sources"])


def test_research_archive_excludes_current_and_returns_compact_public_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        current_id = _insert_source_provider_and_item(repo, source_item_key="current", title="SOL ETF current")
        archive_id = _insert_source_provider_and_item(repo, source_item_key="archive", title="SOL ETF archive")
        conn.execute(
            """
            UPDATE news_items
               SET summary = 'Archive summary for SOL ETF.',
                   body_text = repeat('body should not be selected ', 20),
                   published_at_ms = %s
             WHERE news_item_id = %s
            """,
            (NOW_MS - 60_000, archive_id),
        )
        _insert_token_mention(
            conn,
            news_item_id=archive_id,
            mention_id="mention-archive-sol",
            observed_symbol="SOL",
            target_type="cex_token",
            target_id="binance:SOL",
            display_symbol="SOL",
        )
        _insert_brief(repo, news_item_id=archive_id, run_id="run-archive-sol")
        conn.commit()

        rows = repo.search_news_archive(
            current_news_item_id=current_id,
            query_terms=["SOL ETF"],
            symbols=["SOL"],
            window_hours=168,
            match_modes=["title", "token", "fact", "source_title"],
            limit=8,
            now_ms=NOW_MS,
        )
    finally:
        conn.close()

    assert [row["news_item_id"] for row in rows] == [archive_id]
    row = rows[0]
    assert row["title"] == "SOL ETF archive"
    assert row["summary"] == "Archive summary for SOL ETF."
    assert row["source_domain"] == "example.com"
    assert row["matched_terms"]
    assert row["symbols"] == ["SOL"]
    assert row["brief_status"] == "ready"
    assert row["novelty_status"] == "follow_up"
    assert row["confirmation_state"] == "unconfirmed"
    assert row["source_consensus_zh"] == "单源观察。"
    assert row["result_basis"] in {"term_match", "symbol_match", "similar_news"}
    assert "body_text" not in row
    assert "raw_payload_json" not in row
    assert "provider_item_id" not in row


def test_research_target_context_returns_exact_aggregate_and_heuristic_fallback_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        current_id = _insert_source_provider_and_item(repo, source_item_key="target-current", title="Current SOL")
        exact_id = _insert_source_provider_and_item(repo, source_item_key="target-exact", title="SOL exact listing")
        fallback_id = _insert_source_provider_and_item(
            repo,
            source_item_key="target-fallback",
            title="ARB fallback market update",
        )
        _insert_token_mention(
            conn,
            news_item_id=exact_id,
            mention_id="mention-exact-sol",
            observed_symbol="SOL",
            target_type="cex_token",
            target_id="binance:SOL",
            display_symbol="SOL",
            confidence=0.95,
        )
        _insert_token_mention(
            conn,
            news_item_id=fallback_id,
            mention_id="mention-fallback-sol",
            observed_symbol="ARB",
            target_type=None,
            target_id=None,
            display_symbol="ARB",
            confidence=0.35,
        )
        conn.commit()

        context = repo.get_target_news_context(
            current_news_item_id=current_id,
            target_refs=[
                NewsContextTargetRef(target_type="cex_token", target_id="binance:SOL", display_symbol="SOL")
            ],
            symbol_fallbacks=["SOL", "ARB"],
            window_hours=72,
            limit=12,
            now_ms=NOW_MS,
        )
    finally:
        conn.close()

    assert context["counts"]["total"] == 2
    assert context["counts"]["exact_target"] == 1
    assert context["counts"]["symbol_heuristic"] == 1
    assert context["source_domain_count"] == 1
    assert context["matching_basis"] == ["exact_target", "symbol_heuristic"]
    assert {row["news_item_id"] for row in context["top_items"]} == {exact_id, fallback_id}
    exact_row = next(row for row in context["top_items"] if row["news_item_id"] == exact_id)
    fallback_row = next(row for row in context["top_items"] if row["news_item_id"] == fallback_id)
    assert exact_row["target_type"] == "cex_token"
    assert exact_row["target_id"] == "binance:SOL"
    assert exact_row["matching_basis"] == "exact_target"
    assert fallback_row["display_symbol"] == "ARB"
    assert fallback_row["target_id"] == ""
    assert fallback_row["matching_basis"] == "symbol_heuristic"
    assert all("raw_payload_json" not in row for row in context["top_items"])


def test_research_source_quality_context_returns_targeted_source_health(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_id="source-quality", title="Quality")
        repo.replace_source_quality_rows(
            rows=[
                {
                    **_source_quality_row(source_id="source-quality", computed_at_ms=NOW_MS),
                    "diagnostics_json": {"status": "healthy", "health": "fresh", "window_ms": 86_400_000},
                }
            ],
            status_window="24h",
            commit=True,
        )

        context = repo.get_source_quality_context_for_item(news_item_id=news_item_id)
    finally:
        conn.close()

    assert context["news_item_id"] == news_item_id
    assert context["source_domain"] == "example.com"
    assert context["source_name"] == "Example"
    assert context["source_role"] == "observed_source"
    assert context["trust_tier"] == "standard"
    assert context["window"] == "24h"
    assert context["items_fetched"] == 10
    assert context["duplicate_rate"] == 0.2
    assert context["quality_score"] == 82.0
    assert context["source_quality_status"] == "healthy"
    assert context["source_health"] == "fresh"
    assert "multi_source_confirmed" not in context
    assert "independent_source_confirmed" not in context


def test_repository_session_exposes_news_repository(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = repositories_for_connection(conn)
    finally:
        conn.close()

    assert isinstance(repos.news, NewsRepository)


def test_news_repository_exposes_only_canonical_news_item_writer_surface() -> None:
    assert hasattr(NewsRepository, "upsert_canonical_news_item")
    assert not hasattr(NewsRepository, "upsert_news_item")


def test_canonical_news_item_writer_serializes_canonical_key_upserts() -> None:
    source = inspect.getsource(NewsRepository.upsert_canonical_news_item)

    assert "pg_advisory_xact_lock" in source
    assert "canonical_item_key" in source


def test_provider_item_upsert_keeps_identity_status_monotonic_in_conflict_sql() -> None:
    source = inspect.getsource(NewsRepository.upsert_provider_item)

    assert "provider_article_id = EXCLUDED.provider_article_id" in source
    assert "provider_article_key = EXCLUDED.provider_article_key" in source
    assert "NULLIF(news_provider_items.provider_article_id, '')" not in source
    assert "NULLIF(news_provider_items.provider_article_key, '')" not in source
    assert "news_provider_items.provider_payload_status = 'ready'" in source
    assert "EXCLUDED.provider_payload_status <> 'ready'" in source


def test_source_sync_cursor_round_trips_high_watermark_and_diagnostics(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-realtime",
            provider_type="opennews",
            feed_url="opennews://realtime",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )

        initial = repo.source_sync_cursor("opennews-realtime")
        repo.update_source_sync_state(
            "opennews-realtime",
            {
                "high_watermark_ms": NOW_MS - 5_000,
                "overlap_ms": 1_200_000,
                "pages_scanned": 3,
                "rest_received": 17,
                "oldest_seen_ms": NOW_MS - 90_000,
                "stop_reason": "oldest_before_overlap",
            },
            now_ms=NOW_MS,
        )
        updated = repo.source_sync_cursor("opennews-realtime")
        row = conn.execute(
            """
            SELECT sync_cursor_json, sync_high_watermark_ms, sync_overlap_ms, sync_diagnostics_json
              FROM news_sources
             WHERE source_id = 'opennews-realtime'
            """
        ).fetchone()
    finally:
        conn.close()

    assert initial["high_watermark_ms"] == 0
    assert initial["overlap_ms"] == 900_000
    assert updated["high_watermark_ms"] == NOW_MS - 5_000
    assert updated["overlap_ms"] == 1_200_000
    assert updated["pages_scanned"] == 3
    assert row["sync_high_watermark_ms"] == NOW_MS - 5_000
    assert row["sync_overlap_ms"] == 1_200_000
    assert row["sync_cursor_json"]["stop_reason"] == "oldest_before_overlap"
    assert row["sync_diagnostics_json"] == {
        "pages_scanned": 3,
        "rest_received": 17,
        "oldest_seen_ms": NOW_MS - 90_000,
        "stop_reason": "oldest_before_overlap",
    }


def test_source_status_exposes_news_dedup_and_sync_diagnostics(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(
            repo,
            source_id="opennews-realtime",
            source_item_key="shared",
        )
        repo.update_source_sync_state(
            "opennews-realtime",
            {
                "high_watermark_ms": NOW_MS - 5_000,
                "overlap_ms": 1_200_000,
                "pages_scanned": 3,
                "rest_received": 17,
                "oldest_seen_ms": NOW_MS - 90_000,
                "stop_reason": "oldest_before_overlap",
            },
            now_ms=NOW_MS,
        )
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[_page_row("row-opennews", news_item_id, source_id="opennews-realtime")],
        )

        status = next(row for row in repo.list_source_status() if row["source_id"] == "opennews-realtime")
    finally:
        conn.close()

    assert status["sync_high_watermark_ms"] == NOW_MS - 5_000
    assert status["sync_overlap_ms"] == 1_200_000
    assert status["sync_diagnostics"]["pages_scanned"] == 3
    assert status["dedup_diagnostics"]["raw_observation_count"] == 1
    assert status["dedup_diagnostics"]["canonical_item_count"] == 1
    assert status["dedup_diagnostics"]["observation_edge_count"] == 1
    assert status["dedup_diagnostics"]["enabled_serving_row_count"] == 1
    assert status["dedup_diagnostics"]["disabled_serving_row_count"] == 0


def test_news_dedup_diagnostics_reports_disabled_rows_and_visible_duplicate_excess(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_id="source-1", source_item_key="shared")
        repo.replace_page_rows_for_items(
            news_item_ids=[news_item_id],
            rows=[_page_row("row-shared", news_item_id, source_id="source-1")],
        )
        repo.upsert_source(
            source_id="opennews-realtime",
            provider_type="opennews",
            feed_url="opennews://realtime",
            source_domain="6551.io",
            source_name="OpenNews",
            refresh_interval_seconds=10,
            now_ms=NOW_MS,
        )
        repo.update_source_sync_state(
            "opennews-realtime",
            {
                "high_watermark_ms": NOW_MS - 5_000,
                "overlap_ms": 1_200_000,
                "pages_scanned": 3,
                "rest_received": 17,
                "oldest_seen_ms": NOW_MS - 90_000,
                "stop_reason": "oldest_before_overlap",
            },
            now_ms=NOW_MS,
        )
        conn.execute("UPDATE news_sources SET enabled = false WHERE source_id = 'source-1'")
        conn.commit()

        diagnostics = repo.news_dedup_diagnostics()
    finally:
        conn.close()

    assert diagnostics["raw_observation_count"] == 1
    assert diagnostics["canonical_item_count"] == 1
    assert diagnostics["observation_edge_count"] == 1
    assert diagnostics["disabled_serving_row_count"] == 1
    assert diagnostics["enabled_exact_content_visible_duplicate_excess"] == 0
    assert diagnostics["top_visible_content_duplicate_groups"] == []
    assert diagnostics["top_visible_canonical_duplicate_groups"] == []
    assert diagnostics["source_sync_diagnostics"][0]["source_id"] == "opennews-realtime"
    assert diagnostics["source_sync_diagnostics"][0]["pages_scanned"] == 3
    assert diagnostics["source_sync_diagnostics"][0]["rest_received"] == 17
    assert diagnostics["source_sync_diagnostics"][0]["stop_reason"] == "oldest_before_overlap"
    assert diagnostics["source_sync_diagnostics"][0]["watermark_lag_ms"] >= 0


def test_news_dedup_diagnostics_reports_material_risk_without_repair_actions(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="opennews-listing",
            provider_type="opennews",
            feed_url="opennews://listing",
            source_domain="6551.io",
            source_name="OpenNews Listing",
            refresh_interval_seconds=60,
            now_ms=NOW_MS,
        )
        fetch_run_id = repo.start_fetch_run(source_id="opennews-listing", started_at_ms=NOW_MS)

        for source_item_key, canonical_url, content_hash, now_ms in (
            (
                "2305268",
                "https://news.6551.io/preview/Coinbase-Axelar-AXL",
                "hash-lower",
                NOW_MS,
            ),
            (
                "2305269",
                "https://news.6551.io/preview/coinbase-axelar-axl",
                "hash-upper",
                NOW_MS + 1,
            ),
        ):
            provider = repo.upsert_provider_item(
                source_id="opennews-listing",
                fetch_run_id=fetch_run_id,
                source_item_key=source_item_key,
                canonical_url=canonical_url,
                payload_hash=f"payload-{source_item_key}",
                raw_payload_json={"id": source_item_key, "title": "Coinbase Axelar AXL"},
                fetched_at_ms=now_ms,
            )
            repo.upsert_canonical_news_item(
                provider_item_id=provider["provider_item_id"],
                canonical_url=canonical_url,
                title="Coinbase Axelar AXL is now available to New York residents",
                summary="Coinbase enables AXL for New York residents.",
                body_text="Coinbase enables AXL for New York residents.",
                language="en",
                published_at_ms=NOW_MS - 60_000,
                fetched_at_ms=now_ms,
                content_hash=content_hash,
                title_fingerprint="coinbase axelar axl is now available to new york residents",
                now_ms=now_ms,
                provider_signal={"source": "provider", "status": "ready", "score": 80},
            )

        diagnostics = repo.news_dedup_diagnostics(
            window_ms=8 * 3_600_000,
            score_threshold=80,
            now_ms=NOW_MS + 2,
        )
    finally:
        conn.close()

    assert diagnostics["material_title_duplicate_groups"]["groups"] == 1
    assert diagnostics["case_insensitive_url_duplicate_groups"]["groups"] == 1
    assert diagnostics["case_insensitive_url_duplicate_groups"]["ge_threshold_duplicate_rows"] == 1
    assert "repair_groups" not in diagnostics
    assert "would_merge" not in diagnostics


def _insert_source_provider_and_item(
    repo: NewsRepository,
    *,
    source_id: str = "source-1",
    source_item_key: str = "guid-1",
    title: str = "Title",
) -> str:
    repo.upsert_source(
        source_id=source_id,
        provider_type="rss",
        feed_url=f"https://{source_id}.example.com/rss.xml",
        source_domain="example.com",
        source_name="Example",
        refresh_interval_seconds=300,
        now_ms=NOW_MS,
    )
    fetch_run_id = repo.start_fetch_run(source_id=source_id, started_at_ms=NOW_MS)
    provider = repo.upsert_provider_item(
        source_id=source_id,
        fetch_run_id=fetch_run_id,
        source_item_key=source_item_key,
        canonical_url=f"https://example.com/news/{source_item_key}",
        payload_hash=f"hash-{source_item_key}",
        raw_payload_json={"title": title},
        fetched_at_ms=NOW_MS,
    )
    news = repo.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url=f"https://example.com/news/{source_item_key}",
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


def _insert_legacy_source_provider_and_item(conn) -> str:
    news_item_id = "news-item-legacy"
    conn.execute(
        """
        INSERT INTO news_sources (
          source_id, provider_type, feed_url, source_domain, source_name,
          source_role, trust_tier, created_at_ms, updated_at_ms
        )
        VALUES (
          'source-1', 'rss', 'https://example.com/rss.xml', 'example.com', 'Example',
          'observed_source', 'standard', %s, %s
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
          'provider-item-legacy', 'source-1', 'guid-1', 'https://example.com/guid-1',
          'hash-guid-1', '{"title":"Title"}'::jsonb, %s
        )
        """,
        (NOW_MS,),
    )
    conn.execute(
        """
        INSERT INTO news_items (
          news_item_id, provider_item_id, source_id, source_domain, canonical_url,
          title, summary, body_text, language, published_at_ms, fetched_at_ms,
          content_hash, title_fingerprint, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, 'provider-item-legacy', 'source-1', 'example.com', 'https://example.com/guid-1',
          'Title', 'Summary', 'Body', 'en', %s, %s, 'content-guid-1', 'title', %s, %s
        )
        """,
        (news_item_id, NOW_MS, NOW_MS, NOW_MS, NOW_MS),
    )
    return news_item_id


def _insert_legacy_canonical_source(
    conn,
    *,
    source_id: str = "source-legacy",
    provider_type: str = "rss",
    source_domain: str = "example.com",
) -> None:
    conn.execute(
        """
        INSERT INTO news_sources (
          source_id, provider_type, feed_url, source_domain, source_name,
          source_role, trust_tier, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, %s, %s, 'Example',
          'observed_source', 'standard', %s, %s
        )
        """,
        (source_id, provider_type, f"https://{source_domain}/rss.xml", source_domain, NOW_MS, NOW_MS),
    )


def _insert_legacy_canonical_provider_and_item(
    conn,
    *,
    suffix: str,
    canonical_url: str,
    content_hash: str,
    source_id: str = "source-legacy",
    source_domain: str = "example.com",
    source_item_key: str | None = None,
    raw_payload: object | None = None,
    published_at_ms: int = NOW_MS,
    fetched_at_ms: int = NOW_MS,
) -> None:
    item_key = source_item_key or f"guid-{suffix}"
    conn.execute(
        """
        INSERT INTO news_provider_items (
          provider_item_id, source_id, source_item_key, canonical_url, payload_hash,
          raw_payload_json, fetched_at_ms
        )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            f"provider-item-legacy-{suffix}",
            source_id,
            item_key,
            canonical_url,
            f"hash-{suffix}",
            Jsonb(raw_payload if raw_payload is not None else {"title": f"Title {suffix}", "published_at_ms": NOW_MS}),
            fetched_at_ms,
        ),
    )
    conn.execute(
        """
        INSERT INTO news_items (
          news_item_id, provider_item_id, source_id, source_domain, canonical_url,
          title, summary, body_text, language, published_at_ms, fetched_at_ms,
          content_hash, title_fingerprint, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, %s, %s, %s,
          %s, 'Summary', 'Body', 'en', %s, %s, %s, %s, %s, %s
        )
        """,
        (
            f"news-item-legacy-{suffix}",
            f"provider-item-legacy-{suffix}",
            source_id,
            source_domain,
            canonical_url,
            f"Title {suffix}",
            published_at_ms,
            fetched_at_ms,
            content_hash,
            f"title {suffix}",
            published_at_ms,
            fetched_at_ms,
        ),
    )


def _page_row(
    row_id: str,
    news_item_id: str,
    *,
    source_id: str,
    latest_at_ms: int = NOW_MS,
    projection_version: str = NEWS_PAGE_PROJECTION_VERSION,
    computed_at_ms: int = NOW_MS,
) -> dict[str, object]:
    return {
        "row_id": row_id,
        "news_item_id": news_item_id,
        "latest_at_ms": latest_at_ms,
        "source_domain": "example.com",
        "headline": row_id,
        "summary": "summary",
        "canonical_url": f"https://example.com/{row_id}",
        "lifecycle_status": "raw",
        "token_lanes_json": [],
        "fact_lanes_json": [],
        "source": {"source_id": source_id},
        "source_json": {"source_id": source_id},
        "signal": {"display_signal": {"direction": "neutral", "score": 0}},
        "projection_version": projection_version,
        "computed_at_ms": computed_at_ms,
    }


def _source_quality_row(*, source_id: str, computed_at_ms: int) -> dict[str, object]:
    return {
        "row_id": f"quality:{source_id}:24h",
        "source_id": source_id,
        "window": "24h",
        "computed_at_ms": computed_at_ms,
        "fetch_success_rate": 1.0,
        "items_fetched": 10,
        "items_inserted": 8,
        "duplicate_rate": 0.2,
        "process_success_rate": 0.9,
        "resolved_token_rate": 0.7,
        "attention_rate": 0.4,
        "accepted_fact_rate": 0.3,
        "brief_ready_rate": 0.5,
        "median_lag_ms": 1_000,
        "quality_score": 82.0,
        "diagnostics_json": {"status": "healthy", "window_ms": 86_400_000},
        "projection_version": "source-quality-test-v1",
    }


def _insert_fact_candidate(
    conn,
    *,
    news_item_id: str,
    fact_candidate_id: str,
    validation_status: str,
    claim: str,
) -> None:
    conn.execute(
        """
        INSERT INTO news_fact_candidates (
          fact_candidate_id, news_item_id, event_type, claim, realis, evidence_quote,
          evidence_span_start, evidence_span_end, source_role, required_slots_json,
          affected_targets_json, validation_status, rejection_reasons_json, extraction_method,
          policy_version, created_at_ms, updated_at_ms
        )
        VALUES (
          %s, %s, 'listing', %s, 'reported_claim', 'Evidence quote',
          0, 14, 'observed_source', '{}'::jsonb, %s, %s, '[]'::jsonb,
          'test', 'test', %s, %s
        )
        """,
        (
            fact_candidate_id,
            news_item_id,
            claim,
            Jsonb([{"target_type": "cex_token", "target_id": "binance:SOL", "display_symbol": "SOL"}]),
            validation_status,
            NOW_MS,
            NOW_MS,
        ),
    )


def _insert_token_mention(
    conn,
    *,
    news_item_id: str,
    mention_id: str,
    observed_symbol: str,
    target_type: str | None,
    target_id: str | None,
    display_symbol: str,
    confidence: float = 0.8,
) -> None:
    conn.execute(
        """
        INSERT INTO news_token_mentions (
          mention_id, news_item_id, observed_symbol, resolution_status, target_type,
          target_id, display_symbol, reason_codes_json, candidate_targets_json, evidence_strength,
          confidence, created_at_ms
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, '[]'::jsonb, '[]'::jsonb, 'medium', %s, %s)
        """,
        (
            mention_id,
            news_item_id,
            observed_symbol,
            "known_symbol" if target_type and target_id else "ambiguous_symbol",
            target_type,
            target_id,
            display_symbol,
            confidence,
            NOW_MS,
        ),
    )


def _attach_observation_source(
    repo: NewsRepository,
    *,
    news_item_id: str,
    source_id: str,
    source_domain: str,
    source_name: str,
    source_item_key: str,
) -> None:
    repo.upsert_source(
        source_id=source_id,
        provider_type="rss",
        feed_url=f"https://{source_domain}/{source_id}.xml",
        source_domain=source_domain,
        source_name=source_name,
        refresh_interval_seconds=300,
        now_ms=NOW_MS,
    )
    fetch_run_id = repo.start_fetch_run(source_id=source_id, started_at_ms=NOW_MS)
    provider = repo.upsert_provider_item(
        source_id=source_id,
        fetch_run_id=fetch_run_id,
        source_item_key=source_item_key,
        canonical_url=f"https://{source_domain}/news/{source_item_key}",
        payload_hash=f"hash-{source_item_key}",
        raw_payload_json={"title": source_name},
        fetched_at_ms=NOW_MS,
    )
    repo.conn.execute(
        """
        INSERT INTO news_item_observation_edges (
          provider_item_id, news_item_id, source_id, match_type, match_confidence,
          policy_version, evidence_json, first_seen_at_ms, last_seen_at_ms
        )
        VALUES (%s, %s, %s, 'same_content_hash', 'medium', 'test', '{}'::jsonb, %s, %s)
        """,
        (provider["provider_item_id"], news_item_id, source_id, NOW_MS, NOW_MS),
    )


def _insert_brief(repo: NewsRepository, *, news_item_id: str, run_id: str) -> None:
    _insert_agent_run(repo, news_item_id=news_item_id, run_id=run_id)
    repo.upsert_news_item_agent_brief(
        news_item_id=news_item_id,
        agent_run_id=run_id,
        status="ready",
        direction="neutral",
        decision_class="context",
        brief_json={
            "summary_zh": "简短摘要。",
            "market_read_zh": "市场影响有限。",
            "novelty_status": "follow_up",
            "confirmation_state": "unconfirmed",
            "source_consensus_zh": "单源观察。",
        },
        input_hash="input",
        artifact_version_hash="artifact",
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        computed_at_ms=NOW_MS,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


class _SingleConnectionWorkerDB:
    def __init__(self, conn) -> None:
        self.conn = conn

    @contextmanager
    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        yield repositories_for_connection(self.conn)


def _insert_agent_run(repo: NewsRepository, *, news_item_id: str, run_id: str) -> dict[str, object]:
    return repo.insert_news_item_agent_run(
        run_id=run_id,
        news_item_id=news_item_id,
        provider="litellm",
        model="gpt-5-mini",
        execution_trace_id=f"trace-{run_id}",
        workflow_name=NEWS_ITEM_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_ITEM_BRIEF_AGENT_NAME,
        lane=NEWS_ITEM_BRIEF_LANE,
        artifact_version_hash="artifact-brief-1",
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        guardrail_version=NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
        input_hash="input-brief-1",
        output_hash="output-brief-1",
        execution_started=True,
        status="completed",
        outcome="ready",
        request_json={"redacted": True},
        response_json={"summary_zh": "raw provider response should not be in detail"},
        validation_errors_json=[],
        trace_metadata_json={"attempt": 1},
        usage_json={"input_tokens": 10, "output_tokens": 5},
        latency_ms=10,
        started_at_ms=NOW_MS + 90,
        finished_at_ms=NOW_MS + 100,
        created_at_ms=NOW_MS + 90,
    )
