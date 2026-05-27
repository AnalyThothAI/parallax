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
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from gmgn_twitter_intel.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
)
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


def test_narrative_admission_worker_skips_empty_dirty_queue_without_broad_scan():
    repo = FakeNarrativeRepository()
    dirty_targets = FakeDirtyTargetRepository(claims=[])
    db = FakeDB(repo, narrative_admission_dirty_targets=dirty_targets)
    worker = NarrativeAdmissionWorker(
        name="narrative_admission",
        settings=fake_admission_settings(),
        db=db,
        telemetry=SimpleNamespace(),
    )

    result = worker.run_once_sync(now_ms=10_000)

    assert result.skipped == 1
    assert result.notes["reason"] == "no_due_narrative_admission_targets"
    assert result.notes["claimed"] == 0
    assert result.notes["source_rows_scanned"] == 0
    assert result.notes["targets_loaded"] == 0
    assert result.notes["rows_written"] == 0
    assert dirty_targets.claim_due_calls == [
        {"now_ms": 10_000, "limit": 10, "lease_owner": "narrative_admission", "lease_ms": 60_000, "commit": False}
    ]
    assert repo.admitted_radar_rows_calls == []
    assert repo.admissions_for_window_scope_calls == []
    assert repo.deleted_frontiers == []
    assert repo.load_target_calls == []
    assert db.transaction_entries == 1


def test_narrative_admission_worker_claims_target_and_recomputes_exact_source_set():
    async def scenario():
        repo = FakeNarrativeRepository(
            target_contexts={
                ("chain_token", "solana:So111", "1h", "matched"): {
                    "radar_row": {
                        "target_type": "chain_token",
                        "target_id": "solana:So111",
                        "rank": 1,
                        "rank_score": 90,
                        "source_event_ids_json": ["event-old"],
                        "computed_at_ms": 10_000,
                        "source_max_received_at_ms": 9_000,
                    },
                    "existing_admission": None,
                }
            },
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
        dirty_targets = FakeDirtyTargetRepository(
            claims=[
                {
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
                    "scope": "matched",
                    "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "payload_hash": "payload-1",
                    "lease_owner": "narrative_admission",
                    "attempt_count": 1,
                }
            ]
        )
        digest_dirty_targets = FakeDirtyTargetRepository()
        db = FakeDB(
            repo,
            narrative_admission_dirty_targets=dirty_targets,
            discussion_digest_dirty_targets=digest_dirty_targets,
        )
        worker = NarrativeAdmissionWorker(
            name="narrative_admission",
            settings=fake_admission_settings(),
            db=db,
            telemetry=SimpleNamespace(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 3
        assert result.notes["claimed"] == 1
        assert result.notes["targets_loaded"] == 1
        assert result.notes["source_rows_scanned"] == 1
        assert result.notes["rows_written"] == 3
        assert repo.load_target_calls == [
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "schema_version": NARRATIVE_SCHEMA_VERSION,
            }
        ]
        assert repo.upserted_admissions[0]["source_event_ids"] == ["event-1"]
        assert repo.upserted_admissions[0]["projection_computed_at_ms"] == 10_000
        assert repo.upserted_admissions[0]["source_window_end_ms"] == 10_000
        assert repo.upserted_admissions[0]["source_max_received_at_ms"] == 9_000
        assert repo.upserted_admissions[0]["source_event_count"] == 1
        assert repo.upserted_admissions[0]["independent_author_count"] == 1
        assert repo.enqueued_source_event_ids == ["event-1"]
        assert digest_dirty_targets.enqueued_targets == [
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "matched",
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "schema_version": NARRATIVE_SCHEMA_VERSION,
                "source_watermark_ms": 9_000,
                "priority": repo.upserted_admissions[0]["priority"],
            }
        ]
        assert dirty_targets.mark_done_calls == [{"claims": dirty_targets.claimed, "now_ms": 10_000, "commit": False}]
        assert repo.admitted_radar_rows_calls == []
        assert repo.admissions_for_window_scope_calls == []
        assert repo.deleted_frontiers == []

    asyncio.run(scenario())


def test_narrative_admission_worker_stales_only_claimed_missing_target():
    repo = FakeNarrativeRepository(
        target_contexts={
            ("chain_token", "solana:Exited", "1h", "matched"): {
                "radar_row": None,
                "existing_admission": {
                    "admission_id": "admission-exited",
                    "target_type": "chain_token",
                    "target_id": "solana:Exited",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "status": "admitted",
                    "source_event_ids_json": ["event-exited"],
                },
            }
        }
    )
    dirty_targets = FakeDirtyTargetRepository(
        claims=[
            {
                "target_type": "chain_token",
                "target_id": "solana:Exited",
                "window": "1h",
                "scope": "matched",
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "schema_version": NARRATIVE_SCHEMA_VERSION,
                "payload_hash": "payload-exit",
                "lease_owner": "narrative_admission",
                "attempt_count": 1,
            }
        ]
    )
    db = FakeDB(repo, narrative_admission_dirty_targets=dirty_targets)
    worker = NarrativeAdmissionWorker(
        name="narrative_admission",
        settings=fake_admission_settings(),
        db=db,
        telemetry=SimpleNamespace(),
    )

    result = worker.run_once_sync(now_ms=10_000)

    assert result.processed == 1
    assert result.notes["admissions_staled"] == 1
    assert result.notes["digests_staled"] == 0
    assert result.notes["semantics_staled"] == 0
    assert repo.staled_admission_targets == [
        {
            "target_type": "chain_token",
            "target_id": "solana:Exited",
            "window": "1h",
            "scope": "matched",
            "schema_version": NARRATIVE_SCHEMA_VERSION,
            "now_ms": 10_000,
            "commit": False,
        }
    ]
    assert repo.deleted_frontiers == []
    assert dirty_targets.mark_done_calls == [{"claims": dirty_targets.claimed, "now_ms": 10_000, "commit": False}]


def test_narrative_admission_worker_marks_claim_error_with_completion_token():
    repo = FakeNarrativeRepository()

    def fail_load(**kwargs):
        raise RuntimeError("forced exact load failure")

    repo.load_radar_admission_target = fail_load
    dirty_targets = FakeDirtyTargetRepository(
        claims=[
            {
                "target_type": "chain_token",
                "target_id": "solana:Failed",
                "window": "1h",
                "scope": "matched",
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "schema_version": NARRATIVE_SCHEMA_VERSION,
                "payload_hash": "payload-failed",
                "lease_owner": "narrative_admission",
                "attempt_count": 1,
            }
        ]
    )
    db = FakeDB(repo, narrative_admission_dirty_targets=dirty_targets)
    worker = NarrativeAdmissionWorker(
        name="narrative_admission",
        settings=fake_admission_settings(error_retry_seconds=7),
        db=db,
        telemetry=SimpleNamespace(),
    )

    result = worker.run_once_sync(now_ms=10_000)

    assert result.failed == 1
    assert result.processed == 0
    assert dirty_targets.mark_done_calls == []
    assert dirty_targets.mark_error_calls == [
        {
            "claims": dirty_targets.claimed,
            "error": "RuntimeError: forced exact load failure",
            "now_ms": 10_000,
            "retry_ms": 7_000,
            "commit": False,
        }
    ]


def test_mention_semantics_worker_empty_queue_does_not_scan_admissions():
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

        assert result.skipped == 1
        assert result.notes["reason"] == "no_due_mentions"
        assert result.notes["claimed"] == 0
        assert result.notes["source_rows_scanned"] == 0
        assert result.notes["targets_loaded"] == 0
        assert result.notes["rows_written"] == 0
        assert repo.due_admissions_for_semantics_calls == []
        assert repo.pending_semantics_count_calls == []
        assert repo.enqueued_source_event_ids == []

    asyncio.run(scenario())


def test_mention_semantics_worker_claims_only_existing_semantic_rows():
    async def scenario():
        repo = FakeNarrativeRepository(
            due_mentions=[
                {
                    "semantic_id": "semantic-ready",
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "ready row",
                    "text_fingerprint": "fp-ready",
                }
            ],
            due_admissions=[
                {
                    "admission_id": "admission-1h",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
                    "scope": "all",
                    "source_event_ids_json": ["event-1"],
                }
            ],
            source_rows=[
                {
                    "event_id": "event-new",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "new row",
                    "text_fingerprint": "fp-new",
                    "source_received_at_ms": 9_900,
                }
            ],
        )
        db = FakeDB(repo)
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(windows=("1h",), scopes=("all",)),
            db=db,
            telemetry=SimpleNamespace(),
            provider=BarrierNarrativeProvider(db),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.notes["claimed"] == 1
        assert result.notes["source_rows_scanned"] == 0
        assert result.notes["targets_loaded"] == 1
        assert result.processed == 1
        assert repo.enqueued_source_event_ids == []
        assert repo.due_admissions_for_semantics_calls == []
        assert db.discussion_digest_dirty_targets.enqueued_targets == [
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "window": "1h",
                "scope": "all",
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "schema_version": NARRATIVE_SCHEMA_VERSION,
                "source_watermark_ms": 0,
                "priority": 0,
            }
        ]
        assert repo.claim_due_mention_semantics_calls == [
            {
                "now_ms": 10_000,
                "limit": 10,
                "lease_owner": "mention_semantics",
                "lease_ms": 60_000,
                "max_per_target": 3,
            }
        ]

    asyncio.run(scenario())


