from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel._constants import (
    NEWS_ITEM_BRIEF_GUARDRAIL_VERSION,
    NEWS_ITEM_BRIEF_PROMPT_VERSION,
    NEWS_ITEM_BRIEF_SCHEMA_VERSION,
    NEWS_ITEM_BRIEF_VALIDATOR_VERSION,
)
from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository
from gmgn_twitter_intel.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_AGENT_NAME,
    NEWS_ITEM_BRIEF_LANE,
    NEWS_ITEM_BRIEF_WORKFLOW_NAME,
    NewsItemBriefPayload,
    default_news_item_brief_agent_config,
)
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_779_000_000_000
ARTIFACT_HASH = "artifact-hash-brief-v1"


def test_list_items_for_brief_selects_processed_missing_brief_only(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = NewsRepository(conn)
        processed_id = _insert_source_provider_and_item(repo, suffix="processed", processed=True)
        raw_id = _insert_source_provider_and_item(repo, suffix="raw", processed=False)

        rows = _list_items_for_brief(repo)
    finally:
        conn.close()

    selected_ids = [row["item"]["news_item_id"] for row in rows]
    assert selected_ids == [processed_id]
    assert raw_id not in selected_ids


def test_list_items_for_brief_prioritizes_newest_missing_briefs_for_front_page(tmp_path) -> None:
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

        rows = _list_items_for_brief(repo, limit=2, now_ms=NOW_MS + 1_000)
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [newest_id, middle_id]
    assert oldest_id not in [row["item"]["news_item_id"] for row in rows]


def test_list_items_for_brief_deprioritizes_cooled_backpressure_retry_for_same_publish_time(tmp_path) -> None:
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

        rows = _list_items_for_brief(
            repo,
            limit=2,
            now_ms=NOW_MS + 1_000,
            backpressure_cooldown_ms=100,
        )
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [fresh_id, cooled_backpressure_id]


def test_list_items_for_brief_skips_fresh_current_and_selects_fact_changed_current(tmp_path) -> None:
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
                {
                    "fact_candidate_id": "fact-changed",
                    "news_item_id": changed_id,
                    "event_type": "listing",
                    "claim": "SOL spot ETF filing updated with official docket.",
                    "realis": "reported_claim",
                    "evidence_quote": "updated with official docket",
                    "evidence_span_start": 0,
                    "evidence_span_end": 28,
                    "source_role": "observed_source",
                    "required_slots_json": {"asset": True},
                    "affected_targets_json": [{"target_type": "asset", "target_id": "asset:sol"}],
                    "validation_status": "accepted",
                    "rejection_reasons_json": [],
                    "extraction_method": "test",
                    "policy_version": "test",
                    "created_at_ms": NOW_MS + 200,
                    "updated_at_ms": NOW_MS + 200,
                }
            ],
        )

        rows = _list_items_for_brief(repo)
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [changed_id]
    assert rows[0]["fact_candidates"][0]["fact_candidate_id"] == "fact-changed"


def test_list_items_for_brief_backpressure_cooldown_and_attempt_count_are_separate(tmp_path) -> None:
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
        recent_rows = _list_items_for_brief(repo, now_ms=NOW_MS + 30, backpressure_cooldown_ms=100)
        cooled_rows = _list_items_for_brief(repo, now_ms=NOW_MS + 200, backpressure_cooldown_ms=100, max_attempts=1)
    finally:
        conn.close()

    assert recent_rows == []
    assert [row["item"]["news_item_id"] for row in cooled_rows] == [news_item_id]
    assert cooled_rows[0]["latest_run"]["run_id"] == "run-recent-backpressure"
    assert cooled_rows[0]["latest_run"]["execution_started"] is False


def test_list_items_for_brief_retries_failed_current_until_started_attempt_limit(tmp_path) -> None:
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

        rows = _list_items_for_brief(repo, max_attempts=2)
    finally:
        conn.close()

    assert [row["item"]["news_item_id"] for row in rows] == [retry_id]


def test_list_items_for_brief_payload_contains_packet_inputs_and_audit_rows(tmp_path) -> None:
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
                {
                    "mention_id": "mention-payload",
                    "news_item_id": news_item_id,
                    "entity_id": None,
                    "observed_symbol": "SOL",
                    "chain_id": None,
                    "address": None,
                    "resolution_status": "known_symbol",
                    "target_type": "asset",
                    "target_id": "asset:sol",
                    "display_symbol": "SOL",
                    "display_name": "Solana",
                    "reason_codes_json": ["confirmed_symbol"],
                    "candidate_targets_json": [],
                    "evidence_strength": "strong",
                    "confidence": 0.9,
                    "created_at_ms": NOW_MS + 1,
                }
            ],
        )
        repo.create_story_from_item(
            story_id="story-payload",
            item={"title": "SOL ETF filing", "canonical_url": "https://example.com/payload", "published_at_ms": NOW_MS},
            policy_version="test",
            now_ms=NOW_MS,
        )
        repo.add_story_member(
            story_id="story-payload",
            news_item_id=news_item_id,
            relation="representative",
            match_reason="test",
            match_score=1.0,
            now_ms=NOW_MS + 2,
        )

        row = _list_items_for_brief(repo)[0]
        packet = build_news_item_brief_input_packet(
            item=row["item"],
            story=row["story"],
            token_mentions=row["token_mentions"],
            fact_candidates=row["fact_candidates"],
            story_members=row["story_members"],
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
    assert row["source_updated_at_ms"] == NOW_MS + 2
    assert row["story"]["story_id"] == "story-payload"
    assert row["story_members"][0]["news_item_id"] == news_item_id
    assert packet.news_item.source.source_name == "Payload Source"
    assert packet.token_lanes[0].mention_id == "mention-payload"


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
            affected_assets=[
                {
                    "symbol": "SOL",
                    "name": "Solana",
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
            provider="openai",
            model="gpt-5-mini",
            sdk_trace_id="trace-news-brief-1",
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
            trace_metadata_json={"sdk_trace_id": "trace-news-brief-1", "attempt": 1},
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

    assert run["sdk_trace_id"] == "trace-news-brief-1"
    assert run["request_json"]["gateway"]["lane"] == NEWS_ITEM_BRIEF_LANE
    assert run["response_json"]["summary_zh"] == "ETF filing lifts SOL attention."
    assert run["usage_json"] == {"input_tokens": 321, "output_tokens": 123}
    assert current["status"] == "ready"
    assert current["brief_json"]["summary_zh"] == "ETF filing lifts SOL attention."
    assert fetched == current


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


def _list_items_for_brief(
    repo: NewsRepository,
    *,
    limit: int = 10,
    now_ms: int = NOW_MS + 1_000,
    backpressure_cooldown_ms: int = 500,
    artifact_version_hash: str = ARTIFACT_HASH,
    max_attempts: int = 3,
) -> list[dict[str, object]]:
    return repo.list_items_for_brief(
        limit=limit,
        now_ms=now_ms,
        backpressure_cooldown_ms=backpressure_cooldown_ms,
        artifact_version_hash=artifact_version_hash,
        max_attempts=max_attempts,
    )


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
        provider="openai",
        model="gpt-5-mini",
        sdk_trace_id=f"trace-{run_id}",
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
        raw_payload_json={"title": "SOL ETF filing"},
        fetched_at_ms=now_ms,
    )
    news = repo.upsert_news_item(
        provider_item_id=provider["provider_item_id"],
        source_id=source_id,
        source_domain="example.com",
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
        repo.mark_item_processed(news_item_id=str(news["news_item_id"]), processed_at_ms=now_ms)
    return str(news["news_item_id"])
