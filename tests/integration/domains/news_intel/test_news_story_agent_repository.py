from __future__ import annotations

import json
from typing import Any

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
    NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
    NEWS_STORY_BRIEF_PROMPT_VERSION,
    NEWS_STORY_BRIEF_SCHEMA_VERSION,
    NEWS_STORY_BRIEF_VALIDATOR_VERSION,
    NEWS_STORY_IDENTITY_VERSION,
)
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.runtime.news_projection_work import enqueue_story_brief_work
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

NOW_MS = 1_779_000_000_000


def test_story_current_brief_key_is_stable_story_identity(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        first_item_id = _insert_processed_story_item(
            repo,
            source_item_key="sol-etf-first",
            title="Issuer files first SOL ETF amendment",
        )
        second_item_id = _insert_processed_story_item(
            repo,
            source_item_key="sol-etf-update",
            title="Issuer files second SOL ETF amendment",
        )
        story_key = "news-story:crypto:sol-etf-amendment"
        _set_story_identity(repo, news_item_id=first_item_id, story_key=story_key)
        _set_story_identity(repo, news_item_id=second_item_id, story_key=story_key)
        story_brief_key = story_brief_key_for(
            story_identity_version=NEWS_STORY_IDENTITY_VERSION,
            story_key=story_key,
        )

        _insert_story_run(
            repo,
            run_id="story-run-1",
            story_brief_key=story_brief_key,
            story_key=story_key,
            representative_news_item_id=first_item_id,
            member_news_item_ids=[first_item_id, second_item_id],
            input_hash="input-story-1",
            finished_at_ms=NOW_MS + 100,
        )
        repo.upsert_news_story_agent_brief(
            story_brief_key=story_brief_key,
            story_key=story_key,
            story_identity_version=NEWS_STORY_IDENTITY_VERSION,
            representative_news_item_id=first_item_id,
            member_news_item_ids_json=[first_item_id, second_item_id],
            agent_run_id="story-run-1",
            status="ready",
            direction="bullish",
            decision_class="driver",
            brief_json={"summary_zh": "SOL ETF filing enters the first review round."},
            input_hash="input-story-1",
            artifact_version_hash="artifact-story-1",
            prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_STORY_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 100,
            created_at_ms=NOW_MS + 100,
            updated_at_ms=NOW_MS + 100,
        )
        _insert_story_run(
            repo,
            run_id="story-run-2",
            story_brief_key=story_brief_key,
            story_key=story_key,
            representative_news_item_id=second_item_id,
            member_news_item_ids=[second_item_id, first_item_id],
            input_hash="input-story-2",
            finished_at_ms=NOW_MS + 200,
        )
        repo.upsert_news_story_agent_brief(
            story_brief_key=story_brief_key,
            story_key=story_key,
            story_identity_version=NEWS_STORY_IDENTITY_VERSION,
            representative_news_item_id=second_item_id,
            member_news_item_ids_json=[second_item_id, first_item_id],
            agent_run_id="story-run-2",
            status="ready",
            direction="mixed",
            decision_class="watch",
            brief_json={"summary_zh": "SOL ETF filing update still needs follow-through."},
            input_hash="input-story-2",
            artifact_version_hash="artifact-story-1",
            prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_STORY_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 200,
            created_at_ms=NOW_MS + 200,
            updated_at_ms=NOW_MS + 200,
        )
        conn.commit()

        current = repo.get_news_story_agent_brief(story_brief_key)
        current_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_story_agent_briefs WHERE story_brief_key = %s",
            (story_brief_key,),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert current_count == 1
    assert current is not None
    assert current["story_brief_key"] == story_brief_key
    assert current["story_key"] == story_key
    assert current["representative_news_item_id"] == second_item_id
    assert current["agent_run_id"] == "story-run-2"
    assert _json_value(current["member_news_item_ids_json"]) == [second_item_id, first_item_id]


def test_load_story_brief_targets_uses_story_current_without_item_brief_fallback(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        first_item_id = _insert_processed_story_item(
            repo,
            source_item_key="story-loader-first",
            title="Story loader first item",
        )
        second_item_id = _insert_processed_story_item(
            repo,
            source_item_key="story-loader-second",
            title="Story loader second item",
        )
        story_key = "news-story:crypto:story-loader"
        _set_story_identity(repo, news_item_id=first_item_id, story_key=story_key)
        _set_story_identity(repo, news_item_id=second_item_id, story_key=story_key)
        _insert_item_run_and_brief(repo, news_item_id=first_item_id)
        story_brief_key = story_brief_key_for(
            story_identity_version=NEWS_STORY_IDENTITY_VERSION,
            story_key=story_key,
        )

        without_story_current = repo.load_story_brief_targets(story_keys=[story_key])

        _insert_story_run(
            repo,
            run_id="story-loader-run",
            story_brief_key=story_brief_key,
            story_key=story_key,
            representative_news_item_id=second_item_id,
            member_news_item_ids=[first_item_id, second_item_id],
            input_hash="input-story-loader",
            finished_at_ms=NOW_MS + 500,
        )
        repo.upsert_news_story_agent_brief(
            story_brief_key=story_brief_key,
            story_key=story_key,
            story_identity_version=NEWS_STORY_IDENTITY_VERSION,
            representative_news_item_id=second_item_id,
            member_news_item_ids_json=[first_item_id, second_item_id],
            agent_run_id="story-loader-run",
            status="ready",
            direction="neutral",
            decision_class="context",
            brief_json={"summary_zh": "Story current summary."},
            input_hash="input-story-loader",
            artifact_version_hash="artifact-story-1",
            prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_STORY_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 500,
            created_at_ms=NOW_MS + 500,
            updated_at_ms=NOW_MS + 500,
        )
        with_story_current = repo.load_story_brief_targets(story_keys=[story_key])
    finally:
        conn.close()

    assert len(without_story_current) == 1
    assert without_story_current[0]["current_brief"] is None
    assert len(with_story_current) == 1
    payload = with_story_current[0]
    assert payload["story"]["story_key"] == story_key
    assert payload["story"]["story_identity_version"] == NEWS_STORY_IDENTITY_VERSION
    assert payload["story"]["member_news_item_ids"] == [first_item_id, second_item_id]
    assert payload["current_brief"]["story_brief_key"] == story_brief_key
    assert payload["current_brief"]["brief_json"]["summary_zh"] == "Story current summary."
    assert payload["latest_run"]["run_id"] == "story-loader-run"


def test_same_canonical_item_enqueues_one_story_brief_target(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = repositories_for_connection(
            conn,
            pulse_job_running_timeout_ms=300_000,
            notification_delivery_running_timeout_ms=300_000,
            notification_delivery_stale_running_terminalization_batch_size=100,
        )
        repo = repos.news
        canonical_url = "https://www.coindesk.com/news/sol-etf-same-canonical"
        first_item_id = _insert_processed_story_item(
            repo,
            source_item_key="same-canonical-first",
            title="Issuer files first SOL ETF amendment",
            canonical_url=canonical_url,
        )
        second_item_id = _insert_processed_story_item(
            repo,
            source_item_key="same-canonical-second",
            title="Issuer files duplicate SOL ETF amendment",
            canonical_url=canonical_url,
        )
        story_key = "news-story:crypto:same-canonical-sol-etf"
        _set_story_identity(repo, news_item_id=first_item_id, story_key=story_key)

        enqueue_story_brief_work(
            repos,
            story_keys=[story_key, story_key],
            reason="news_item_processed",
            now_ms=NOW_MS + 1,
            priority_by_story_key={story_key: 12},
            source_watermark_ms_by_story_key={story_key: NOW_MS},
            commit=True,
        )
        enqueue_story_brief_work(
            repos,
            story_keys=[story_key],
            reason="news_item_processed",
            now_ms=NOW_MS + 2,
            priority_by_story_key={story_key: 12},
            source_watermark_ms_by_story_key={story_key: NOW_MS},
            commit=True,
        )
        rows = conn.execute(
            """
            SELECT projection_name, target_kind, target_id, "window", source_watermark_ms, priority
              FROM news_projection_dirty_targets
             WHERE projection_name = 'story_brief'
             ORDER BY target_id
            """
        ).fetchall()
    finally:
        conn.close()

    assert first_item_id == second_item_id
    assert [dict(row) for row in rows] == [
        {
            "projection_name": "story_brief",
            "target_kind": "story",
            "target_id": story_key,
            "window": "",
            "source_watermark_ms": NOW_MS,
            "priority": 12,
        }
    ]


def _insert_processed_story_item(
    repo: NewsRepository,
    *,
    source_item_key: str,
    title: str,
    canonical_url: str | None = None,
) -> str:
    resolved_canonical_url = canonical_url or f"https://www.coindesk.com/news/{source_item_key}"
    repo.upsert_source(
        source_id="coindesk-rss",
        provider_type="rss",
        feed_url="https://www.coindesk.com/rss",
        source_domain="coindesk.com",
        source_name="CoinDesk",
        refresh_interval_seconds=300,
        now_ms=NOW_MS,
    )
    fetch_run_id = repo.start_fetch_run(source_id="coindesk-rss", started_at_ms=NOW_MS)
    provider = repo.upsert_provider_item(
        source_id="coindesk-rss",
        fetch_run_id=fetch_run_id,
        source_item_key=source_item_key,
        canonical_url=resolved_canonical_url,
        payload_hash=f"payload-{source_item_key}",
        raw_payload_json={"title": title},
        fetched_at_ms=NOW_MS,
    )
    news_item = repo.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url=resolved_canonical_url,
        title=title,
        summary=f"{title} summary",
        body_text=f"{title} body",
        language="en",
        published_at_ms=NOW_MS,
        fetched_at_ms=NOW_MS,
        content_hash=f"content-{source_item_key}",
        title_fingerprint=title.lower(),
        now_ms=NOW_MS,
    )
    news_item_id = str(news_item["news_item_id"])
    repo.mark_item_processed(news_item_id=news_item_id, processed_at_ms=NOW_MS)
    return news_item_id


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


def _insert_story_run(
    repo: NewsRepository,
    *,
    run_id: str,
    story_brief_key: str,
    story_key: str,
    representative_news_item_id: str,
    member_news_item_ids: list[str],
    input_hash: str,
    finished_at_ms: int,
) -> dict[str, Any]:
    return repo.insert_news_story_agent_run(
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
        response_json={"summary_zh": "story response"},
        validation_errors_json=[],
        trace_metadata_json={"attempt": 1},
        usage_json={"input_tokens": 10, "output_tokens": 5},
        latency_ms=10,
        started_at_ms=finished_at_ms - 10,
        finished_at_ms=finished_at_ms,
        created_at_ms=finished_at_ms - 10,
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


def _json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value
