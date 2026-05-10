import time

from gmgn_twitter_intel.domains.evidence.interfaces import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.evidence.services.ingest_service import IngestService
from gmgn_twitter_intel.domains.social_enrichment.repositories.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.domains.social_enrichment.types.social_event_extraction import AnchorTerm, SocialEventExtraction
from gmgn_twitter_intel.domains.token_intel.interfaces import SignalRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def make_event(
    event_id: str = "event-1",
    *,
    text: str | None = "Solana XDP throughput is nearly ready",
    is_watched: bool = True,
) -> TwitterEvent:
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
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=["toly"] if is_watched else [],
        raw={"id": event_id},
    )


def open_repositories(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    enrichment = EnrichmentRepository(conn)
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
    )
    return conn, evidence, enrichment, ingest


def test_migration_creates_current_llm_job_tables(tmp_path):
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
        "enrichment_jobs",
        "model_runs",
    }.issubset(tables)


def test_watched_ingest_enqueues_one_durable_enrichment_job(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        result = ingest.ingest_event(make_event("watched-1"), is_watched=True)
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert result.inserted is True
    assert result.enrichment_job_id is not None
    assert len(jobs) == 1
    assert jobs[0]["event_id"] == "watched-1"
    assert jobs[0]["job_type"] == "watched_social_event_extraction"
    assert jobs[0]["status"] == "pending"


def test_unwatched_or_textless_events_do_not_enqueue_enrichment_jobs(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        ingest.ingest_event(make_event("unwatched", is_watched=False), is_watched=False)
        ingest.ingest_event(make_event("textless", text=None), is_watched=True)
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert jobs == []


def test_low_information_watched_service_reply_does_not_enqueue_llm_job(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        result = ingest.ingest_event(
            make_event(
                "low-info-service-reply",
                text=(
                    "@user skill installed: $SOLVR Bankr Club Airdrop checked your claim status. "
                    "Wallet 0x35f300000000000000000000000000000000064f is not eligible."
                ),
            ),
            is_watched=True,
        )
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert result.inserted is True
    assert result.enrichment_job_id is None
    assert jobs == []


def test_duplicate_watched_event_does_not_duplicate_enrichment_job(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        assert ingest.ingest_event(make_event("dup"), is_watched=True).inserted is True
        assert ingest.ingest_event(make_event("dup"), is_watched=True).inserted is False
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert [job["event_id"] for job in jobs] == ["dup"]


def test_backfill_missing_watched_events_enqueues_existing_raw_events_without_legacy_reads(tmp_path):
    conn, evidence, enrichment, _ = open_repositories(tmp_path)
    try:
        assert evidence.insert_event(make_event("old-watched"), is_watched=True) is True
        assert evidence.insert_event(make_event("old-public"), is_watched=False) is True
        result = enrichment.enqueue_missing_watched_events(limit=10)
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert result["watched_events_scanned"] == 1
    assert result["jobs_enqueued"] == 1
    assert [job["event_id"] for job in jobs] == ["old-watched"]


def test_claim_next_job_marks_running_and_respects_status(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        ingest.ingest_event(make_event("claim-me"), is_watched=True)
        claimed = enrichment.claim_next_job(now_ms=int(time.time() * 1000))
        second_claim = enrichment.claim_next_job(now_ms=int(time.time() * 1000))
        stored = enrichment.list_jobs(limit=10)[0]
    finally:
        conn.close()

    assert claimed is not None
    assert claimed["event_id"] == "claim-me"
    assert second_claim is None
    assert stored["status"] == "running"


def test_claim_next_job_ignores_legacy_enrichment_job_types(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        event = make_event("legacy-job")
        ingest.ingest_event(event, is_watched=True)
        conn.execute(
            """
            UPDATE enrichment_jobs
            SET job_type = 'watched_event_enrichment'
            WHERE event_id = %s
            """,
            ("legacy-job",),
        )
        conn.commit()

        claimed = enrichment.claim_next_job(now_ms=int(time.time() * 1000))
        stored = enrichment.list_jobs(limit=10)[0]
    finally:
        conn.close()

    assert claimed is None
    assert stored["status"] == "dead"
    assert stored["last_error"] == "legacy_job_type_retired"


def test_complete_social_event_job_records_agents_sdk_run_audit(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        ingest.ingest_event(make_event("agent-run-audit", text="Solana XDP agent audit"), is_watched=True)
        job = enrichment.claim_next_job(now_ms=int(time.time() * 1000))
        result = SocialEventExtraction(
            is_signal_event=True,
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="Solana XDP",
            direction_hint="attention_positive",
            attention_mechanism="product_or_feature",
            impact_hint=0.7,
            semantic_novelty_hint=0.6,
            confidence=0.85,
            anchor_terms=[AnchorTerm(term="Solana XDP", role="product", evidence="Solana XDP")],
            token_candidates=[],
            semantic_risks=["public_stream_coverage"],
            summary_zh="Solana XDP 形成注意力种子。",
            raw_response={"is_signal_event": True},
            agent_run_audit={
                "backend": "openai_agents_sdk",
                "sdk_trace_id": "trace_0123456789abcdef0123456789abcdef",
                "workflow_name": "gmgn-twitter-intel.social_event_extraction",
                "agent_name": "SocialEventExtractionAgent",
                "prompt_version": "social-event-agents-sdk-v1",
                "schema_version": "social_event_v2",
                "artifact_version_hash": "artifact:gpt-test",
                "trace_metadata": {"event_id": "agent-run-audit"},
            },
        )

        enrichment.complete_social_event_job(
            job=job,
            run_id="run-agent-audit",
            result=result,
            provider="openai",
            model="gpt-test",
            request={"job_id": job["job_id"]},
        )
        run = conn.execute("SELECT * FROM model_runs WHERE run_id = %s", ("run-agent-audit",)).fetchone()
    finally:
        conn.close()

    assert run["backend"] == "openai_agents_sdk"
    assert run["sdk_trace_id"] == "trace_0123456789abcdef0123456789abcdef"
    assert run["workflow_name"] == "gmgn-twitter-intel.social_event_extraction"
    assert run["agent_name"] == "SocialEventExtractionAgent"
    assert run["prompt_version"] == "social-event-agents-sdk-v1"
    assert run["schema_version"] == "social_event_v2"
    assert run["artifact_version_hash"] == "artifact:gpt-test"
    assert run["trace_metadata_json"]["event_id"] == "agent-run-audit"


def test_claim_next_job_reclaims_stale_running_job(tmp_path):
    conn, _, enrichment, ingest = open_repositories(tmp_path)
    try:
        ingest.ingest_event(make_event("stale-running"), is_watched=True)
        now_ms = int(time.time() * 1000) + 1_000
        first_claim = enrichment.claim_next_job(now_ms=now_ms)
        conn.execute(
            """
            UPDATE enrichment_jobs
            SET updated_at_ms = %s
            WHERE job_id = %s
            """,
            (now_ms - 10_000, first_claim["job_id"]),
        )
        conn.commit()

        reclaimed = EnrichmentRepository(conn, running_timeout_ms=1_000).claim_next_job(now_ms=now_ms)
        stored = enrichment.list_jobs(limit=10)[0]
    finally:
        conn.close()

    assert reclaimed is not None
    assert reclaimed["event_id"] == "stale-running"
    assert reclaimed["attempt_count"] == 2
    assert stored["status"] == "running"


def test_claim_next_job_skips_row_locked_by_another_worker(tmp_path):
    conn, _, _enrichment, ingest = open_repositories(tmp_path)
    second_conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        ingest.ingest_event(make_event("locked-job"), is_watched=True)
        ingest.ingest_event(make_event("available-job"), is_watched=True)
        conn.execute(
            """
            UPDATE enrichment_jobs
            SET priority = 100, next_run_at_ms = 1_700_000_000_000, created_at_ms = 1_700_000_000_000
            WHERE event_id = 'locked-job'
            """
        )
        conn.execute(
            """
            UPDATE enrichment_jobs
            SET priority = 100, next_run_at_ms = 1_700_000_000_000, created_at_ms = 1_700_000_000_001
            WHERE event_id = 'available-job'
            """
        )
        conn.commit()
        conn.execute("BEGIN")
        conn.execute("SELECT job_id FROM enrichment_jobs WHERE event_id = %s FOR UPDATE", ("locked-job",))
        second_conn.execute("SET statement_timeout TO 200")

        claimed = EnrichmentRepository(second_conn).claim_next_job(now_ms=1_700_000_000_100)
    finally:
        conn.execute("ROLLBACK")
        second_conn.execute("RESET statement_timeout")
        second_conn.close()
        conn.close()

    assert claimed is not None
    assert claimed["event_id"] == "available-job"
