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
            since_ms=0,
            max_mentions=10,
        )
    finally:
        conn.close()

    assert context["source_event_count"] == 3
    assert context["labeled_event_count"] == 0
    assert context["semantic_rows"] == []


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


def test_cleanup_current_backlog_preserves_sources_current_in_other_windows(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-1h", "event-24h", "event-obsolete"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True

        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:OneHour",
                    "window": "1h",
                    "scope": "all",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-1h"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Day",
                    "window": "24h",
                    "scope": "all",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-24h"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 1,
                },
            ],
            now_ms=2_000,
        )
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-1h",
                    "target_type": "chain_token",
                    "target_id": "solana:OneHour",
                    "text_clean": "one hour source",
                    "source_received_at_ms": 2_000,
                },
                {
                    "event_id": "event-24h",
                    "target_type": "chain_token",
                    "target_id": "solana:Day",
                    "text_clean": "day source",
                    "source_received_at_ms": 2_000,
                },
                {
                    "event_id": "event-obsolete",
                    "target_type": "chain_token",
                    "target_id": "solana:Old",
                    "text_clean": "obsolete source",
                    "source_received_at_ms": 2_000,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=2_100,
        )
        conn.execute(
            """
            UPDATE token_mention_semantics
            SET status = 'retryable_error',
                error = 'transient',
                next_retry_at_ms = 9_999_999
            WHERE event_id = 'event-1h'
            """
        )
        conn.commit()

        result = repo.cleanup_current_backlog(
            schema_version="narrative_intel_v1",
            window="1h",
            scope="all",
            now_ms=3_000,
        )
        rows = {
            row["event_id"]: row["status"]
            for row in conn.execute(
                """
                SELECT event_id, status
                FROM token_mention_semantics
                ORDER BY event_id
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert result["deleted_obsolete_semantics"] == 1
    assert result["reset_retryable_semantics"] == 1
    assert rows == {
        "event-1h": "queued",
        "event-24h": "queued",
    }


def test_prune_pending_mention_semantics_backlog_keeps_recent_per_target_rows(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-old", "event-mid", "event-new", "event-other"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-old",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "old source",
                    "source_received_at_ms": 1_000,
                },
                {
                    "event_id": "event-mid",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "mid source",
                    "source_received_at_ms": 3_000,
                },
                {
                    "event_id": "event-new",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "new source",
                    "source_received_at_ms": 4_000,
                },
                {
                    "event_id": "event-other",
                    "target_type": "chain_token",
                    "target_id": "solana:Bonk",
                    "text_clean": "other target",
                    "source_received_at_ms": 4_500,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=5_000,
        )

        result = repo.prune_pending_mention_semantics_backlog(
            schema_version="narrative_intel_v1",
            now_ms=10_000,
            max_source_age_ms=7_000,
            max_pending_per_target=1,
        )
        rows = [
            row["event_id"]
            for row in conn.execute(
                """
                SELECT event_id
                FROM token_mention_semantics
                ORDER BY event_id
                """
            ).fetchall()
        ]
    finally:
        conn.close()

    assert result == {"deleted_old_semantics": 1, "deleted_overflow_semantics": 1}
    assert rows == ["event-new", "event-other"]


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
