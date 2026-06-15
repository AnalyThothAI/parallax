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
        content=Content(text=f"SOL breakout discussion {event_id}", media=[]),
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


def insert_admitted_admission(
    conn,
    *,
    admission_id: str,
    target_id: str,
    window: str,
    source_event_ids: list[str],
    scope: str = "matched",
    source_fingerprint: str = "source-fingerprint",
    source_max_received_at_ms: int = 3_000,
) -> None:
    payload = {
        "admission_id": admission_id,
        "target_type": "chain_token",
        "target_id": target_id,
        "window": window,
        "scope": scope,
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "status": "admitted",
        "reason": "unit_test",
        "priority": 1,
        "last_radar_rank": 1,
        "last_rank_score": 90.0,
        "source_event_ids_json": Jsonb(source_event_ids),
        "source_fingerprint": source_fingerprint,
        "source_max_received_at_ms": source_max_received_at_ms,
        "projection_computed_at_ms": None,
        "source_window_start_ms": None,
        "source_window_end_ms": source_max_received_at_ms,
        "source_event_count": len(source_event_ids),
        "independent_author_count": len(source_event_ids),
        "admission_generation": None,
        "admitted_at_ms": source_max_received_at_ms,
        "last_seen_at_ms": source_max_received_at_ms,
        "updated_at_ms": source_max_received_at_ms,
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


def test_removed_narrative_llm_writer_methods_are_not_repository_api(tmp_path):
    _, _, repo = open_repo(tmp_path)

    for name in (
        "enqueue_missing_mention_semantics",
        "claim_due_mention_semantics",
        "complete_mention_semantics_batch",
        "replace_current_digest",
        "record_narrative_model_run",
        "cleanup_narrative_current_hard_cut",
        "digest_context",
        "due_digest_targets",
    ):
        assert not hasattr(repo, name)


def test_upsert_admissions_uses_product_identity_and_zero_writes_unchanged(tmp_path):
    conn, _, repo = open_repo(tmp_path)
    try:
        row = {
            "target_type": "chain_token",
            "target_id": "solana:Stable",
            "window": "1h",
            "scope": "matched",
            "schema_version": NARRATIVE_SCHEMA_VERSION,
            "source_event_ids": ["event-stable"],
            "source_max_received_at_ms": 2_000,
            "source_event_count": 1,
            "independent_author_count": 1,
        }

        first = repo.upsert_admissions([row], now_ms=2_000)
        second = repo.upsert_admissions([row], now_ms=3_000)
        count = conn.execute("SELECT COUNT(*) AS count FROM narrative_admissions").fetchone()["count"]
    finally:
        conn.close()

    assert first == {"upserted": 1, "seen": 1}
    assert second == {"upserted": 0, "seen": 1}
    assert count == 1


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
            row_id="radar-old",
            event_id="event-old-1",
            intent_id="intent-event-old-1",
            target_id="asset:old",
            rank=1,
            computed_at_ms=1_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-latest",
            event_id="event-latest",
            intent_id="intent-event-latest",
            target_id="asset:latest",
            rank=2,
            computed_at_ms=1_000,
        )

        context = repo.load_radar_admission_target(
            target_type="Asset",
            target_id="asset:latest",
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    assert context["radar_row"]["target_id"] == "asset:latest"
    assert context["radar_row"]["rank"] == 2
    assert context["existing_admission"] is None


def test_current_digests_for_targets_reads_legacy_digest_without_exact_fingerprint_match(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        assert evidence.insert_event(make_event("event-ready"), is_watched=True) is True
        insert_admitted_admission(
            conn,
            admission_id="admission-ready",
            target_id="solana:Ready",
            window="1h",
            source_event_ids=["event-ready"],
            source_fingerprint="current-source-fingerprint",
        )
        _insert_legacy_digest(
            conn,
            digest_id="digest-ready",
            target_id="solana:Ready",
            window="1h",
            scope="matched",
            source_event_ids=["event-ready"],
            source_fingerprint="old-source-fingerprint",
            headline="Legacy digest is readable",
            computed_at_ms=2_500,
        )

        current = repo.current_digests_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:Ready"}],
            window="1h",
            scope="matched",
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    row = current[("chain_token", "solana:Ready")]
    assert row["headline_zh"] == "Legacy digest is readable"
    assert row["currentness"]["display_status"] == "current"
    assert row["currentness"]["reason"] == "fingerprint_match"


def test_current_digests_for_targets_does_not_treat_legacy_semantics_as_current_backlog(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-labeled", "event-missing"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
        insert_admitted_admission(
            conn,
            admission_id="admission-pending",
            target_id="solana:Pending",
            window="1h",
            source_event_ids=["event-labeled", "event-missing"],
        )
        _insert_legacy_semantic(
            conn,
            event_id="event-labeled",
            target_id="solana:Pending",
            status="labeled",
            computed_at_ms=2_500,
        )

        current = repo.current_digests_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:Pending"}],
            window="1h",
            scope="matched",
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    row = current[("chain_token", "solana:Pending")]
    assert row["status"] == "pending"
    assert row["data_gaps_json"] == [{"reason": "no_ready_digest"}]
    assert "semantic_backlog_pending" not in row
    assert row["source_event_count"] == 2
    assert row["labeled_event_count"] == 0


def test_semantics_for_posts_reads_legacy_label_rows(tmp_path):
    conn, evidence, repo = open_repo(tmp_path)
    try:
        assert evidence.insert_event(make_event("event-label"), is_watched=True) is True
        _insert_legacy_semantic(
            conn,
            event_id="event-label",
            target_id="solana:Label",
            status="labeled",
            trade_stance="bullish",
            attention_valence="positive",
            computed_at_ms=3_000,
        )

        semantics = repo.semantics_for_posts(
            [{"event_id": "event-label", "target_type": "chain_token", "target_id": "solana:Label"}],
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    row = semantics[("event-label", "chain_token", "solana:Label")]
    assert row["status"] == "labeled"
    assert row["trade_stance"] == "bullish"
    assert row["attention_valence"] == "positive"


def _insert_legacy_semantic(
    conn,
    *,
    event_id: str,
    target_id: str,
    status: str,
    computed_at_ms: int | None = None,
    trade_stance: str = "unknown",
    attention_valence: str = "unknown",
) -> None:
    conn.execute(
        """
        INSERT INTO token_mention_semantics(
          semantic_id, event_id, target_type, target_id, schema_version, model_version,
          text_fingerprint, language, status, trade_stance, attention_valence,
          narrative_cluster_key, claim_type, evidence_type, semantic_confidence,
          co_mentioned_targets_json, evidence_refs_json, raw_label_json,
          source_received_at_ms, queued_at_ms, computed_at_ms, next_retry_at_ms
        )
        VALUES (
          %s, %s, 'chain_token', %s, %s, 'legacy-model',
          %s, 'en', %s, %s, %s,
          'cluster:test', 'market_view', 'claim', 0.85,
          %s, %s, %s,
          2_000, 2_000, %s, 0
        )
        """,
        (
            f"semantic:{event_id}:{target_id}",
            event_id,
            target_id,
            NARRATIVE_SCHEMA_VERSION,
            f"text:{event_id}",
            status,
            trade_stance,
            attention_valence,
            Jsonb([]),
            Jsonb([{"ref_id": f"event:{event_id}", "kind": "event"}]),
            Jsonb({"status": status}),
            computed_at_ms,
        ),
    )


def _insert_legacy_digest(
    conn,
    *,
    digest_id: str,
    target_id: str,
    window: str,
    scope: str,
    source_event_ids: list[str],
    source_fingerprint: str,
    headline: str,
    computed_at_ms: int,
    status: str = "ready",
) -> None:
    conn.execute(
        """
        INSERT INTO token_discussion_digests(
          digest_id, target_type, target_id, "window", scope, schema_version, model_version,
          status, is_current, epoch_id, epoch_policy_version, source_event_ids_json,
          source_window_start_ms, source_window_end_ms, epoch_closed_at_ms,
          display_current_until_ms, refresh_reason, source_fingerprint, label_fingerprint, headline_zh,
          dominant_narratives_json, bull_view_json, bear_view_json, stance_mix_json,
          attention_valence_mix_json, propagation_read_json, reflexivity_read_json,
          watch_triggers_json, invalidation_conditions_json, data_gaps_json,
          semantic_coverage, source_event_count, labeled_event_count, independent_author_count,
          evidence_refs_json, computed_at_ms, expires_at_ms, superseded_at_ms, payload_hash
        )
        VALUES (
          %s, 'chain_token', %s, %s, %s, %s, 'legacy-model',
          %s, true, 'epoch:test', 'token_narrative_epoch_v1', %s,
          1_000, 2_000, 2_000,
          9_999_999_999_999, 'legacy_read', %s, 'label:test', %s,
          %s, %s, %s, %s,
          %s, %s, %s,
          %s, %s, %s,
          1.0, %s, %s, %s,
          %s, %s, NULL, NULL, %s
        )
        """,
        (
            digest_id,
            target_id,
            window,
            scope,
            NARRATIVE_SCHEMA_VERSION,
            status,
            Jsonb(source_event_ids),
            source_fingerprint,
            headline,
            Jsonb([{"cluster_key": "cluster:test", "label": "Test"}]),
            Jsonb({"summary": "bull"}),
            Jsonb({"summary": "bear"}),
            Jsonb({"bullish": 1}),
            Jsonb({"positive": 1}),
            Jsonb({"summary": "propagation"}),
            Jsonb({"summary": "reflexivity"}),
            Jsonb([]),
            Jsonb([]),
            Jsonb([]),
            len(source_event_ids),
            len(source_event_ids),
            len(source_event_ids),
            Jsonb([{"ref_id": "event:ready", "kind": "event"}]),
            computed_at_ms,
            f"payload:{digest_id}",
        ),
    )


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
        VALUES (%s, %s, %s, %s, %s, %s, 2, 2, %s, 'ready', %s, %s, NULL, %s)
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
