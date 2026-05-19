import asyncio
import inspect
from contextlib import contextmanager
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.domains.narrative_intel.repositories.narrative_repository import NarrativeRepository
from gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker import (
    MentionSemanticsWorker,
)
from gmgn_twitter_intel.domains.narrative_intel.runtime.narrative_admission_worker import (
    NarrativeAdmissionWorker,
)
from gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker import (
    TokenDiscussionDigestWorker,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticLabel,
    MentionSemanticsBatchResult,
)


def test_workers_are_workerbase_subclasses():
    assert issubclass(NarrativeAdmissionWorker, WorkerBase)
    assert issubclass(MentionSemanticsWorker, WorkerBase)
    assert issubclass(TokenDiscussionDigestWorker, WorkerBase)


def test_mention_semantics_worker_does_not_own_admission_reconciliation():
    source = inspect.getsource(MentionSemanticsWorker)

    assert "upsert_admissions_from_radar_rows" not in source
    assert "admitted_radar_rows" not in source
    assert "source_mentions_for_admission" not in source


def test_source_set_query_uses_indexable_current_resolution_predicate():
    source = inspect.getsource(NarrativeRepository.source_set_for_admission)

    assert "COALESCE(resolution.is_current" not in source
    assert "resolution.is_current = true" in source


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