def test_mention_semantics_worker_has_no_runtime_admission_enqueue_path():
    repo = FakeNarrativeRepository(due_mentions=[])
    db = FakeDB(repo)
    worker = MentionSemanticsWorker(
        name="mention_semantics",
        settings=fake_settings(),
        db=db,
        telemetry=SimpleNamespace(),
        provider=BarrierNarrativeProvider(db),
    )

    assert not hasattr(worker, "_enqueue_missing_from_admissions_sync")
    assert not hasattr(worker, "_missing_source_rows_for_semantics")


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
            "lease_owner": "mention_semantics",
            "attempt_count": 1,
            "error": "worker_timeout_cancelled",
            "next_retry_at_ms": repo.recorded_runs[0]["finished_at_ms"] + 7_000,
        }

    asyncio.run(scenario())


def test_mention_semantics_capacity_denied_does_not_increment_retry_count():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        provider = NoStartNarrativeProvider()
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 0
        assert result.failed == 0
        assert result.skipped == 1
        assert result.notes["claimed"] == 0
        assert result.notes["agent_backpressure"] == "capacity_denied"
        assert result.notes["rows_written"] == 0
        assert provider.reserve_calls == ["narrative.mention_semantics"]
        assert repo.claim_due_mention_semantics_calls == []
        assert repo.recorded_runs == []
        assert repo.completed_batches == []
        assert repo.released_semantic_claims == []

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


