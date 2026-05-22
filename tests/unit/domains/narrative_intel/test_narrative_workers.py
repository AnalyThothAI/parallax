import asyncio
import inspect
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
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
from gmgn_twitter_intel.domains.narrative_intel.types.discussion_digest import (
    DigestArgument,
    DiscussionDigestResult,
    NarrativeCluster,
    TokenDiscussionDigest,
)
from gmgn_twitter_intel.domains.narrative_intel.types.mention_semantics import (
    MentionSemanticLabel,
    MentionSemanticsBatchResult,
)
from gmgn_twitter_intel.platform.agent_execution import AgentExecutionError, AgentExecutionErrorClass
from gmgn_twitter_intel.platform.cancellation import WORKER_HARD_TIMEOUT_CANCEL_REASON


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
        assert repo.recorded_run_commits == [False]

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
                    "window": "1h",
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
        assert repo.due_admissions_for_semantics_calls == [{"now_ms": 10_000, "limit": 10, "windows": ("1h",)}]
        assert repo.enqueued_source_event_ids == ["event-1", "event-2"]
        assert result.processed == 1

    asyncio.run(scenario())


def test_mention_semantics_enqueue_budget_counts_only_missing_rows():
    repo = FakeNarrativeRepository(
        due_mentions=[],
        due_admissions=[
            {
                "admission_id": "admission-1",
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
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
        existing_semantic_event_ids={"event-1", "event-2"},
    )
    db = FakeDB(repo)
    worker = MentionSemanticsWorker(
        name="mention_semantics",
        settings=fake_settings(
            max_semantic_rows_enqueued_per_cycle=3,
            max_pending_semantics_per_target=10,
        ),
        db=db,
        telemetry=SimpleNamespace(),
        provider=BarrierNarrativeProvider(db),
    )

    stats = worker._enqueue_missing_from_admissions_sync(now_ms=10_000)

    assert stats["semantic_existing"] == 2
    assert stats["semantic_inserted"] == 3
    assert stats["semantic_suppressed_budget"] == 0
    assert repo.enqueued_source_event_ids == ["event-3", "event-4", "event-5"]


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


def test_mention_semantics_worker_persists_cleanup_when_provider_call_is_cancelled():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(provider_failure_backoff_seconds=7),
            db=db,
            telemetry=SimpleNamespace(),
            provider=CancelledNarrativeProvider(),
        )

        with pytest.raises(asyncio.CancelledError):
            await worker.run_once(now_ms=10_000)

        assert repo.recorded_runs[0]["status"] == "failed"
        assert repo.recorded_runs[0]["error"] == "worker_timeout_cancelled"
        assert repo.recorded_runs[0]["trace_metadata_json"]["error_type"] == "CancelledError"
        assert repo.completed_batches[0]["failures"][0] == {
            "semantic_id": "semantic-1",
            "event_id": "event-1",
            "target_type": "chain_token",
            "target_id": "solana:So111",
            "schema_version": NARRATIVE_SCHEMA_VERSION,
            "text_fingerprint": "fp-1",
            "error": "worker_timeout_cancelled",
            "next_retry_at_ms": repo.recorded_runs[0]["finished_at_ms"] + 7_000,
        }

    asyncio.run(scenario())


def test_mention_semantics_capacity_denied_does_not_increment_retry_count():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=NoStartNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 0
        assert result.failed == 0
        assert result.skipped == 1
        assert result.notes["agent_backpressure"] == "capacity_denied"
        assert repo.recorded_runs == []
        assert repo.completed_batches == []

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


def test_mention_semantics_worker_hard_cuts_source_age_prune_and_claims_first():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(max_pending_semantics_per_target=5),
            db=db,
            telemetry=SimpleNamespace(),
            provider=BarrierNarrativeProvider(db),
        )

        result = await worker.run_once(now_ms=10_000)

        assert not hasattr(worker, "_prune_pending_backlog_sync")
        assert not any(str(key).startswith("prune_") for key in result.notes)
        assert result.processed == 1

    asyncio.run(scenario())


