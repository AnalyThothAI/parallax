from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.social_enrichment.repositories.social_event_extraction_repository import (
    SocialEventExtractionRepository,
)
from gmgn_twitter_intel.domains.token_intel.repositories.intent_resolution_repository import (
    IntentResolutionRepository,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_intent_repository import TokenIntentRepository
from gmgn_twitter_intel.domains.watchlist_intel.repositories.watchlist_intel_repository import (
    WatchlistIntelRepository,
)
from gmgn_twitter_intel.domains.watchlist_intel.types import encode_watchlist_timeline_cursor
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_watchlist_summary_job_claim_lifecycle(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = WatchlistIntelRepository(conn)
        repo.enqueue_handle_summary_job(
            handle="Toly",
            next_run_at_ms=1_000,
            pending_signal_count=3,
            trigger_reason="signal_threshold",
            max_attempts=2,
            commit=True,
        )

        claimed = repo.claim_next_summary_job(now_ms=1_000, lease_ms=500)
        second = repo.claim_next_summary_job(now_ms=1_100, lease_ms=500)
        stale = repo.claim_next_summary_job(now_ms=1_501, lease_ms=500)
        repo.mark_summary_job_failed(stale, "model_timeout", now_ms=1_600)
        dead = repo.pending_summary_job("toly")
    finally:
        conn.close()

    assert claimed is not None
    assert claimed["handle"] == "toly"
    assert claimed["attempt_count"] == 1
    assert second is None
    assert stale is not None
    assert stale["attempt_count"] == 2
    assert dead is not None
    assert dead["status"] == "dead"
    assert dead["last_error"] == "model_timeout"


def test_watchlist_summary_completion_requires_current_lease_token(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = WatchlistIntelRepository(conn)
        repo.enqueue_handle_summary_job(
            handle="toly",
            next_run_at_ms=1_000,
            pending_signal_count=3,
            trigger_reason="signal_threshold",
            max_attempts=3,
            commit=True,
        )
        first_claim = repo.claim_next_summary_job(now_ms=1_000, lease_ms=500)
        second_claim = repo.claim_next_summary_job(now_ms=1_501, lease_ms=500)

        stale_complete = repo.complete_handle_summary(
            job=first_claim,
            handle="toly",
            summary=_summary_payload("stale summary"),
            run=_run_payload("run-stale", status="succeeded"),
        )
        still_pending = repo.pending_summary_job("toly")
        current_complete = repo.complete_handle_summary(
            job=second_claim,
            handle="toly",
            summary=_summary_payload("current summary"),
            run=_run_payload("run-current", status="succeeded"),
        )
        finished_job = repo.pending_summary_job("toly")
        summary = repo.get_handle_summary("toly")
    finally:
        conn.close()

    assert stale_complete is None
    assert still_pending is not None
    assert still_pending["status"] == "running"
    assert still_pending["attempt_count"] == 2
    assert current_complete is not None
    assert finished_job is None
    assert summary is not None
    assert summary["summary_zh"] == "current summary"


def test_watchlist_timeline_pages_all_and_signal_events(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        social_events = SocialEventExtractionRepository(conn)
        repo = WatchlistIntelRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="toly", text="$SOL launch", received_at_ms=1_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-2", author_handle="toly", text="gm", received_at_ms=2_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-3", author_handle="toly", text="$BONK meta", received_at_ms=3_000),
            is_watched=True,
        )
        _extract_signal(social_events, event_id="event-1", received_at_ms=1_000, summary_zh="SOL 讨论升温。")
        _extract_signal(social_events, event_id="event-3", received_at_ms=3_000, summary_zh="BONK 叙事变强。")
        _insert_token_resolution(conn, event_id="event-3", symbol="BONK")

        first_page = repo.timeline(handle="toly", scope="all", cursor=None, limit=2)
        signal_page = repo.timeline(handle="toly", scope="signal", cursor=None, limit=10)
        cursor = encode_watchlist_timeline_cursor(received_at_ms=2_000, event_id="event-2")
        second_page = repo.timeline(handle="toly", scope="all", cursor=cursor, limit=10)
    finally:
        conn.close()

    assert [item["event_id"] for item in first_page["items"]] == ["event-3", "event-2"]
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]
    assert [item["event_id"] for item in signal_page["items"]] == ["event-3", "event-1"]
    assert signal_page["items"][0]["social_event"]["summary_zh"] == "BONK 叙事变强。"
    assert signal_page["items"][0]["token_resolutions"][0]["target_id"] == "cex_token:BONK"
    assert second_page["items"][0]["event_id"] == "event-1"


def test_watchlist_handle_overview_separates_resolved_tokens_from_candidate_mentions(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        social_events = SocialEventExtractionRepository(conn)
        repo = WatchlistIntelRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="marionawfal", text="$ALOY #macro", received_at_ms=1_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-2", author_handle="marionawfal", text="$BONK #solana", received_at_ms=2_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-3", author_handle="marionawfal", text="source stream #fed", received_at_ms=3_000),
            is_watched=True,
        )
        _extract_signal(
            social_events,
            event_id="event-1",
            author_handle="marionawfal",
            received_at_ms=1_000,
            summary_zh="ALOY 讨论升温。",
            token_candidates=[{"symbol": "ALOY", "evidence": "$ALOY", "confidence": 0.8}],
            anchor_terms=[{"term": "macro", "role": "topic", "evidence": "#macro"}],
        )
        _extract_signal(
            social_events,
            event_id="event-2",
            author_handle="marionawfal",
            received_at_ms=2_000,
            summary_zh="BONK 已解析为交易标的。",
            token_candidates=[{"symbol": "BONK", "evidence": "$BONK", "confidence": 0.9}],
            anchor_terms=[{"term": "solana", "role": "ecosystem", "evidence": "#solana"}],
        )
        _insert_token_resolution(conn, event_id="event-2", symbol="BONK")

        overview = repo.handle_overview(handle="MarionAwfal", scope="signal", since_ms=0)
        all_overview = repo.handle_overview(handle="marionawfal", scope="all", since_ms=0)
    finally:
        conn.close()

    assert overview["query"]["handle"] == "marionawfal"
    assert overview["query"]["scope"] == "signal"
    assert overview["metrics"]["source_event_count"] == 2
    assert overview["metrics"]["signal_event_count"] == 2
    assert overview["metrics"]["candidate_mention_count"] == 1
    assert overview["metrics"]["resolved_token_count"] == 1
    assert overview["candidate_mention_clusters"][0]["label"] == "$ALOY"
    assert overview["candidate_mention_clusters"][0]["source"] == "social_event_candidates"
    assert overview["resolved_token_clusters"][0]["label"] == "$BONK"
    assert overview["resolved_token_clusters"][0]["kind"] == "resolved_token"
    assert overview["resolved_token_clusters"][0]["target_type"] == "CexToken"
    assert "candidate_mentions_unresolved" in overview["risk_notes"]
    assert all_overview["metrics"]["source_event_count"] == 3
    assert any(cluster["label"] == "#fed" for cluster in all_overview["narrative_clusters"])


def test_watchlist_handle_overview_metrics_are_not_limited_by_cluster_sample(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        social_events = SocialEventExtractionRepository(conn)
        repo = WatchlistIntelRepository(conn)
        for index, symbol in enumerate(("ONE", "TWO", "THREE"), start=1):
            event_id = f"event-{index}"
            evidence.insert_event(
                make_event(
                    event_id,
                    author_handle="marionawfal",
                    text=f"${symbol} #macro",
                    received_at_ms=index * 1_000,
                ),
                is_watched=True,
            )
            _extract_signal(
                social_events,
                event_id=event_id,
                author_handle="marionawfal",
                received_at_ms=index * 1_000,
                summary_zh=f"{symbol} 讨论升温。",
                token_candidates=[{"symbol": symbol, "evidence": f"${symbol}", "confidence": 0.8}],
                anchor_terms=[{"term": "macro", "role": "topic", "evidence": "#macro"}],
            )

        overview = repo.handle_overview(handle="marionawfal", scope="signal", since_ms=0, limit=2)
    finally:
        conn.close()

    assert overview["metrics"]["source_event_count"] == 3
    assert overview["metrics"]["signal_event_count"] == 3
    assert overview["metrics"]["candidate_mention_count"] == 3
    assert len(overview["candidate_mention_clusters"]) == 2
    assert overview["clusters_truncated"] is True


def test_watchlist_handles_overview_returns_configured_handle_rows(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        social_events = SocialEventExtractionRepository(conn)
        repo = WatchlistIntelRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="marionawfal", text="$ALOY", received_at_ms=1_000),
            is_watched=True,
        )
        evidence.insert_event(
            make_event("event-2", author_handle="toly", text="$SOL", received_at_ms=2_000),
            is_watched=True,
        )
        _extract_signal(
            social_events,
            event_id="event-1",
            author_handle="marionawfal",
            received_at_ms=1_000,
            summary_zh="ALOY 讨论升温。",
        )
        repo.upsert_handle_summary(
            handle="marionawfal",
            generated_at_ms=2_500,
            input_window_start_ms=0,
            input_window_end_ms=2_500,
            input_event_count=1,
            signal_count_at_generation=1,
            model="test-model",
            summary_zh="Marion 聚焦 ALOY。",
            topics=[],
            raw_response={"ok": True},
            commit=True,
        )

        rows = repo.handles_overview(handles=("marionawfal", "toly"), since_ms=0)
    finally:
        conn.close()

    by_handle = {row["handle"]: row for row in rows}
    assert set(by_handle) == {"marionawfal", "toly"}
    assert by_handle["marionawfal"]["last_source_event_at_ms"] == 1_000
    assert by_handle["marionawfal"]["recent_source_event_count"] == 1
    assert by_handle["marionawfal"]["recent_signal_event_count"] == 1
    assert by_handle["marionawfal"]["total_signal_event_count"] == 1
    assert by_handle["marionawfal"]["summary_status"] == "ready"
    assert by_handle["toly"]["last_source_event_at_ms"] == 2_000
    assert by_handle["toly"]["recent_signal_event_count"] == 0
    assert by_handle["toly"]["summary_status"] == "not_ready"


def test_watchlist_timeline_uses_lower_author_cursor_index(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="Toly", text="$SOL launch", received_at_ms=1_000),
            is_watched=True,
        )
        conn.execute("SET enable_seqscan = off")
        plan_rows = conn.execute(
            """
            EXPLAIN (COSTS OFF)
            SELECT e.event_id
            FROM events e
            WHERE lower(e.author_handle) = %s
            ORDER BY e.received_at_ms DESC, e.event_id DESC
            LIMIT 30
            """,
            ("toly",),
        ).fetchall()
    finally:
        conn.close()

    plan = "\n".join(_first_column(row) for row in plan_rows)
    assert "idx_events_author_received_event_lower_desc" in plan