def test_mention_semantics_no_start_backpressure_leaves_due_rows_unclaimed():
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
                }
            ]
        )
        db = FakeDB(repo)
        provider = NoStartNarrativeProvider()
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(provider_failure_backoff_seconds=7),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.skipped == 1
        assert result.notes["claimed"] == 0
        assert result.notes["agent_backpressure"] == "capacity_denied"
        assert result.notes["rows_written"] == 0
        assert provider.reserve_calls == ["narrative.mention_semantics"]
        assert repo.claim_due_mention_semantics_calls == []
        assert repo.released_semantic_claims == []
        assert repo.recorded_runs == []
        assert repo.completed_batches == []

    asyncio.run(scenario())


def test_mention_semantics_provider_started_validation_error_writes_failed_model_run():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        provider = InvalidMentionResultProvider()
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.failed == 1
        assert provider.reserve_calls == ["narrative.mention_semantics"]
        assert provider.release_calls == 1
        assert repo.recorded_runs[0]["stage"] == "mention_semantics"
        assert repo.recorded_runs[0]["status"] == "failed"
        assert repo.recorded_runs[0]["execution_started"] is True
        assert repo.recorded_runs[0]["trace_metadata_json"]["error_type"] == "AttributeError"
        assert repo.completed_batches[0]["failures"][0]["event_id"] == "event-1"

    asyncio.run(scenario())


