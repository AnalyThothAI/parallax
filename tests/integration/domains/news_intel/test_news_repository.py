from __future__ import annotations

from alembic import command
from psycopg.types.json import Jsonb

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
    NEWS_PAGE_PROJECTION_VERSION,
)
from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository, news_page_cursor
from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
)
from gmgn_twitter_intel.platform.db.postgres_migrations import alembic_config
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
        news = repo.upsert_news_item(
            provider_item_id=provider["provider_item_id"],
            source_id="coindesk-rss",
            source_domain="coindesk.com",
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

        rows = repo.list_news_page_rows(limit=10, include_unprojected=True)
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
    assert rows[0]["story_json"] == {}
    assert rows[0]["source_json"] == {
        "source_id": "coindesk-rss",
        "provider_type": "rss",
        "source_domain": "coindesk.com",
        "source_name": "CoinDesk",
        "source_role": "observed_source",
        "trust_tier": "standard",
        "coverage_tags": [],
        "source_quality_status": "unknown",
    }


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
            canonical_url="https://example.com/a",
            payload_hash="hash-old",
            raw_payload_json={"title": "Old"},
            fetched_at_ms=NOW_MS,
        )
        first_news = repo.upsert_news_item(
            provider_item_id=first_provider["provider_item_id"],
            source_id="source-1",
            source_domain="example.com",
            canonical_url="https://example.com/a",
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
            canonical_url="https://example.com/a",
            payload_hash="hash-new",
            raw_payload_json={"title": "New"},
            fetched_at_ms=NOW_MS + 1_000,
        )
        second_news = repo.upsert_news_item(
            provider_item_id=second_provider["provider_item_id"],
            source_id="source-1",
            source_domain="example.com",
            canonical_url="https://example.com/a",
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

    assert [row["source_id"] for row in rows] == ["configured-source"]
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
                    "story_id": "story-old",
                    "latest_at_ms": NOW_MS,
                    "source_domain": "example.com",
                    "headline": "Stale",
                    "summary": "Old summary",
                    "canonical_url": "https://example.com/stale",
                    "lifecycle_status": "raw",
                    "token_lanes_json": [],
                    "fact_lanes_json": [],
                    "story_json": {"story_id": "story-old"},
                    "source_json": {"source_id": "source-1"},
                    "projection_version": "test-v1",
                    "computed_at_ms": NOW_MS,
                },
                {
                    "row_id": "row-other",
                    "news_item_id": other_news_item_id,
                    "story_id": "story-other",
                    "latest_at_ms": NOW_MS,
                    "source_domain": "example.com",
                    "headline": "Other",
                    "summary": "Other summary",
                    "canonical_url": "https://example.com/other",
                    "lifecycle_status": "raw",
                    "token_lanes_json": [],
                    "fact_lanes_json": [],
                    "story_json": {"story_id": "story-other"},
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
                    "story_id": "story-new",
                    "latest_at_ms": NOW_MS + 1,
                    "source_domain": "example.com",
                    "headline": "Fresh",
                    "summary": "New summary",
                    "canonical_url": "https://example.com/fresh",
                    "lifecycle_status": "processed",
                    "token_lanes_json": [{"lane": "resolved", "symbol": "SOL"}],
                    "fact_lanes_json": [],
                    "story_json": {"story_id": "story-new"},
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

        deleted = repo.delete_page_rows_for_sources(source_ids=["source-1"])
        rows = conn.execute("SELECT row_id FROM news_page_rows ORDER BY row_id").fetchall()
    finally:
        conn.close()

    assert deleted == 1
    assert [row["row_id"] for row in rows] == ["row-2"]


def test_list_news_page_rows_keeps_raw_items_until_projection_catches_up(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        projected_item_id = _insert_source_provider_and_item(repo, source_item_key="projected", title="Projected")
        raw_item_id = _insert_source_provider_and_item(repo, source_item_key="raw", title="Raw")
        repo.replace_page_rows_for_items(
            news_item_ids=[projected_item_id],
            rows=[_page_row("row-projected", projected_item_id, source_id="source-1")],
        )

        rows = repo.list_news_page_rows(limit=10, include_unprojected=True)
    finally:
        conn.close()

    row_ids = {row["row_id"] for row in rows}
    assert row_ids == {"row-projected", raw_item_id}
    raw = next(row for row in rows if row["row_id"] == raw_item_id)
    assert raw["headline"] == "Raw"
    assert raw["agent_status"] == "pending"
    assert raw["agent_brief_status"] == "pending"
    assert raw["agent_brief_json"] == {"status": "pending"}


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
    assert rows[0]["agent_brief_json"]["status"] == "pending"
    assert rows[0]["agent_brief"]["status"] == "pending"


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

        candidates = repo.list_items_for_page_projection(limit=10)
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
    assert rows[0]["agent_brief_status"] == "ready"
    assert rows[0]["agent_brief_json"]["summary_zh"] == "SOL ETF 申请提升关注。"
    assert rows[0]["agent_brief"]["agent_run_id"] == "run-brief-1"


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


def test_list_news_page_rows_filters_by_agent_brief_direction(tmp_path) -> None:
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
                },
                {
                    **_page_row("row-bearish", bearish_item_id, source_id="source-1"),
                    "agent_status": "ready",
                    "agent_brief_json": {"status": "ready", "direction": "bearish"},
                },
            ],
        )

        rows = repo.list_news_page_rows(limit=10, direction="bearish")
    finally:
        conn.close()

    assert [row["row_id"] for row in rows] == ["row-bearish"]
    assert rows[0]["agent_brief_json"]["direction"] == "bearish"


