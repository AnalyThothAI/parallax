from __future__ import annotations

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
)
from parallax.domains.news_intel.repositories.news_repository import NewsRepository
from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from parallax.domains.news_intel.types.news_extraction import NewsFactCandidate, NewsTokenMention
from parallax.domains.news_intel.types.news_item_agent_admission import NewsItemAgentAdmission
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NewsItemBriefPayload,
    default_news_item_brief_agent_config,
)
from parallax.domains.news_intel.types.news_market_scope import NewsMarketScope
from parallax.domains.news_intel.types.news_story_identity import NEWS_STORY_IDENTITY_VERSION, NewsStoryIdentity
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000
ARTIFACT_HASH = "artifact-hash-brief-v1"


def test_load_items_for_brief_targets_selects_processed_targets_only(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        processed_id = _insert_source_provider_and_item(repo, suffix="processed", processed=True)
        raw_id = _insert_source_provider_and_item(repo, suffix="raw", processed=False)

        rows = _load_items_for_brief_targets(repo, news_item_ids=[processed_id, raw_id])
    finally:
        conn.close()

    selected_ids = [row["item"]["news_item_id"] for row in rows]
    assert selected_ids == [processed_id]
    assert raw_id not in selected_ids


def test_load_items_for_brief_targets_preserves_claim_order(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        oldest_id = _insert_source_provider_and_item(
            repo,
            suffix="oldest",
            processed=True,
            published_at_ms=NOW_MS - 120_000,
            now_ms=NOW_MS - 120_000,
        )
        middle_id = _insert_source_provider_and_item(
            repo,
            suffix="middle",
            processed=True,
            published_at_ms=NOW_MS - 60_000,
            now_ms=NOW_MS - 60_000,
        )
        newest_id = _insert_source_provider_and_item(
            repo,
            suffix="newest",
            processed=True,
            published_at_ms=NOW_MS,
            now_ms=NOW_MS,
        )

        rows = _load_items_for_brief_targets(repo, news_item_ids=[newest_id, middle_id, oldest_id])
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [newest_id, middle_id, oldest_id]


def test_load_items_for_brief_targets_includes_backpressure_audit_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        cooled_backpressure_id = _insert_source_provider_and_item(
            repo,
            suffix="cooled-backpressure",
            processed=True,
            published_at_ms=NOW_MS,
            now_ms=NOW_MS - 100,
        )
        fresh_id = _insert_source_provider_and_item(
            repo,
            suffix="fresh-never-attempted",
            processed=True,
            published_at_ms=NOW_MS,
            now_ms=NOW_MS,
        )
        _insert_run(
            repo,
            news_item_id=cooled_backpressure_id,
            run_id="run-cooled-backpressure",
            output_hash=None,
            execution_started=False,
            status="backpressure",
            outcome="backpressure_capacity_denied",
            started_at_ms=NOW_MS - 90,
            finished_at_ms=NOW_MS - 80,
        )

        rows = _load_items_for_brief_targets(repo, news_item_ids=[fresh_id, cooled_backpressure_id])
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [fresh_id, cooled_backpressure_id]
    assert rows[1]["latest_run"]["status"] == "backpressure"
    assert rows[1]["latest_run"]["execution_started"] is False


def test_load_items_for_brief_targets_returns_current_and_changed_fact_inputs(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        fresh_id = _insert_source_provider_and_item(repo, suffix="fresh", processed=True)
        changed_id = _insert_source_provider_and_item(repo, suffix="changed", processed=True)
        _insert_ready_current(repo, news_item_id=fresh_id, run_id="run-fresh", computed_at_ms=NOW_MS + 100)
        _insert_ready_current(repo, news_item_id=changed_id, run_id="run-changed", computed_at_ms=NOW_MS + 100)
        repo.replace_fact_candidates(
            news_item_id=changed_id,
            candidates=[
                NewsFactCandidate(
                    fact_candidate_id="fact-changed",
                    news_item_id=changed_id,
                    event_type="listing",
                    claim="SOL spot ETF filing updated with official docket.",
                    realis="reported_claim",
                    evidence_quote="updated with official docket",
                    evidence_span_start=0,
                    evidence_span_end=28,
                    source_role="observed_source",
                    required_slots={"asset": True},
                    affected_targets=[{"target_type": "asset", "target_id": "asset:sol"}],
                    validation_status="accepted",
                    rejection_reasons=[],
                    extraction_method="test",
                    policy_version="test",
                    created_at_ms=NOW_MS + 200,
                    updated_at_ms=NOW_MS + 200,
                )
            ],
        )

        rows = _load_items_for_brief_targets(repo, news_item_ids=[fresh_id, changed_id])
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [fresh_id, changed_id]
    assert rows[0]["current_brief"]["agent_run_id"] == "run-fresh"
    assert rows[1]["fact_candidates"][0]["fact_candidate_id"] == "fact-changed"


def test_load_items_for_brief_targets_returns_recent_backpressure_attempt(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo, suffix="backpressure", processed=True)
        _insert_run(
            repo,
            news_item_id=news_item_id,
            run_id="run-recent-backpressure",
            output_hash=None,
            execution_started=False,
            status="backpressure",
            outcome="backpressure_capacity_denied",
            started_at_ms=NOW_MS + 10,
            finished_at_ms=NOW_MS + 20,
        )
        rows = _load_items_for_brief_targets(repo, news_item_ids=[news_item_id])
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [news_item_id]
    assert rows[0]["latest_run"]["run_id"] == "run-recent-backpressure"
    assert rows[0]["latest_run"]["execution_started"] is False


def test_load_items_for_brief_targets_returns_failed_current_attempt_state(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        retry_id = _insert_source_provider_and_item(repo, suffix="retry", processed=True)
        exhausted_id = _insert_source_provider_and_item(repo, suffix="exhausted", processed=True)
        _insert_failed_current(repo, news_item_id=retry_id, run_id="run-retry-1", computed_at_ms=NOW_MS + 100)
        _insert_failed_current(repo, news_item_id=exhausted_id, run_id="run-exhausted-1", computed_at_ms=NOW_MS + 100)
        _insert_run(
            repo,
            news_item_id=exhausted_id,
            run_id="run-exhausted-2",
            output_hash=None,
            status="failed",
            outcome="failed",
            artifact_version_hash=ARTIFACT_HASH,
            started_at_ms=NOW_MS + 101,
            finished_at_ms=NOW_MS + 110,
        )

        rows = _load_items_for_brief_targets(repo, news_item_ids=[retry_id, exhausted_id])
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [retry_id, exhausted_id]
    assert rows[0]["current_brief"]["status"] == "failed"
    assert rows[1]["latest_run"]["run_id"] == "run-exhausted-2"


def test_load_items_for_brief_targets_payload_contains_packet_inputs_and_audit_rows(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(
            repo,
            suffix="payload",
            processed=True,
            source_name="Payload Source",
            source_role="official_protocol",
            trust_tier="high",
        )
        _insert_ready_current(repo, news_item_id=news_item_id, run_id="run-current", computed_at_ms=NOW_MS - 50)
        repo.replace_token_mentions(
            news_item_id=news_item_id,
            mentions=[
                NewsTokenMention(
                    mention_id="mention-payload",
                    news_item_id=news_item_id,
                    entity_id=None,
                    observed_symbol="SOL",
                    chain_id=None,
                    address=None,
                    resolution_status="known_symbol",
                    target_type="asset",
                    target_id="asset:sol",
                    display_symbol="SOL",
                    display_name="Solana",
                    reason_codes=["confirmed_symbol"],
                    candidate_targets=[],
                    evidence_strength="strong",
                    confidence=0.9,
                    created_at_ms=NOW_MS + 1,
                )
            ],
        )
        row = _load_items_for_brief_targets(repo, news_item_ids=[news_item_id])[0]
        packet = build_news_item_brief_input_packet(
            item=row["item"],
            token_mentions=row["token_mentions"],
            fact_candidates=row["fact_candidates"],
            agent_config=default_news_item_brief_agent_config(
                model="gpt-5-mini",
                artifact_version_hash=ARTIFACT_HASH,
            ),
        )
    finally:
        conn.close()

    assert row["item"]["source_name"] == "Payload Source"
    assert row["item"]["source_role"] == "official_protocol"
    assert row["item"]["trust_tier"] == "high"
    assert row["current_brief"]["agent_run_id"] == "run-current"
    assert row["latest_run"]["run_id"] == "run-current"
    assert row["source_updated_at_ms"] == NOW_MS + 1
    assert "story" not in row
    assert "story_members" not in row
    assert packet.news_item.source.source_name == "Payload Source"
    assert packet.entity_lanes[0].entity_id == "mention-payload"


def test_brief_target_material_watermark_ignores_refetch_updated_at(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        now = 1_779_000_000_000
        news_item_id = _insert_source_provider_and_item(
            repo,
            suffix="refetch-watermark",
            processed=True,
            now_ms=now,
        )
        first = repo.load_items_for_brief_targets(news_item_ids=[news_item_id])[0]
        item = conn.execute(
            "SELECT * FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()

        repo.upsert_canonical_news_item(
            provider_item_id=item["provider_item_id"],
            canonical_url=item["canonical_url"],
            title=item["title"],
            summary=item["summary"],
            body_text=item["body_text"],
            language=item["language"],
            published_at_ms=item["published_at_ms"],
            fetched_at_ms=now + 60_000,
            content_hash=item["content_hash"],
            title_fingerprint=item["title_fingerprint"],
            now_ms=now + 60_000,
            provider_signal=item["provider_signal_json"] or {},
            provider_token_impacts=item["provider_token_impacts_json"] or [],
            commit=True,
        )
        second = repo.load_items_for_brief_targets(news_item_ids=[news_item_id])[0]
    finally:
        conn.close()

    assert second["source_updated_at_ms"] == first["source_updated_at_ms"]


def test_material_duplicate_observation_reuses_current_brief_target(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repos = repositories_for_connection(
            conn,
            notification_delivery_running_timeout_ms=300_000,
            notification_delivery_stale_running_terminalization_batch_size=100,
        )
        repo = repos.news
        _upsert_opennews_source(repo)
        coindesk_url = (
            "https://www.coindesk.com/markets/2026/06/03/"
            "bitcoin-crashes-to-usd62-000-as-billions-of-longs-get-liquidated"
        )
        title = "Bitcoin crashes to $62,000 as billions of longs get liquidated"
        fallback_news = _upsert_opennews_observation(
            repo,
            article_id="2514742",
            canonical_url="opennews://item/2514742",
            title=f"COINDESK: {title}",
            now_ms=NOW_MS,
            processed=True,
        )
        public_news = _upsert_opennews_observation(
            repo,
            article_id="2514740",
            canonical_url=coindesk_url,
            title=title,
            now_ms=NOW_MS + 1,
            processed=True,
        )
        affected_ids = [str(item_id) for item_id in public_news["affected_news_item_ids"]]

        servable_ids = repo.servable_news_item_ids(affected_ids)
        repos.news_projection_dirty_targets.enqueue_targets(
            [
                {
                    "projection_name": "brief_input",
                    "target_kind": "news_item",
                    "target_id": news_item_id,
                    "source_watermark_ms": int(public_news["published_at_ms"]),
                }
                for news_item_id in servable_ids
            ],
            reason="canonical_news_item_merge",
            now_ms=NOW_MS + 2,
            commit=True,
        )
        targets = conn.execute(
            """
            SELECT projection_name, target_id
              FROM news_projection_dirty_targets
             WHERE projection_name = 'brief_input'
             ORDER BY target_id
            """
        ).fetchall()
    finally:
        conn.close()

    assert str(fallback_news["news_item_id"]) != str(public_news["news_item_id"])
    assert affected_ids == [str(public_news["news_item_id"]), str(fallback_news["news_item_id"])]
    assert [dict(row) for row in targets] == [
        {
            "projection_name": "brief_input",
            "target_id": str(public_news["news_item_id"]),
        }
    ]


def test_agent_run_and_current_brief_round_trip_gateway_audit_metadata(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        brief_payload = NewsItemBriefPayload(
            status="ready",
            direction="bullish",
            decision_class="driver",
            summary_zh="ETF filing lifts SOL attention.",
            market_read_zh=(
                "SOL ETF filing adds regulatory narrative attention, while approval timing remains uncertain."
            ),
            event_type="etf_fund_flow",
            market_domains=["crypto", "regulation"],
            transmission_paths=[
                {
                    "market_domain": "regulation",
                    "channel": "regulatory_overhang",
                    "direction": "bullish",
                    "strength": "moderate",
                    "explanation_zh": "ETF filing adds source-backed regulatory narrative attention.",
                    "evidence_refs": ["item:summary"],
                }
            ],
            bull_view={
                "strength": "moderate",
                "thesis_zh": "Regulatory narrative could pull forward approval positioning.",
                "evidence_refs": ["item:summary"],
            },
            bear_view={
                "strength": "weak",
                "thesis_zh": "Approval timing is uncertain and may already be priced.",
                "evidence_refs": ["item:summary"],
            },
            affected_entities=[
                {
                    "label": "SOL",
                    "entity_type": "crypto_asset",
                    "symbol": "SOL",
                    "name": "Solana",
                    "market_domain": "crypto",
                    "resolution_status": "known_symbol",
                    "target_type": "asset",
                    "target_id": "asset:sol",
                    "impact_direction": "bullish",
                    "reason_zh": "The item directly concerns a SOL ETF filing.",
                    "evidence_refs": ["item:summary"],
                }
            ],
            watch_triggers=["Official filing URL or regulatory docket update."],
            invalidation_conditions=["Filing is withdrawn or denied."],
            data_gaps=[{"description_zh": "Missing official filing URL.", "severity": "medium"}],
            evidence_refs=["item:summary"],
        ).model_dump(mode="json")

        run = repo.insert_news_item_agent_run(
            run_id="news-item-agent-run-1",
            news_item_id=news_item_id,
            provider="litellm",
            model="gpt-5-mini",
            backend="litellm_sdk",
            execution_trace_id="trace-news-brief-1",
            workflow_name=NEWS_ITEM_BRIEF_WORKFLOW_NAME,
            agent_name=NEWS_ITEM_BRIEF_AGENT_NAME,
            lane=NEWS_ITEM_BRIEF_LANE,
            artifact_version_hash="artifact-hash-1",
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
            guardrail_version=NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
            input_hash="input-hash-1",
            output_hash="output-hash-1",
            execution_started=True,
            status="completed",
            outcome="ready",
            request_json={"gateway": {"lane": NEWS_ITEM_BRIEF_LANE}},
            response_json=brief_payload,
            validation_errors_json=[],
            trace_metadata_json={"execution_trace_id": "trace-news-brief-1", "attempt": 1},
            usage_json={"input_tokens": 321, "output_tokens": 123},
            latency_ms=987,
            started_at_ms=NOW_MS,
            finished_at_ms=NOW_MS + 987,
            created_at_ms=NOW_MS,
        )
        current = repo.upsert_news_item_agent_brief(
            news_item_id=news_item_id,
            agent_run_id=run["run_id"],
            status="ready",
            direction="bullish",
            decision_class="driver",
            brief_json=brief_payload,
            input_hash="input-hash-1",
            artifact_version_hash="artifact-hash-1",
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 987,
            created_at_ms=NOW_MS + 987,
            updated_at_ms=NOW_MS + 987,
        )
        fetched = repo.get_news_item_agent_brief(news_item_id)
    finally:
        conn.close()

    assert run["execution_trace_id"] == "trace-news-brief-1"
    assert run["request_json"]["gateway"]["lane"] == NEWS_ITEM_BRIEF_LANE
    assert run["response_json"]["summary_zh"] == "ETF filing lifts SOL attention."
    assert run["usage_json"] == {"input_tokens": 321, "output_tokens": 123}
    assert current["status"] == "ready"
    assert current["brief_json"]["summary_zh"] == "ETF filing lifts SOL attention."
    assert fetched == current


def test_upsert_news_item_agent_brief_rejects_ready_without_publishable_text(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        run = _insert_run(repo, news_item_id=news_item_id, run_id="run-empty-ready", output_hash="output-empty")

        with pytest.raises(ValueError, match="ready news item agent brief requires publishable"):
            repo.upsert_news_item_agent_brief(
                news_item_id=news_item_id,
                agent_run_id=run["run_id"],
                status="ready",
                direction="bullish",
                decision_class="driver",
                brief_json={},
                input_hash="input-empty",
                artifact_version_hash="artifact-empty",
                prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
                schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
                validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
                computed_at_ms=NOW_MS + 1,
                created_at_ms=NOW_MS + 1,
                updated_at_ms=NOW_MS + 1,
            )
    finally:
        conn.close()


def test_upsert_news_item_agent_brief_replaces_current_row_for_item(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        news_item_id = _insert_source_provider_and_item(repo)
        first_run = _insert_run(repo, news_item_id=news_item_id, run_id="run-1", output_hash="output-1")
        second_run = _insert_run(repo, news_item_id=news_item_id, run_id="run-2", output_hash="output-2")

        repo.upsert_news_item_agent_brief(
            news_item_id=news_item_id,
            agent_run_id=first_run["run_id"],
            status="insufficient",
            direction="neutral",
            decision_class="watch",
            brief_json={"summary_zh": "Initial brief lacks enough information."},
            input_hash="input-1",
            artifact_version_hash="artifact-1",
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 1,
            created_at_ms=NOW_MS + 1,
            updated_at_ms=NOW_MS + 1,
        )
        updated = repo.upsert_news_item_agent_brief(
            news_item_id=news_item_id,
            agent_run_id=second_run["run_id"],
            status="ready",
            direction="mixed",
            decision_class="context",
            brief_json={"summary_zh": "Updated brief keeps this as context."},
            input_hash="input-2",
            artifact_version_hash="artifact-2",
            prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
            schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
            validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
            computed_at_ms=NOW_MS + 2,
            created_at_ms=NOW_MS + 2,
            updated_at_ms=NOW_MS + 2,
        )
        row_count = conn.execute(
            "SELECT COUNT(*) AS count FROM news_item_agent_briefs WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()["count"]
    finally:
        conn.close()

    assert row_count == 1
    assert updated["agent_run_id"] == "run-2"
    assert updated["status"] == "ready"
    assert updated["direction"] == "mixed"
    assert updated["decision_class"] == "context"
    assert updated["brief_json"]["summary_zh"] == "Updated brief keeps this as context."
    assert updated["input_hash"] == "input-2"
    assert updated["artifact_version_hash"] == "artifact-2"


def _load_items_for_brief_targets(
    repo: NewsRepository,
    *,
    news_item_ids: list[str],
) -> list[dict[str, object]]:
    return repo.load_items_for_brief_targets(news_item_ids=news_item_ids)


def _insert_ready_current(
    repo: NewsRepository,
    *,
    news_item_id: str,
    run_id: str,
    computed_at_ms: int,
    artifact_version_hash: str = ARTIFACT_HASH,
) -> None:
    run = _insert_run(
        repo,
        news_item_id=news_item_id,
        run_id=run_id,
        output_hash=f"output-{run_id}",
        artifact_version_hash=artifact_version_hash,
        started_at_ms=computed_at_ms - 10,
        finished_at_ms=computed_at_ms,
    )
    repo.upsert_news_item_agent_brief(
        news_item_id=news_item_id,
        agent_run_id=run["run_id"],
        status="ready",
        direction="bullish",
        decision_class="watch",
        brief_json={"summary_zh": run_id, "status": "ready"},
        input_hash=f"input-{run_id}",
        artifact_version_hash=artifact_version_hash,
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        computed_at_ms=computed_at_ms,
        created_at_ms=computed_at_ms,
        updated_at_ms=computed_at_ms,
    )


def _insert_failed_current(
    repo: NewsRepository,
    *,
    news_item_id: str,
    run_id: str,
    computed_at_ms: int,
    artifact_version_hash: str = ARTIFACT_HASH,
) -> None:
    run = _insert_run(
        repo,
        news_item_id=news_item_id,
        run_id=run_id,
        output_hash=None,
        status="failed",
        outcome="failed",
        artifact_version_hash=artifact_version_hash,
        started_at_ms=computed_at_ms - 10,
        finished_at_ms=computed_at_ms,
    )
    repo.upsert_news_item_agent_brief(
        news_item_id=news_item_id,
        agent_run_id=run["run_id"],
        status="failed",
        direction="neutral",
        decision_class="discard",
        brief_json={"status": "failed", "data_gaps": [{"description_zh": "validation failed"}]},
        input_hash=f"input-{run_id}",
        artifact_version_hash=artifact_version_hash,
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        computed_at_ms=computed_at_ms,
        created_at_ms=computed_at_ms,
        updated_at_ms=computed_at_ms,
    )


def _insert_run(
    repo: NewsRepository,
    *,
    news_item_id: str,
    run_id: str,
    output_hash: str | None,
    artifact_version_hash: str = "artifact-1",
    execution_started: bool = True,
    status: str = "completed",
    outcome: str = "ready",
    started_at_ms: int = NOW_MS,
    finished_at_ms: int = NOW_MS + 10,
) -> dict[str, object]:
    return repo.insert_news_item_agent_run(
        run_id=run_id,
        news_item_id=news_item_id,
        provider="litellm",
        model="gpt-5-mini",
        backend="litellm_sdk",
        execution_trace_id=f"trace-{run_id}",
        workflow_name=NEWS_ITEM_BRIEF_WORKFLOW_NAME,
        agent_name=NEWS_ITEM_BRIEF_AGENT_NAME,
        lane=NEWS_ITEM_BRIEF_LANE,
        artifact_version_hash=artifact_version_hash,
        prompt_version=NEWS_ITEM_BRIEF_PROMPT_VERSION,
        schema_version=NEWS_ITEM_BRIEF_SCHEMA_VERSION,
        validator_version=NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
        guardrail_version=NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
        input_hash="input-1",
        output_hash=output_hash,
        execution_started=execution_started,
        status=status,
        outcome=outcome,
        request_json={},
        response_json={"summary_zh": run_id} if output_hash is not None else None,
        validation_errors_json=[],
        trace_metadata_json={},
        usage_json={},
        latency_ms=max(0, int(finished_at_ms) - int(started_at_ms)),
        started_at_ms=started_at_ms,
        finished_at_ms=finished_at_ms,
        created_at_ms=started_at_ms,
    )


def _insert_source_provider_and_item(
    repo: NewsRepository,
    *,
    suffix: str = "1",
    processed: bool = False,
    source_name: str = "Example",
    source_role: str = "observed_source",
    trust_tier: str = "standard",
    published_at_ms: int = NOW_MS,
    now_ms: int = NOW_MS,
) -> str:
    source_id = f"source-{suffix}"
    source_item_key = f"guid-{suffix}"
    repo.upsert_source(
        source_id=source_id,
        provider_type="rss",
        feed_url=f"https://example.com/{suffix}.xml",
        source_domain="example.com",
        source_name=source_name,
        source_role=source_role,
        trust_tier=trust_tier,
        refresh_interval_seconds=300,
        now_ms=now_ms,
    )
    fetch_run_id = repo.start_fetch_run(source_id=source_id, started_at_ms=now_ms)
    provider = repo.upsert_provider_item(
        source_id=source_id,
        fetch_run_id=fetch_run_id,
        source_item_key=source_item_key,
        canonical_url=f"https://example.com/{source_item_key}",
        payload_hash=f"payload-hash-{suffix}",
        raw_payload={"title": "SOL ETF filing"},
        fetched_at_ms=now_ms,
    )
    news = repo.upsert_canonical_news_item(
        provider_item_id=provider["provider_item_id"],
        canonical_url=f"https://example.com/{source_item_key}",
        title="SOL ETF filing",
        summary="Issuer files for a SOL ETF.",
        body_text="Issuer files for a SOL ETF.",
        language="en",
        published_at_ms=published_at_ms,
        fetched_at_ms=now_ms,
        content_hash=f"content-hash-{suffix}",
        title_fingerprint="sol etf filing",
        now_ms=now_ms,
    )
    if processed:
        _mark_item_processed_with_agent_state(repo, news_item_id=str(news["news_item_id"]), now_ms=now_ms)
    return str(news["news_item_id"])


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
    processed: bool,
) -> dict[str, object]:
    provider = repo.upsert_provider_item(
        source_id="opennews-news",
        fetch_run_id=repo.start_fetch_run(source_id="opennews-news", started_at_ms=now_ms),
        source_item_key=article_id,
        canonical_url=canonical_url,
        payload_hash=f"payload-{article_id}",
        raw_payload={"id": article_id, "link": canonical_url, "text": title},
        fetched_at_ms=now_ms,
        provider_article_id=article_id,
    )
    news = repo.upsert_canonical_news_item(
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
    if processed:
        _mark_item_processed_with_agent_state(repo, news_item_id=str(news["news_item_id"]), now_ms=now_ms)
    return news


def _mark_item_processed_with_agent_state(repo: NewsRepository, *, news_item_id: str, now_ms: int) -> None:
    repo.mark_item_processed(news_item_id=news_item_id, processed_at_ms=now_ms)
    repo.update_item_market_scope_and_agent_admission(
        news_item_id=news_item_id,
        market_scope=NewsMarketScope(
            scope=("crypto",),
            primary="crypto",
            status="classified",
            reason="fixture_crypto_market_scope",
            basis={"source": "integration_fixture"},
        ),
        story_identity=NewsStoryIdentity(
            story_key=f"story:{news_item_id}",
            confidence="high",
            basis={"source": "integration_fixture"},
            version=NEWS_STORY_IDENTITY_VERSION,
        ),
        admission=NewsItemAgentAdmission(
            eligible=True,
            status="eligible",
            reason="fixture_agent_ready",
            representative_news_item_id=news_item_id,
            basis={"source": "integration_fixture"},
        ),
        now_ms=now_ms,
    )
