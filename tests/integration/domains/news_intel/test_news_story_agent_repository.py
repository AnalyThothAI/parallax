from __future__ import annotations

import json
from typing import Any

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.news_intel._constants import (
    NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
    NEWS_STORY_BRIEF_PROMPT_VERSION,
    NEWS_STORY_BRIEF_SCHEMA_VERSION,
    NEWS_STORY_BRIEF_VALIDATOR_VERSION,
    NEWS_STORY_IDENTITY_VERSION,
)
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_AGENT_NAME,
    NEWS_STORY_BRIEF_LANE,
    NEWS_STORY_BRIEF_WORKFLOW_NAME,
    story_brief_key_for,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_story_current_is_one_row_per_stable_story_key(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = _repositories(conn)
        story_key = "news-story:crypto:sol-etf-amendment"
        story_brief_key = story_brief_key_for(
            story_identity_version=NEWS_STORY_IDENTITY_VERSION,
            story_key=story_key,
        )
        with repos.transaction():
            news_item_id = _seed_item(repos)
            _insert_run(repos, story_brief_key, story_key, news_item_id)
            _upsert_current(
                repos,
                story_brief_key=story_brief_key,
                story_key=story_key,
                news_item_id=news_item_id,
                direction="bullish",
                updated_at_ms=NOW_MS + 100,
            )
            _upsert_current(
                repos,
                story_brief_key=story_brief_key,
                story_key=story_key,
                news_item_id=news_item_id,
                direction="mixed",
                updated_at_ms=NOW_MS + 200,
            )
        current = repos.news_story_agents.get_news_story_agent_brief(story_brief_key)
        current_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_story_agent_briefs WHERE story_brief_key = %s",
            (story_brief_key,),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert current_count == 1
    assert current is not None
    assert current["story_key"] == story_key
    assert current["direction"] == "mixed"
    assert _json_value(current["member_news_item_ids_json"]) == [news_item_id]


def _seed_item(repos) -> str:
    repos.news_sources.upsert_source(
        source_id="story-source",
        provider_type="rss",
        feed_url="https://example.com/story.xml",
        source_domain="example.com",
        source_name="Story source",
        now_ms=NOW_MS,
    )
    fetch_run_id = repos.news_sources.start_fetch_run(source_id="story-source", started_at_ms=NOW_MS)
    provider = repos.news_sources.upsert_provider_item(
        source_id="story-source",
        fetch_run_id=fetch_run_id,
        source_item_key="story-observation-1",
        canonical_url="https://example.com/story-1",
        payload_hash="story-payload-1",
        raw_payload={"title": "SOL ETF amendment"},
        fetched_at_ms=NOW_MS,
    )
    item = repos.news_items.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url="https://example.com/story-1",
        title="SOL ETF amendment",
        summary="Summary",
        body_text="Body",
        language="en",
        published_at_ms=NOW_MS,
        fetched_at_ms=NOW_MS,
        content_hash="story-content-1",
        title_fingerprint="sol etf amendment",
        now_ms=NOW_MS,
    )
    return str(item["news_item_id"])


def _insert_run(repos, story_brief_key: str, story_key: str, news_item_id: str) -> None:
    repos.news_story_agents.insert_news_story_agent_run(
        run_id="story-run-1",
        story_brief_key=story_brief_key,
        story_key=story_key,
        story_identity_version=NEWS_STORY_IDENTITY_VERSION,
        representative_news_item_id=news_item_id,
        member_news_item_ids_json=[news_item_id],
        provider="litellm",
        model="gpt-5-mini",
        backend="litellm_sdk",
        execution_trace_id="trace-story-run-1",
        workflow_name=NEWS_STORY_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_STORY_BRIEF_AGENT_NAME,
        lane=NEWS_STORY_BRIEF_LANE,
        artifact_version_hash="artifact-story-1",
        prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_STORY_BRIEF_VALIDATOR_VERSION,
        guardrail_version=NEWS_STORY_BRIEF_GUARDRAIL_VERSION,
        input_hash="input-story-1",
        output_hash="output-story-1",
        execution_started=True,
        status="completed",
        outcome="ready",
        request_json={"redacted": True},
        response_json={"summary_zh": "story response"},
        validation_errors_json=[],
        trace_metadata_json={"attempt": 1},
        usage_json={"input_tokens": 10, "output_tokens": 5},
        latency_ms=10,
        started_at_ms=NOW_MS,
        finished_at_ms=NOW_MS + 10,
        created_at_ms=NOW_MS,
    )


def _upsert_current(
    repos,
    *,
    story_brief_key: str,
    story_key: str,
    news_item_id: str,
    direction: str,
    updated_at_ms: int,
) -> None:
    repos.news_story_agents.upsert_news_story_agent_brief(
        story_brief_key=story_brief_key,
        story_key=story_key,
        story_identity_version=NEWS_STORY_IDENTITY_VERSION,
        representative_news_item_id=news_item_id,
        member_news_item_ids_json=[news_item_id],
        agent_run_id="story-run-1",
        status="ready",
        direction=direction,
        decision_class="driver",
        brief_json={"summary_zh": "SOL ETF filing update."},
        input_hash="input-story-1",
        artifact_version_hash="artifact-story-1",
        prompt_version=NEWS_STORY_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_STORY_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_STORY_BRIEF_VALIDATOR_VERSION,
        computed_at_ms=updated_at_ms,
        created_at_ms=NOW_MS + 100,
        updated_at_ms=updated_at_ms,
    )


def _json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _repositories(conn):
    return repositories_for_connection(
        conn,
        notification_delivery_running_timeout_ms=300_000,
        notification_delivery_stale_running_terminalization_batch_size=100,
    )