def test_list_news_page_rows_filters_by_source_classification(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="coinbase",
            provider_type="rss",
            feed_url="https://coinbase.com/rss.xml",
            source_domain="coinbase.com",
            source_name="Coinbase",
            source_role="official_exchange",
            trust_tier="official",
            coverage_tags=("crypto_exchange", "exchange_listing"),
            now_ms=NOW_MS,
        )
        matching_item_id = _insert_source_provider_and_item(
            repo,
            source_id="coinbase",
            source_item_key="matching",
            title="Matching",
        )
        other_item_id = _insert_source_provider_and_item(repo, source_item_key="other", title="Other")
        repo.replace_page_rows_for_items(
            news_item_ids=[matching_item_id, other_item_id],
            rows=[
                {
                    **_page_row("row-matching", matching_item_id, source_id="coinbase"),
                    "source_domain": "coinbase.com",
                    "source_json": {
                        "source_id": "coinbase",
                        "provider_type": "rss",
                        "source_domain": "coinbase.com",
                        "source_name": "Coinbase",
                        "source_role": "official_exchange",
                        "trust_tier": "official",
                        "coverage_tags": ["crypto_exchange", "exchange_listing"],
                        "source_quality_status": "healthy",
                    },
                    "fact_lanes_json": [{"content_class": "exchange_listing", "event_type": "listing"}],
                },
                {
                    **_page_row("row-other", other_item_id, source_id="source-1"),
                    "source_json": {
                        "source_id": "source-1",
                        "provider_type": "rss",
                        "source_domain": "example.com",
                        "source_name": "Example",
                        "source_role": "observed_source",
                        "trust_tier": "standard",
                        "coverage_tags": [],
                        "source_quality_status": "unknown",
                    },
                    "fact_lanes_json": [{"content_class": "market_commentary"}],
                },
            ],
        )

        rows = repo.list_news_page_rows(
            limit=10,
            provider_type="rss",
            source_role="official_exchange",
            trust_tier="official",
            coverage_tag="exchange_listing",
            content_class="exchange_listing",
        )
    finally:
        conn.close()

    assert [row["row_id"] for row in rows] == ["row-matching"]


def test_page_projection_candidates_include_rows_when_source_classification_changes(tmp_path) -> None:
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

        candidates = repo.list_items_for_page_projection(limit=10)
    finally:
        conn.close()

    assert [candidate["item"]["news_item_id"] for candidate in candidates] == [news_item_id]
    assert candidates[0]["item"]["coverage_tags_json"] == ["exchange_listing"]
    assert candidates[0]["item"]["source_quality_status"] == "healthy"