def test_mention_semantics_releases_reservation_when_request_audit_fails():
    async def scenario():
        repo = FakeNarrativeRepository()
        db = FakeDB(repo)
        provider = AuditFailingMentionProvider()
        worker = MentionSemanticsWorker(
            name="mention_semantics",
            settings=fake_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        with pytest.raises(RuntimeError, match="request audit failed"):
            await worker.run_once(now_ms=10_000)

        assert provider.release_calls == 1

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
    assert repo.claim_due_mention_semantics_calls == [
        {
            "now_ms": 10_000,
            "limit": 10,
            "lease_owner": "mention_semantics",
            "lease_ms": 60_000,
            "max_per_target": 3,
        }
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
        assert db.discussion_digest_dirty_targets.claim_due_calls == [
            {
                "now_ms": 10_000,
                "limit": 1,
                "lease_owner": "token_discussion_digest",
                "lease_ms": 60_000,
                "commit": True,
                "windows": ("1h",),
                "scopes": ("matched",),
                "schema_version": NARRATIVE_SCHEMA_VERSION,
            }
        ]
        assert repo.due_digest_target_calls == []
        assert result.notes["llm_calls"] == 1
        assert result.notes["llm_failures"] == 1
        assert repo.recorded_runs[0]["stage"] == "discussion_digest"
        assert repo.recorded_runs[0]["status"] == "failed"
        assert repo.recorded_runs[0]["trace_metadata_json"]["lane"] == "narrative.discussion_digest"
        assert repo.recorded_runs[0]["trace_metadata_json"]["error_type"] == "TimeoutError"
        assert db.discussion_digest_dirty_targets.mark_error_calls == [
            {
                "claims": db.discussion_digest_dirty_targets.claimed,
                "error": "TimeoutError: provider timed out",
                "now_ms": 10_000,
                "retry_ms": 600_000,
                "commit": True,
            }
        ]
        assert repo.digest_scans == []

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
        assert db.discussion_digest_dirty_targets.mark_error_calls == [
            {
                "claims": db.discussion_digest_dirty_targets.claimed,
                "error": "worker_timeout_cancelled",
                "now_ms": repo.recorded_runs[0]["finished_at_ms"],
                "retry_ms": 7_000,
                "commit": True,
            }
        ]
        assert repo.digest_scans == []

    asyncio.run(scenario())


def test_token_discussion_digest_worker_claims_only_llm_cycle_budget():
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

        assert provider.reserve_rate_units == [1]
        assert provider.calls == ["solana:So111"]
        assert result.notes["ready"] == 1
        assert result.notes["pending"] == 0
        assert result.failed == 0
        assert result.notes["llm_calls"] == 1
        assert result.notes["deferred_llm_budget"] == 0
        assert "llm_cycle_budget_exhausted" not in result.notes["refresh_reasons"]
        assert [
            call["claims"][0]["admission_id"] for call in db.discussion_digest_dirty_targets.reschedule_calls
        ] == ["admission-1"]

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
        provider = FailingNarrativeProvider()
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
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert provider.reserve_rate_units == [2]
        assert result.notes["failed"] == 1
        assert result.notes["pending"] == 1
        assert result.notes["llm_calls"] == 1
        assert result.notes["llm_failures"] == 1
        assert result.notes["deferred_llm_budget"] == 1
        assert result.notes["refresh_reasons"]["llm_failure_budget_exhausted"] == 1
        assert db.discussion_digest_dirty_targets.mark_error_calls == [
            {
                "claims": [db.discussion_digest_dirty_targets.claimed[0]],
                "error": "TimeoutError: provider timed out",
                "now_ms": 10_000,
                "retry_ms": 7_000,
                "commit": True,
            }
        ]
        assert db.discussion_digest_dirty_targets.reschedule_calls[-1]["claims"] == [
            db.discussion_digest_dirty_targets.claimed[1]
        ]
        assert db.discussion_digest_dirty_targets.reschedule_calls[-1]["due_at_ms"] == 11_000
        assert db.discussion_digest_dirty_targets.reschedule_calls[-1]["now_ms"] == 10_000

    asyncio.run(scenario())


def test_digest_capacity_denied_marks_pending_not_failed():
    async def scenario():
        repo = FakeDigestRepository()
        db = FakeDB(repo)
        provider = NoStartNarrativeProvider()
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 0
        assert result.failed == 0
        assert result.skipped == 1
        assert result.notes["claimed"] == 0
        assert result.notes["agent_backpressure"] == "capacity_denied"
        assert provider.reserve_calls == ["narrative.discussion_digest"]
        assert db.discussion_digest_dirty_targets.claim_due_calls == []
        assert repo.recorded_runs == []
        assert db.discussion_digest_dirty_targets.reschedule_calls == []

    asyncio.run(scenario())


def test_token_discussion_digest_provider_started_validation_error_writes_failed_model_run():
    async def scenario():
        repo = FakeDigestRepository()
        db = FakeDB(repo)
        provider = InvalidRefsDigestProvider()
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.failed == 1
        assert provider.reserve_calls == ["narrative.discussion_digest"]
        assert provider.release_calls == 1
        assert repo.recorded_runs[0]["stage"] == "discussion_digest"
        assert repo.recorded_runs[0]["status"] == "failed"
        assert repo.recorded_runs[0]["execution_started"] is True
        assert repo.recorded_runs[0]["error"] == "invalid_evidence_refs"
        assert db.discussion_digest_dirty_targets.mark_error_calls == [
            {
                "claims": db.discussion_digest_dirty_targets.claimed,
                "error": "invalid_evidence_refs",
                "now_ms": 10_000,
                "retry_ms": 900_000,
                "commit": True,
            }
        ]

    asyncio.run(scenario())


def test_token_discussion_digest_releases_reservation_when_context_load_fails():
    async def scenario():
        repo = FailingDigestContextRepository()
        db = FakeDB(repo)
        provider = InvalidRefsDigestProvider()
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(),
            db=db,
            telemetry=SimpleNamespace(),
            provider=provider,
        )

        with pytest.raises(RuntimeError, match="digest context failed"):
            await worker.run_once(now_ms=10_000)

        assert provider.release_calls == 1

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
        assert db.discussion_digest_dirty_targets.reschedule_calls == [
            {
                "claims": db.discussion_digest_dirty_targets.claimed,
                "due_at_ms": 70_000,
                "now_ms": 10_000,
                "commit": True,
            }
        ]

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
        assert result.notes == {
            "reason": "no_due_digest_targets",
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
        }
        assert db.discussion_digest_dirty_targets.claim_due_calls == []
        assert repo.due_digest_target_calls == []
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
            current_ready_digest={
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
        assert db.discussion_digest_dirty_targets.reschedule_calls == [
            {
                "claims": db.discussion_digest_dirty_targets.claimed,
                "due_at_ms": 910_000,
                "now_ms": 10_000,
                "commit": True,
            }
        ]

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
            current_ready_digest={
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
        assert db.discussion_digest_dirty_targets.reschedule_calls == [
            {
                "claims": db.discussion_digest_dirty_targets.claimed,
                "due_at_ms": 910_000,
                "now_ms": 10_000,
                "commit": True,
            }
        ]

    asyncio.run(scenario())


def test_token_discussion_digest_worker_refreshes_no_ready_digest_with_bounded_pending_tail():
    async def scenario():
        pending_tail = 2
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
                    {"event_id": "event-4", "author_handle": "d", "status": "queued"},
                    {"event_id": "event-5", "author_handle": "e", "status": "queued"},
                ],
                "semantic_rows": [
                    {"event_id": "event-1", "semantic_id": "semantic-1", "author_handle": "a", "status": "labeled"},
                    {"event_id": "event-2", "semantic_id": "semantic-2", "author_handle": "b", "status": "labeled"},
                    {"event_id": "event-3", "semantic_id": "semantic-3", "author_handle": "c", "status": "labeled"},
                    {"event_id": "event-4", "author_handle": "d", "status": "queued"},
                    {"event_id": "event-5", "author_handle": "e", "status": "queued"},
                ],
                "source_event_ids": ["event-1", "event-2", "event-3", "event-4", "event-5"],
                "source_fingerprint": "source-current-with-tail",
                "source_window_start_ms": 1_000,
                "source_window_end_ms": 9_000,
                "source_event_count": 5,
                "semantic_row_count": 5,
                "missing_semantic_count": 0,
                "pending_semantic_count": pending_tail,
                "retryable_semantic_count": 0,
                "terminal_unavailable_count": 0,
                "labeled_event_count": 3,
                "independent_author_count": 5,
                "allowed_refs": [
                    {"ref_id": "event:event-1", "kind": "event", "source_table": "events"},
                    {"ref_id": "event:event-2", "kind": "event", "source_table": "events"},
                    {"ref_id": "event:event-3", "kind": "event", "source_table": "events"},
                    {"ref_id": "semantic:semantic-1", "kind": "semantic", "source_table": "token_mention_semantics"},
                    {"ref_id": "semantic:semantic-2", "kind": "semantic", "source_table": "token_mention_semantics"},
                    {"ref_id": "semantic:semantic-3", "kind": "semantic", "source_table": "token_mention_semantics"},
                ],
            },
            current_ready_digest=None,
        )
        db = FakeDB(repo)
        worker = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=fake_digest_settings(max_pending_semantic_rows_for_digest=pending_tail),
            db=db,
            telemetry=SimpleNamespace(),
            provider=StaleButValidDigestProvider(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.notes["ready"] == 1
        assert result.notes["refresh_reasons"]["thresholds_met_partial_semantic_tail"] == 1
        assert repo.replaced_digests[0]["status"] == "ready"
        assert repo.replaced_digests[0]["source_fingerprint"] == "source-current-with-tail"
        assert repo.replaced_digests[0]["refresh_reason"] == "thresholds_met_partial_semantic_tail"

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
        assert repo.replaced_digests[0]["refresh_reason"] == "thresholds_met"
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
        windows=("1h",),
        scopes=("matched",),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(self, narrative_repo, *, narrative_admission_dirty_targets=None, discussion_digest_dirty_targets=None):
        self.narrative_repo = narrative_repo
        self.narrative_admission_dirty_targets = narrative_admission_dirty_targets or FakeDirtyTargetRepository()
        if discussion_digest_dirty_targets is None and hasattr(narrative_repo, "digest_dirty_claims"):
            discussion_digest_dirty_targets = FakeDirtyTargetRepository(claims=narrative_repo.digest_dirty_claims())
        self.discussion_digest_dirty_targets = discussion_digest_dirty_targets or FakeDirtyTargetRepository()
        self.active_sessions = 0
        self.transaction_entries = 0

    @contextmanager
    def worker_session(self, name, statement_timeout_seconds=None):
        self.active_sessions += 1
        try:
            yield FakeRepositorySession(
                narratives=self.narrative_repo,
                narrative_admission_dirty_targets=self.narrative_admission_dirty_targets,
                discussion_digest_dirty_targets=self.discussion_digest_dirty_targets,
                transaction_hook=self._record_transaction,
            )
        finally:
            self.active_sessions -= 1

    def _record_transaction(self):
        self.transaction_entries += 1


class FakeRepositorySession(SimpleNamespace):
    @contextmanager
    def transaction(self):
        self.transaction_hook()
        yield


class FakeDirtyTargetRepository:
    def __init__(self, *, claims=None):
        self.claims = list(claims or [])
        self.claimed = []
        self.enqueued_targets = []
        self.claim_due_calls = []
        self.mark_done_calls = []
        self.mark_error_calls = []
        self.reschedule_calls = []
        self.queue_depth_calls = []

    def claim_due(self, *, now_ms, limit, lease_owner, lease_ms, commit=True, **filters):
        self.claim_due_calls.append(
            {
                "now_ms": now_ms,
                "limit": limit,
                "lease_owner": lease_owner,
                "lease_ms": lease_ms,
                "commit": commit,
                **filters,
            }
        )
        claims = self.claims
        windows = set(filters.get("windows") or [])
        scopes = set(filters.get("scopes") or [])
        schema_version = filters.get("schema_version")
        if windows:
            claims = [claim for claim in claims if claim.get("window") in windows]
        if scopes:
            claims = [claim for claim in claims if claim.get("scope") in scopes]
        if schema_version:
            claims = [claim for claim in claims if claim.get("schema_version") == schema_version]
        claimed = claims[:limit]
        self.claimed = list(claimed)
        claimed_ids = {id(claim) for claim in claimed}
        self.claims = [claim for claim in self.claims if id(claim) not in claimed_ids]
        return claimed

    def enqueue_targets(self, targets, *, reason, now_ms, due_at_ms=None, commit=True):
        rows = [dict(target) for target in targets]
        self.enqueued_targets.extend(rows)
        return {"targets": len(rows)}

    def mark_done(self, claims, *, now_ms, commit=True):
        payload = {"claims": list(claims), "now_ms": now_ms, "commit": commit}
        self.mark_done_calls.append(payload)
        return len(payload["claims"])

    def mark_error(self, claims, *, error, now_ms, retry_ms, commit=True):
        payload = {
            "claims": list(claims),
            "error": error,
            "now_ms": now_ms,
            "retry_ms": retry_ms,
            "commit": commit,
        }
        self.mark_error_calls.append(payload)
        return len(payload["claims"])

    def reschedule(self, claims, *, due_at_ms, now_ms, commit=True):
        payload = {"claims": list(claims), "due_at_ms": due_at_ms, "now_ms": now_ms, "commit": commit}
        self.reschedule_calls.append(payload)
        return len(payload["claims"])

    def queue_depth(self, *, now_ms, **filters):
        self.queue_depth_calls.append({"now_ms": now_ms, **filters})
        claims = self.claims
        windows = set(filters.get("windows") or [])
        scopes = set(filters.get("scopes") or [])
        schema_version = filters.get("schema_version")
        if windows:
            claims = [claim for claim in claims if claim.get("window") in windows]
        if scopes:
            claims = [claim for claim in claims if claim.get("scope") in scopes]
        if schema_version:
            claims = [claim for claim in claims if claim.get("schema_version") == schema_version]
        return len(claims)


class FakeNarrativeRepository:
    def __init__(
        self,
        *,
        radar_rows=None,
        source_rows=None,
        target_contexts=None,
        due_mentions=None,
        due_admissions=None,
        pending_semantics=None,
        existing_semantic_event_ids=None,
    ):
        self.radar_rows = list(radar_rows or [])
        self.source_rows = list(source_rows or [])
        self.target_contexts = dict(target_contexts or {})
        self.due_mentions = due_mentions
        self.due_admissions = due_admissions
        self.pending_semantics = dict(pending_semantics or {})
        self.existing_semantic_event_ids = set(existing_semantic_event_ids or set())
        self.recorded_runs = []
        self.recorded_run_commits = []
        self.completed_batches = []
        self.upserted_admissions = []
        self.deleted_frontiers = []
        self.staled_admission_targets = []
        self.scanned_admission_ids = []
        self.enqueued_source_event_ids = []
        self.semantic_scans = []
        self.load_target_calls = []
        self.admitted_radar_rows_calls = []
        self.admissions_for_window_scope_calls = []
        self.due_mentions_calls = []
        self.claim_due_mention_semantics_calls = []
        self.mention_semantics_queue_depth_calls = []
        self.released_semantic_claims = []
        self.due_admissions_for_semantics_calls = []
        self.pending_semantics_count_calls = []

    def admitted_radar_rows(self, *, window, scope, limit, projection_version):
        self.admitted_radar_rows_calls.append(
            {"window": window, "scope": scope, "limit": limit, "projection_version": projection_version}
        )
        return self.radar_rows[:limit]

    def admissions_for_window_scope(self, *, window, scope, schema_version, limit):
        self.admissions_for_window_scope_calls.append(
            {"window": window, "scope": scope, "schema_version": schema_version, "limit": limit}
        )
        return []

    def load_radar_admission_target(self, *, target_type, target_id, window, scope, projection_version, schema_version):
        self.load_target_calls.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "projection_version": projection_version,
                "schema_version": schema_version,
            }
        )
        return dict(self.target_contexts.get((target_type, target_id, window, scope), {}))

    def source_set_for_admission(self, *, target_type, target_id, since_ms, until_ms, watched_only, limit):
        rows = [
            row
            for row in self.source_rows[:limit]
            if row.get("target_type") == target_type and row.get("target_id") == target_id
        ]
        return {
            "source_event_ids": [row["event_id"] for row in rows],
            "source_rows": rows,
            "source_event_count": len(rows),
            "independent_author_count": len({row.get("author_handle") for row in rows if row.get("author_handle")}),
            "source_max_received_at_ms": max((row.get("source_received_at_ms") or 0 for row in rows), default=None),
        }

    def upsert_admissions(self, rows, *, now_ms, limit=None, commit=True):
        selected = list(rows)[:limit] if limit is not None else list(rows)
        self.upserted_admissions.extend(selected)
        return {"upserted": len(selected), "seen": len(selected)}

    def stale_admission_target(self, *, target_type, target_id, window, scope, schema_version, now_ms, commit=True):
        self.staled_admission_targets.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "schema_version": schema_version,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return {"staled_admissions": 1, "staled_digests": 0, "staled_semantics": 0}

    def delete_admissions_outside_frontier(self, *, window, scope, schema_version, active_target_keys, now_ms):
        self.deleted_frontiers.append(set(active_target_keys))
        return {"deleted_admissions": 0, "deleted_digests": 0, "deleted_obsolete_semantics": 0}

    def due_admissions_for_semantics(self, *, now_ms, limit, windows, scopes):
        self.due_admissions_for_semantics_calls.append(
            {"now_ms": now_ms, "limit": limit, "windows": tuple(windows), "scopes": tuple(scopes)}
        )
        if self.due_admissions is not None:
            return [
                admission
                for admission in self.due_admissions
                if admission.get("window") in windows and admission.get("scope") in scopes
            ][:limit]
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
            row for row in self.source_rows[:limit] if str(row.get("event_id")) not in self.existing_semantic_event_ids
        ]

    def pending_mention_semantics_count(
        self, *, target_type, target_id, schema_version, model_version=None, windows=("1h",), scopes=("all",)
    ):
        self.pending_semantics_count_calls.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "schema_version": schema_version,
                "model_version": model_version,
                "windows": tuple(windows),
                "scopes": tuple(scopes),
            }
        )
        return int(self.pending_semantics.get((target_type, target_id), 0))

    def enqueue_missing_mention_semantics(self, source_rows, *, schema_version, model_version, now_ms, commit=True):
        rows = list(source_rows)
        self.enqueued_source_event_ids.extend(str(row["event_id"]) for row in rows)
        inserted_rows = [row for row in rows if str(row.get("event_id")) not in self.existing_semantic_event_ids]
        if self.due_mentions is not None:
            self.due_mentions.extend(inserted_rows)
        return {"inserted": len(inserted_rows), "existing": len(rows) - len(inserted_rows)}

    def mark_admissions_semantics_scanned(self, admission_ids, *, next_due_at_ms, now_ms):
        self.scanned_admission_ids.extend(admission_ids)
        self.semantic_scans.append(
            {"admission_ids": list(admission_ids), "next_due_at_ms": next_due_at_ms, "now_ms": now_ms}
        )
        return {"updated": len(admission_ids)}

    def due_mentions_for_labeling(self, *, now_ms, limit, windows, scopes, max_per_target=None):
        self.due_mentions_calls.append(
            {
                "now_ms": now_ms,
                "limit": limit,
                "max_per_target": max_per_target,
                "windows": tuple(windows),
                "scopes": tuple(scopes),
            }
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

    def claim_due_mention_semantics(self, *, now_ms, limit, lease_owner, lease_ms, max_per_target=None):
        self.claim_due_mention_semantics_calls.append(
            {
                "now_ms": now_ms,
                "limit": limit,
                "lease_owner": lease_owner,
                "lease_ms": lease_ms,
                "max_per_target": max_per_target,
            }
        )
        if self.due_mentions is not None:
            rows = self.due_mentions[:limit]
        else:
            rows = [
                {
                    "semantic_id": "semantic-1",
                    "event_id": "event-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "text_clean": "SOL breakout",
                    "text_fingerprint": "fp-1",
                }
            ][:limit]
        return [
            {
                "schema_version": NARRATIVE_SCHEMA_VERSION,
                "retry_count": 0,
                **row,
                "lease_owner": lease_owner,
                "attempt_count": int(row.get("attempt_count") or 0) + 1,
            }
            for row in rows
        ]

    def mention_semantics_queue_depth(self, *, now_ms):
        self.mention_semantics_queue_depth_calls.append({"now_ms": now_ms})
        if self.due_mentions is not None:
            return len(self.due_mentions)
        return 1

    def release_mention_semantics_claims(self, claims, *, next_retry_at_ms, now_ms, error=None):
        rows = list(claims)
        self.released_semantic_claims.append(
            {
                "claims": rows,
                "next_retry_at_ms": next_retry_at_ms,
                "now_ms": now_ms,
                "error": error,
            }
        )
        return len(rows)

    def record_narrative_model_run(self, run, *, commit=True):
        self.recorded_run_commits.append(commit)
        self.recorded_runs.append(run)
        return run

    def complete_mention_semantics_batch(self, *, run_id, labels, failures, now_ms, commit=True):
        self.completed_batches.append({"run_id": run_id, "labels": labels, "failures": failures, "now_ms": now_ms})
        unavailable = sum(1 for failure in failures if failure.get("status") == "semantic_unavailable")
        return {
            "labeled": len(labels),
            "semantic_unavailable": unavailable,
            "failed": len(failures) - unavailable,
        }

    def digest_dirty_targets_for_mention_semantics_claims(self, claims, *, projection_version, schema_version):
        rows = []
        seen = set()
        for claim in claims:
            event_id = str(claim.get("event_id") or "")
            target_type = str(claim.get("target_type") or "")
            target_id = str(claim.get("target_id") or "")
            matching_admissions = [
                admission
                for admission in (self.due_admissions or [])
                if admission.get("target_type") == target_type
                and admission.get("target_id") == target_id
                and event_id in (admission.get("source_event_ids_json") or [])
            ]
            if not matching_admissions:
                matching_admissions = [
                    {
                        "target_type": target_type,
                        "target_id": target_id,
                        "window": "1h",
                        "scope": "matched",
                        "source_max_received_at_ms": 0,
                        "priority": 0,
                    }
                ]
            for admission in matching_admissions:
                key = (
                    admission.get("target_type"),
                    admission.get("target_id"),
                    admission.get("window"),
                    admission.get("scope"),
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "target_type": str(admission.get("target_type") or ""),
                        "target_id": str(admission.get("target_id") or ""),
                        "window": str(admission.get("window") or ""),
                        "scope": str(admission.get("scope") or ""),
                        "projection_version": projection_version,
                        "schema_version": schema_version,
                        "source_watermark_ms": int(admission.get("source_max_received_at_ms") or 0),
                        "priority": int(admission.get("priority") or 0),
                    }
                )
        return rows


