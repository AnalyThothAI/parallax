import time

from psycopg.types.json import Jsonb

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


def test_admitted_radar_rows_uses_latest_ready_projection_frontier(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-old-1", "event-old-2", "event-latest"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
            _insert_intent(conn, intent_id=f"intent-{event_id}", event_id=event_id, observed_at_ms=1_000)
        _insert_radar_coverage(
            conn,
            window="24h",
            scope="all",
            projection_version="token_radar_v3",
            computed_at_ms=1_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-old-1",
            event_id="event-old-1",
            intent_id="intent-event-old-1",
            target_id="asset:old:rank1",
            rank=1,
            computed_at_ms=1_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-old-2",
            event_id="event-old-2",
            intent_id="intent-event-old-2",
            target_id="asset:old:rank2",
            rank=2,
            computed_at_ms=1_000,
        )
        conn.execute(
            """
            UPDATE token_radar_projection_coverage
            SET computed_at_ms = 2_000,
                started_at_ms = 2_000,
                finished_at_ms = 2_000,
                updated_at_ms = 2_000
            WHERE projection_version = 'token_radar_v3'
              AND "window" = '24h'
              AND scope = 'all'
            """
        )
        _insert_radar_row(
            conn,
            row_id="radar-latest",
            event_id="event-latest",
            intent_id="intent-event-latest",
            target_id="asset:latest:rank10",
            rank=10,
            computed_at_ms=2_000,
        )
        conn.commit()

        rows = repo.admitted_radar_rows(
            window="24h",
            scope="all",
            limit=3,
            projection_version="token_radar_v3",
        )
    finally:
        conn.close()

    assert [row["computed_at_ms"] for row in rows] == [2_000]
    assert [row["target_id"] for row in rows] == ["asset:latest:rank10"]


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
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-1"],
                    "source_max_received_at_ms": 1_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                }
            ],
            now_ms=2_000,
        )

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
        conn.execute(
            """
            INSERT INTO narrative_admissions(
              admission_id, target_type, target_id, "window", scope, schema_version, status, reason,
              priority, last_radar_rank, last_rank_score, source_event_ids_json, source_fingerprint,
              source_max_received_at_ms, admitted_at_ms, last_seen_at_ms, updated_at_ms
            )
            VALUES (
              'admission-event-1', 'chain_token', 'solana:So111', '24h', 'matched',
              'narrative_intel_v1', 'admitted', 'unit_test', 1, 1, 90.0, %s,
              'source-fingerprint', 3_000, 3_000, 3_000, 3_000
            )
            """,
            (Jsonb(["event-1"]),),
        )
        conn.commit()
        context = repo.digest_context(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
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


def test_missing_source_rows_for_mention_semantics_excludes_existing_semantics(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-missing-1", "event-existing", "event-missing-2"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True

        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-existing",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "existing source",
                    "source_received_at_ms": 1_000,
                }
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=2_000,
        )

        admission = {
            "target_type": "chain_token",
            "target_id": "solana:So111",
            "source_event_ids_json": ["event-missing-1", "event-existing", "event-missing-2"],
        }
        missing_rows = repo.missing_source_rows_for_mention_semantics(
            admission,
            limit=10,
            schema_version="narrative_intel_v1",
        )
    finally:
        conn.close()

    assert {row["event_id"] for row in missing_rows} == {"event-missing-1", "event-missing-2"}
    assert all(row["target_id"] == "solana:So111" for row in missing_rows)