def test_page_projection_candidates_progress_after_partial_rebuild(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        item_ids = [
            _insert_source_provider_and_item(repo, source_item_key="first", title="First"),
            _insert_source_provider_and_item(repo, source_item_key="second", title="Second"),
            _insert_source_provider_and_item(repo, source_item_key="third", title="Third"),
        ]

        first_batch = repo.list_items_for_page_projection(limit=2)
        first_ids = [str(row["item"]["news_item_id"]) for row in first_batch]
        repo.replace_page_rows_for_items(
            news_item_ids=first_ids,
            rows=[
                _page_row(
                    f"row-{index}",
                    news_item_id,
                    source_id="source-1",
                    projection_version=NEWS_PAGE_PROJECTION_VERSION,
                    computed_at_ms=NOW_MS + 1,
                )
                | {
                    "source_json": {
                        "source_id": "source-1",
                        "provider_type": "rss",
                        "source_domain": "example.com",
                        "source_name": "Example",
                        "source_role": "observed_source",
                        "trust_tier": "standard",
                        "coverage_tags": [],
                        "source_quality_status": "unknown",
                    }
                }
                for index, news_item_id in enumerate(first_ids)
            ],
        )

        second_batch = repo.list_items_for_page_projection(limit=2)
        second_ids = [str(row["item"]["news_item_id"]) for row in second_batch]
    finally:
        conn.close()

    assert len(first_ids) == 2
    assert second_ids == [next(item_id for item_id in item_ids if item_id not in set(first_ids))]


def test_updating_news_item_clears_stale_story_and_page_projection(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        item = conn.execute("SELECT * FROM news_items WHERE news_item_id = %s", (news_item_id,)).fetchone()
        repo.create_story_from_item(
            story_id="story-1",
            item=item,
            policy_version="test-story-v1",
            now_ms=NOW_MS,
        )
        repo.add_story_member(
            story_id="story-1",
            news_item_id=news_item_id,
            relation="representative",
            match_reason="exact_url",
            match_score=1.0,
            now_ms=NOW_MS,
        )
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

        repo.upsert_news_item(
            provider_item_id=provider["provider_item_id"],
            source_id="source-1",
            source_domain="example.com",
            canonical_url="https://example.com/guid-1",
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

        story_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_story_members WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["count"]
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
        story = conn.execute(
            "SELECT item_count, source_count, status FROM news_story_groups WHERE story_id = %s",
            ("story-1",),
        ).fetchone()
        status = conn.execute(
            "SELECT lifecycle_status FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["lifecycle_status"]
    finally:
        conn.close()

    assert story_count == 0
    assert page_count == 0
    assert entity_count == 0
    assert mention_count == 0
    assert fact_count == 0
    assert story["item_count"] == 0
    assert story["source_count"] == 0
    assert story["status"] == "stale"
    assert status == "raw"


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
    assert detail["agent_brief"]["input_hash"] == "input-brief-1"
    assert detail["agent_run"] == {
        "run_id": "run-detail-1",
        "status": "completed",
        "outcome": "ready",
        "execution_started": True,
        "model": "gpt-5-mini",
        "provider": "openai",
        "lane": NEWS_ITEM_BRIEF_LANE,
        "sdk_trace_id": "trace-run-detail-1",
        "error_class": None,
        "error": None,
        "usage_json": {"input_tokens": 10, "output_tokens": 5},
        "trace_metadata_json": {"attempt": 1},
        "started_at_ms": NOW_MS + 90,
        "finished_at_ms": NOW_MS + 100,
    }
    assert "request_json" not in detail["agent_run"]
    assert "response_json" not in detail["agent_run"]


def test_repository_session_exposes_news_repository(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = repositories_for_connection(conn)
    finally:
        conn.close()

    assert isinstance(repos.news, NewsRepository)


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
        canonical_url=f"https://example.com/{source_item_key}",
        payload_hash=f"hash-{source_item_key}",
        raw_payload_json={"title": title},
        fetched_at_ms=NOW_MS,
    )
    news = repo.upsert_news_item(
        provider_item_id=provider["provider_item_id"],
        source_id=source_id,
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


def _page_row(
    row_id: str,
    news_item_id: str,
    *,
    source_id: str,
    latest_at_ms: int = NOW_MS,
    projection_version: str = "test-v1",
    computed_at_ms: int = NOW_MS,
) -> dict[str, object]:
    return {
        "row_id": row_id,
        "news_item_id": news_item_id,
        "story_id": None,
        "latest_at_ms": latest_at_ms,
        "source_domain": "example.com",
        "headline": row_id,
        "summary": "summary",
        "canonical_url": f"https://example.com/{row_id}",
        "lifecycle_status": "raw",
        "token_lanes_json": [],
        "fact_lanes_json": [],
        "story_json": {},
        "source_json": {"source_id": source_id},
        "projection_version": projection_version,
        "computed_at_ms": computed_at_ms,
    }


def _insert_agent_run(repo: NewsRepository, *, news_item_id: str, run_id: str) -> dict[str, object]:
    return repo.insert_news_item_agent_run(
        run_id=run_id,
        news_item_id=news_item_id,
        provider="openai",
        model="gpt-5-mini",
        sdk_trace_id=f"trace-{run_id}",
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