class FakeDigestRepository:
    def __init__(self, *, context=None, contexts=None, targets=None, current_ready_digest=None, market_context=None):
        self.recorded_runs = []
        self.context = context
        self.contexts = dict(contexts or {})
        self.targets = list(targets) if targets is not None else None
        self.current_ready_digest = current_ready_digest
        self.market_context = dict(market_context or {})
        self.replaced_digests = []
        self.digest_scans = []
        self.digest_context_calls = []
        self.due_digest_target_calls = []

    def digest_dirty_claims(self):
        targets = self.targets
        if targets is None:
            targets = [
                {
                    "admission_id": "admission-1",
                    "target_type": "chain_token",
                    "target_id": "solana:So111",
                    "window": "1h",
                    "scope": "matched",
                }
            ]
        return [
            {
                **target,
                "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
                "schema_version": NARRATIVE_SCHEMA_VERSION,
                "payload_hash": f"payload-{index}",
                "lease_owner": "token_discussion_digest",
                "attempt_count": 1,
            }
            for index, target in enumerate(targets, start=1)
        ]

    def due_digest_targets(self, *, now_ms, limit, windows=("1h",), scopes=("all",)):
        self.due_digest_target_calls.append(
            {"now_ms": now_ms, "limit": limit, "windows": tuple(windows), "scopes": tuple(scopes)}
        )
        if self.targets is not None:
            return [
                target for target in self.targets if target.get("window") in windows and target.get("scope") in scopes
            ][:limit]
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

    def current_ready_digest_for_target(self, *, target_type, target_id, window, scope, schema_version):
        return self.current_ready_digest

    def market_context_for_admission(self, admission, *, current_ready_digest):
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