def test_mention_semantics_partial_enqueue_uses_short_retry_and_exposes_missing_backlog():
    async def scenario():
        repo = FakeNarrativeRepository(
            due_mentions=[],
            due_admissions=[
                {
                    "admission_id": "admission-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
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
                    "text_fingerprint": f"fp-{index}",
                    "source_received_at_ms": 9_000 + index,
                }
                for index in range(1, 6)
            ],
        )
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(
                interval_seconds=60.0,
                max_semantic_rows_enqueued_per_cycle=4,
                max_semantic_rows_enqueued_per_admission=2,
                max_pending_semantics_per_target=10,
                partial_enqueue_retry_seconds=5,
            ),
            db=db,
            telemetry=SimpleNamespace(),
            provider=BarrierNarrativeProvider(db),
        )

        result = await worker.run_once(now_ms=10_000)

        assert repo.enqueued_source_event_ids == ["event-1", "event-2"]
        assert result.notes["enqueue_semantic_inserted"] == 2
        assert result.notes["enqueue_missing_after_enqueue"] == 3
        assert result.notes["enqueue_semantic_suppressed_budget"] == 3
        assert repo.semantic_scans == [
            {"admission_ids": ["admission-1"], "next_due_at_ms": 15_000, "now_ms": 10_000}
        ]

    asyncio.run(scenario())


def test_mention_semantics_claim_passes_per_target_cycle_cap():
    repo = FakeNarrativeRepository()
    worker = MentionSemanticsWorker(
        name="mention_semantics",
        settings=fake_settings(max_semantics_claimed_per_target_per_cycle=3),
        db=FakeDB(repo),
        telemetry=SimpleNamespace(),
        provider=BarrierNarrativeProvider(FakeDB(repo)),
    )

    rows = worker._claim_due_rows_sync(now_ms=10_000, limit=10)

    assert len(rows) == 1
    assert repo.due_mentions_calls == [
        {"now_ms": 10_000, "limit": 10, "max_per_target": 3, "windows": ("1h",)}
    ]


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


def test_mention_semantics_worker_accepts_provider_event_ref_id_alias():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=EventRefAliasNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        batch = repo.completed_batches[0]
        assert result.processed == 1
        assert result.failed == 0
        assert batch["labels"][0]["event_id"] == "event-1"
        assert batch["failures"] == []

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
        assert repo.due_digest_target_calls == [{"now_ms": 10_000, "limit": 10, "windows": ("1h",)}]
        assert result.notes["llm_calls"] == 1
        assert result.notes["llm_failures"] == 1
        assert repo.recorded_runs[0]["stage"] == "discussion_digest"
        assert repo.recorded_runs[0]["status"] == "failed"
        assert repo.recorded_runs[0]["trace_metadata_json"]["lane"] == "narrative.discussion_digest"
        assert repo.recorded_runs[0]["trace_metadata_json"]["error_type"] == "TimeoutError"
        assert repo.digest_scans == [{"admission_ids": ["admission-1"], "next_due_at_ms": 610_000, "now_ms": 10_000}]

    asyncio.run(scenario())


def test_token_discussion_digest_worker_persists_cleanup_when_provider_call_is_cancelled():
    async def scenario():
        repo = FakeDigestRepository()
        db = FakeDB(repo)
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(provider_failure_backoff_seconds=7),
            db=db,
            telemetry=SimpleNamespace(),
            provider=CancelledNarrativeProvider(),
        )

        with pytest.raises(asyncio.CancelledError):
            await worker.run_once(now_ms=10_000)

        assert repo.recorded_runs[0]["stage"] == "discussion_digest"
        assert repo.recorded_runs[0]["status"] == "failed"
        assert repo.recorded_runs[0]["error"] == "worker_timeout_cancelled"
        assert repo.recorded_runs[0]["trace_metadata_json"]["error_type"] == "CancelledError"
        assert repo.digest_scans == [
            {
                "admission_ids": ["admission-1"],
                "next_due_at_ms": repo.recorded_runs[0]["finished_at_ms"] + 7_000,
                "now_ms": repo.recorded_runs[0]["finished_at_ms"],
            }
        ]

    asyncio.run(scenario())


