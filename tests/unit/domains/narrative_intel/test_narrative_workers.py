import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker import (
    MentionSemanticsWorker,
)
from gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker import (
    TokenDiscussionDigestWorker,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticLabel,
    MentionSemanticsBatchResult,
)


def test_workers_are_workerbase_subclasses():
    assert issubclass(MentionSemanticsWorker, WorkerBase)
    assert issubclass(TokenDiscussionDigestWorker, WorkerBase)


def test_mention_semantics_worker_calls_provider_outside_db_session():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        provider = BarrierNarrativeProvider(db)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 1
        assert result.notes["claimed"] == 1
        assert provider.max_sessions_seen == 0
        assert repo.completed_batches[0]["labels"][0]["event_id"] == "event-1"
        assert repo.recorded_runs[0]["stage"] == "mention_semantics"

    asyncio.run(scenario())


def test_mention_semantics_worker_reconciles_radar_admission_before_labeling():
    async def scenario():
        repo = FakeNarrativeRepository(
            radar_rows=[
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "rank": 1,
                    "rank_score": 90,
                    "source_event_ids_json": ["event-1"],
                    "computed_at_ms": 10_000,
                }
            ],
            due_mentions=[],
            source_mentions=[
                {
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "SOL breakout",
                    "source_received_at_ms": 9_000,
                }
            ],
        )
        db = FakeDB(repo)
        provider = BarrierNarrativeProvider(db)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 1
        assert result.notes["admission_radar_rows"] == 1
        assert result.notes["admission_admissions_upserted"] == 1
        assert result.notes["admission_semantic_inserted"] == 1
        assert repo.scanned_admission_ids == ["admission-1"]
        assert repo.completed_batches[0]["labels"][0]["event_id"] == "event-1"

    asyncio.run(scenario())


def fake_settings():
    return SimpleNamespace(
        enabled=True,
        interval_seconds=1.0,
        timeout_seconds=0.0,
        statement_timeout_seconds=9.0,
        batch_size=10,
        windows=("24h",),
        scopes=("matched",),
        admission_limit=10,
        source_limit=100,
        model_version="gpt-test",
    )


class FakeDB:
    def __init__(self, narrative_repo):
        self.narrative_repo = narrative_repo
        self.active_sessions = 0

    @contextmanager
    def worker_session(self, name, statement_timeout_seconds=None):
        self.active_sessions += 1
        try:
            yield SimpleNamespace(narratives=self.narrative_repo)
        finally:
            self.active_sessions -= 1


class FakeNarrativeRepository:
    def __init__(self, *, radar_rows=None, source_mentions=None, due_mentions=None):
        self.radar_rows = list(radar_rows or [])
        self.source_mentions = list(source_mentions or [])
        self.due_mentions = due_mentions
        self.recorded_runs = []
        self.completed_batches = []
        self.upserted_admissions = []
        self.scanned_admission_ids = []

    def admitted_radar_rows(self, *, window, scope, limit, projection_version):
        return self.radar_rows[:limit]

    def admissions_for_window_scope(self, *, window, scope, schema_version, limit):
        return []

    def upsert_admissions_from_radar_rows(self, rows, *, window, scope, schema_version, now_ms, source_limit):
        self.upserted_admissions.extend(rows[:source_limit])
        return {"upserted": len(rows[:source_limit]), "seen": len(rows)}

    def due_admissions_for_semantics(self, *, now_ms, limit):
        if not self.upserted_admissions:
            return []
        first = self.upserted_admissions[0]
        return [
            {
                "admission_id": "admission-1",
                "target_type": first["target_type"],
                "target_id": first["target_id"],
                "window": first["window"],
                "scope": first["scope"],
            }
        ][:limit]

    def source_mentions_for_admission(self, *, target_type, target_id, since_ms, watched_only, limit):
        return self.source_mentions[:limit]

    def enqueue_missing_mention_semantics(self, source_rows, *, schema_version, model_version, now_ms):
        if self.due_mentions is not None:
            self.due_mentions.extend(source_rows)
        return {"inserted": len(source_rows), "existing": 0}

    def mark_admissions_semantics_scanned(self, admission_ids, *, next_due_at_ms, now_ms):
        self.scanned_admission_ids.extend(admission_ids)
        return {"updated": len(admission_ids)}

    def due_mentions_for_labeling(self, *, now_ms, limit):
        if self.due_mentions is not None:
            return self.due_mentions[:limit]
        return [
            {
                "semantic_id": "semantic-1",
                "event_id": "event-1",
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "text_clean": "SOL breakout",
                "text_fingerprint": "fp-1",
            }
        ]

    def record_narrative_model_run(self, run, *, commit=True):
        self.recorded_runs.append(run)
        return run

    def complete_mention_semantics_batch(self, *, run_id, labels, failures, now_ms):
        self.completed_batches.append({"run_id": run_id, "labels": labels, "failures": failures, "now_ms": now_ms})
        return {"labeled": len(labels), "semantic_unavailable": 0, "failed": len(failures)}


class BarrierNarrativeProvider:
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    def __init__(self, db):
        self.db = db
        self.max_sessions_seen = 0

    async def label_mentions(self, *, run_id, request):
        self.max_sessions_seen = max(self.max_sessions_seen, self.db.active_sessions)
        return MentionSemanticsBatchResult(
            run_id=run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            labels=[
                MentionSemanticLabel(
                    event_id="event-1",
                    target_type="chain_token",
                    target_id="solana:So111",
                    trade_stance="bullish",
                    attention_valence="celebratory",
                    claim_type="price-action",
                    evidence_type="scanner-alert",
                    semantic_confidence=0.8,
                    evidence_refs=[
                        {
                            "ref_id": "event:event-1",
                            "kind": "event",
                            "source_table": "events",
                            "event_id": "event-1",
                        }
                    ],
                    status="labeled",
                )
            ],
            failures=[],
            raw_response={"ok": True},
            agent_run_audit={"usage": {"input_tokens": 1}},
        )

    async def summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        raise NotImplementedError

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None
