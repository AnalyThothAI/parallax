from __future__ import annotations

from parallax.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
    NEWS_PAGE_PROJECTION_VERSION,
    NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
    NEWS_STORY_BRIEF_PROMPT_VERSION,
    NEWS_STORY_BRIEF_SCHEMA_VERSION,
    NEWS_STORY_BRIEF_VALIDATOR_VERSION,
    NEWS_STORY_IDENTITY_VERSION,
)
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.services.news_page_projection import build_news_page_row
from parallax.domains.news_intel.types.news_item_agent_admission import NewsItemAgentAdmission
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
)
from parallax.domains.news_intel.types.news_market_scope import NewsMarketScope
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_AGENT_NAME,
    NEWS_STORY_BRIEF_LANE,
    NEWS_STORY_BRIEF_WORKFLOW_NAME,
    story_brief_key_for,
)
from parallax.domains.news_intel.types.news_story_identity import NewsStoryIdentity
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


def test_list_news_page_rows_exposes_story_and_market_scope_fields(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    story_key = "news-story:subject:jpmorgan-citi-tokenized-deposit:t412000"
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, source_item_key="projected-story", title="Projected")
        row = {
            **_page_row("row-projected-story", news_item_id),
            "representative_news_item_id": news_item_id,
            "story_key": story_key,
            "story": {
                "story_key": story_key,
                "representative_news_item_id": news_item_id,
                "member_news_item_ids": [news_item_id],
                "member_count": 1,
                "source_domains": ["example.com"],
            },
            "market_scope": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "market_scope_classified",
                "basis": {"subject": "tokenized_deposit"},
                "version": "news_market_scope_v1",
            },
        }
        repo.replace_page_rows_for_story_targets(
            news_item_ids=[news_item_id],
            story_keys=[story_key],
            rows=[row],
        )

        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert rows[0]["representative_news_item_id"] == news_item_id
    assert rows[0]["story_key"] == story_key
    assert rows[0]["story"]["member_count"] == 1
    assert rows[0]["market_scope"]["primary"] == "crypto"
    assert rows[0]["market_scope"]["basis"] == {"subject": "tokenized_deposit"}


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