def test_narrative_admission_worker_rebuilds_current_frontier_source_sets():
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
                    "source_max_received_at_ms": 9_000,
                }
            ],
            source_rows=[
                {
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "SOL breakout",
                    "source_received_at_ms": 9_000,
                    "author_handle": "toly",
                }
            ],
        )
        db = FakeDB(repo)
        worker = NarrativeAdmissionWorker(
            name="narrative_admission",
            settings=fake_admission_settings(),
            db=db,
            telemetry=SimpleNamespace(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 1
        assert result.notes["frontier_rows"] == 1
        assert result.notes["source_events"] == 1
        assert repo.upserted_admissions[0]["source_event_ids"] == ["event-1"]
        assert repo.upserted_admissions[0]["projection_computed_at_ms"] == 10_000
        assert repo.upserted_admissions[0]["source_window_end_ms"] == 10_000
        assert repo.upserted_admissions[0]["source_max_received_at_ms"] == 9_000
        assert repo.upserted_admissions[0]["source_event_count"] == 1
        assert repo.upserted_admissions[0]["independent_author_count"] == 1

    asyncio.run(scenario())


def test_mention_semantics_worker_bounds_semantic_enqueue_from_admitted_source_sets():
    async def scenario():
        repo = FakeNarrativeRepository(
            due_mentions=[],
            due_admissions=[
                {
                    "admission_id": "admission-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "24h",
                    "scope": "matched",
                    "source_event_ids_json": [f"event-{index}" for index in range(1, 6)],
                }
            ],
            source_rows=[
                {
                    "event_id": f"event-{index}",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": f"SOL breakout {index}",
                    "source_received_at_ms": 9_000 + index,
                }
                for index in range(1, 6)
            ],
            pending_semantics={("chain_token", "solana:So111"): 1},
        )
        db = FakeDB(repo)
        provider = BarrierNarrativeProvider(db)
        settings = fake_settings(
            max_semantic_rows_enqueued_per_cycle=3,
            max_pending_semantics_per_target=3,
        )
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=settings,
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.notes["enqueue_semantic_inserted"] == 2
        assert result.notes["enqueue_semantic_suppressed_budget"] == 3
        assert result.notes["enqueue_semantic_pending_before"] == 1
        assert repo.enqueued_source_event_ids == ["event-1", "event-2"]
        assert result.processed == 1

    asyncio.run(scenario())


def test_mention_semantics_worker_records_provider_failure_without_poisoning_worker_loop():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=FailingNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 0
        assert result.failed == 1
        assert result.notes["provider_error"] == "TimeoutError"
        assert repo.recorded_runs[0]["status"] == "failed"
        assert repo.recorded_runs[0]["trace_metadata_json"]["lane"] == "narrative.mention_semantics"
        assert repo.recorded_runs[0]["trace_metadata_json"]["error_type"] == "TimeoutError"
        assert repo.completed_batches[0]["failures"][0]["event_id"] == "event-1"

    asyncio.run(scenario())


def test_mention_semantics_worker_terminalizes_provider_failure_after_max_attempts():
    async def scenario():
        repo = FakeNarrativeRepository(
            due_mentions=[
                {
                    "semantic_id": "semantic-1",
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "SOL breakout",
                    "text_fingerprint": "fp-1",
                    "retry_count": 2,
                }
            ]
        )
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=FailingNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        failure = repo.completed_batches[0]["failures"][0]
        assert failure["status"] == "semantic_unavailable"
        assert failure["error"] == "TimeoutError: provider timed out"
        assert result.processed == 1
        assert result.failed == 0
        assert result.notes["semantic_unavailable"] == 1

    asyncio.run(scenario())


def test_mention_semantics_worker_normalizes_provider_failure_keys():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=PartialFailureNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 0
        assert result.failed == 1
        assert repo.completed_batches[0]["failures"][0]["event_id"] == "event-1"
        assert repo.completed_batches[0]["failures"][0]["target_type"] == "chain_token"
        assert repo.completed_batches[0]["failures"][0]["target_id"] == "solana:So111"

    asyncio.run(scenario())


def test_mention_semantics_worker_scopes_event_only_failures_to_matching_rows():
    async def scenario():
        repo = FakeNarrativeRepository(
            due_mentions=[
                {
                    "semantic_id": "semantic-1",
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "SOL breakout",
                    "text_fingerprint": "fp-1",
                },
                {
                    "semantic_id": "semantic-2",
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:Bonk",
                    "text_clean": "SOL and BONK rotate together",
                    "text_fingerprint": "fp-2",
                },
                {
                    "semantic_id": "semantic-3",
                    "event_id": "event-2",
                    "target_type": "chain_token",
                    "target_id": "solana:Wif",
                    "text_clean": "WIF separate setup",
                    "text_fingerprint": "fp-3",
                },
            ]
        )
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=PartialFailureNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        target_ids = {failure["target_id"] for failure in repo.completed_batches[0]["failures"]}
        assert result.processed == 0
        assert result.failed == 2
        assert target_ids == {"solana:So111", "solana:Bonk"}

    asyncio.run(scenario())


def test_mention_semantics_worker_prunes_old_pending_backlog_before_claiming():
    async def scenario():
        repo = FakeNarrativeRepository(
            prune_result={"deleted_old_semantics": 2, "deleted_overflow_semantics": 1}
        )
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(max_pending_source_age_seconds=3600, max_pending_semantics_per_target=5),
            db=db,
            telemetry=SimpleNamespace(),
            provider=BarrierNarrativeProvider(db),
        )

        result = await worker.run_once(now_ms=10_000)

        assert repo.prune_calls == [
            {
                "schema_version": "narrative_intel_v1",
                "now_ms": 10_000,
                "max_source_age_ms": 3_600_000,
                "max_pending_per_target": 5,
            }
        ]
        assert result.notes["prune_deleted_old_semantics"] == 2
        assert result.notes["prune_deleted_overflow_semantics"] == 1
        assert result.processed == 1

    asyncio.run(scenario())


def test_mention_semantics_worker_treats_unknown_provider_labels_as_retryable_failure():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=UnknownLabelNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        batch = repo.completed_batches[0]
        assert result.processed == 0
        assert result.failed == 1
        assert batch["labels"] == []
        assert batch["failures"][0]["event_id"] == "event-1"
        assert "provider_returned_unknown_labels" in batch["failures"][0]["error"]
        assert repo.recorded_runs[0]["status"] == "done"

    asyncio.run(scenario())


def test_token_discussion_digest_worker_records_provider_failure_without_poisoning_worker_loop():
    async def scenario():
        repo = FakeDigestRepository()
        db = FakeDB(repo)
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=FailingNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 0
        assert result.failed == 1
        assert repo.recorded_runs[0]["stage"] == "discussion_digest"
        assert repo.recorded_runs[0]["status"] == "failed"
        assert repo.recorded_runs[0]["trace_metadata_json"]["lane"] == "narrative.discussion_digest"
        assert repo.recorded_runs[0]["trace_metadata_json"]["error_type"] == "TimeoutError"

    asyncio.run(scenario())


def test_token_discussion_digest_worker_keeps_labeling_gap_pending_and_reschedules():
    async def scenario():
        repo = FakeDigestRepository(
            context={
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
                "mentions": [
                    {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "author_handle": "b", "status": "queued"},
                    {"event_id": "event-3", "author_handle": "c", "status": "retryable_error"},
                ],
                "semantic_rows": [
                    {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "author_handle": "b", "status": "queued"},
                    {"event_id": "event-3", "author_handle": "c", "status": "retryable_error"},
                ],
                "source_event_count": 3,
                "labeled_event_count": 1,
                "independent_author_count": 3,
                "allowed_refs": [],
            }
        )
        db = FakeDB(repo)
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=UnexpectedDigestProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.notes["pending"] == 1
        assert result.notes["insufficient"] == 0
        assert repo.replaced_digests[0]["status"] == "pending"
        assert repo.replaced_digests[0]["data_gaps"] == [{"reason": "semantic_labeling_pending"}]
        assert repo.digest_scans == [{"admission_ids": ["admission-1"], "next_due_at_ms": 11_000, "now_ms": 10_000}]

    asyncio.run(scenario())


def fake_settings(**overrides):
    values = dict(
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
    values.update(overrides)
    return SimpleNamespace(
        **values,
    )


def fake_admission_settings(**overrides):
    values = dict(
        enabled=True,
        interval_seconds=1.0,
        timeout_seconds=0.0,
        statement_timeout_seconds=9.0,
        windows=("24h",),
        scopes=("matched",),
        admission_limit=10,
        source_limit=100,
        hot_rank_limit=50,
        min_rank_score=30,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def fake_digest_settings():
    return SimpleNamespace(
        enabled=True,
        interval_seconds=1.0,
        timeout_seconds=0.0,
        statement_timeout_seconds=9.0,
        batch_size=10,
        min_source_mentions=3,
        min_independent_authors=2,
        min_semantic_coverage=0.35,
        max_mentions_per_digest=10,
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
    def __init__(
        self,
        *,
        radar_rows=None,
        source_rows=None,
        due_mentions=None,
        due_admissions=None,
        pending_semantics=None,
        prune_result=None,
    ):
        self.radar_rows = list(radar_rows or [])
        self.source_rows = list(source_rows or [])
        self.due_mentions = due_mentions
        self.due_admissions = due_admissions
        self.pending_semantics = dict(pending_semantics or {})
        self.prune_result = dict(prune_result or {"deleted_old_semantics": 0, "deleted_overflow_semantics": 0})
        self.recorded_runs = []
        self.completed_batches = []
        self.upserted_admissions = []
        self.suppressed_frontiers = []
        self.scanned_admission_ids = []
        self.enqueued_source_event_ids = []
        self.prune_calls = []

    def admitted_radar_rows(self, *, window, scope, limit, projection_version):
        return self.radar_rows[:limit]

    def admissions_for_window_scope(self, *, window, scope, schema_version, limit):
        return []

    def source_set_for_admission(self, *, target_type, target_id, since_ms, until_ms, watched_only, limit):
        rows = [
            row
            for row in self.source_rows[:limit]
            if row.get("target_type") == target_type and row.get("target_id") == target_id
        ]
        return {
            "source_event_ids": [row["event_id"] for row in rows],
            "source_event_count": len(rows),
            "independent_author_count": len({row.get("author_handle") for row in rows if row.get("author_handle")}),
            "source_max_received_at_ms": max((row.get("source_received_at_ms") or 0 for row in rows), default=None),
        }

    def upsert_admissions(self, rows, *, now_ms, limit=None):
        selected = list(rows)[:limit] if limit is not None else list(rows)
        self.upserted_admissions.extend(selected)
        return {"upserted": len(selected), "seen": len(selected)}

    def suppress_admissions_outside_frontier(self, *, window, scope, schema_version, active_target_keys, now_ms):
        self.suppressed_frontiers.append(set(active_target_keys))
        return {"suppressed": 0}

    def due_admissions_for_semantics(self, *, now_ms, limit):
        if self.due_admissions is not None:
            return self.due_admissions[:limit]
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

    def source_rows_for_admission(self, admission, *, limit):
        return self.source_rows[:limit]

    def pending_mention_semantics_count(self, *, target_type, target_id, schema_version, model_version=None):
        return int(self.pending_semantics.get((target_type, target_id), 0))

    def prune_pending_mention_semantics_backlog(
        self,
        *,
        schema_version,
        now_ms,
        max_source_age_ms=None,
        max_pending_per_target=None,
    ):
        self.prune_calls.append(
            {
                "schema_version": schema_version,
                "now_ms": now_ms,
                "max_source_age_ms": max_source_age_ms,
                "max_pending_per_target": max_pending_per_target,
            }
        )
        return dict(self.prune_result)

    def enqueue_missing_mention_semantics(self, source_rows, *, schema_version, model_version, now_ms):
        self.enqueued_source_event_ids.extend(str(row["event_id"]) for row in source_rows)
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
        unavailable = sum(1 for failure in failures if failure.get("status") == "semantic_unavailable")
        return {
            "labeled": len(labels),
            "semantic_unavailable": unavailable,
            "failed": len(failures) - unavailable,
        }


class FakeDigestRepository:
    def __init__(self, *, context=None):
        self.recorded_runs = []
        self.context = context
        self.replaced_digests = []
        self.digest_scans = []

    def due_digest_targets(self, *, now_ms, limit):
        return [
            {
                "admission_id": "admission-1",
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "24h",
                "scope": "matched",
            }
        ][:limit]

    def digest_context(self, *, target_type, target_id, window, scope, since_ms, max_mentions):
        if self.context is not None:
            return self.context
        mentions = [
            {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
            {"event_id": "event-2", "author_handle": "b", "status": "labeled"},
            {"event_id": "event-3", "author_handle": "b", "status": "labeled"},
        ]
        return {
            "target_type": target_type,
            "target_id": target_id,
            "window": window,
            "scope": scope,
            "mentions": mentions,
            "semantic_rows": mentions,
            "source_event_count": 3,
            "labeled_event_count": 3,
            "independent_author_count": 2,
            "allowed_refs": [],
        }

    def record_narrative_model_run(self, run, *, commit=True):
        self.recorded_runs.append(run)
        return run

    def replace_current_digest(self, digest, *, now_ms):
        self.replaced_digests.append(digest)
        return digest

    def mark_admissions_digest_scanned(self, admission_ids, *, next_due_at_ms, now_ms):
        self.digest_scans.append(
            {"admission_ids": list(admission_ids), "next_due_at_ms": next_due_at_ms, "now_ms": now_ms}
        )
        return {"updated": len(admission_ids)}


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

    def request_audit_for_label_mentions(self, *, run_id, request):
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class FailingNarrativeProvider:
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request):
        raise TimeoutError("provider timed out")

    def request_audit_for_label_mentions(self, *, run_id, request):
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request):
        raise TimeoutError("provider timed out")

    def request_audit_for_summarize_discussion(self, *, run_id, request):
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class UnexpectedDigestProvider:
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request):
        raise AssertionError("digest provider should not be called while semantics are still pending")

    def request_audit_for_summarize_discussion(self, *, run_id, request):
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class PartialFailureNarrativeProvider:
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request):
        return MentionSemanticsBatchResult(
            run_id=run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            labels=[],
            failures=[{"event_id": "event-1", "error": "semantic_unavailable"}],
            raw_response={"ok": False},
            agent_run_audit={"usage": {"input_tokens": 1}},
        )

    def request_audit_for_label_mentions(self, *, run_id, request):
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class UnknownLabelNarrativeProvider:
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request):
        return MentionSemanticsBatchResult(
            run_id=run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            labels=[
                MentionSemanticLabel(
                    event_id="event-unknown",
                    target_type="chain_token",
                    target_id="solana:So111",
                    trade_stance="bullish",
                    attention_valence="celebratory",
                    claim_type="price-action",
                    evidence_type="scanner-alert",
                    semantic_confidence=0.8,
                    evidence_refs=[
                        {
                            "ref_id": "event:event-unknown",
                            "kind": "event",
                            "source_table": "events",
                            "event_id": "event-unknown",
                        }
                    ],
                    status="labeled",
                )
            ],
            failures=[],
            raw_response={"ok": True},
            agent_run_audit={"usage": {"input_tokens": 1}},
        )

    def request_audit_for_label_mentions(self, *, run_id, request):
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


def _request_audit(*, stage, run_id):
    return {
        "backend": "openai_agents_sdk",
        "stage": stage,
        "run_id": run_id,
        "lane": f"narrative.{stage}",
        "input_hash": "sha256:request",
        "usage": {},
    }