def test_watchlist_summary_read_model_and_signal_counts(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        social_events = SocialEventExtractionRepository(conn)
        repo = WatchlistIntelRepository(conn)
        evidence.insert_event(
            make_event("event-1", author_handle="toly", text="$SOL launch", received_at_ms=1_000),
            is_watched=True,
        )
        _extract_signal(social_events, event_id="event-1", received_at_ms=1_000, summary_zh="SOL 讨论升温。")

        assert repo.count_signal_events_total("TOLY") == 1
        inputs = repo.signal_events_for_summary(handle="toly", since_ms=0, limit=10)
        repo.upsert_handle_summary(
            handle="toly",
            generated_at_ms=2_000,
            input_window_start_ms=0,
            input_window_end_ms=2_000,
            input_event_count=1,
            signal_count_at_generation=1,
            model="test-model",
            summary_zh="Toly 的核心话题集中在 SOL。",
            topics=[{"title": "SOL", "description": "SOL 生态讨论升温。", "event_count": 1}],
            raw_response={"ok": True},
            commit=True,
        )
        summary = repo.get_handle_summary("toly")
    finally:
        conn.close()

    assert inputs[0]["summary_zh"] == "SOL 讨论升温。"
    assert summary is not None
    assert summary["summary_zh"] == "Toly 的核心话题集中在 SOL。"
    assert summary["topics"][0]["title"] == "SOL"


def _extract_signal(
    social_events: SocialEventExtractionRepository,
    *,
    event_id: str,
    received_at_ms: int,
    summary_zh: str,
    author_handle: str = "toly",
    token_candidates: list[dict] | None = None,
    anchor_terms: list[dict] | None = None,
) -> None:
    social_events.upsert_extraction(
        extraction_id=f"extract-{event_id}",
        event_id=event_id,
        run_id=None,
        author_handle=author_handle,
        received_at_ms=received_at_ms,
        schema_version="social-event-v2",
        model_version="test-model",
        event_type="meme_phrase_seed",
        source_action="posted",
        subject="topic",
        direction_hint="attention_positive",
        attention_mechanism="meme_phrase",
        impact_hint=0.7,
        semantic_novelty_hint=0.6,
        confidence=0.85,
        is_signal_event=True,
        anchor_terms=anchor_terms or [{"term": "topic", "role": "topic", "evidence": "topic"}],
        token_candidates=token_candidates or [{"symbol": "SOL", "evidence": "$SOL", "confidence": 0.8}],
        semantic_risks=["public_stream_coverage"],
        summary_zh=summary_zh,
        raw_response={"ok": True},
    )


def _insert_token_resolution(conn, *, event_id: str, symbol: str) -> None:
    TokenIntentRepository(conn).insert(
        {
            "intent_id": f"intent-{event_id}",
            "event_id": event_id,
            "intent_key": f"symbol:{symbol}",
            "construction_policy": "test",
            "primary_evidence_id": None,
            "display_symbol": symbol,
            "display_name": symbol,
            "chain_hint": None,
            "address_hint": None,
            "intent_status": "resolved",
            "intent_confidence": 0.9,
            "created_at_ms": 1_000,
            "updated_at_ms": 1_000,
        },
        commit=False,
    )
    IntentResolutionRepository(conn).insert_resolution(
        {
            "intent_id": f"intent-{event_id}",
            "event_id": event_id,
            "resolution_status": "RESOLVED",
            "resolver_policy_version": "test",
            "target_type": "CexToken",
            "target_id": f"cex_token:{symbol}",
            "pricefeed_id": f"pf:{symbol}",
            "reason_codes": ["test"],
            "candidate_ids": [symbol],
            "lookup_keys": [f"symbol:{symbol}"],
            "decision_time_ms": 1_100,
            "created_at_ms": 1_100,
        },
        commit=True,
    )


def _summary_payload(summary_zh: str) -> dict:
    return {
        "handle": "toly",
        "generated_at_ms": 2_000,
        "input_window_start_ms": 1_000,
        "input_window_end_ms": 2_000,
        "input_event_count": 1,
        "signal_count_at_generation": 1,
        "model": "test-model",
        "summary_zh": summary_zh,
        "topics": [],
        "raw_response": {"summary_zh": summary_zh},
    }


def _run_payload(run_id: str, *, status: str) -> dict:
    return {
        "run_id": run_id,
        "handle": "toly",
        "status": status,
        "model": "test-model",
        "request_json": {"handle": "toly"},
        "response_json": {"ok": True} if status == "succeeded" else None,
        "input_event_count": 1,
        "usage_json": {},
        "error": None,
        "started_at_ms": 2_000,
        "finished_at_ms": 2_100,
    }


def _first_column(row) -> str:
    if isinstance(row, dict):
        return str(next(iter(row.values())))
    return str(row[0])
