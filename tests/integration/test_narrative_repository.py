import time

from gmgn_twitter_intel.domains.evidence.interfaces import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.narrative_intel.repositories.narrative_repository import NarrativeRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def make_event(event_id: str) -> TwitterEvent:
    received_at_ms = int(time.time() * 1000)
    return TwitterEvent(
        event_id=event_id,
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_basic",
        ),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle="toly", name="toly", avatar=None, followers=100, tags=[]),
        content=Content(text="SOL breakout discussion", media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["toly"],
        raw={"id": event_id},
    )


def open_repo(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    return conn, evidence, NarrativeRepository(conn)


def test_migration_creates_narrative_read_model_tables(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = 'public'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "narrative_admissions",
        "narrative_model_runs",
        "token_mention_semantics",
        "token_discussion_digests",
    }.issubset(tables)


def test_admitted_radar_rows_query_matches_current_token_radar_schema(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_radar_rows'
                """
            ).fetchall()
        }
        rows = repo.admitted_radar_rows(
            window="5m",
            scope="all",
            limit=10,
            projection_version="token_radar_v3",
        )
    finally:
        conn.close()

    assert "rank_score" not in columns
    assert "factor_snapshot_json" in columns
    assert rows == []


def test_repository_enqueues_completes_and_hydrates_semantics(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        assert evidence.insert_event(make_event("event-1"), is_watched=True) is True
        source_rows = [
            {
                "event_id": "event-1",
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "text_clean": "SOL breakout discussion",
                "source_received_at_ms": 1_000,
            }
        ]

        enqueue = repo.enqueue_missing_mention_semantics(
            source_rows,
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=2_000,
        )
        due = repo.due_mentions_for_labeling(now_ms=2_001, limit=10)
        run = repo.record_narrative_model_run(
            {
                "stage": "mention_semantics",
                "provider": "test-provider",
                "model": "gpt-test",
                "schema_version": "narrative_intel_v1",
                "prompt_version": "mention_semantics_v1",
                "input_hash": "input-hash",
                "request_json": {"event_ids": ["event-1"]},
                "status": "done",
                "started_at_ms": 2_000,
                "finished_at_ms": 2_010,
                "latency_ms": 10,
            }
        )
        complete = repo.complete_mention_semantics_batch(
            run_id=run["run_id"],
            labels=[
                {
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "trade_stance": "bullish",
                    "attention_valence": "celebratory",
                    "claim_type": "price-action",
                    "evidence_type": "scanner-alert",
                    "semantic_confidence": 0.8,
                    "evidence_refs": [
                        {
                            "ref_id": "event:event-1",
                            "kind": "event",
                            "source_table": "events",
                            "event_id": "event-1",
                        }
                    ],
                    "raw_label": {"ok": True},
                }
            ],
            failures=[],
            now_ms=2_020,
        )
        hydrated = repo.semantics_for_posts(
            [{"event_id": "event-1", "target_type": "chain_token", "target_id": "solana:So111"}],
            schema_version="narrative_intel_v1",
        )
        context = repo.digest_context(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
            since_ms=0,
            max_mentions=10,
        )
    finally:
        conn.close()

    assert enqueue == {"inserted": 1, "existing": 0}
    assert [row["event_id"] for row in due] == ["event-1"]
    assert due[0]["text_clean"] == "SOL breakout discussion"
    assert complete["labeled"] == 1
    assert hydrated[("event-1", "chain_token", "solana:So111")]["trade_stance"] == "bullish"
    assert context["independent_author_count"] == 1
    assert context["mentions"][0]["text_clean"] == "SOL breakout discussion"


def test_replace_current_digest_supersedes_previous_current(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        first = repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "insufficient",
                "source_fingerprint": "source-1",
                "label_fingerprint": "labels-1",
                "data_gaps": [{"reason": "low_source_volume"}],
                "semantic_coverage": 0.0,
                "source_event_count": 1,
                "labeled_event_count": 0,
                "independent_author_count": 1,
            },
            now_ms=1_000,
        )
        second = repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "insufficient",
                "source_fingerprint": "source-2",
                "label_fingerprint": "labels-2",
                "data_gaps": [{"reason": "low_semantic_coverage"}],
                "semantic_coverage": 0.2,
                "source_event_count": 3,
                "labeled_event_count": 1,
                "independent_author_count": 2,
            },
            now_ms=2_000,
        )
        current = repo.current_digests_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:So111"}],
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
        )
        rows = conn.execute(
            """
            SELECT digest_id, is_current, superseded_at_ms
            FROM token_discussion_digests
            ORDER BY computed_at_ms ASC
            """
        ).fetchall()
    finally:
        conn.close()

    assert first["digest_id"] != second["digest_id"]
    assert current[("chain_token", "solana:So111")]["digest_id"] == second["digest_id"]
    assert rows[0]["is_current"] is False
    assert rows[0]["superseded_at_ms"] == 2_000
    assert rows[1]["is_current"] is True


def test_replace_current_digest_is_idempotent_for_same_digest(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    digest = {
        "target_type": "chain_token",
        "target_id": "solana:So111",
        "window": "24h",
        "scope": "matched",
        "schema_version": "narrative_intel_v1",
        "model_version": "deterministic",
        "status": "insufficient",
        "source_fingerprint": "source-1",
        "label_fingerprint": "labels-1",
        "data_gaps": [{"reason": "low_source_volume"}],
        "semantic_coverage": 0.0,
        "source_event_count": 1,
        "labeled_event_count": 0,
        "independent_author_count": 1,
    }
    try:
        first = repo.replace_current_digest(digest, now_ms=1_000)
        second = repo.replace_current_digest(digest, now_ms=2_000)
        rows = conn.execute(
            """
            SELECT digest_id, is_current, computed_at_ms, superseded_at_ms
            FROM token_discussion_digests
            """
        ).fetchall()
    finally:
        conn.close()

    assert second["digest_id"] == first["digest_id"]
    assert len(rows) == 1
    assert rows[0]["digest_id"] == first["digest_id"]
    assert rows[0]["is_current"] is True
    assert rows[0]["computed_at_ms"] == 2_000
    assert rows[0]["superseded_at_ms"] is None
