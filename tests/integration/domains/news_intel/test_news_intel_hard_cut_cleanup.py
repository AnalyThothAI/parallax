from __future__ import annotations

import pytest

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.services.news_intel_hard_cut_cleanup import (
    NewsIntelHardCutCleanupAbort,
    cleanup_news_intel_hard_cut,
)
from parallax.domains.news_intel.types.news_item_brief_contract import CURRENT_NEWS_ITEM_BRIEF_CONTRACT
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000
CURRENT_ARTIFACT_HASH = "current-artifact"
OLD_PROMPT = "news-item-brief-synthesizer-v1"
OLD_SCHEMA = "news_item_brief_v2"
OLD_VALIDATOR = "news_item_brief_validator_v4"
MATERIAL_FACT_TABLES = (
    "news_sources",
    "news_fetch_runs",
    "news_provider_items",
    "news_item_observation_edges",
    "news_items",
    "news_item_entities",
    "news_token_mentions",
    "news_fact_candidates",
)
CURRENT_READ_MODEL_TABLES = ("news_source_quality_rows",)
ARTIFACT_TABLES = (
    "news_item_agent_briefs",
    "news_item_agent_runs",
    "news_page_rows",
    "news_projection_dirty_targets",
    "notifications",
)


def test_news_intel_hard_cut_cleanup_dry_run_counts_without_deleting(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_cleanup_state(conn)

        result = cleanup_news_intel_hard_cut(
            _repos(conn),
            execute=False,
            now_ms=NOW_MS,
            current_artifact_version_hash=CURRENT_ARTIFACT_HASH,
        )

        old_contract_key = _contract_key(OLD_PROMPT, OLD_SCHEMA, OLD_VALIDATOR, "old-artifact")
        current_old_tool_key = _contract_key(
            CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"],
            CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"],
            CURRENT_NEWS_ITEM_BRIEF_CONTRACT["validator_version"],
            CURRENT_ARTIFACT_HASH,
        )
        current_old_artifact_key = _contract_key(
            CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"],
            CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"],
            CURRENT_NEWS_ITEM_BRIEF_CONTRACT["validator_version"],
            "old-artifact-hash",
        )
        assert result["mode"] == "dry_run"
        assert result["execute"] is False
        assert result["current_contract"] == {
            **CURRENT_NEWS_ITEM_BRIEF_CONTRACT,
            "artifact_version_hash": CURRENT_ARTIFACT_HASH,
        }
        assert result["legacy_briefs_by_contract"][old_contract_key] == 1
        assert result["legacy_briefs_by_contract"][current_old_artifact_key] == 1
        assert result["legacy_runs_by_contract"][old_contract_key] == 1
        assert result["legacy_runs_by_contract"][current_old_tool_key] == 1
        assert result["legacy_runs_by_contract"][current_old_artifact_key] == 1
        assert result["retired_page_rows"] == 4
        assert result["retired_notifications"]["notifications"] == 3
        assert result["deleted"] == {}
        assert result["preserved_material_facts"] == _counts(conn, MATERIAL_FACT_TABLES)
        assert result["preserved_current_read_models"] == _counts(conn, CURRENT_READ_MODEL_TABLES)
        assert _count(conn, "news_item_agent_briefs") == 5
        assert _count(conn, "news_item_agent_runs") == 5
        assert _count(conn, "news_page_rows") == 5
        assert _count(conn, "notifications") == 5
    finally:
        conn.close()


def test_news_intel_hard_cut_cleanup_execute_deletes_retired_artifacts_and_preserves_material_facts(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_cleanup_state(conn)
        material_counts_before = _counts(conn, MATERIAL_FACT_TABLES)
        current_read_model_counts_before = _counts(conn, CURRENT_READ_MODEL_TABLES)
        source_before = dict(conn.execute("SELECT * FROM news_sources WHERE source_id = 'source-1'").fetchone())

        result = cleanup_news_intel_hard_cut(
            _repos(conn),
            execute=True,
            now_ms=NOW_MS,
            current_artifact_version_hash=CURRENT_ARTIFACT_HASH,
        )

        assert result["execute"] is True
        assert result["deleted"] == {
            "news_item_agent_briefs": 3,
            "news_item_agent_runs": 3,
            "news_page_rows": 4,
            "news_projection_dirty_targets": 3,
            "notifications": 3,
            "notification_reads": 3,
            "notification_deliveries": 3,
        }
        assert _counts(conn, MATERIAL_FACT_TABLES) == material_counts_before
        assert _counts(conn, CURRENT_READ_MODEL_TABLES) == current_read_model_counts_before
        assert dict(conn.execute("SELECT * FROM news_sources WHERE source_id = 'source-1'").fetchone()) == source_before
        assert _count(conn, "news_item_agent_briefs") == 2
        assert _count(conn, "news_item_agent_runs") == 2
        assert _count(conn, "news_page_rows") == 1
        assert _count(conn, "news_projection_dirty_targets") == 1
        assert _count(conn, "notifications") == 2
        assert _count(conn, "notification_reads") == 1
        assert _count(conn, "notification_deliveries") == 1
        assert _ids(conn, "news_item_agent_runs", "run_id") == [
            "run-current-clean",
            "run-current-prose-tool-mention",
        ]
        assert _ids(conn, "news_page_rows", "row_id") == ["row-current-clean"]
        assert _ids(conn, "notifications", "notification_id") == ["current-news-notification", "pulse-notification"]
    finally:
        conn.close()


def test_news_intel_hard_cut_cleanup_preserves_pending_page_rows_without_agent_contract(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        _seed_cleanup_state(conn)
        pending_item_id = _seed_news_item(repo, slug="current-pending", offset=8)
        repo.replace_page_rows_for_items(
            news_item_ids=[pending_item_id],
            rows=[
                _page_row(
                    "row-current-pending",
                    pending_item_id,
                    projection_version=NEWS_PAGE_PROJECTION_VERSION,
                    agent_brief={"status": "pending"},
                )
            ],
        )

        dry_run = cleanup_news_intel_hard_cut(
            _repos(conn),
            execute=False,
            now_ms=NOW_MS,
            current_artifact_version_hash=CURRENT_ARTIFACT_HASH,
        )
        assert dry_run["retired_page_rows"] == 4

        cleanup_news_intel_hard_cut(
            _repos(conn),
            execute=True,
            now_ms=NOW_MS,
            current_artifact_version_hash=CURRENT_ARTIFACT_HASH,
        )

        assert _ids(conn, "news_page_rows", "row_id") == ["row-current-clean", "row-current-pending"]
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
        artifact_counts_before = _counts(conn, ARTIFACT_TABLES)

        with pytest.raises(NewsIntelHardCutCleanupAbort):
            cleanup_news_intel_hard_cut(
                _repos(conn),
                execute=True,
                now_ms=NOW_MS,
                current_artifact_version_hash=CURRENT_ARTIFACT_HASH,
            )

        assert _counts(conn, ARTIFACT_TABLES) == artifact_counts_before
        assert _count(conn, "news_fetch_runs") == 8
    finally:
        conn.close()


def test_news_intel_hard_cut_cleanup_rejects_active_dirty_lease_without_deleting(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_cleanup_state(conn, dirty_leased_until_ms=NOW_MS + 60_000)
        artifact_counts_before = _counts(conn, ARTIFACT_TABLES)

        with pytest.raises(NewsIntelHardCutCleanupAbort):
            cleanup_news_intel_hard_cut(
                _repos(conn),
                execute=True,
                now_ms=NOW_MS,
                current_artifact_version_hash=CURRENT_ARTIFACT_HASH,
            )

        assert _counts(conn, ARTIFACT_TABLES) == artifact_counts_before
    finally:
        conn.close()


def _repos(conn):
    return type("Repos", (), {"conn": conn})()


def _seed_cleanup_state(conn, *, dirty_leased_until_ms: int | None = None) -> list[str]:
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
    old_item_id = _seed_news_item(repo, slug="old", offset=1)
    current_tool_item_id = _seed_news_item(repo, slug="current-tool", offset=2)
    old_page_item_id = _seed_news_item(repo, slug="old-page", offset=3)
    current_clean_item_id = _seed_news_item(repo, slug="current-clean", offset=4)
    old_artifact_item_id = _seed_news_item(repo, slug="old-artifact", offset=5)
    current_prose_tool_item_id = _seed_news_item(repo, slug="current-prose-tool", offset=6)
    missing_page_contract_item_id = _seed_news_item(repo, slug="missing-page-contract", offset=7)

    _seed_agent_artifact(
        repo,
        news_item_id=old_item_id,
        run_id="run-old-contract",
        artifact_version_hash="old-artifact",
        prompt_version=OLD_PROMPT,
        schema_version=OLD_SCHEMA,
        validator_version=OLD_VALIDATOR,
        brief_json={"summary_zh": "测试", "retrieval_notes_zh": "旧检索记录"},
        request_json={"tool_results": {"get_target_news_context": {"items": []}}},
        response_json={"research_packet": {"source_consensus_zh": "旧共识"}},
    )
    _seed_agent_artifact(
        repo,
        news_item_id=current_tool_item_id,
        run_id="run-current-old-tool",
        artifact_version_hash=CURRENT_ARTIFACT_HASH,
        prompt_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"],
        schema_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"],
        validator_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["validator_version"],
        brief_json={"summary_zh": "当前合约但旧字段", "confidence": 0.4},
        request_json={"tool_results": [{"name": "get_target_news_context", "value": {"items": []}}]},
        response_json={"tool_results": [{"name": "get_observation_history"}]},
    )
    _seed_agent_artifact(
        repo,
        news_item_id=old_artifact_item_id,
        run_id="run-current-old-artifact",
        artifact_version_hash="old-artifact-hash",
        prompt_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"],
        schema_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"],
        validator_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["validator_version"],
        brief_json={"summary_zh": "当前版本但旧 artifact hash"},
        request_json={"input": "clean old artifact"},
        response_json={"summary_zh": "clean old artifact"},
    )
    _seed_agent_artifact(
        repo,
        news_item_id=current_clean_item_id,
        run_id="run-current-clean",
        artifact_version_hash=CURRENT_ARTIFACT_HASH,
        prompt_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"],
        schema_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"],
        validator_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["validator_version"],
        brief_json={"summary_zh": "当前干净 brief"},
        request_json={"input": "clean"},
        response_json={"summary_zh": "clean"},
    )
    _seed_agent_artifact(
        repo,
        news_item_id=current_prose_tool_item_id,
        run_id="run-current-prose-tool-mention",
        artifact_version_hash=CURRENT_ARTIFACT_HASH,
        prompt_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"],
        schema_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"],
        validator_version=CURRENT_NEWS_ITEM_BRIEF_CONTRACT["validator_version"],
        brief_json={"summary_zh": "当前干净 prose"},
        request_json={"messages": [{"content": "The phrase search_news_archive appears here as prose only."}]},
        response_json={"summary_zh": "clean prose"},
    )
    _seed_page_rows(
        repo,
        old_item_id=old_item_id,
        current_tool_item_id=current_tool_item_id,
        old_page_item_id=old_page_item_id,
        missing_page_contract_item_id=missing_page_contract_item_id,
        current_clean_item_id=current_clean_item_id,
    )
    _seed_dirty_targets(
        conn,
        old_item_id=old_item_id,
        current_tool_item_id=current_tool_item_id,
        old_artifact_item_id=old_artifact_item_id,
        current_clean_item_id=current_clean_item_id,
        dirty_leased_until_ms=dirty_leased_until_ms,
    )
    _seed_notifications(
        conn,
        old_item_id=old_item_id,
        current_clean_item_id=current_clean_item_id,
    )
    return [
        old_item_id,
        current_tool_item_id,
        old_page_item_id,
        current_clean_item_id,
        old_artifact_item_id,
        current_prose_tool_item_id,
        missing_page_contract_item_id,
    ]


def _seed_news_item(repo: NewsRepository, *, slug: str, offset: int) -> str:
    fetch_run_id = repo.start_fetch_run(source_id="source-1", started_at_ms=NOW_MS - (10_000 - offset))
    repo.finish_fetch_run(
        fetch_run_id=fetch_run_id,
        source_id="source-1",
        status="success",
        finished_at_ms=NOW_MS - (9_000 - offset),
        fetched_count=1,
        inserted_count=1,
    )
    provider_item = repo.upsert_provider_item(
        source_id="source-1",
        fetch_run_id=fetch_run_id,
        source_item_key=f"item-{slug}",
        canonical_url=f"https://example.com/{slug}",
        payload_hash=f"provider-hash-{slug}",
        raw_payload={"id": f"item-{slug}"},
        fetched_at_ms=NOW_MS - (8_000 - offset),
    )
    item = repo.upsert_canonical_news_item(
        provider_item_id=str(provider_item["provider_item_id"]),
        canonical_url=f"https://example.com/{slug}",
        title=f"BTC news {slug}",
        summary=f"BTC summary {slug}",
        body_text=f"BTC body {slug}",
        language="en",
        published_at_ms=NOW_MS - (7_000 - offset),
        fetched_at_ms=NOW_MS - (6_000 - offset),
        content_hash=f"content-hash-{slug}",
        title_fingerprint=f"btc news {slug}",
        now_ms=NOW_MS - (5_000 - offset),
    )
    news_item_id = str(item["news_item_id"])
    repo.replace_item_entities(
        news_item_id=news_item_id,
        entities=[
            {
                "entity_id": f"entity-{slug}",
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
                "mention_id": f"mention-{slug}",
                "news_item_id": news_item_id,
                "entity_id": f"entity-{slug}",
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
                "fact_candidate_id": f"fact-{slug}",
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
    repo.replace_source_quality_rows(
        rows=[
            {
                "row_id": f"quality:source-1:{slug}:24h",
                "source_id": "source-1",
                "window": f"{slug}:24h",
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
        status_window=f"{slug}:24h",
    )
    return news_item_id


def _seed_agent_artifact(
    repo: NewsRepository,
    *,
    news_item_id: str,
    run_id: str,
    artifact_version_hash: str,
    prompt_version: str,
    schema_version: str,
    validator_version: str,
    brief_json: dict[str, object],
    request_json: dict[str, object],
    response_json: dict[str, object],
) -> None:
    repo.insert_news_item_agent_run(
        run_id=run_id,
        news_item_id=news_item_id,
        provider="litellm",
        model="gpt-test",
        backend="litellm_sdk",
        execution_trace_id=None,
        workflow_name="news.item_brief",
        agent_name="news_item_brief",
        lane="news.item_brief",
        artifact_version_hash=artifact_version_hash,
        prompt_version=prompt_version,
        schema_version=schema_version,
        validator_version=validator_version,
        guardrail_version="guardrail",
        input_hash="input",
        output_hash="output",
        execution_started=True,
        status="completed",
        outcome="ready",
        error_class=None,
        error=None,
        request_json=request_json,
        response_json=response_json,
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
        agent_run_id=run_id,
        status="ready",
        direction="bullish",
        decision_class="driver",
        brief_json=brief_json,
        input_hash="input",
        artifact_version_hash=artifact_version_hash,
        prompt_version=prompt_version,
        schema_version=schema_version,
        validator_version=validator_version,
        computed_at_ms=NOW_MS,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _seed_page_rows(
    repo: NewsRepository,
    *,
    old_item_id: str,
    current_tool_item_id: str,
    old_page_item_id: str,
    missing_page_contract_item_id: str,
    current_clean_item_id: str,
) -> None:
    repo.replace_page_rows_for_items(
        news_item_ids=[
            old_item_id,
            current_tool_item_id,
            old_page_item_id,
            missing_page_contract_item_id,
            current_clean_item_id,
        ],
        rows=[
            _page_row(
                "row-old-contract",
                old_item_id,
                projection_version=NEWS_PAGE_PROJECTION_VERSION,
                agent_brief={
                    "status": "ready",
                    "prompt_version": OLD_PROMPT,
                    "schema_version": OLD_SCHEMA,
                    "validator_version": OLD_VALIDATOR,
                    "brief_json": {"summary_zh": "旧页面", "retrieval_notes_zh": "旧字段"},
                },
            ),
            _page_row(
                "row-current-old-tool",
                current_tool_item_id,
                projection_version=NEWS_PAGE_PROJECTION_VERSION,
                agent_brief={
                    "status": "ready",
                    **CURRENT_NEWS_ITEM_BRIEF_CONTRACT,
                    "brief_json": {"summary_zh": "当前合约页面", "source_consensus_zh": "旧字段"},
                },
            ),
            _page_row(
                "row-old-projection",
                old_page_item_id,
                projection_version="news_page_rows_v2",
                agent_brief={"status": "pending", **CURRENT_NEWS_ITEM_BRIEF_CONTRACT, "brief_json": {}},
            ),
            _page_row(
                "row-missing-contract",
                missing_page_contract_item_id,
                projection_version=NEWS_PAGE_PROJECTION_VERSION,
                agent_brief={
                    "status": "ready",
                    "prompt_version": CURRENT_NEWS_ITEM_BRIEF_CONTRACT["prompt_version"],
                    "schema_version": CURRENT_NEWS_ITEM_BRIEF_CONTRACT["schema_version"],
                    "brief_json": {"summary_zh": "缺少 validator"},
                },
            ),
            _page_row(
                "row-current-clean",
                current_clean_item_id,
                projection_version=NEWS_PAGE_PROJECTION_VERSION,
                agent_brief={
                    "status": "ready",
                    **CURRENT_NEWS_ITEM_BRIEF_CONTRACT,
                    "brief_json": {"summary_zh": "当前干净页面"},
                },
            ),
        ],
    )


def _page_row(
    row_id: str,
    news_item_id: str,
    *,
    projection_version: str,
    agent_brief: dict[str, object],
) -> dict[str, object]:
    return {
        "row_id": row_id,
        "news_item_id": news_item_id,
        "latest_at_ms": NOW_MS,
        "source_domain": "example.com",
        "headline": f"BTC news {row_id}",
        "summary": "BTC summary",
        "canonical_url": f"https://example.com/{row_id}",
        "lifecycle_status": "processed",
        "token_lanes_json": [],
        "fact_lanes_json": [],
        "source": {"source_id": "source-1"},
        "signal": {"display_signal": {"direction": "bullish", "score": 90}},
        "agent_brief": agent_brief,
        "projection_version": projection_version,
        "computed_at_ms": NOW_MS,
    }


def _seed_dirty_targets(
    conn,
    *,
    old_item_id: str,
    current_tool_item_id: str,
    old_artifact_item_id: str,
    current_clean_item_id: str,
    dirty_leased_until_ms: int | None,
) -> None:
    conn.execute(
        """
        INSERT INTO news_projection_dirty_targets(
          projection_name, target_kind, target_id, "window", dirty_reason, payload_hash,
          priority, due_at_ms, leased_until_ms, lease_owner, first_dirty_at_ms, updated_at_ms
        )
        VALUES
          ('brief_input', 'news_item', %s, '', 'test', 'hash-old', 10, %s, %s, 'worker', %s, %s),
          ('brief_input', 'news_item', %s, '', 'test', 'hash-tool', 10, %s, NULL, NULL, %s, %s),
          ('brief_input', 'news_item', %s, '', 'test', 'hash-artifact', 10, %s, NULL, NULL, %s, %s),
          ('brief_input', 'news_item', %s, '', 'test', 'hash-clean', 10, %s, NULL, NULL, %s, %s)
        """,
        (
            old_item_id,
            NOW_MS,
            dirty_leased_until_ms,
            NOW_MS,
            NOW_MS,
            current_tool_item_id,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            old_artifact_item_id,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            current_clean_item_id,
            NOW_MS,
            NOW_MS,
            NOW_MS,
        ),
    )


def _seed_notifications(conn, *, old_item_id: str, current_clean_item_id: str) -> None:
    conn.execute(
        """
        INSERT INTO notifications(
          notification_id, dedup_key, rule_id, severity, title, body, entity_type, entity_key,
          source_table, source_id, first_seen_at_ms, last_seen_at_ms, payload_json, created_at_ms, updated_at_ms
        )
        VALUES
          (
            'old-row-news-notification', 'news-dedup-old-row', 'news_high_signal', 'high', 'News', 'News body',
            'news_item', %s, 'news_page_rows', 'row-old-contract', %s, %s, '{}'::jsonb, %s, %s
          ),
          (
            'retired-payload-news-notification', 'news-dedup-retired-payload', 'news_high_signal',
            'high', 'News', 'News body',
            'news_item', %s, 'news_page_rows', 'row-current-clean', %s, %s,
            '{"brief_json":{"watch_items_zh":[]}}'::jsonb, %s, %s
          ),
          (
            'deleted-source-news-notification', 'news-dedup-deleted-source', 'news_high_signal',
            'high', 'News', 'News body',
            'news_item', 'news-missing', 'news_page_rows', 'row-missing', %s, %s, '{}'::jsonb, %s, %s
          ),
          (
            'current-news-notification', 'news-dedup-current', 'news_high_signal', 'high', 'News', 'News body',
            'news_item', %s, 'news_page_rows', 'row-current-clean', %s, %s, '{}'::jsonb, %s, %s
          ),
          (
            'pulse-notification', 'pulse-dedup', 'signal_pulse_candidate', 'high', 'Pulse', 'Pulse body',
            'pulse_candidate', 'pulse-1', 'pulse_candidates', 'pulse-1', %s, %s, '{}'::jsonb, %s, %s
          )
        """,
        (
            old_item_id,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            current_clean_item_id,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            current_clean_item_id,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
            NOW_MS,
        ),
    )
    conn.execute(
        """
        INSERT INTO notification_reads(notification_id, subscriber_key, read_at_ms)
        VALUES
          ('old-row-news-notification', 'operator', %s),
          ('retired-payload-news-notification', 'operator', %s),
          ('deleted-source-news-notification', 'operator', %s),
          ('current-news-notification', 'operator', %s)
        """,
        (NOW_MS, NOW_MS, NOW_MS, NOW_MS),
    )
    conn.execute(
        """
        INSERT INTO notification_deliveries(
          delivery_id, notification_id, channel_id, provider, status,
          next_run_at_ms, created_at_ms, updated_at_ms
        )
        VALUES
          ('delivery-old-row', 'old-row-news-notification', 'in_app', 'log', 'pending', %s, %s, %s),
          ('delivery-retired-payload', 'retired-payload-news-notification', 'in_app', 'log', 'pending', %s, %s, %s),
          ('delivery-deleted-source', 'deleted-source-news-notification', 'in_app', 'log', 'pending', %s, %s, %s),
          ('delivery-current', 'current-news-notification', 'in_app', 'log', 'pending', %s, %s, %s)
        """,
        (NOW_MS, NOW_MS, NOW_MS) * 4,
    )


def _count(conn, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])


def _counts(conn, table_names: tuple[str, ...]) -> dict[str, int]:
    return {table_name: _count(conn, table_name) for table_name in table_names}


def _ids(conn, table_name: str, column_name: str) -> list[str]:
    return [
        str(row[column_name])
        for row in conn.execute(f"SELECT {column_name} FROM {table_name} ORDER BY {column_name}").fetchall()
    ]


def _contract_key(prompt_version: str, schema_version: str, validator_version: str, artifact_version_hash: str) -> str:
    return (
        f"prompt_version={prompt_version}|schema_version={schema_version}|"
        f"validator_version={validator_version}|artifact_version_hash={artifact_version_hash}"
    )
