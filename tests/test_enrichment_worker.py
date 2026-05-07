import asyncio
import time

from gmgn_twitter_intel.pipeline.enrichment_worker import EnrichmentWorker
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.pipeline.social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.harness_repository import HarnessRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from tests.postgres_test_utils import connect_postgres_test, repository_session_for_connection
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_enrichment_repository import make_event


class FakeClient:
    provider = "fake"
    model = "fake-model"

    def __init__(self, result: SocialEventExtraction | None = None):
        self.result = result or SocialEventExtraction(
            is_signal_event=True,
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="Solana XDP attention seed",
            direction_hint="attention_positive",
            attention_mechanism="product_or_feature",
            impact_hint=0.72,
            semantic_novelty_hint=0.68,
            confidence=0.86,
            anchor_terms=[AnchorTerm(term="Solana XDP", role="product", evidence="Solana XDP")],
            token_candidates=[
                SocialTokenCandidate(
                    symbol="SOL",
                    project_name="Solana",
                    chain=None,
                    address=None,
                    evidence="Solana",
                    confidence=0.91,
                )
            ],
            semantic_risks=["public_stream_coverage"],
            summary_zh="Toly 提到 Solana XDP，形成注意力种子。",
            raw_response={"ok": True},
        )

    async def enrich_event(self, *, event, entities, run_id, job):  # noqa: ARG002
        return self.result


class HangingClient:
    provider = "fake"
    model = "fake-model"
    timeout_seconds = 0.01

    def request_audit(self, *, event, entities, run_id, job):  # noqa: ARG002
        return {
            "backend": "openai_agents_sdk",
            "sdk_trace_id": "trace_timeout",
            "workflow_name": "gmgn-twitter-intel.social_event_extraction",
            "agent_name": "SocialEventExtractionAgent",
            "prompt_version": "social-event-agents-sdk-v1",
            "schema_version": "social_event_v2",
            "artifact_version_hash": "artifact:fake-model",
            "trace_metadata": {"event_id": event["event_id"], "run_id": run_id},
        }

    async def enrich_event(self, *, event, entities, run_id, job):  # noqa: ARG002
        await asyncio.sleep(60)


class RecordingPublisher:
    def __init__(self):
        self.messages = []

    async def publish(self, payload):
        self.messages.append(payload)


class ConcurrentProbeWorker(EnrichmentWorker):
    def __init__(self):
        super().__init__(
            client=FakeClient(),
            repository_session=lambda: repository_session_for_connection(None),
            poll_interval=0.01,
            concurrency=3,
        )
        self.active = 0
        self.max_active = 0
        self.calls = 0

    async def process_one(self, *, now_ms=None):  # noqa: ARG002
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.03)
        self.calls += 1
        self.active -= 1
        if self.calls >= 6:
            self.stop()
        return True


def open_runtime(tmp_path, *, client=None, publisher=None):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    enrichment = EnrichmentRepository(conn)
    harness = HarnessRepository(conn)
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
    )
    worker = EnrichmentWorker(
        client=client or FakeClient(),
        publisher=publisher,
        repository_session=lambda: repository_session_for_connection(conn),
    )
    return conn, ingest, worker, enrichment, harness


def test_enrichment_worker_run_can_process_jobs_concurrently():
    worker = ConcurrentProbeWorker()

    asyncio.run(worker.run())

    assert worker.max_active > 1


def test_enrichment_worker_materializes_closed_loop_harness_and_publishes_update(tmp_path):
    publisher = RecordingPublisher()
    conn, ingest, worker, enrichment, harness = open_runtime(tmp_path, publisher=publisher)
    try:
        event = make_event("event-worker", text="Solana XDP scaling is nearly ready")
        ingest.ingest_event(event, is_watched=True)

        processed = asyncio.run(worker.process_one(now_ms=int(time.time() * 1000)))
        jobs = enrichment.list_jobs(limit=10)
        social_events = harness.list_social_events(window_ms=86_400_000, limit=10)
        seeds = harness.list_attention_seeds(window_ms=86_400_000, limit=10)
        snapshots = harness.list_snapshots(window_ms=86_400_000, horizon="6h", limit=10)
        decisions = conn.execute("SELECT * FROM harness_decisions").fetchall()
    finally:
        conn.close()

    assert processed is True
    assert jobs[0]["status"] == "done"
    assert social_events[0]["summary_zh"] == "Toly 提到 Solana XDP，形成注意力种子。"
    assert seeds[0]["seed_status"] == "snapshot_ready"
    assert snapshots[0]["asset"] == "SOL"
    assert snapshots[0]["shadow_signal"] == "LONG_SMALL"
    assert decisions[0]["execution_mode"] == "shadow"
    assert publisher.messages[0]["type"] == "harness_update"
    assert publisher.messages[0]["event"]["event_id"] == "event-worker"
    assert publisher.messages[0]["social_event"]["event_type"] == "meme_phrase_seed"


def test_enrichment_worker_stores_non_signal_extraction_without_snapshot(tmp_path):
    result = SocialEventExtraction(
        is_signal_event=False,
        event_type="founder_reply",
        source_action="replied",
        subject="casual reply",
        direction_hint="neutral",
        attention_mechanism="reply_target",
        impact_hint=0.2,
        semantic_novelty_hint=0.1,
        confidence=0.8,
        anchor_terms=[AnchorTerm(term="gm", role="meme_phrase", evidence="gm")],
        token_candidates=[],
        semantic_risks=["low_information"],
        summary_zh="普通回复。",
        raw_response={"ok": True},
    )
    conn, ingest, worker, enrichment, harness = open_runtime(tmp_path, client=FakeClient(result))
    try:
        event = make_event("event-worker-non-signal", text="gm")
        ingest.ingest_event(event, is_watched=True)

        processed = asyncio.run(worker.process_one(now_ms=int(time.time() * 1000)))
        social_events = harness.list_social_events(window_ms=86_400_000, limit=10)
        snapshots = harness.list_snapshots(window_ms=86_400_000, horizon="6h", limit=10)
        jobs = enrichment.list_jobs(limit=10)
    finally:
        conn.close()

    assert processed is True
    assert jobs[0]["status"] == "done"
    assert social_events[0]["is_signal_event"] is False
    assert snapshots == []


def test_enrichment_worker_times_out_hung_llm_job(tmp_path):
    conn, ingest, worker, enrichment, _ = open_runtime(tmp_path, client=HangingClient())
    try:
        ingest.ingest_event(make_event("event-worker-timeout", text="Solana XDP timeout test"), is_watched=True)

        processed = asyncio.run(worker.process_one(now_ms=int(time.time() * 1000) + 1_000))
        job = enrichment.list_jobs(limit=10)[0]
        run = conn.execute("SELECT * FROM model_runs WHERE event_id = %s", ("event-worker-timeout",)).fetchone()
    finally:
        conn.close()

    assert processed is True
    assert job["status"] == "failed"
    assert "timed out" in job["last_error"].lower()
    assert run["status"] == "model_error"
    assert "timed out" in run["error"].lower()
    assert run["backend"] == "openai_agents_sdk"
    assert run["sdk_trace_id"] == "trace_timeout"
    assert run["workflow_name"] == "gmgn-twitter-intel.social_event_extraction"
