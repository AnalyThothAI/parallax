import asyncio
import time
from threading import RLock

from gmgn_twitter_intel.pipeline.enrichment_worker import EnrichmentWorker
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.pipeline.llm_enrichment import EnrichmentResult, NarrativeItem, TokenCandidate
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_enrichment_repository import make_event


class FakeClient:
    provider = "fake"
    model = "fake-model"

    async def enrich_event(self, *, event, entities):
        return EnrichmentResult(
            summary="Toly says Solana XDP scaling is nearly ready.",
            summary_zh="Toly 表示 Solana XDP 扩容接近准备完成。",
            token_candidates=[
                TokenCandidate(
                    symbol="SOL",
                    project_name="Solana",
                    chain=None,
                    address=None,
                    evidence="Solana XDP",
                    confidence=0.91,
                )
            ],
            narratives=[
                NarrativeItem(
                    label="solana_scaling",
                    display_name_zh="Solana XDP 扩容",
                    headline_zh="Solana XDP 扩容进展重新获得关注",
                    description_zh="Solana throughput and XDP readiness",
                    seed_family="solana_scaling",
                    trigger_terms=["Solana", "XDP"],
                    market_interpretation_zh="交易员可能关注 Solana scaling tokens。",
                    evidence="XDP scaling",
                    confidence=0.87,
                )
            ],
            stance="informational",
            intent="technical_commentary",
            confidence=0.9,
            raw_response={"ok": True},
        )


class RecordingPublisher:
    def __init__(self):
        self.messages = []

    async def publish(self, payload):
        self.messages.append(payload)


def test_enrichment_worker_materializes_narrative_signals_and_publishes_update(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    enrichment = EnrichmentRepository(conn)
    tokens = TokenRepository(conn)
    write_lock = RLock()
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        tokens=tokens,
        write_lock=write_lock,
    )
    publisher = RecordingPublisher()
    worker = EnrichmentWorker(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        tokens=tokens,
        client=FakeClient(),
        publisher=publisher,
        write_lock=write_lock,
    )
    try:
        event = make_event("event-worker", text="Solana XDP scaling is nearly ready")
        ingest.ingest_event(event, is_watched=True)

        processed = asyncio.run(worker.process_one(now_ms=int(time.time() * 1000)))
        account_narratives = enrichment.account_narratives(window_ms=86_400_000, limit=10)
        narrative_flow = enrichment.narrative_flow(window="1h", limit=10)
        event_enrichment = enrichment.enrichment_for_event("event-worker")
        seeds = enrichment.narrative_seeds(window_ms=86_400_000, limit=10)
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert processed is True
    assert jobs[0]["status"] == "done"
    assert event_enrichment["summary"] == "Toly says Solana XDP scaling is nearly ready."
    assert seeds[0]["narrative_label"] == "solana_scaling"
    assert account_narratives[0]["narrative_label"] == "solana_scaling"
    assert narrative_flow[0]["narrative_label"] == "solana_scaling"
    assert publisher.messages[0]["type"] == "enrichment_update"
    assert publisher.messages[0]["event"]["event_id"] == "event-worker"


def test_enrichment_worker_keeps_completed_job_when_link_materialization_fails(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    enrichment = EnrichmentRepository(conn)
    tokens = TokenRepository(conn)
    write_lock = RLock()
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        tokens=tokens,
        write_lock=write_lock,
    )
    worker = EnrichmentWorker(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        tokens=tokens,
        client=FakeClient(),
        write_lock=write_lock,
    )

    def raise_link_failure(*, event, result):
        raise RuntimeError("link materialization failed")

    worker._materialize_narrative_links = raise_link_failure
    try:
        event = make_event("event-worker-link-fail", text="Solana XDP scaling is nearly ready")
        ingest.ingest_event(event, is_watched=True)

        processed = asyncio.run(worker.process_one(now_ms=int(time.time() * 1000)))
        event_enrichment = enrichment.enrichment_for_event("event-worker-link-fail")
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert processed is True
    assert event_enrichment["summary"] == "Toly says Solana XDP scaling is nearly ready."
    assert jobs[0]["status"] == "done"