class FailingDigestContextRepository(FakeDigestRepository):
    def digest_context(self, *, target_type, target_id, window, scope, max_mentions):
        raise RuntimeError("digest context failed")


class AcquiringNarrativeProvider:
    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        reserve_rate_units = getattr(self, "reserve_rate_units", None)
        if reserve_rate_units is None:
            reserve_rate_units = []
            self.reserve_rate_units = reserve_rate_units
        reserve_rate_units.append(rate_units)
        return AgentCapacityReservation(lane=lane, acquired=True, rate_units=rate_units)


class BarrierNarrativeProvider(AcquiringNarrativeProvider):
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    def __init__(self, db):
        self.db = db
        self.max_sessions_seen = 0

    async def label_mentions(self, *, run_id, request, reservation=None):
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

    async def summarize_discussion(self, *, run_id, request, reservation=None):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class FailingNarrativeProvider(AcquiringNarrativeProvider):
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request, reservation=None):
        raise TimeoutError("provider timed out")

    def request_audit_for_label_mentions(self, *, run_id, request):
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request, reservation=None):
        raise TimeoutError("provider timed out")

    def request_audit_for_summarize_discussion(self, *, run_id, request):
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class CancelledNarrativeProvider(FailingNarrativeProvider):
    async def label_mentions(self, *, run_id, request, reservation=None):
        raise asyncio.CancelledError(WORKER_HARD_TIMEOUT_CANCEL_REASON)

    async def summarize_discussion(self, *, run_id, request, reservation=None):
        raise asyncio.CancelledError(WORKER_HARD_TIMEOUT_CANCEL_REASON)


