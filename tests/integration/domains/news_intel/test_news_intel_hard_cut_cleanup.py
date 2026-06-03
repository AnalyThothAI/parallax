from __future__ import annotations

import pytest

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.services.news_intel_hard_cut_cleanup import (
    NewsIntelHardCutCleanupAbort,
    cleanup_news_intel_hard_cut,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000


def test_news_intel_hard_cut_cleanup_dry_run_counts_without_deleting(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_cleanup_state(conn)

        result = cleanup_news_intel_hard_cut(_repos(conn), execute=False, now_ms=NOW_MS)

        assert result["execute"] is False
        assert result["table_counts"]["news_page_rows"] == 1
        assert result["table_counts"]["news_provider_items"] == 1
        assert result["notification_counts"] == {
            "notifications": 1,
            "notification_reads": 1,
            "notification_deliveries": 1,
        }
        assert _count(conn, "news_page_rows") == 1
        assert _count(conn, "notifications") == 2
    finally:
        conn.close()


def test_news_intel_hard_cut_cleanup_execute_clears_news_data_notifications_and_resets_sources(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_cleanup_state(conn)

        result = cleanup_news_intel_hard_cut(_repos(conn), execute=True, now_ms=NOW_MS)

        assert result["execute"] is True
        for table_name in (
            "news_projection_dirty_targets",
            "news_page_rows",
            "news_source_quality_rows",
            "news_item_agent_briefs",
            "news_item_agent_runs",
            "news_fact_candidates",
            "news_token_mentions",
            "news_item_entities",
            "news_item_observation_edges",
            "news_items",
            "news_provider_items",
            "news_fetch_runs",
        ):
            assert _count(conn, table_name) == 0
        assert result["deleted_notifications"]["deleted_notifications"] == 1
        assert _count(conn, "notifications") == 1
        assert _count(conn, "notification_reads") == 0
        assert _count(conn, "notification_deliveries") == 0
        source = conn.execute("SELECT * FROM news_sources WHERE source_id = 'source-1'").fetchone()
        assert source is not None
        assert source["etag"] is None
        assert source["last_modified"] is None
        assert source["last_fetch_at_ms"] is None
        assert source["last_success_at_ms"] is None
        assert source["consecutive_failures"] == 0
        assert source["last_error"] is None
        assert source["source_quality_status"] == "unknown"
        assert source["next_fetch_after_ms"] == 0
        assert source["sync_cursor_json"] == {}
        assert source["sync_high_watermark_ms"] == 0
        assert source["sync_diagnostics_json"] == {}
    finally:
        conn.close()


def test_news_intel_hard_cut_cleanup_rejects_running_fetch_without_deleting(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_cleanup_state(conn)
        conn.execute(
            """
            INSERT INTO news_fetch_runs(fetch_run_id, source_id, started_at_ms, status)
            VALUES ('fetch-running', 'source-1', %s, 'running')
            """,
            (NOW_MS,),
        )

        with pytest.raises(NewsIntelHardCutCleanupAbort):
            cleanup_news_intel_hard_cut(_repos(conn), execute=True, now_ms=NOW_MS)

        assert _count(conn, "news_page_rows") == 1
        assert _count(conn, "news_fetch_runs") == 2
        assert _count(conn, "notifications") == 2
    finally:
        conn.close()


def test_news_intel_hard_cut_cleanup_rejects_active_dirty_lease_without_deleting(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_cleanup_state(conn, dirty_leased_until_ms=NOW_MS + 60_000)

        with pytest.raises(NewsIntelHardCutCleanupAbort):
            cleanup_news_intel_hard_cut(_repos(conn), execute=True, now_ms=NOW_MS)

        assert _count(conn, "news_projection_dirty_targets") == 1
        assert _count(conn, "news_page_rows") == 1
        assert _count(conn, "notifications") == 2
    finally:
        conn.close()


def _repos(conn):
    return type("Repos", (), {"conn": conn})()


def _seed_cleanup_state(conn, *, dirty_leased_until_ms: int | None = None) -> str:
    repo = NewsRepository(conn)
    repo.upsert_source(
        source_id="source-1",
        provider_type="rss",
        feed_url="https://example.com/rss.xml",
        source_domain="example.com",
        source_name="Example",
        now_ms=NOW_MS - 10_000,
    )
    conn.execute(
        """
        UPDATE news_sources
           SET etag = 'old-etag',
               last_modified = 'old-last-modified',
               last_fetch_at_ms = %s,
               last_success_at_ms = %s,
               consecutive_failures = 3,
               last_error = 'old failure',
               source_quality_status = 'poor',
               next_fetch_after_ms = %s,
               sync_cursor_json = '{"cursor": true}'::jsonb,
               sync_high_watermark_ms = %s,
               sync_diagnostics_json = '{"pages": 2}'::jsonb
         WHERE source_id = 'source-1'
        """,
        (NOW_MS - 9_000, NOW_MS - 8_000, NOW_MS + 60_000, NOW_MS - 7_000),
    )
    fetch_run_id = repo.start_fetch_run(source_id="source-1", started_at_ms=NOW_MS - 6_000)
    repo.finish_fetch_run(
        fetch_run_id=fetch_run_id,
        source_id="source-1",
        status="success",
        finished_at_ms=NOW_MS - 5_000,
        fetched_count=1,
        inserted_count=1,
    )
    provider_item = repo.upsert_provider_item(
        source_id="source-1",
        fetch_run_id=fetch_run_id,
        source_item_key="item-1",
        canonical_url="https://example.com/story",
        payload_hash="provider-hash",
        raw_payload={"id": "item-1"},
        fetched_at_ms=NOW_MS - 4_000,
    )
    item = repo.upsert_canonical_news_item(
        provider_item_id=str(provider_item["provider_item_id"]),
        canonical_url="https://example.com/story",
        title="BTC news",
        summary="BTC summary",
        body_text="BTC body",
        language="en",
        published_at_ms=NOW_MS - 3_000,
        fetched_at_ms=NOW_MS - 2_000,
        content_hash="content-hash",
        title_fingerprint="btc news",
        now_ms=NOW_MS - 1_000,
    )
    news_item_id = str(item["news_item_id"])
    repo.replace_item_entities(
        news_item_id=news_item_id,
        entities=[
            {
                "entity_id": "entity-1",
                "news_item_id": news_item_id,
                "entity_type": "token",
                "raw_value": "BTC",
                "normalized_value": "BTC",
                "chain": None,
                "span_start": 0,
                "span_end": 3,
                "text_surface": "BTC",
                "confidence": 0.9,
                "extraction_policy_version": "test",
                "created_at_ms": NOW_MS,
            }
        ],
    )
    repo.replace_token_mentions(
        news_item_id=news_item_id,
        mentions=[
            {
                "mention_id": "mention-1",
                "news_item_id": news_item_id,
                "entity_id": "entity-1",
                "observed_symbol": "BTC",
                "chain_id": None,
                "address": None,
                "resolution_status": "known_symbol",
                "target_type": "CexToken",
                "target_id": "cex:BTC",
                "display_symbol": "BTC",
                "display_name": "Bitcoin",
                "reason_codes": [],
                "candidate_targets": [],
                "evidence_strength": "strong",
                "confidence": 0.95,
                "created_at_ms": NOW_MS,
            }
        ],
    )
    repo.replace_fact_candidates(
        news_item_id=news_item_id,
        candidates=[
            {
                "fact_candidate_id": "fact-1",
                "news_item_id": news_item_id,
                "event_type": "market",
                "claim": "BTC moved",
                "realis": "actual",
                "evidence_quote": "BTC moved",
                "evidence_span_start": 0,
                "evidence_span_end": 9,
                "source_role": "observed_source",
                "required_slots": {},
                "affected_targets": [],
                "validation_status": "attention",
                "rejection_reasons": [],
                "extraction_method": "test",
                "policy_version": "test",
                "created_at_ms": NOW_MS,
                "updated_at_ms": NOW_MS,
            }
        ],
    )
    repo.insert_news_item_agent_run(
        run_id="run-1",
        news_item_id=news_item_id,
        provider="litellm",
        model="gpt-test",
        backend="litellm_sdk",
        execution_trace_id=None,
        workflow_name="news.item_brief",
        agent_name="news_item_brief",
        lane="news.item_brief",
        artifact_version_hash="artifact",
        prompt_version="prompt",
        schema_version="schema",
        validator_version="validator",
        guardrail_version="guardrail",
        input_hash="input",
        output_hash="output",
        execution_started=True,
        status="completed",
        outcome="ready",
        error_class=None,
        error=None,
        request_json={},
        response_json={},
        validation_errors_json=[],
        trace_metadata_json={},
        usage_json={},
        latency_ms=1,
        started_at_ms=NOW_MS,
        finished_at_ms=NOW_MS + 1,
        created_at_ms=NOW_MS,
    )
    repo.upsert_news_item_agent_brief(
        news_item_id=news_item_id,
        agent_run_id="run-1",
        status="ready",
        direction="bullish",
        decision_class="driver",
        brief_json={"summary_zh": "测试"},
        input_hash="input",
        artifact_version_hash="artifact",
        prompt_version="prompt",
        schema_version="schema",
        validator_version="validator",
        computed_at_ms=NOW_MS,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )
    repo.replace_page_rows_for_items(
        news_item_ids=[news_item_id],
        rows=[
            {
                "row_id": "row-1",
                "news_item_id": news_item_id,
                "latest_at_ms": NOW_MS,
                "source_domain": "example.com",
                "headline": "BTC news",
                "summary": "BTC summary",
                "canonical_url": "https://example.com/story",
                "lifecycle_status": "processed",
                "token_lanes_json": [],
                "fact_lanes_json": [],
                "source": {"source_id": "source-1"},
                "signal": {"display_signal": {"direction": "bullish", "score": 90}},
                "projection_version": NEWS_PAGE_PROJECTION_VERSION,
                "computed_at_ms": NOW_MS,
            }
        ],
    )
    repo.replace_source_quality_rows(
        rows=[
            {
                "row_id": "quality:source-1:24h",
                "source_id": "source-1",
                "window": "24h",
                "computed_at_ms": NOW_MS,
                "fetch_success_rate": 1.0,
                "items_fetched": 1,
                "items_inserted": 1,
                "duplicate_rate": 0.0,
                "process_success_rate": 1.0,
                "resolved_token_rate": 1.0,
                "attention_rate": 1.0,
                "accepted_fact_rate": 0.0,
                "brief_ready_rate": 1.0,
                "median_lag_ms": 1000,
                "quality_score": 80.0,
                "diagnostics_json": {"status": "healthy", "counts": {"fetch_run_count": 1}},
                "projection_version": "test",
            }
        ],
        status_window="24h",
    )
    conn.execute(
        """
        INSERT INTO news_projection_dirty_targets(
          projection_name, target_kind, target_id, "window", dirty_reason, payload_hash,
          priority, due_at_ms, leased_until_ms, lease_owner, first_dirty_at_ms, updated_at_ms
        )
        VALUES ('page', 'news_item', %s, '', 'test', 'hash', 10, %s, %s, 'worker', %s, %s)
        """,
        (news_item_id, NOW_MS, dirty_leased_until_ms, NOW_MS, NOW_MS),
    )
    _seed_notifications(conn)
    return news_item_id


def _seed_notifications(conn) -> None:
    conn.execute(
        """
        INSERT INTO notifications(
          notification_id, dedup_key, rule_id, severity, title, body, entity_type, entity_key,
          source_table, source_id, first_seen_at_ms, last_seen_at_ms, created_at_ms, updated_at_ms
        )
        VALUES
          (
            'news-notification', 'news-dedup', 'news_high_signal', 'high', 'News', 'News body',
            'news_item', 'news-1', 'news_page_rows', 'row-1', %s, %s, %s, %s
          ),
          (
            'pulse-notification', 'pulse-dedup', 'signal_pulse_candidate', 'high', 'Pulse', 'Pulse body',
            'pulse_candidate', 'pulse-1', 'pulse_candidates', 'pulse-1', %s, %s, %s, %s
          )
        """,
        (NOW_MS, NOW_MS, NOW_MS, NOW_MS, NOW_MS, NOW_MS, NOW_MS, NOW_MS),
    )
    conn.execute(
        """
        INSERT INTO notification_reads(notification_id, subscriber_key, read_at_ms)
        VALUES ('news-notification', 'operator', %s)
        """,
        (NOW_MS,),
    )
    conn.execute(
        """
        INSERT INTO notification_deliveries(
          delivery_id, notification_id, channel_id, provider, status,
          next_run_at_ms, created_at_ms, updated_at_ms
        )
        VALUES ('delivery-1', 'news-notification', 'in_app', 'log', 'pending', %s, %s, %s)
        """,
        (NOW_MS, NOW_MS, NOW_MS),
    )


def _count(conn, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])