def test_complete_mention_semantics_targets_current_semantic_identity(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        assert evidence.insert_event(make_event("event-identity"), is_watched=True) is True
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-identity",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "SOL breakout discussion",
                    "text_fingerprint": "fingerprint-old",
                    "source_received_at_ms": 1_000,
                },
                {
                    "event_id": "event-identity",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "SOL breakout discussion updated",
                    "text_fingerprint": "fingerprint-current",
                    "source_received_at_ms": 2_000,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=2_000,
        )
        current = conn.execute(
            """
            SELECT semantic_id, schema_version, text_fingerprint
            FROM token_mention_semantics
            WHERE text_fingerprint = 'fingerprint-current'
            """
        ).fetchone()
        run = repo.record_narrative_model_run(
            {
                "stage": "mention_semantics",
                "provider": "test-provider",
                "model": "gpt-test",
                "schema_version": "narrative_intel_v1",
                "prompt_version": "mention_semantics_v1",
                "input_hash": "identity-input-hash",
                "request_json": {"event_ids": ["event-identity"]},
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
                    "semantic_id": current["semantic_id"],
                    "event_id": "event-identity",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "schema_version": current["schema_version"],
                    "text_fingerprint": current["text_fingerprint"],
                    "trade_stance": "bullish",
                    "attention_valence": "celebratory",
                    "claim_type": "price-action",
                    "evidence_type": "scanner-alert",
                    "semantic_confidence": 0.8,
                    "evidence_refs": [],
                    "raw_label": {"ok": True},
                }
            ],
            failures=[],
            now_ms=2_020,
        )
        rows = {
            row["text_fingerprint"]: row
            for row in conn.execute(
                """
                SELECT text_fingerprint, status, model_run_id
                FROM token_mention_semantics
                WHERE event_id = 'event-identity'
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert complete["labeled"] == 1
    assert rows["fingerprint-current"]["status"] == "labeled"
    assert rows["fingerprint-current"]["model_run_id"] == run["run_id"]
    assert rows["fingerprint-old"]["status"] == "queued"
    assert rows["fingerprint-old"]["model_run_id"] is None


def test_digest_context_counts_admission_source_set_without_semantics(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-source-1", "event-source-2", "event-source-3"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
        conn.execute(
            """
            INSERT INTO narrative_admissions(
              admission_id, target_type, target_id, "window", scope, schema_version, status, reason,
              priority, last_radar_rank, last_rank_score, source_event_ids_json, source_fingerprint,
              source_max_received_at_ms, admitted_at_ms, last_seen_at_ms, updated_at_ms
            )
            VALUES (
              'admission-source-set', 'chain_token', 'solana:So111', '24h', 'matched',
              'narrative_intel_v1', 'admitted', 'unit_test', 1, 1, 90.0, %s,
              'source-fingerprint', 3_000, 3_000, 3_000, 3_000
            )
            """,
            (Jsonb(["event-source-1", "event-source-2", "event-source-3"]),),
        )
        conn.commit()

        context = repo.digest_context(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
            max_mentions=10,
        )
    finally:
        conn.close()

    assert context["source_event_count"] == 3
    assert context["semantic_row_count"] == 0
    assert context["missing_semantic_count"] == 3
    assert context["pending_semantic_count"] == 0
    assert context["retryable_semantic_count"] == 0
    assert context["labeled_event_count"] == 0
    assert context["terminal_unavailable_count"] == 0
    assert context["semantic_rows"] == []


def test_due_mentions_for_labeling_filters_to_current_admitted_1h_sources(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        assert evidence.insert_event(make_event("event-1"), is_watched=True) is True
        assert evidence.insert_event(make_event("event-24h"), is_watched=True) is True
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-1"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-24h"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
            ],
            now_ms=2_000,
        )
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "1h source",
                    "source_received_at_ms": 2_000,
                },
                {
                    "event_id": "event-24h",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "legacy source",
                    "source_received_at_ms": 2_000,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=2_000,
        )

        due = repo.due_mentions_for_labeling(now_ms=2_001, limit=10, max_per_target=10, windows=("1h",))
    finally:
        conn.close()

    assert [row["event_id"] for row in due] == ["event-1"]


def test_digest_context_counts_missing_semantics_outside_prompt_limit(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    event_ids = [f"event-context-{index:02d}" for index in range(30)]
    try:
        for index, event_id in enumerate(event_ids):
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
            conn.execute(
                "UPDATE events SET received_at_ms = %s WHERE event_id = %s",
                (10_000 + index, event_id),
            )
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": event_ids,
                    "source_max_received_at_ms": 20_000,
                    "source_event_count": 30,
                    "independent_author_count": 1,
                }
            ],
            now_ms=20_000,
        )
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": event_id,
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "SOL breakout discussion",
                    "source_received_at_ms": 10_000 + index,
                }
                for index, event_id in enumerate(event_ids[:24])
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=20_100,
        )
        conn.execute(
            """
            UPDATE token_mention_semantics
            SET status = 'labeled',
                computed_at_ms = 20_200
            """
        )
        conn.commit()

        context = repo.digest_context(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
            max_mentions=10,
        )
    finally:
        conn.close()

    assert context["source_event_count"] == 30
    assert context["semantic_row_count"] == 24
    assert context["missing_semantic_count"] == 6
    assert context["labeled_event_count"] == 24
    assert context["prompt_mention_count"] == 10
    assert context["prompt_mention_limit"] == 10
    assert len(context["mentions"]) == 10


def test_due_digest_targets_filters_legacy_windows(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:OneHour",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-1h"],
                    "source_max_received_at_ms": 9_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Legacy",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-24h"],
                    "source_max_received_at_ms": 9_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
            ],
            now_ms=9_000,
        )
        conn.execute("UPDATE narrative_admissions SET next_digest_due_at_ms = 9_000")
        conn.commit()

        rows = repo.due_digest_targets(now_ms=10_000, limit=10, windows=("1h",))
    finally:
        conn.close()

    assert [row["window"] for row in rows] == ["1h"]
    assert [row["target_id"] for row in rows] == ["solana:OneHour"]


def test_digest_context_full_source_counts_ignore_digest_now_window_filter(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    old_ms = 1_000
    new_ms = 100_000_000
    try:
        for event_id, received_at_ms in [("event-older-than-window", old_ms), ("event-current", new_ms)]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
            conn.execute(
                "UPDATE events SET received_at_ms = %s WHERE event_id = %s",
                (received_at_ms, event_id),
            )
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-older-than-window", "event-current"],
                    "source_max_received_at_ms": new_ms,
                    "source_event_count": 2,
                    "independent_author_count": 1,
                }
            ],
            now_ms=new_ms,
        )
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-older-than-window",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "old source still in admission",
                    "source_received_at_ms": old_ms,
                },
                {
                    "event_id": "event-current",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "new source",
                    "source_received_at_ms": new_ms,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=new_ms,
        )
        conn.execute("UPDATE token_mention_semantics SET status = 'labeled', computed_at_ms = %s", (new_ms,))
        conn.commit()

        context = repo.digest_context(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
            max_mentions=10,
        )
    finally:
        conn.close()

    assert context["source_event_count"] == 2
    assert context["semantic_row_count"] == 2
    assert context["missing_semantic_count"] == 0
    assert {row["event_id"] for row in context["mentions"]} == {"event-older-than-window", "event-current"}


def test_semantic_coverage_counts_duplicate_text_fingerprints_once_per_source_row(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        assert evidence.insert_event(make_event("event-duplicate-semantic"), is_watched=True) is True
        admission = {
            "target_type": "chain_token",
            "target_id": "solana:So111",
            "window": "24h",
            "scope": "matched",
            "schema_version": "narrative_intel_v1",
            "source_event_ids_json": ["event-duplicate-semantic"],
        }
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-duplicate-semantic",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "same source old text",
                    "text_fingerprint": "fingerprint-old",
                    "source_received_at_ms": 1_000,
                },
                {
                    "event_id": "event-duplicate-semantic",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "same source updated text",
                    "text_fingerprint": "fingerprint-new",
                    "source_received_at_ms": 1_000,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=2_000,
        )
        conn.commit()

        coverage = repo.semantic_coverage_for_admission(admission)
        missing = repo.missing_semantic_count_for_admission(
            admission,
            schema_version="narrative_intel_v1",
        )
    finally:
        conn.close()

    assert coverage["source_event_count"] == 1
    assert coverage["semantic_row_count"] == 1
    assert missing == 0


def test_replace_current_digest_supersedes_previous_current(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-1"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 1,
                }
            ],
            now_ms=1_000,
        )
        admission_fingerprint = conn.execute(
            "SELECT source_fingerprint FROM narrative_admissions WHERE target_id = 'solana:So111'"
        ).fetchone()["source_fingerprint"]
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
                "source_fingerprint": admission_fingerprint,
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
    assert current[("chain_token", "solana:So111")]["status"] == "pending"
    assert current[("chain_token", "solana:So111")]["currentness"]["display_status"] == "not_ready"
    assert current[("chain_token", "solana:So111")]["data_gaps_json"] == [
        {"reason": "low_independent_author_count"}
    ]
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


def test_current_digests_returns_matching_fingerprint_digest(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        admission = repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-source"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                }
            ],
            now_ms=3_000,
        )
        source_fingerprint = conn.execute(
            "SELECT source_fingerprint FROM narrative_admissions WHERE admission_id IS NOT NULL"
        ).fetchone()["source_fingerprint"]
        digest = repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": source_fingerprint,
                "label_fingerprint": "labels-current",
                "semantic_coverage": 1.0,
                "source_event_count": 1,
                "labeled_event_count": 1,
                "independent_author_count": 1,
            },
            now_ms=3_100,
        )

        current = repo.current_digests_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:So111"}],
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
        )
    finally:
        conn.close()

    assert admission == {"upserted": 1, "seen": 1}
    assert current[("chain_token", "solana:So111")]["digest_id"] == digest["digest_id"]
    assert current[("chain_token", "solana:So111")]["status"] == "ready"
    assert current[("chain_token", "solana:So111")]["currentness"]["display_status"] == "current"


def test_current_narrative_snapshots_keep_last_ready_on_source_delta(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-a", "event-b"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 2,
                    "independent_author_count": 1,
                }
            ],
            now_ms=2_000,
        )
        ready_fingerprint = conn.execute(
            "SELECT source_fingerprint FROM narrative_admissions WHERE target_id = 'solana:So111'"
        ).fetchone()["source_fingerprint"]
        digest = repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "epoch_id": "epoch-ready",
                "epoch_policy_version": "token-narrative-epoch-v1",
                "source_event_ids": ["event-a", "event-b"],
                "source_fingerprint": ready_fingerprint,
                "label_fingerprint": "labels-ready",
                "source_window_end_ms": 2_000,
                "display_current_until_ms": 9_000,
                "semantic_coverage": 1.0,
                "source_event_count": 2,
                "labeled_event_count": 2,
                "independent_author_count": 1,
            },
            now_ms=2_100,
        )
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-a", "event-b", "event-c"],
                    "source_max_received_at_ms": 4_000,
                    "source_event_count": 3,
                    "independent_author_count": 2,
                }
            ],
            now_ms=4_000,
        )

        current = repo.current_narrative_snapshots_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:So111"}],
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
            now_ms=5_000,
        )
    finally:
        conn.close()

    row = current[("chain_token", "solana:So111")]
    assert row["digest_id"] == digest["digest_id"]
    assert row["status"] == "ready"
    assert row["currentness"]["display_status"] == "updating"
    assert row["currentness"]["delta_source_event_count"] == 1
    assert row["currentness"]["ready_source_event_count"] == 2
    assert row["currentness"]["current_source_event_count"] == 3


def test_current_narrative_snapshots_returns_unsupported_5m_without_insert(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "5m",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-5m"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                }
            ],
            now_ms=3_000,
        )
        before_count = conn.execute("SELECT COUNT(*) AS count FROM token_discussion_digests").fetchone()["count"]

        current = repo.current_narrative_snapshots_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:So111"}],
            window="5m",
            scope="matched",
            schema_version="narrative_intel_v1",
            now_ms=3_100,
        )
        after_count = conn.execute("SELECT COUNT(*) AS count FROM token_discussion_digests").fetchone()["count"]
    finally:
        conn.close()

    row = current[("chain_token", "solana:So111")]
    assert row["status"] == "pending"
    assert row["currentness"]["display_status"] == "unsupported_window"
    assert row["data_gaps_json"] == [{"reason": "narrative_not_supported_for_window"}]
    assert after_count == before_count


def test_latest_ready_digest_ignores_newer_status_digest(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": "ready-source",
                "label_fingerprint": "labels-ready",
                "semantic_coverage": 1.0,
                "source_event_count": 2,
                "labeled_event_count": 2,
                "independent_author_count": 1,
            },
            now_ms=2_000,
        )
        repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "insufficient",
                "source_fingerprint": "status-source",
                "label_fingerprint": "labels-status",
                "data_gaps": [{"reason": "low_semantic_coverage"}],
                "semantic_coverage": 0.2,
                "source_event_count": 3,
                "labeled_event_count": 1,
                "independent_author_count": 1,
            },
            now_ms=3_000,
        )

        ready = repo.latest_ready_digest_for_target(
            target_type="chain_token",
            target_id="solana:So111",
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
        )
    finally:
        conn.close()

    assert ready is not None
    assert ready["status"] == "ready"
    assert ready["source_fingerprint"] == "ready-source"


def test_replace_current_digest_persists_epoch_metadata(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        digest = repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "epoch_id": "epoch-1",
                "epoch_policy_version": "token-narrative-epoch-v1",
                "source_event_ids": ["event-a", "event-b"],
                "source_window_start_ms": 1_000,
                "source_window_end_ms": 2_000,
                "epoch_closed_at_ms": 2_100,
                "display_current_until_ms": 9_000,
                "refresh_reason": "material_delta_due",
                "source_fingerprint": "source-ready",
                "label_fingerprint": "labels-ready",
                "semantic_coverage": 1.0,
                "source_event_count": 2,
                "labeled_event_count": 2,
                "independent_author_count": 1,
            },
            now_ms=2_100,
        )
        row = conn.execute(
            """
            SELECT epoch_id, epoch_policy_version, source_event_ids_json, source_window_start_ms,
                   source_window_end_ms, epoch_closed_at_ms, display_current_until_ms, refresh_reason
            FROM token_discussion_digests
            WHERE digest_id = %s
            """,
            (digest["digest_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert row["epoch_id"] == "epoch-1"
    assert row["epoch_policy_version"] == "token-narrative-epoch-v1"
    assert row["source_event_ids_json"] == ["event-a", "event-b"]
    assert row["source_window_start_ms"] == 1_000
    assert row["source_window_end_ms"] == 2_000
    assert row["epoch_closed_at_ms"] == 2_100
    assert row["display_current_until_ms"] == 9_000
    assert row["refresh_reason"] == "material_delta_due"


def test_market_context_for_admission_reports_price_move_since_last_ready(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        _insert_market_tick(
            conn,
            tick_id="tick-ready",
            target_id="solana:So111",
            observed_at_ms=1_000,
            price_usd=1.00,
        )
        _insert_market_tick(
            conn,
            tick_id="tick-current",
            target_id="solana:So111",
            observed_at_ms=4_000,
            price_usd=1.25,
        )
        conn.commit()

        context = repo.market_context_for_admission(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "source_max_received_at_ms": 4_000,
            },
            last_ready_digest={"computed_at_ms": 1_000},
        )
    finally:
        conn.close()

    assert round(context["price_move_pct"], 2) == 25.0
    assert context["price_move_pct_since_ready"] == context["price_move_pct"]
    assert context["ready_tick_observed_at_ms"] == 1_000
    assert context["current_tick_observed_at_ms"] == 4_000


def test_current_digests_marks_suppressed_ready_digest_out_of_frontier(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "status": "suppressed",
                    "source_event_ids": ["event-source"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                }
            ],
            now_ms=3_000,
        )
        repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": "old-source",
                "label_fingerprint": "labels-current",
                "semantic_coverage": 1.0,
                "source_event_count": 1,
                "labeled_event_count": 1,
                "independent_author_count": 1,
            },
            now_ms=3_100,
        )

        current = repo.current_digests_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:So111"}],
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
        )
        persisted = conn.execute("SELECT COUNT(*) AS count FROM token_discussion_digests").fetchone()["count"]
    finally:
        conn.close()

    row = current[("chain_token", "solana:So111")]
    assert row["status"] == "ready"
    assert row["is_current"] is True
    assert row["currentness"]["display_status"] == "out_of_frontier"
    assert row["currentness"]["reason"] == "not_in_current_frontier"
    assert persisted == 1


def test_current_digests_returns_last_ready_when_fingerprint_mismatches(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-source-new"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                }
            ],
            now_ms=3_000,
        )
        repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": "old-source",
                "label_fingerprint": "labels-current",
                "semantic_coverage": 1.0,
                "source_event_count": 1,
                "labeled_event_count": 1,
                "independent_author_count": 1,
            },
            now_ms=3_100,
        )

        current = repo.current_digests_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:So111"}],
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
        )
    finally:
        conn.close()

    row = current[("chain_token", "solana:So111")]
    assert row["status"] == "ready"
    assert row["is_current"] is True
    assert row["source_fingerprint"] == "old-source"
    assert row["currentness"]["display_status"] == "updating"
    assert row["currentness"]["reason"] == "digest_updating"
    assert row["currentness"]["current_source_fingerprint"] != row["currentness"]["ready_source_fingerprint"]


def test_current_digests_returns_not_ready_without_admission_or_digest(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        current = repo.current_digests_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:So111"}],
            window="24h",
            scope="matched",
            schema_version="narrative_intel_v1",
        )
    finally:
        conn.close()

    row = current[("chain_token", "solana:So111")]
    assert row["status"] == "pending"
    assert row["is_current"] is False
    assert row["data_gaps_json"] == [{"reason": "no_ready_digest"}]
    assert row["currentness"]["display_status"] == "not_ready"


def test_due_mentions_for_labeling_limits_rows_per_target(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        hot_rows = []
        cold_rows = []
        for index in range(5):
            event_id = f"event-hot-{index}"
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
            hot_rows.append(
                {
                    "event_id": event_id,
                    "target_type": "chain_token",
                    "target_id": "solana:Hot",
                    "text_clean": "hot target",
                    "source_received_at_ms": 10_000 + index,
                }
            )
        for index in range(2):
            event_id = f"event-cold-{index}"
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
            cold_rows.append(
                {
                    "event_id": event_id,
                    "target_type": "chain_token",
                    "target_id": "solana:Cold",
                    "text_clean": "cold target",
                    "source_received_at_ms": 9_000 + index,
                }
            )
        repo.enqueue_missing_mention_semantics(
            hot_rows + cold_rows,
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=20_000,
        )
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Hot",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": [row["event_id"] for row in hot_rows],
                    "source_max_received_at_ms": 10_004,
                    "source_event_count": len(hot_rows),
                    "independent_author_count": len(hot_rows),
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Cold",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": [row["event_id"] for row in cold_rows],
                    "source_max_received_at_ms": 9_001,
                    "source_event_count": len(cold_rows),
                    "independent_author_count": len(cold_rows),
                },
            ],
            now_ms=20_000,
        )

        due = repo.due_mentions_for_labeling(now_ms=20_001, limit=6, max_per_target=3)
    finally:
        conn.close()

    by_target = {}
    for row in due:
        by_target[row["target_id"]] = by_target.get(row["target_id"], 0) + 1
    assert by_target == {"solana:Hot": 3, "solana:Cold": 2}


def test_cleanup_narrative_current_hard_cut_reports_exact_counts(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-current", "event-obsolete", "event-labeled"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Current",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-current"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Suppressed",
                    "window": "24h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "status": "suppressed",
                    "source_event_ids": ["event-obsolete"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                },
            ],
            now_ms=3_000,
        )
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-current",
                    "target_type": "chain_token",
                    "target_id": "solana:Current",
                    "text_clean": "current source",
                    "source_received_at_ms": 3_000,
                },
                {
                    "event_id": "event-obsolete",
                    "target_type": "chain_token",
                    "target_id": "solana:Obsolete",
                    "text_clean": "obsolete queued source",
                    "source_received_at_ms": 2_000,
                },
                {
                    "event_id": "event-labeled",
                    "target_type": "chain_token",
                    "target_id": "solana:Obsolete",
                    "text_clean": "obsolete labeled source",
                    "source_received_at_ms": 2_000,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=3_100,
        )
        conn.execute("UPDATE token_mention_semantics SET status = 'labeled' WHERE event_id = 'event-labeled'")
        repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:Current",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": "old-current",
                "label_fingerprint": "labels-mismatch",
                "semantic_coverage": 1.0,
                "source_event_count": 1,
                "labeled_event_count": 1,
                "independent_author_count": 1,
            },
            now_ms=3_200,
        )
        repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:Suppressed",
                "window": "24h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": "suppressed-source",
                "label_fingerprint": "labels-suppressed",
                "semantic_coverage": 1.0,
                "source_event_count": 1,
                "labeled_event_count": 1,
                "independent_author_count": 1,
            },
            now_ms=3_300,
        )
        conn.commit()

        result = repo.cleanup_narrative_current_hard_cut(schema_version="narrative_intel_v1", now_ms=4_000)
        semantics = {
            row["event_id"]: row["status"]
            for row in conn.execute("SELECT event_id, status FROM token_mention_semantics").fetchall()
        }
        digest_rows = {
            row["target_id"]: row
            for row in conn.execute(
                """
                SELECT target_id, status, is_current, superseded_at_ms
                FROM token_discussion_digests
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert result == {
        "deleted_obsolete_pending_semantics": 1,
        "stale_suppressed_digests": 1,
        "fingerprint_mismatch_digests_preserved": 1,
    }
    assert semantics == {"event-current": "queued", "event-labeled": "labeled"}
    assert digest_rows["solana:Suppressed"]["status"] == "stale"
    assert digest_rows["solana:Suppressed"]["is_current"] is False
    assert digest_rows["solana:Suppressed"]["superseded_at_ms"] == 4_000
    assert digest_rows["solana:Current"]["status"] == "ready"
    assert digest_rows["solana:Current"]["is_current"] is True


def _insert_intent(conn, *, intent_id: str, event_id: str, observed_at_ms: int) -> None:
    conn.execute(
        """
        INSERT INTO token_intents(
          intent_id, event_id, intent_key, construction_policy, intent_status,
          intent_confidence, created_at_ms, updated_at_ms
        )
        VALUES (%s, %s, %s, 'unit-test', 'active', 1.0, %s, %s)
        """,
        (intent_id, event_id, f"intent-key:{intent_id}", observed_at_ms, observed_at_ms),
    )


def _insert_radar_coverage(
    conn,
    *,
    window: str,
    scope: str,
    projection_version: str,
    computed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_radar_projection_coverage(
          projection_version, "window", scope, status, reason, source_rows, row_count,
          computed_at_ms, started_at_ms, finished_at_ms, error, updated_at_ms
        )
        VALUES (%s, %s, %s, 'ready', NULL, 1, 1, %s, %s, %s, NULL, %s)
        """,
        (projection_version, window, scope, computed_at_ms, computed_at_ms, computed_at_ms, computed_at_ms),
    )


def _insert_radar_row(
    conn,
    *,
    row_id: str,
    event_id: str,
    intent_id: str,
    target_id: str,
    rank: int,
    computed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_radar_rows(
          row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
          lane, rank, intent_id, event_id, intent_json, asset_json, primary_venue_json,
          attention_json, resolution_json, market_json, score_json, decision, data_health_json,
          source_event_ids_json, created_at_ms, target_type, target_id, pricefeed_id, target_json,
          price_json, factor_snapshot_json, factor_version
        )
        VALUES (
          %s, 'token_radar_v3', '24h', 'all', %s, %s,
          'all', %s, %s, %s, %s, %s, NULL,
          %s, %s, %s, %s, 'watch', %s,
          %s, %s, 'Asset', %s, NULL, %s,
          %s, %s, 'token_factor_snapshot_v3_social_attention'
        )
        """,
        (
            row_id,
            computed_at_ms,
            computed_at_ms,
            rank,
            intent_id,
            event_id,
            Jsonb({"intent_id": intent_id}),
            Jsonb({}),
            Jsonb({}),
            Jsonb({}),
            Jsonb({}),
            Jsonb({"rank_score": max(0, 100 - rank)}),
            Jsonb({"alpha": "ready"}),
            Jsonb([event_id]),
            computed_at_ms,
            target_id,
            Jsonb({"target_id": target_id}),
            Jsonb({}),
            Jsonb({"composite": {"rank_score": max(0, 100 - rank)}}),
        ),
    )


def _insert_market_tick(
    conn,
    *,
    tick_id: str,
    target_id: str,
    observed_at_ms: int,
    price_usd: float,
) -> None:
    conn.execute(
        """
        INSERT INTO market_ticks(
          tick_id, target_type, target_id, chain, token_address, source_tier, source_provider,
          observed_at_ms, received_at_ms, price_usd, created_at_ms
        )
        VALUES (
          %s, 'chain_token', %s, 'solana', 'So111', 'tier2_poll', 'okx_dex_rest',
          %s, %s, %s, %s
        )
        """,
        (tick_id, target_id, observed_at_ms, observed_at_ms, price_usd, observed_at_ms),
    )