class NoStartNarrativeProvider(FailingNarrativeProvider):
    def __init__(self):
        self.reserve_calls = []

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        self.reserve_calls.append(lane)
        return AgentCapacityReservation(
            lane=lane,
            acquired=False,
            reason=AgentExecutionErrorClass.CAPACITY_DENIED,
            rate_units=rate_units,
        )

    async def label_mentions(self, *, run_id, request, reservation=None):
        raise AgentExecutionError(
            AgentExecutionErrorClass.CAPACITY_DENIED,
            "agent lane capacity denied",
            execution_started=False,
        )

    async def summarize_discussion(self, *, run_id, request, reservation=None):
        raise AgentExecutionError(
            AgentExecutionErrorClass.CAPACITY_DENIED,
            "agent lane capacity denied",
            execution_started=False,
        )


class InvalidMentionResultProvider:
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    def __init__(self):
        self.reserve_calls = []
        self.release_calls = 0

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        self.reserve_calls.append(lane)

        def release() -> None:
            self.release_calls += 1

        return AgentCapacityReservation(lane=lane, acquired=True, rate_units=rate_units, _release=release)

    async def label_mentions(self, *, run_id, request, reservation=None):
        assert reservation is not None
        return {"invalid": "schema"}

    def request_audit_for_label_mentions(self, *, run_id, request):
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request, reservation=None):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class AuditFailingMentionProvider(InvalidMentionResultProvider):
    async def label_mentions(self, *, run_id, request, reservation=None):  # pragma: no cover - must fail earlier
        raise AssertionError("provider call should not run after request audit failure")

    def request_audit_for_label_mentions(self, *, run_id, request):
        raise RuntimeError("request audit failed")


