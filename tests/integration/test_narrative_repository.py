import time

from psycopg.types.json import Jsonb

from parallax.domains.evidence.interfaces import Author, Content, Source, TwitterEvent
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from parallax.domains.narrative_intel.repositories.narrative_repository import (
    NarrativeRepository,
    admission_payload_hash,
)
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


class _CountingConnection:
    def __init__(self, conn):
        self.conn = conn
        self.execute_count = 0

    def execute(self, *args, **kwargs):
        self.execute_count += 1
        return self.conn.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.conn, name)


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


def insert_admitted_admission(
    conn,
    *,
    admission_id: str,
    target_id: str,
    window: str,
    source_event_ids: list[str],
) -> None:
    payload = {
        "admission_id": admission_id,
        "target_type": "chain_token",
        "target_id": target_id,
        "window": window,
        "scope": "matched",
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "status": "admitted",
        "reason": "unit_test",
        "priority": 1,
        "last_radar_rank": 1,
        "last_rank_score": 90.0,
        "source_event_ids_json": Jsonb(source_event_ids),
        "source_fingerprint": "source-fingerprint",
        "source_max_received_at_ms": 3_000,
        "projection_computed_at_ms": None,
        "source_window_start_ms": None,
        "source_window_end_ms": 3_000,
        "source_event_count": len(source_event_ids),
        "independent_author_count": len(source_event_ids),
        "admission_generation": None,
        "admitted_at_ms": 3_000,
        "last_seen_at_ms": 3_000,
        "updated_at_ms": 3_000,
    }
    payload["payload_hash"] = admission_payload_hash(payload)
    conn.execute(
        """
        INSERT INTO narrative_admissions(
          admission_id, target_type, target_id, "window", scope, schema_version, status, reason,
          priority, last_radar_rank, last_rank_score, source_event_ids_json, source_fingerprint,
          source_max_received_at_ms, projection_computed_at_ms, source_window_start_ms, source_window_end_ms,
          source_event_count, independent_author_count, admission_generation,
          admitted_at_ms, last_seen_at_ms, updated_at_ms, payload_hash
        )
        VALUES (
          %(admission_id)s, %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(schema_version)s,
          %(status)s, %(reason)s, %(priority)s, %(last_radar_rank)s, %(last_rank_score)s,
          %(source_event_ids_json)s, %(source_fingerprint)s, %(source_max_received_at_ms)s,
          %(projection_computed_at_ms)s, %(source_window_start_ms)s, %(source_window_end_ms)s,
          %(source_event_count)s, %(independent_author_count)s, %(admission_generation)s,
          %(admitted_at_ms)s, %(last_seen_at_ms)s, %(updated_at_ms)s, %(payload_hash)s
        )
        """,
        payload,
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


def test_load_radar_admission_target_query_matches_current_token_radar_schema(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        columns = {
            row["column_name"]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'token_radar_current_rows'
                """
            ).fetchall()
        }
        context = repo.load_radar_admission_target(
            target_type="Asset",
            target_id="asset:missing",
            window="5m",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    assert "rank_score" in columns
    assert "factor_snapshot_json" in columns
    assert context["radar_row"] is None
    assert context["existing_admission"] is None


def test_load_radar_admission_target_uses_exact_latest_ready_projection_frontier(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-old-1", "event-old-2", "event-latest"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
            _insert_intent(conn, intent_id=f"intent-{event_id}", event_id=event_id, observed_at_ms=1_000)
        _insert_radar_publication_state(
            conn,
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
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
            UPDATE token_radar_publication_state
            SET current_generation_id = 'test-generation:2000',
                current_published_at_ms = 2_000,
                latest_attempt_started_at_ms = 2_000,
                latest_attempt_generation_id = 'test-generation:2000',
                latest_attempt_finished_at_ms = 2_000,
                updated_at_ms = 2_000
            WHERE projection_version = %s
              AND "window" = '24h'
              AND scope = 'all'
            """,
            (TOKEN_RADAR_PROJECTION_VERSION,),
        )
        conn.execute(
            """
            DELETE FROM token_radar_current_rows
            WHERE row_id IN ('radar-old-1', 'radar-old-2')
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

        context = repo.load_radar_admission_target(
            target_type="Asset",
            target_id="asset:latest:rank10",
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    assert context["radar_row"]["computed_at_ms"] == 2_000
    assert context["radar_row"]["target_id"] == "asset:latest:rank10"


def test_load_radar_admission_target_uses_current_row_when_publication_timestamp_advances_without_row_churn(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        assert evidence.insert_event(make_event("event-stable"), is_watched=True) is True
        _insert_intent(conn, intent_id="intent-event-stable", event_id="event-stable", observed_at_ms=1_000)
        _insert_radar_publication_state(
            conn,
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            computed_at_ms=1_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-stable",
            event_id="event-stable",
            intent_id="intent-event-stable",
            target_id="asset:stable:rank1",
            rank=1,
            computed_at_ms=1_000,
        )
        conn.execute(
            """
            UPDATE token_radar_publication_state
            SET current_published_at_ms = 2_000,
                latest_attempt_started_at_ms = 2_000,
                latest_attempt_finished_at_ms = 2_000,
                updated_at_ms = 2_000
            WHERE projection_version = %s
              AND "window" = '24h'
              AND scope = 'all'
            """,
            (TOKEN_RADAR_PROJECTION_VERSION,),
        )
        conn.commit()

        context = repo.load_radar_admission_target(
            target_type="Asset",
            target_id="asset:stable:rank1",
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    assert context["radar_row"]["target_id"] == "asset:stable:rank1"
    assert context["radar_row"]["computed_at_ms"] == 2_000
    assert context["radar_row"]["row_computed_at_ms"] == 1_000


def test_upsert_admissions_unchanged_payload_writes_zero_rows(tmp_path) -> None:
    conn, _, repo = open_repo(tmp_path)
    try:
        row = {
            "target_type": "chain_token",
            "target_id": "solana:So111",
            "window": "1h",
            "scope": "matched",
            "schema_version": NARRATIVE_SCHEMA_VERSION,
            "source_event_ids": ["event-1", "event-2"],
            "source_max_received_at_ms": 2_000,
            "source_window_start_ms": 1_000,
            "source_window_end_ms": 2_000,
            "source_event_count": 2,
            "independent_author_count": 2,
            "rank": 4,
            "rank_score": 72.5,
            "admission_generation": "1h:matched:2000",
        }

        assert repo.upsert_admissions([row], now_ms=2_100) == {"upserted": 1, "seen": 1}
        before = conn.execute(
            """
            SELECT admission_id, updated_at_ms, last_seen_at_ms, payload_hash
            FROM narrative_admissions
            WHERE target_type = 'chain_token'
              AND target_id = 'solana:So111'
              AND "window" = '1h'
              AND scope = 'matched'
            """
        ).fetchone()

        watermark_only_row = {
            **row,
            "computed_at_ms": 9_000,
            "admission_generation": "1h:matched:9000",
        }
        assert repo.upsert_admissions([watermark_only_row], now_ms=9_000) == {"upserted": 0, "seen": 1}
        after = conn.execute(
            """
            SELECT admission_id, updated_at_ms, last_seen_at_ms, payload_hash
            FROM narrative_admissions
            WHERE target_type = 'chain_token'
              AND target_id = 'solana:So111'
              AND "window" = '1h'
              AND scope = 'matched'
            """
        ).fetchone()
    finally:
        conn.close()

    assert before["payload_hash"]
    assert after["payload_hash"] == before["payload_hash"]
    assert after["admission_id"] == before["admission_id"]
    assert after["updated_at_ms"] == before["updated_at_ms"]
    assert after["last_seen_at_ms"] == before["last_seen_at_ms"]


def test_replace_current_digest_unchanged_non_ready_writes_zero_rows(tmp_path) -> None:
    conn, _, repo = open_repo(tmp_path)
    try:
        digest = {
            "target_type": "chain_token",
            "target_id": "solana:So111",
            "window": "1h",
            "scope": "matched",
            "schema_version": NARRATIVE_SCHEMA_VERSION,
            "model_version": "deterministic:pending",
            "status": "pending",
            "source_event_ids": ["event-1", "event-2"],
            "source_fingerprint": "source:fingerprint",
            "label_fingerprint": "labels:pending",
            "semantic_coverage": 0.25,
            "source_event_count": 2,
            "labeled_event_count": 1,
            "independent_author_count": 2,
            "data_gaps": [{"reason": "semantic_labeling_pending"}],
        }

        first = repo.replace_current_digest(digest, now_ms=2_100)
        before = conn.execute(
            """
            SELECT digest_id, computed_at_ms, payload_hash
            FROM token_discussion_digests
            WHERE target_type = 'chain_token'
              AND target_id = 'solana:So111'
              AND "window" = '1h'
              AND scope = 'matched'
              AND is_current = true
            """
        ).fetchone()
        second = repo.replace_current_digest(digest, now_ms=9_000)
        after = conn.execute(
            """
            SELECT digest_id, computed_at_ms, payload_hash
            FROM token_discussion_digests
            WHERE target_type = 'chain_token'
              AND target_id = 'solana:So111'
              AND "window" = '1h'
              AND scope = 'matched'
              AND is_current = true
            """
        ).fetchone()
    finally:
        conn.close()

    assert first["rows_written"] == 1
    assert second["rows_written"] == 0
    assert before["payload_hash"]
    assert after["payload_hash"] == before["payload_hash"]
    assert after["digest_id"] == before["digest_id"]
    assert after["computed_at_ms"] == before["computed_at_ms"]


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
        due = repo.claim_due_mention_semantics(
            now_ms=2_001,
            limit=10,
            lease_owner="mention_semantics",
            lease_ms=60_000,
            max_per_target=10,
        )
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
                    "semantic_id": due[0]["semantic_id"],
                    "schema_version": due[0]["schema_version"],
                    "text_fingerprint": due[0]["text_fingerprint"],
                    "lease_owner": due[0]["lease_owner"],
                    "attempt_count": due[0]["attempt_count"],
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
        digest_dirty_targets = repo.digest_dirty_targets_for_mention_semantics_claims(
            [
                {
                    **due[0],
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                }
            ],
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version="narrative_intel_v1",
        )
        hydrated = repo.semantics_for_posts(
            [{"event_id": "event-1", "target_type": "chain_token", "target_id": "solana:So111"}],
            schema_version="narrative_intel_v1",
        )
        insert_admitted_admission(
            conn,
            admission_id="admission-event-1",
            target_id="solana:So111",
            window="24h",
            source_event_ids=["event-1"],
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
    assert digest_dirty_targets == [
        {
            "target_type": "chain_token",
            "target_id": "solana:So111",
            "window": "1h",
            "scope": "matched",
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "schema_version": "narrative_intel_v1",
            "source_watermark_ms": 1000,
            "priority": 0,
        }
    ]
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
        due = repo.claim_due_mention_semantics(
            now_ms=2_001,
            limit=10,
            lease_owner="mention_semantics",
            lease_ms=60_000,
            max_per_target=10,
        )
        current = next(row for row in due if row["text_fingerprint"] == "fingerprint-current")
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
                    "lease_owner": current["lease_owner"],
                    "attempt_count": current["attempt_count"],
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
        insert_admitted_admission(
            conn,
            admission_id="admission-source-set",
            target_id="solana:So111",
            window="24h",
            source_event_ids=["event-source-1", "event-source-2", "event-source-3"],
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

        due = repo.due_mentions_for_labeling(
            now_ms=2_001,
            limit=10,
            max_per_target=10,
            windows=("1h",),
            scopes=("matched",),
        )
    finally:
        conn.close()

    assert [row["event_id"] for row in due] == ["event-1"]


def test_claim_due_mention_semantics_leases_rows_before_provider_work(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-1", "event-2"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "first source",
                    "source_received_at_ms": 1_000,
                },
                {
                    "event_id": "event-2",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "second source",
                    "source_received_at_ms": 2_000,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=2_000,
        )

        claims = repo.claim_due_mention_semantics(
            now_ms=2_001,
            limit=10,
            lease_owner="worker-a",
            lease_ms=60_000,
            max_per_target=10,
        )
        second_claims = repo.claim_due_mention_semantics(
            now_ms=2_002,
            limit=10,
            lease_owner="worker-b",
            lease_ms=60_000,
            max_per_target=10,
        )
    finally:
        conn.close()

    assert [row["event_id"] for row in claims] == ["event-2", "event-1"]
    assert {row["lease_owner"] for row in claims} == {"worker-a"}
    assert {row["attempt_count"] for row in claims} == {1}
    assert second_claims == []


def test_complete_mention_semantics_requires_fresh_claim_token(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        assert evidence.insert_event(make_event("event-stale-claim"), is_watched=True) is True
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-stale-claim",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "claim token source",
                    "source_received_at_ms": 1_000,
                }
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=2_000,
        )
        claim = repo.claim_due_mention_semantics(
            now_ms=2_001,
            limit=1,
            lease_owner="worker-a",
            lease_ms=60_000,
        )[0]
        run = repo.record_narrative_model_run(
            {
                "stage": "mention_semantics",
                "provider": "test-provider",
                "model": "gpt-test",
                "schema_version": "narrative_intel_v1",
                "prompt_version": "mention_semantics_v1",
                "input_hash": "stale-claim-input",
                "request_json": {"event_ids": ["event-stale-claim"]},
                "status": "done",
                "started_at_ms": 2_000,
                "finished_at_ms": 2_010,
                "latency_ms": 10,
            }
        )

        stale_complete = repo.complete_mention_semantics_batch(
            run_id=run["run_id"],
            labels=[
                {
                    **claim,
                    "attempt_count": claim["attempt_count"] + 1,
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
        fresh_complete = repo.complete_mention_semantics_batch(
            run_id=run["run_id"],
            labels=[
                {
                    **claim,
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
            now_ms=2_030,
        )
        row = conn.execute(
            """
            SELECT status, lease_owner, leased_until_ms, attempt_count
            FROM token_mention_semantics
            WHERE semantic_id = %s
            """,
            (claim["semantic_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert stale_complete == {"labeled": 0, "semantic_unavailable": 0, "failed": 0}
    assert fresh_complete["labeled"] == 1
    assert row["status"] == "labeled"
    assert row["lease_owner"] is None
    assert row["leased_until_ms"] is None
    assert row["attempt_count"] == 1


def test_pending_mention_semantics_count_filters_to_current_admitted_1h_sources(tmp_path):
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
                    "window": "1h",
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

        count = repo.pending_mention_semantics_count(
            target_type="chain_token",
            target_id="solana:So111",
            schema_version="narrative_intel_v1",
            windows=("1h",),
            scopes=("matched",),
        )
    finally:
        conn.close()

    assert count == 1


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
                    "window": "1h",
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
            window="1h",
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
                    "target_id": "solana:Allowed",
                    "window": "1h",
                    "scope": "all",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-1h-all"],
                    "source_max_received_at_ms": 9_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
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

        rows = repo.due_digest_targets(now_ms=10_000, limit=10, windows=("1h",), scopes=("all",))
    finally:
        conn.close()

    assert [row["window"] for row in rows] == ["1h"]
    assert [row["scope"] for row in rows] == ["all"]
    assert [row["target_id"] for row in rows] == ["solana:Allowed"]


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


def test_replace_current_digest_replaces_previous_current_row(tmp_path):
    window = "1h"
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": window,
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
                "window": window,
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
                "window": window,
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
            window=window,
            scope="matched",
            schema_version="narrative_intel_v1",
        )
        rows = conn.execute(
            """
            SELECT digest_id, is_current, source_fingerprint, label_fingerprint, superseded_at_ms
            FROM token_discussion_digests
            ORDER BY computed_at_ms ASC
            """
        ).fetchall()
    finally:
        conn.close()

    assert first["digest_id"] != second["digest_id"]
    assert current[("chain_token", "solana:So111")]["status"] == "pending"
    assert current[("chain_token", "solana:So111")]["currentness"]["display_status"] == "not_ready"
    assert current[("chain_token", "solana:So111")]["data_gaps_json"] == [{"reason": "low_independent_author_count"}]
    assert rows == [
        {
            "digest_id": second["digest_id"],
            "is_current": True,
            "source_fingerprint": admission_fingerprint,
            "label_fingerprint": "labels-2",
            "superseded_at_ms": None,
        }
    ]


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
    assert first["rows_written"] == 1
    assert second["rows_written"] == 0
    assert len(rows) == 1
    assert rows[0]["digest_id"] == first["digest_id"]
    assert rows[0]["is_current"] is True
    assert rows[0]["computed_at_ms"] == 1_000
    assert second["computed_at_ms"] == 1_000
    assert rows[0]["superseded_at_ms"] is None


def test_current_digests_returns_matching_fingerprint_digest(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        admission = repo.upsert_admissions(
            [
                    {
                        "target_type": "chain_token",
                        "target_id": "solana:So111",
                        "window": "1h",
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
                "window": "1h",
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
            window="1h",
            scope="matched",
            schema_version="narrative_intel_v1",
        )
    finally:
        conn.close()

    assert admission == {"upserted": 1, "seen": 1}
    assert current[("chain_token", "solana:So111")]["digest_id"] == digest["digest_id"]
    assert current[("chain_token", "solana:So111")]["status"] == "ready"
    assert current[("chain_token", "solana:So111")]["currentness"]["display_status"] == "current"


def test_current_narrative_snapshots_uses_current_ready_digest_with_source_delta(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
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
                "window": "1h",
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
                    "window": "1h",
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
            window="1h",
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


def test_current_narrative_snapshots_batches_target_lookup(tmp_path):
    conn, _, seed_repo = open_repo(tmp_path)
    try:
        seed_repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Ready",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["ready-a", "ready-b"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 2,
                    "independent_author_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Pending",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["pending-a"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
            ],
            now_ms=3_000,
        )
        seed_repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:Ready",
                "window": "1h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": "ready-source",
                "label_fingerprint": "ready-label",
                "source_window_end_ms": 2_000,
                "display_current_until_ms": 8_000,
                "semantic_coverage": 1.0,
                "source_event_count": 2,
                "labeled_event_count": 2,
                "independent_author_count": 1,
            },
            now_ms=3_100,
        )
        counting_conn = _CountingConnection(conn)
        repo = NarrativeRepository(counting_conn)

        current = repo.current_narrative_snapshots_for_targets(
            [
                {"target_type": "chain_token", "target_id": "solana:Ready"},
                {"target_type": "chain_token", "target_id": "solana:Pending"},
                {"target_type": "chain_token", "target_id": "solana:Missing"},
            ],
            window="1h",
            scope="matched",
            schema_version="narrative_intel_v1",
            now_ms=4_000,
        )
    finally:
        conn.close()

    assert current[("chain_token", "solana:Ready")]["status"] == "ready"
    assert current[("chain_token", "solana:Pending")]["status"] == "pending"
    assert current[("chain_token", "solana:Pending")]["data_gaps_json"] == [{"reason": "semantic_labeling_pending"}]
    assert current[("chain_token", "solana:Missing")]["data_gaps_json"] == [{"reason": "no_ready_digest"}]
    assert counting_conn.execute_count <= 4


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


def test_market_context_for_admission_reports_price_move_since_current_ready_digest(tmp_path):
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
            current_ready_digest={"computed_at_ms": 1_000},
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
                    "window": "1h",
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
                "window": "1h",
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
            window="1h",
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


def test_current_digests_returns_not_ready_without_admission_or_digest(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
            current = repo.current_digests_for_targets(
                [{"target_type": "chain_token", "target_id": "solana:So111"}],
                window="1h",
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

        due = repo.due_mentions_for_labeling(now_ms=20_001, limit=6, max_per_target=3, scopes=("matched",))
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
                    "window": "1h",
                    "scope": "all",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-current"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Suppressed",
                    "window": "1h",
                    "scope": "all",
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
                "window": "1h",
                "scope": "all",
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
                "window": "1h",
                "scope": "all",
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
        "deleted_old_admissions": 1,
        "deleted_old_digests": 2,
        "deleted_old_semantics": 2,
        "deleted_old_model_runs": 0,
    }
    assert semantics == {"event-current": "queued"}
    assert digest_rows == {}


def test_cleanup_narrative_current_hard_cut_suppresses_non_realtime_state(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-1h", "event-1h-matched", "event-24h", "event-obsolete"]:
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
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:LegacyMatched",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-1h-matched"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:LegacyDay",
                    "window": "24h",
                    "scope": "all",
                    "schema_version": "narrative_intel_v1",
                    "source_event_ids": ["event-24h"],
                    "source_max_received_at_ms": 3_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
            ],
            now_ms=3_000,
        )
        repo.enqueue_missing_mention_semantics(
            [
                {
                    "event_id": "event-1h",
                    "target_type": "chain_token",
                    "target_id": "solana:OneHour",
                    "text_clean": "current 1h source",
                    "source_received_at_ms": 3_000,
                },
                {
                    "event_id": "event-1h-matched",
                    "target_type": "chain_token",
                    "target_id": "solana:LegacyMatched",
                    "text_clean": "legacy matched source",
                    "source_received_at_ms": 3_000,
                },
                {
                    "event_id": "event-24h",
                    "target_type": "chain_token",
                    "target_id": "solana:LegacyDay",
                    "text_clean": "legacy 24h source",
                    "source_received_at_ms": 3_000,
                },
                {
                    "event_id": "event-obsolete",
                    "target_type": "chain_token",
                    "target_id": "solana:Obsolete",
                    "text_clean": "obsolete queued source",
                    "source_received_at_ms": 2_000,
                },
            ],
            schema_version="narrative_intel_v1",
            model_version="gpt-test",
            now_ms=3_100,
        )
        repo.replace_current_digest(
            {
                "target_type": "chain_token",
                "target_id": "solana:LegacyMatched",
                "window": "1h",
                "scope": "matched",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": "legacy-matched-source",
                "label_fingerprint": "legacy-matched-labels",
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
                "target_id": "solana:LegacyDay",
                "window": "24h",
                "scope": "all",
                "schema_version": "narrative_intel_v1",
                "model_version": "deterministic",
                "status": "ready",
                "source_fingerprint": "legacy-day-source",
                "label_fingerprint": "legacy-day-labels",
                "semantic_coverage": 1.0,
                "source_event_count": 1,
                "labeled_event_count": 1,
                "independent_author_count": 1,
            },
            now_ms=3_200,
        )
        conn.commit()

        result = repo.cleanup_narrative_current_hard_cut(
            schema_version="narrative_intel_v1",
            now_ms=4_000,
            realtime_windows=("1h",),
            realtime_scopes=("all",),
        )
        admissions = {
            row["target_id"]: row
            for row in conn.execute(
                """
                SELECT target_id, status, reason
                FROM narrative_admissions
                ORDER BY target_id
                """
            ).fetchall()
        }
        semantics = {
            row["event_id"]: row["status"]
            for row in conn.execute("SELECT event_id, status FROM token_mention_semantics ORDER BY event_id").fetchall()
        }
        digests = {
            row["target_id"]: row
            for row in conn.execute(
                """
                SELECT target_id, status, is_current, superseded_at_ms
                FROM token_discussion_digests
                WHERE target_id IN ('solana:LegacyDay', 'solana:LegacyMatched')
                """
            ).fetchall()
        }
    finally:
        conn.close()

    assert result == {
        "deleted_old_admissions": 2,
        "deleted_old_digests": 2,
        "deleted_old_semantics": 3,
        "deleted_old_model_runs": 0,
    }
    assert admissions["solana:OneHour"]["status"] == "admitted"
    assert set(admissions) == {"solana:OneHour"}
    assert semantics == {"event-1h": "queued"}
    assert digests == {}


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


def _insert_radar_publication_state(
    conn,
    *,
    window: str,
    scope: str,
    projection_version: str,
    computed_at_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO token_radar_publication_state(
          projection_version, "window", scope, current_generation_id, current_published_at_ms,
          current_source_frontier_ms, current_row_count, current_source_rows,
          latest_attempt_generation_id, latest_attempt_status, latest_attempt_started_at_ms,
          latest_attempt_finished_at_ms, latest_attempt_error, updated_at_ms
        )
        VALUES (%s, %s, %s, %s, %s, %s, 1, 1, %s, 'ready', %s, %s, NULL, %s)
        """,
        (
            projection_version,
            window,
            scope,
            f"test-generation:{computed_at_ms}",
            computed_at_ms,
            computed_at_ms,
            f"test-generation:{computed_at_ms}",
            computed_at_ms,
            computed_at_ms,
            computed_at_ms,
        ),
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
        INSERT INTO token_radar_current_rows(
          row_id, projection_version, "window", scope, computed_at_ms, source_max_received_at_ms,
          generation_id, published_at_ms, source_frontier_ms,
          lane, target_type_key, identity_id, rank, rank_score, intent_id, event_id, intent_json,
          resolution_json, factor_snapshot_json, factor_version, decision,
          quality_status, degraded_reasons_json, data_health_json,
          source_event_ids_json, payload_hash, listed_at_ms, created_at_ms, target_type, target_id,
          pricefeed_id
        )
        VALUES (
          %s, %s, '24h', 'all', %s, %s,
          %s, %s, %s,
          'all', 'Asset', %s, %s, %s, %s, %s, %s,
          %s, %s, 'token_factor_snapshot_v3_social_attention', 'watch',
          'ready', %s, %s,
          %s, %s, %s, %s, 'Asset', %s, NULL
        )
        """,
        (
            row_id,
            TOKEN_RADAR_PROJECTION_VERSION,
            computed_at_ms,
            computed_at_ms,
            f"test-generation:{computed_at_ms}",
            computed_at_ms,
            computed_at_ms,
            target_id,
            rank,
            max(0, 100 - rank),
            intent_id,
            event_id,
            Jsonb({"intent_id": intent_id}),
            Jsonb({"status": "EXACT", "target_type": "Asset", "target_id": target_id}),
            Jsonb(
                {
                    "schema_version": "token_factor_snapshot_v3_social_attention",
                    "subject": {"target_type": "Asset", "target_id": target_id, "target_market_type": "dex"},
                    "composite": {"rank_score": max(0, 100 - rank), "recommended_decision": "watch"},
                }
            ),
            Jsonb([]),
            Jsonb({"alpha": "ready"}),
            Jsonb([event_id]),
            f"test-payload-hash:{row_id}",
            computed_at_ms,
            computed_at_ms,
            target_id,
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
