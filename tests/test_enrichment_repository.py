import time
from threading import RLock

from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate


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
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
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
        write_lock=RLock(),
    )
    return conn, evidence, enrichment, ingest


def test_migration_creates_enrichment_tables_and_removes_keyword_product_tables(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    try:
        migrate(conn)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchall()
        }
    finally:
        conn.close()

    assert {
        "enrichment_jobs",
        "model_runs",
        "event_enrichments",
        "event_token_candidates",
        "event_narratives",
        "narrative_windows",
        "account_narrative_alerts",
    }.issubset(tables)
    assert "keyword_windows" not in tables
    assert "account_keyword_alerts" not in tables


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
    assert jobs[0]["job_type"] == "watched_event_enrichment"
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