def test_page_rows_read_story_brief_without_item_brief_fallback(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    story_key = "news-story:crypto:story-current"
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        first_id = _insert_source_provider_and_item(
            repo,
            source_item_key="story-current-first",
            title="Story current first item",
        )
        second_id = _insert_source_provider_and_item(
            repo,
            source_item_key="story-current-second",
            title="Story current second item",
        )
        _set_story_identity(repo, news_item_id=first_id, story_key=story_key)
        _set_story_identity(repo, news_item_id=second_id, story_key=story_key)
        _insert_item_run_and_brief(repo, news_item_id=first_id)

        before_story_current = repo.load_story_projection_payloads_for_items(news_item_ids=[first_id, second_id])[0]
        story_brief_key = story_brief_key_for(
            story_identity_version=NEWS_STORY_IDENTITY_VERSION,
            story_key=story_key,
        )
        _insert_story_run(
            repo,
            run_id="story-current-run",
            story_brief_key=story_brief_key,
            story_key=story_key,
            representative_news_item_id=first_id,
            member_news_item_ids=[first_id, second_id],
            input_hash="input-story-current",
        )
        repo.upsert_news_story_agent_brief(
            story_brief_key=story_brief_key,
            story_key=story_key,
            story_identity_version=NEWS_STORY_IDENTITY_VERSION,
            representative_news_item_id=first_id,
            member_news_item_ids_json=[first_id, second_id],
            agent_run_id="story-current-run",
            status="ready",
            direction="bullish",
            decision_class="driver",
            brief_json={"summary_zh": "Story current summary."},
            input_hash="input-story-current",
            artifact_version_hash="artifact-story-1",
            prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_STORY_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 100,
            created_at_ms=NOW_MS + 100,
            updated_at_ms=NOW_MS + 100,
        )
        after_story_current = repo.load_story_projection_payloads_for_items(news_item_ids=[first_id, second_id])[0]
        row = build_news_page_row(
            item=dict(after_story_current["item"]),
            token_mentions=[dict(item) for item in after_story_current.get("token_mentions") or []],
            fact_candidates=[dict(item) for item in after_story_current.get("fact_candidates") or []],
            agent_brief=dict(after_story_current["current_brief"]),
            story=dict(after_story_current["story"]),
            computed_at_ms=NOW_MS + 200,
        )
        repo.replace_page_rows_for_story_targets(
            news_item_ids=[first_id, second_id],
            story_keys=[story_key],
            rows=[row],
        )
        rows = repo.list_news_page_rows(limit=10)
    finally:
        conn.close()

    assert before_story_current["current_brief"] is None
    assert after_story_current["current_brief"]["story_brief_key"] == story_brief_key
    assert rows[0]["agent_brief"]["summary_zh"] == "Story current summary."
    assert rows[0]["agent_brief"]["summary_zh"] != "old item current"


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


def _set_story_identity(repo: NewsRepository, *, news_item_id: str, story_key: str) -> None:
    repo.update_item_market_scope_and_story_identity(
        news_item_id=news_item_id,
        market_scope=NewsMarketScope(
            scope=("crypto",),
            primary="crypto",
            status="classified",
            reason="crypto_context",
            basis={"test": True},
        ),
        story_identity=NewsStoryIdentity(
            story_key=story_key,
            confidence="strong",
            basis={"test": True},
            version=NEWS_STORY_IDENTITY_VERSION,
        ),
        now_ms=NOW_MS,
    )
    repo.mark_item_processed(news_item_id=news_item_id, processed_at_ms=NOW_MS)
    repo.update_item_agent_admission(
        news_item_id=news_item_id,
        admission=NewsItemAgentAdmission(
            eligible=True,
            status="eligible",
            reason="test_eligible",
            representative_news_item_id=news_item_id,
            basis={"test": True},
        ),
        now_ms=NOW_MS,
    )


def _insert_item_run_and_brief(repo: NewsRepository, *, news_item_id: str) -> None:
    repo.insert_news_item_agent_run(
        run_id=f"item-run-{news_item_id}",
        news_item_id=news_item_id,
        provider="litellm",
        model="gpt-5-mini",
        execution_trace_id=f"trace-item-{news_item_id}",
        workflow_name=NEWS_ITEM_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_ITEM_BRIEF_AGENT_NAME,
        lane=NEWS_ITEM_BRIEF_LANE,
        artifact_version_hash="artifact-item-1",
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        guardrail_version=NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
        input_hash="input-item-1",
        output_hash="output-item-1",
        execution_started=True,
        status="completed",
        outcome="ready",
        request_json={"redacted": True},
        response_json={"summary_zh": "old item current"},
        validation_errors_json=[],
        trace_metadata_json={},
        usage_json={},
        latency_ms=10,
        started_at_ms=NOW_MS,
        finished_at_ms=NOW_MS + 10,
        created_at_ms=NOW_MS,
    )
    repo.upsert_news_item_agent_brief(
        news_item_id=news_item_id,
        agent_run_id=f"item-run-{news_item_id}",
        status="ready",
        direction="neutral",
        decision_class="context",
        brief_json={"summary_zh": "old item current"},
        input_hash="input-item-1",
        artifact_version_hash="artifact-item-1",
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        computed_at_ms=NOW_MS + 10,
        created_at_ms=NOW_MS + 10,
        updated_at_ms=NOW_MS + 10,
    )


def _insert_story_run(
    repo: NewsRepository,
    *,
    run_id: str,
    story_brief_key: str,
    story_key: str,
    representative_news_item_id: str,
    member_news_item_ids: list[str],
    input_hash: str,
) -> None:
    repo.insert_news_story_agent_run(
        run_id=run_id,
        story_brief_key=story_brief_key,
        story_key=story_key,
        story_identity_version=NEWS_STORY_IDENTITY_VERSION,
        representative_news_item_id=representative_news_item_id,
        member_news_item_ids_json=member_news_item_ids,
        provider="litellm",
        model="gpt-5-mini",
        execution_trace_id=f"trace-{run_id}",
        workflow_name=NEWS_STORY_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_STORY_BRIEF_AGENT_NAME,
        lane=NEWS_STORY_BRIEF_LANE,
        artifact_version_hash="artifact-story-1",
        prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_STORY_BRIEF_VALIDATOR_VERSION,
        guardrail_version=NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
        input_hash=input_hash,
        output_hash=f"output-{run_id}",
        execution_started=True,
        status="completed",
        outcome="ready",
        request_json={"redacted": True},
        response_json={"summary_zh": "Story current summary."},
        validation_errors_json=[],
        trace_metadata_json={},
        usage_json={},
        latency_ms=10,
        started_at_ms=NOW_MS + 90,
        finished_at_ms=NOW_MS + 100,
        created_at_ms=NOW_MS + 90,
    )


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
