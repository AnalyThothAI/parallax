from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
from gmgn_twitter_intel.domains.news_intel.services.source_quality_projection import build_source_quality_rows
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000
DAY_MS = 24 * 60 * 60 * 1000


def test_source_quality_repository_aggregates_and_replaces_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        repo.upsert_source(
            source_id="coindesk",
            provider_type="rss",
            feed_url="https://www.coindesk.com/arc/outboundfeeds/rss/",
            source_domain="coindesk.com",
            source_name="CoinDesk",
            source_role="specialist_media",
            trust_tier="high",
            context_policy={"enabled": True},
            now_ms=NOW_MS - 10_000,
        )
        fetch_run_id = repo.start_fetch_run(source_id="coindesk", started_at_ms=NOW_MS - 9_000)
        repo.finish_fetch_run(
            fetch_run_id=fetch_run_id,
            source_id="coindesk",
            status="success",
            finished_at_ms=NOW_MS - 8_000,
            fetched_count=2,
            inserted_count=1,
            duplicate_count=1,
        )
        provider_item = repo.upsert_provider_item(
            source_id="coindesk",
            fetch_run_id=fetch_run_id,
            source_item_key="guid-1",
            canonical_url="https://www.coindesk.com/story",
            payload_hash="hash-1",
            raw_payload={"id": "guid-1"},
            fetched_at_ms=NOW_MS - 7_000,
        )
        item = repo.upsert_canonical_news_item(
            provider_item_id=str(provider_item["provider_item_id"]),
            canonical_url="https://www.coindesk.com/story",
            title="Coinbase lists $BTC",
            summary="Trading starts today.",
            body_text="Trading starts today.",
            language="en",
            published_at_ms=NOW_MS - 60_000,
            fetched_at_ms=NOW_MS - 7_000,
            content_hash="content-hash-1",
            title_fingerprint="coinbase lists btc",
            now_ms=NOW_MS - 6_000,
        )
        news_item_id = str(item["news_item_id"])
        repo.replace_token_mentions(
            news_item_id=news_item_id,
            mentions=[
                {
                    "mention_id": "mention-1",
                    "news_item_id": news_item_id,
                    "entity_id": None,
                    "observed_symbol": "BTC",
                    "chain_id": None,
                    "address": None,
                    "resolution_status": "known_symbol",
                    "target_type": "CexToken",
                    "target_id": "cex:BTC",
                    "display_symbol": "BTC",
                    "display_name": "Bitcoin",
                    "reason_codes": ["CONFIRMED_CEX_TOKEN"],
                    "candidate_targets": [],
                    "evidence_strength": "strong",
                    "confidence": 0.95,
                    "created_at_ms": NOW_MS - 5_000,
                }
            ],
        )
        repo.replace_fact_candidates(
            news_item_id=news_item_id,
            candidates=[
                {
                    "fact_candidate_id": "fact-1",
                    "news_item_id": news_item_id,
                    "event_type": "exchange_listing",
                    "claim": "Coinbase lists BTC",
                    "realis": "actual",
                    "evidence_quote": "Coinbase lists $BTC",
                    "evidence_span_start": 0,
                    "evidence_span_end": 19,
                    "source_role": "specialist_media",
                    "required_slots": {"target": "BTC"},
                    "affected_targets": [{"target_type": "CexToken", "target_id": "cex:BTC"}],
                    "validation_status": "accepted",
                    "rejection_reasons": [],
                    "extraction_method": "deterministic",
                    "policy_version": "test",
                    "created_at_ms": NOW_MS - 4_000,
                    "updated_at_ms": NOW_MS - 4_000,
                }
            ],
        )
        repo.mark_item_processed(news_item_id=news_item_id, processed_at_ms=NOW_MS - 3_000)
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
            artifact_version_hash="artifact-1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
            guardrail_version="guard-v1",
            input_hash="input-1",
            output_hash="output-1",
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
            latency_ms=10,
            started_at_ms=NOW_MS - 2_000,
            finished_at_ms=NOW_MS - 1_900,
            created_at_ms=NOW_MS - 2_000,
        )
        repo.upsert_news_item_agent_brief(
            news_item_id=news_item_id,
            agent_run_id="run-1",
            status="ready",
            direction="neutral",
            decision_class="context",
            brief_json={"summary_zh": "测试"},
            input_hash="input-1",
            artifact_version_hash="artifact-1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            validator_version="validator-v1",
            computed_at_ms=NOW_MS - 1_800,
            created_at_ms=NOW_MS - 1_800,
            updated_at_ms=NOW_MS - 1_800,
        )
        repo.upsert_news_context_item(
            context_item_id="ctx-1",
            source_id="coindesk",
            parent_news_item_id=news_item_id,
            context_type="reply",
            author="analyst",
            canonical_url="https://example.test/reply",
            body_text="Useful context",
            published_at_ms=NOW_MS - 1_000,
            created_at_ms=NOW_MS - 1_000,
        )

        aggregate_inputs = repo.list_source_quality_inputs_for_targets(
            source_windows=[("coindesk", "24h")],
            now_ms=NOW_MS,
        )
        rows = build_source_quality_rows(
            aggregate_inputs=aggregate_inputs,
            window="24h",
            window_ms=DAY_MS,
            computed_at_ms=NOW_MS,
        )
        repo.replace_source_quality_rows(rows=rows, status_window="24h")
        stored = conn.execute("SELECT * FROM news_source_quality_rows WHERE source_id = %s", ("coindesk",)).fetchone()
        source = conn.execute(
            "SELECT source_quality_status FROM news_sources WHERE source_id = %s",
            ("coindesk",),
        ).fetchone()
        source_status = repo.list_source_status()[0]
    finally:
        conn.close()

    assert aggregate_inputs[0]["fetch_run_count"] == 1
    assert aggregate_inputs[0]["items_fetched"] == 2
    assert aggregate_inputs[0]["items_duplicate"] == 1
    assert aggregate_inputs[0]["resolved_mention_count"] == 1
    assert aggregate_inputs[0]["accepted_fact_count"] == 1
    assert aggregate_inputs[0]["ready_brief_count"] == 1
    assert aggregate_inputs[0]["context_parent_item_count"] == 1
    assert aggregate_inputs[0]["useful_item_count"] == 1
    assert stored is not None
    assert stored["window"] == "24h"
    assert stored["items_fetched"] == 2
    assert stored["quality_score"] is not None
    assert source["source_quality_status"] == stored["diagnostics_json"]["status"]
    assert source_status["latest_item_published_at_ms"] == NOW_MS - 60_000
    assert source_status["latest_item_fetched_at_ms"] == NOW_MS - 7_000
    assert source_status["context_item_count"] == 1
    assert source_status["latest_context_seen_at_ms"] == NOW_MS - 1_000
    assert source_status["last_seen_at_ms"] == NOW_MS - 1_000
    assert source_status["latest_fetch_run"] == {
        "status": "success",
        "started_at_ms": NOW_MS - 9_000,
        "finished_at_ms": NOW_MS - 8_000,
        "http_status": None,
        "fetched_count": 2,
        "inserted_count": 1,
        "updated_count": 0,
        "duplicate_count": 1,
        "error": None,
    }
    assert source_status["latest_quality_counts"]["fetch_run_count"] == 1
    assert source_status["latest_quality_counts"]["context_item_count"] == 1
    assert source_status["provider_health"]["status"] == stored["diagnostics_json"]["status"]
    assert source_status["provider_health"]["last_seen_at_ms"] == NOW_MS - 1_000
    assert source_status["provider_capability_tags"] == [
        "poll_primary_items",
        "http_cache",
        "context_items",
        "high_trust",
    ]
