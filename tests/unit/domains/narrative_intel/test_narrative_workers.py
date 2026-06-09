import asyncio
import inspect
from contextlib import contextmanager
from types import SimpleNamespace

from parallax.app.runtime.worker_base import WorkerBase
from parallax.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from parallax.domains.narrative_intel.repositories.narrative_repository import NarrativeRepository
from parallax.domains.narrative_intel.runtime.narrative_admission_worker import (
    NarrativeAdmissionWorker,
)
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION


def test_workers_are_workerbase_subclasses():
    assert issubclass(NarrativeAdmissionWorker, WorkerBase)


def test_source_set_query_uses_indexable_current_resolution_predicate():
    source = inspect.getsource(NarrativeRepository.source_set_for_admission)

    assert "COALESCE(resolution.is_current" not in source
    assert "resolution.is_current = true" in source


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
        db = FakeDB(repo, narrative_admission_dirty_targets=dirty_targets)
        worker = NarrativeAdmissionWorker(
            name="narrative_admission",
            settings=fake_admission_settings(),
            db=db,
            telemetry=SimpleNamespace(),
        )

        result = await worker.run_once(now_ms=10_000)

        assert result.processed == 1
        assert result.notes["claimed"] == 1
        assert result.notes["targets_loaded"] == 1
        assert result.notes["source_rows_scanned"] == 1
        assert result.notes["rows_written"] == 1
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
        assert repo.upserted_admissions[0]["source_window_end_ms"] == 9_000
        assert repo.upserted_admissions[0]["source_max_received_at_ms"] == 9_000
        assert repo.upserted_admissions[0]["source_event_count"] == 1
        assert repo.upserted_admissions[0]["independent_author_count"] == 1
        assert repo.source_set_calls == [
            {
                "target_type": "chain_token",
                "target_id": "solana:So111",
                "since_ms": 0,
                "until_ms": 9_000,
                "watched_only": True,
                "limit": 100,
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


class FakeDB:
    def __init__(self, narrative_repo, *, narrative_admission_dirty_targets=None):
        self.narrative_repo = narrative_repo
        self.narrative_admission_dirty_targets = narrative_admission_dirty_targets or FakeDirtyTargetRepository()
        self.active_sessions = 0
        self.transaction_entries = 0

    @contextmanager
    def worker_session(self, name, statement_timeout_seconds=None):
        self.active_sessions += 1
        try:
            yield FakeRepositorySession(
                narratives=self.narrative_repo,
                narrative_admission_dirty_targets=self.narrative_admission_dirty_targets,
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
        self.claim_due_calls = []
        self.mark_done_calls = []
        self.mark_error_calls = []
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
        claimed = self.claims[:limit]
        self.claimed = list(claimed)
        claimed_ids = {id(claim) for claim in claimed}
        self.claims = [claim for claim in self.claims if id(claim) not in claimed_ids]
        return claimed

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

    def queue_depth(self, *, now_ms, **filters):
        self.queue_depth_calls.append({"now_ms": now_ms, **filters})
        return len(self.claims)


class FakeNarrativeRepository:
    def __init__(
        self,
        *,
        source_rows=None,
        target_contexts=None,
    ):
        self.source_rows = list(source_rows or [])
        self.target_contexts = dict(target_contexts or {})
        self.upserted_admissions = []
        self.source_set_calls = []
        self.deleted_frontiers = []
        self.staled_admission_targets = []
        self.load_target_calls = []
        self.admitted_radar_rows_calls = []
        self.admissions_for_window_scope_calls = []

    def admitted_radar_rows(self, *, window, scope, limit, projection_version):
        self.admitted_radar_rows_calls.append(
            {"window": window, "scope": scope, "limit": limit, "projection_version": projection_version}
        )
        return []

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
        self.source_set_calls.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "since_ms": since_ms,
                "until_ms": until_ms,
                "watched_only": watched_only,
                "limit": limit,
            }
        )
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
        return {"deleted_admissions": 0}