def test_token_discussion_digest_worker_defers_threshold_targets_after_llm_cycle_budget():
    async def scenario():
        targets = [
            {
                "admission_id": "admission-1",
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
            },
            {
                "admission_id": "admission-2",
                "target_type": "chain_token",
                "target_id": "solana:Bonk",
                "window": "1h",
                "scope": "matched",
            },
        ]
        repo = FakeDigestRepository(targets=targets)
        db = FakeDB(repo)
        provider = CountingDigestProvider()
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(batch_size=2, max_llm_calls_per_cycle=1),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert provider.calls == ["solana:So111"]
        assert result.notes["ready"] == 1
        assert result.notes["pending"] == 1
        assert result.failed == 0
        assert result.notes["llm_calls"] == 1
        assert result.notes["deferred_llm_budget"] == 1
        assert result.notes["refresh_reasons"]["llm_cycle_budget_exhausted"] == 1
        assert repo.digest_scans[-1] == {
            "admission_ids": ["admission-2"],
            "next_due_at_ms": 11_000,
            "now_ms": 10_000,
        }

    asyncio.run(scenario())


def test_token_discussion_digest_worker_defers_after_provider_failure_budget():
    async def scenario():
        targets = [
            {
                "admission_id": "admission-1",
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
            },
            {
                "admission_id": "admission-2",
                "target_type": "chain_token",
                "target_id": "solana:Bonk",
                "window": "1h",
                "scope": "matched",
            },
        ]
        repo = FakeDigestRepository(targets=targets)
        db = FakeDB(repo)
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(
                batch_size=2,
                max_llm_calls_per_cycle=10,
                max_llm_failures_per_cycle=1,
                provider_failure_backoff_seconds=7,
            ),
            db=db,
            telemetry=SimpleNamespace(),
            provider=FailingNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.notes["failed"] == 1
        assert result.notes["pending"] == 1
        assert result.notes["llm_calls"] == 1
        assert result.notes["llm_failures"] == 1
        assert result.notes["deferred_llm_budget"] == 1
        assert result.notes["refresh_reasons"]["llm_failure_budget_exhausted"] == 1
        assert repo.digest_scans == [
            {"admission_ids": ["admission-1"], "next_due_at_ms": 17_000, "now_ms": 10_000},
            {"admission_ids": ["admission-2"], "next_due_at_ms": 11_000, "now_ms": 10_000},
        ]

    asyncio.run(scenario())


def test_digest_capacity_denied_marks_pending_not_failed():
    async def scenario():
        repo = FakeDigestRepository()
        db = FakeDB(repo)
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=NoStartNarrativeProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 1
        assert result.failed == 0
        assert result.notes["pending"] == 1
        assert result.notes["failed"] == 0
        assert result.notes["refresh_reasons"]["agent_backpressure"] == 1
        assert repo.recorded_runs == []
        assert repo.digest_scans == [{"admission_ids": ["admission-1"], "next_due_at_ms": 11_000, "now_ms": 10_000}]

    asyncio.run(scenario())