class UnexpectedDigestProvider(AcquiringNarrativeProvider):
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request, reservation=None):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request, reservation=None):
        raise AssertionError("digest provider should not be called while semantics are still pending")

    def request_audit_for_summarize_discussion(self, *, run_id, request):
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class StaleButValidDigestProvider(AcquiringNarrativeProvider):
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request, reservation=None):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request, reservation=None):
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

    async def summarize_discussion(self, *, run_id, request, reservation=None):
        self.calls.append(request.target_id)
        return await super().summarize_discussion(run_id=run_id, request=request, reservation=reservation)


class InvalidRefsDigestProvider(StaleButValidDigestProvider):
    def __init__(self):
        self.reserve_calls = []
        self.release_calls = 0

    def try_reserve_execution(self, lane: str, *, rate_units: int = 1) -> AgentCapacityReservation:
        self.reserve_calls.append(lane)

        def release() -> None:
            self.release_calls += 1

        return AgentCapacityReservation(lane=lane, acquired=True, rate_units=rate_units, _release=release)

    async def summarize_discussion(self, *, run_id, request, reservation=None):
        assert reservation is not None
        result = await super().summarize_discussion(run_id=run_id, request=request)
        missing_ref = {"ref_id": "event:missing", "kind": "event", "source_table": "events"}
        digest = result.digest.model_copy(update={"evidence_refs": [missing_ref]})
        return result.model_copy(update={"digest": digest})


class SparseDigestProvider(AcquiringNarrativeProvider):
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request, reservation=None):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_label_mentions(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="mention_semantics", run_id=run_id)

    async def summarize_discussion(self, *, run_id, request, reservation=None):
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


class PartialFailureNarrativeProvider(AcquiringNarrativeProvider):
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request, reservation=None):
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

    async def summarize_discussion(self, *, run_id, request, reservation=None):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class UnknownLabelNarrativeProvider(AcquiringNarrativeProvider):
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request, reservation=None):
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

    async def summarize_discussion(self, *, run_id, request, reservation=None):  # pragma: no cover - protocol stub
        raise NotImplementedError

    def request_audit_for_summarize_discussion(self, *, run_id, request):  # pragma: no cover - protocol stub
        return _request_audit(stage="discussion_digest", run_id=run_id)

    async def aclose(self):  # pragma: no cover - runtime-owned provider
        return None


class EventRefAliasNarrativeProvider(AcquiringNarrativeProvider):
    provider = "test-provider"
    model = "gpt-test"
    artifact_version_hash = "artifact-test"

    async def label_mentions(self, *, run_id, request, reservation=None):
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

    async def summarize_discussion(self, *, run_id, request, reservation=None):  # pragma: no cover - protocol stub
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
