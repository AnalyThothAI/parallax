import time

from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
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
    conn, _, enrichment, ingest = open_repositories(tmp_path)
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