def test_token_discussion_digest_worker_keeps_labeling_gap_pending_and_reschedules():
    async def scenario():
        repo = FakeDigestRepository(
            context={
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "mentions": [
                    {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "author_handle": "b", "status": "labeled"},
                    {"event_id": "event-3", "author_handle": "c", "status": "labeled"},
                    {"event_id": "event-4", "author_handle": "d", "status": "labeled"},
                    {"event_id": "event-5", "author_handle": "e", "status": "queued"},
                    {"event_id": "event-6", "author_handle": "f", "status": "queued"},
                    {"event_id": "event-7", "author_handle": "g", "status": "queued"},
                    {"event_id": "event-8", "author_handle": "h", "status": "retryable_error"},
                    {"event_id": "event-9", "author_handle": "i", "status": "retryable_error"},
                    {"event_id": "event-10", "author_handle": "j", "status": "retryable_error"},
                ],
                "semantic_rows": [
                    {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "author_handle": "b", "status": "labeled"},
                    {"event_id": "event-3", "author_handle": "c", "status": "labeled"},
                    {"event_id": "event-4", "author_handle": "d", "status": "labeled"},
                    {"event_id": "event-5", "author_handle": "e", "status": "queued"},
                    {"event_id": "event-6", "author_handle": "f", "status": "queued"},
                    {"event_id": "event-7", "author_handle": "g", "status": "queued"},
                    {"event_id": "event-8", "author_handle": "h", "status": "retryable_error"},
                    {"event_id": "event-9", "author_handle": "i", "status": "retryable_error"},
                    {"event_id": "event-10", "author_handle": "j", "status": "retryable_error"},
                ],
                "source_event_count": 10,
                "semantic_row_count": 10,
                "missing_semantic_count": 0,
                "pending_semantic_count": 3,
                "retryable_semantic_count": 3,
                "terminal_unavailable_count": 0,
                "labeled_event_count": 4,
                "independent_author_count": 10,
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
        assert repo.digest_scans == [{"admission_ids": ["admission-1"], "next_due_at_ms": 70_000, "now_ms": 10_000}]

    asyncio.run(scenario())


def test_token_discussion_digest_worker_does_not_claim_unsupported_5m_by_default():
    async def scenario():
        repo = FakeDigestRepository(
            targets=[
                {
                    "admission_id": "admission-5m",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "5m",
                    "scope": "matched",
                }
            ]
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

        assert result.skipped == 1
        assert result.notes == {"reason": "no_due_digest_targets", "claimed": 0}
        assert repo.due_digest_target_calls == [{"now_ms": 10_000, "limit": 10, "windows": ("1h",)}]
        assert result.processed == 0
        assert result.failed == 0
        assert repo.replaced_digests == []
        assert repo.digest_scans == []

    asyncio.run(scenario())


def test_token_discussion_digest_worker_defer_below_threshold_delta_with_ready_digest():
    async def scenario():
        repo = FakeDigestRepository(
            context={
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "source_event_ids": ["event-1", "event-2", "event-3", "event-4"],
                "source_fingerprint": "source-current",
                "mentions": [
                    {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "author_handle": "b", "status": "labeled"},
                    {"event_id": "event-3", "author_handle": "c", "status": "labeled"},
                    {"event_id": "event-4", "author_handle": "d", "status": "labeled"},
                ],
                "semantic_rows": [{"status": "labeled"} for _ in range(4)],
                "source_event_count": 4,
                "semantic_row_count": 4,
                "missing_semantic_count": 0,
                "pending_semantic_count": 0,
                "retryable_semantic_count": 0,
                "terminal_unavailable_count": 0,
                "labeled_event_count": 4,
                "independent_author_count": 4,
                "allowed_refs": [{"ref_id": "event:event-1", "kind": "event", "source_table": "events"}],
            },
            last_ready_digest={
                "status": "ready",
                "source_event_ids_json": ["event-1", "event-2", "event-3"],
                "independent_author_count": 4,
                "display_current_until_ms": 10_001,
            },
            targets=[
                {
                    "admission_id": "admission-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
                    "scope": "matched",
                }
            ],
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

        assert result.processed == 1
        assert result.notes["deferred_epoch_policy"] == 1
        assert result.notes["refresh_reasons"]["no_material_delta"] == 1
        assert repo.replaced_digests == []
        assert repo.digest_scans == [{"admission_ids": ["admission-1"], "next_due_at_ms": 910_000, "now_ms": 10_000}]

    asyncio.run(scenario())


def test_token_discussion_digest_worker_keeps_ready_digest_when_semantics_pending():
    async def scenario():
        repo = FakeDigestRepository(
            context={
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "source_event_ids": ["event-1", "event-2", "event-3", "event-4"],
                "source_fingerprint": "source-current",
                "mentions": [
                    {"event_id": f"event-{index}", "author_handle": str(index), "status": "queued"}
                    for index in range(1, 5)
                ],
                "semantic_rows": [],
                "source_event_count": 4,
                "semantic_row_count": 0,
                "missing_semantic_count": 4,
                "pending_semantic_count": 0,
                "retryable_semantic_count": 0,
                "terminal_unavailable_count": 0,
                "labeled_event_count": 0,
                "independent_author_count": 4,
                "allowed_refs": [],
            },
            last_ready_digest={
                "status": "ready",
                "source_event_ids_json": ["event-1", "event-2", "event-3"],
                "independent_author_count": 4,
                "display_current_until_ms": 10_001,
            },
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

        assert result.processed == 1
        assert result.notes["deferred_epoch_policy"] == 1
        assert repo.replaced_digests == []

    asyncio.run(scenario())


def test_token_discussion_digest_worker_writes_status_digest_without_ready_snapshot():
    async def scenario():
        repo = FakeDigestRepository(
            context={
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "source_event_ids": [f"event-{index}" for index in range(1, 8)],
                "source_fingerprint": "source-current",
                "mentions": [
                    {"event_id": "event-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "author_handle": "b", "status": "queued"},
                    {"event_id": "event-3", "author_handle": "c", "status": "queued"},
                ],
                "semantic_rows": [{"event_id": "event-1", "author_handle": "a", "status": "labeled"}],
                "source_event_count": 7,
                "semantic_row_count": 1,
                "missing_semantic_count": 6,
                "pending_semantic_count": 0,
                "retryable_semantic_count": 0,
                "terminal_unavailable_count": 0,
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
        digest = repo.replaced_digests[0]
        assert digest["status"] == "pending"
        assert digest["data_gaps"] == [{"reason": "semantic_labeling_pending"}]
        assert digest["epoch_policy_version"] == "token-narrative-epoch-v1"
        assert digest["source_event_ids"] == [f"event-{index}" for index in range(1, 8)]
        assert digest["refresh_reason"] == "initial_ready"

    asyncio.run(scenario())


def test_token_discussion_digest_worker_counts_terminal_semantic_unavailable():
    async def scenario():
        repo = FakeDigestRepository(
            context={
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "mentions": [
                    {"event_id": "event-1", "author_handle": "a", "status": "semantic_unavailable"},
                    {"event_id": "event-2", "author_handle": "b", "status": "semantic_unavailable"},
                    {"event_id": "event-3", "author_handle": "c", "status": "semantic_unavailable"},
                ],
                "semantic_rows": [
                    {"event_id": "event-1", "author_handle": "a", "status": "semantic_unavailable"},
                    {"event_id": "event-2", "author_handle": "b", "status": "semantic_unavailable"},
                    {"event_id": "event-3", "author_handle": "c", "status": "semantic_unavailable"},
                ],
                "source_event_count": 3,
                "semantic_row_count": 3,
                "missing_semantic_count": 0,
                "pending_semantic_count": 0,
                "retryable_semantic_count": 0,
                "terminal_unavailable_count": 3,
                "labeled_event_count": 0,
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

        assert result.processed == 1
        assert result.failed == 0
        assert result.notes["semantic_unavailable"] == 1
        assert result.notes["refresh_reasons"]["semantic_provider_unavailable"] == 1
        assert repo.replaced_digests[0]["status"] == "semantic_unavailable"
        assert repo.replaced_digests[0]["data_gaps"] == [{"reason": "semantic_provider_unavailable"}]
        assert repo.digest_scans == [{"admission_ids": ["admission-1"], "next_due_at_ms": 910_000, "now_ms": 10_000}]

    asyncio.run(scenario())


def test_token_discussion_digest_worker_publishes_successful_refresh_as_ready():
    async def scenario():
        repo = FakeDigestRepository(
            context={
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "mentions": [
                    {
                        "event_id": "event-1",
                        "semantic_id": "semantic-1",
                        "author_handle": "a",
                        "status": "labeled",
                        "evidence_refs_json": [{"ref_id": "event:event-1", "kind": "event", "source_table": "events"}],
                    },
                    {
                        "event_id": "event-2",
                        "semantic_id": "semantic-2",
                        "author_handle": "b",
                        "status": "labeled",
                        "evidence_refs_json": [{"ref_id": "event:event-2", "kind": "event", "source_table": "events"}],
                    },
                    {
                        "event_id": "event-3",
                        "semantic_id": "semantic-3",
                        "author_handle": "b",
                        "status": "labeled",
                        "evidence_refs_json": [{"ref_id": "event:event-3", "kind": "event", "source_table": "events"}],
                    },
                ],
                "semantic_rows": [
                    {"event_id": "event-1", "semantic_id": "semantic-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "semantic_id": "semantic-2", "author_handle": "b", "status": "labeled"},
                    {"event_id": "event-3", "semantic_id": "semantic-3", "author_handle": "b", "status": "labeled"},
                ],
                "source_event_ids": ["event-1", "event-2", "event-3"],
                "source_fingerprint": "source-current",
                "source_window_start_ms": 1_000,
                "source_window_end_ms": 9_000,
                "source_event_count": 3,
                "labeled_event_count": 3,
                "independent_author_count": 2,
                "allowed_refs": [
                    {"ref_id": "event:event-1", "kind": "event", "source_table": "events"},
                    {"ref_id": "event:event-2", "kind": "event", "source_table": "events"},
                    {"ref_id": "event:event-3", "kind": "event", "source_table": "events"},
                    {"ref_id": "semantic:semantic-1", "kind": "semantic", "source_table": "token_mention_semantics"},
                    {"ref_id": "semantic:semantic-2", "kind": "semantic", "source_table": "token_mention_semantics"},
                    {"ref_id": "semantic:semantic-3", "kind": "semantic", "source_table": "token_mention_semantics"},
                ],
            }
        )
        db = FakeDB(repo)
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=StaleButValidDigestProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.notes["ready"] == 1
        assert result.failed == 0
        assert repo.replaced_digests[0]["status"] == "ready"
        assert repo.replaced_digests[0]["epoch_policy_version"] == "token-narrative-epoch-v1"
        assert repo.replaced_digests[0]["source_event_ids"] == ["event-1", "event-2", "event-3"]
        assert repo.replaced_digests[0]["source_window_start_ms"] == 1_000
        assert repo.replaced_digests[0]["source_window_end_ms"] == 9_000
        assert repo.replaced_digests[0]["display_current_until_ms"] == 910_000
        assert repo.replaced_digests[0]["refresh_reason"] == "initial_ready"
        assert repo.recorded_runs[0]["status"] == "done"

    asyncio.run(scenario())


def test_token_discussion_digest_worker_repairs_sparse_provider_digest_as_ready():
    async def scenario():
        repo = FakeDigestRepository(
            context={
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "mentions": [
                    {
                        "event_id": "event-1",
                        "semantic_id": "semantic-1",
                        "author_handle": "a",
                        "status": "labeled",
                        "evidence_refs_json": [{"ref_id": "event:event-1", "kind": "event", "source_table": "events"}],
                    },
                    {
                        "event_id": "event-2",
                        "semantic_id": "semantic-2",
                        "author_handle": "b",
                        "status": "labeled",
                        "evidence_refs_json": [{"ref_id": "event:event-2", "kind": "event", "source_table": "events"}],
                    },
                    {
                        "event_id": "event-3",
                        "semantic_id": "semantic-3",
                        "author_handle": "c",
                        "status": "labeled",
                        "evidence_refs_json": [{"ref_id": "event:event-3", "kind": "event", "source_table": "events"}],
                    },
                ],
                "semantic_rows": [
                    {"event_id": "event-1", "semantic_id": "semantic-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "semantic_id": "semantic-2", "author_handle": "b", "status": "labeled"},
                    {"event_id": "event-3", "semantic_id": "semantic-3", "author_handle": "c", "status": "labeled"},
                ],
                "source_event_count": 3,
                "labeled_event_count": 3,
                "independent_author_count": 3,
                "allowed_refs": [
                    {"ref_id": "event:event-1", "kind": "event", "source_table": "events"},
                    {"ref_id": "event:event-2", "kind": "event", "source_table": "events"},
                    {"ref_id": "event:event-3", "kind": "event", "source_table": "events"},
                    {"ref_id": "semantic:semantic-1", "kind": "semantic", "source_table": "token_mention_semantics"},
                    {"ref_id": "semantic:semantic-2", "kind": "semantic", "source_table": "token_mention_semantics"},
                    {"ref_id": "semantic:semantic-3", "kind": "semantic", "source_table": "token_mention_semantics"},
                ],
            }
        )
        db = FakeDB(repo)
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=SparseDigestProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        digest = repo.replaced_digests[0]
        assert result.notes["ready"] == 1
        assert result.failed == 0
        assert digest["status"] == "ready"
        assert digest["dominant_narratives"]
        assert digest["bull_view"]["evidence_refs"]
        assert digest["evidence_refs"]

    asyncio.run(scenario())


def fake_settings(**overrides):
    values = dict(
        enabled=True,
        interval_seconds=1.0,
        timeout_seconds=0.0,
        statement_timeout_seconds=9.0,
        batch_size=10,
        windows=("1h",),
        scopes=("matched",),
        admission_limit=10,
        source_limit=100,
        model_version="gpt-test",
        max_semantic_rows_enqueued_per_admission=20,
        max_semantics_claimed_per_target_per_cycle=3,
        partial_enqueue_retry_seconds=5,
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
        windows=("1h",),
        scopes=("matched",),
        admission_limit=10,
        source_limit=100,
        hot_rank_limit=50,
        min_rank_score=30,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def fake_digest_settings(**overrides):
    values = dict(
        enabled=True,
        interval_seconds=1.0,
        timeout_seconds=0.0,
        statement_timeout_seconds=9.0,
        batch_size=10,
        min_source_mentions=3,
        min_independent_authors=2,
        min_semantic_coverage=0.35,
        max_mentions_per_digest=10,
        max_llm_calls_per_cycle=3,
        max_llm_failures_per_cycle=2,
        provider_failure_backoff_seconds=600,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


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
        existing_semantic_event_ids=None,
    ):
        self.radar_rows = list(radar_rows or [])
        self.source_rows = list(source_rows or [])
        self.due_mentions = due_mentions
        self.due_admissions = due_admissions
        self.pending_semantics = dict(pending_semantics or {})
        self.existing_semantic_event_ids = set(existing_semantic_event_ids or set())
        self.recorded_runs = []
        self.recorded_run_commits = []
        self.completed_batches = []
        self.upserted_admissions = []
        self.suppressed_frontiers = []
        self.scanned_admission_ids = []
        self.enqueued_source_event_ids = []
        self.semantic_scans = []
        self.due_mentions_calls = []
        self.due_admissions_for_semantics_calls = []

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

    def due_admissions_for_semantics(self, *, now_ms, limit, windows):
        self.due_admissions_for_semantics_calls.append({"now_ms": now_ms, "limit": limit, "windows": tuple(windows)})
        if self.due_admissions is not None:
            return [admission for admission in self.due_admissions if admission.get("window") in windows][:limit]
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

    def missing_source_rows_for_mention_semantics(self, admission, *, limit, schema_version):
        return [
            row
            for row in self.source_rows[:limit]
            if str(row.get("event_id")) not in self.existing_semantic_event_ids
        ]

    def pending_mention_semantics_count(self, *, target_type, target_id, schema_version, model_version=None):
        return int(self.pending_semantics.get((target_type, target_id), 0))

    def enqueue_missing_mention_semantics(self, source_rows, *, schema_version, model_version, now_ms):
        self.enqueued_source_event_ids.extend(str(row["event_id"]) for row in source_rows)
        inserted_rows = [
            row
            for row in source_rows
            if str(row.get("event_id")) not in self.existing_semantic_event_ids
        ]
        if self.due_mentions is not None:
            self.due_mentions.extend(inserted_rows)
        return {"inserted": len(inserted_rows), "existing": len(source_rows) - len(inserted_rows)}

    def mark_admissions_semantics_scanned(self, admission_ids, *, next_due_at_ms, now_ms):
        self.scanned_admission_ids.extend(admission_ids)
        self.semantic_scans.append(
            {"admission_ids": list(admission_ids), "next_due_at_ms": next_due_at_ms, "now_ms": now_ms}
        )
        return {"updated": len(admission_ids)}

    def due_mentions_for_labeling(self, *, now_ms, limit, windows, max_per_target=None):
        self.due_mentions_calls.append(
            {"now_ms": now_ms, "limit": limit, "max_per_target": max_per_target, "windows": tuple(windows)}
        )
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
        self.recorded_run_commits.append(commit)
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
    def __init__(self, *, context=None, contexts=None, targets=None, last_ready_digest=None, market_context=None):
        self.recorded_runs = []
        self.context = context
        self.contexts = dict(contexts or {})
        self.targets = list(targets) if targets is not None else None
        self.last_ready_digest = last_ready_digest
        self.market_context = dict(market_context or {})
        self.replaced_digests = []
        self.digest_scans = []
        self.digest_context_calls = []
        self.due_digest_target_calls = []

    def due_digest_targets(self, *, now_ms, limit, windows=("1h",)):
        self.due_digest_target_calls.append({"now_ms": now_ms, "limit": limit, "windows": tuple(windows)})
        if self.targets is not None:
            return [target for target in self.targets if target.get("window") in windows][:limit]
        return [
            {
                "admission_id": "admission-1",
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
            }
        ][:limit]

    def digest_context(self, *, target_type, target_id, window, scope, max_mentions):
        self.digest_context_calls.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "max_mentions": max_mentions,
            }
        )
        if target_id in self.contexts:
            return self.contexts[target_id]
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
            "semantic_row_count": 3,
            "missing_semantic_count": 0,
            "pending_semantic_count": 0,
            "retryable_semantic_count": 0,
            "terminal_unavailable_count": 0,
            "labeled_event_count": 3,
            "independent_author_count": 2,
            "allowed_refs": [{"ref_id": "event:event-1", "kind": "event", "source_table": "events"}],
        }

    def latest_ready_digest_for_target(self, *, target_type, target_id, window, scope, schema_version):
        return self.last_ready_digest

    def market_context_for_admission(self, admission, *, last_ready_digest):
        return self.market_context

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


class CancelledNarrativeProvider(FailingNarrativeProvider):
    async def label_mentions(self, *, run_id, request):
        raise asyncio.CancelledError(WORKER_HARD_TIMEOUT_CANCEL_REASON)

    async def summarize_discussion(self, *, run_id, request):
        raise asyncio.CancelledError(WORKER_HARD_TIMEOUT_CANCEL_REASON)


class NoStartNarrativeProvider(FailingNarrativeProvider):
    async def label_mentions(self, *, run_id, request):
        raise AgentExecutionError(
            AgentExecutionErrorClass.CAPACITY_DENIED,
            "agent lane capacity denied",
            execution_started=False,
        )

    async def summarize_discussion(self, *, run_id, request):
        raise AgentExecutionError(
            AgentExecutionErrorClass.CAPACITY_DENIED,
            "agent lane capacity denied",
            execution_started=False,
        )


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


class StaleButValidDigestProvider:
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request):
        ref = {"ref_id": "event:event-1", "kind": "event", "source_table": "events"}
        return DiscussionDigestResult(
            run_id=run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            digest=TokenDiscussionDigest(
                target_type=request.target_type,
                target_id=request.target_id,
                window=request.window,
                scope=request.scope,
                schema_version=request.schema_version,
                model_version="gpt-test",
                status="stale",
                headline_zh="SOL discussion turns to breakout",
                dominant_narratives=[
                    NarrativeCluster(
                        cluster_key="breakout",
                        label_zh="breakout narrative",
                        summary_zh="discussion concentrates on breakout and chase.",
                        evidence_refs=[ref],
                    )
                ],
                bull_view=DigestArgument(summary_zh="bulls see breakout", evidence_refs=[ref]),
                bear_view=DigestArgument(summary_zh="bears worry about chase", evidence_refs=[]),
                semantic_coverage=1.0,
                source_event_count=3,
                labeled_event_count=3,
                independent_author_count=2,
                evidence_refs=[ref],
                computed_at_ms=10_000,
            ),
            raw_response={"ok": True},
            agent_run_audit={"usage": {"input_tokens": 1}},
        )

    def request_audit_for_summarize_discussion(self, *, run_id, request):
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class CountingDigestProvider(StaleButValidDigestProvider):
    def __init__(self):
        self.calls = []

    async def summarize_discussion(self, *, run_id, request):
        self.calls.append(request.target_id)
        return await super().summarize_discussion(run_id=run_id, request=request)


class SparseDigestProvider:
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request):
        return DiscussionDigestResult(
            run_id=run_id,
            schema_version=request.schema_version,
            prompt_version=request.prompt_version,
            digest={
                "target_type": request.target_type,
                "target_id": request.target_id,
                "window": request.window,
                "scope": request.scope,
                "schema_version": request.schema_version,
                "model_version": "gpt-test",
                "status": "stale",
                "semantic_coverage": 0.0,
                "source_event_count": 0,
                "labeled_event_count": 0,
                "independent_author_count": 0,
                "computed_at_ms": 10_000,
            },
            raw_response={"ok": True},
            agent_run_audit={"usage": {"input_tokens": 1}},
        )

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


class EventRefAliasNarrativeProvider:
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
                    event_id="event:event-1",
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


def _request_audit(*, stage, run_id):
    return {
        "backend": "openai_agents_sdk",
        "stage": stage,
        "run_id": run_id,
        "lane": f"narrative.{stage}",
        "input_hash": "sha256:request",
        "usage": {},
    }
