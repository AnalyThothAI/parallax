from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_evidence_hydration_worker import (
    EquityEventEvidenceHydrationWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import (
    EquityEvidenceHydrationResult,
    NormalizedEquityEvidenceArtifact,
)

NOW_MS = 1_765_900_000_000


def test_hydration_worker_claims_job_writes_artifacts_finishes_and_wakes() -> None:
    repo = _HydrationRepo()
    wake_bus = _WakeBus()
    worker = EquityEventEvidenceHydrationWorker(
        name="equity_event_evidence_hydration",
        settings=SimpleNamespace(
            batch_size=10,
            max_attempts=3,
            lease_ms=60_000,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert repo.reaped == [
        {
            "now_ms": NOW_MS,
            "limit": 10,
            "lease_owner": "equity_event_evidence_hydration",
            "lease_ms": 60_000,
        }
    ]
    assert repo.claims == [{"now_ms": NOW_MS, "limit": 10, "lease_owner": "equity_event_evidence_hydration"}]
    assert repo.replaced_artifacts[0]["event_document_id"] == "event-document-id"
    assert repo.marked_statuses == [
        {
            "event_document_id": "event-document-id",
            "evidence_status": "ready",
            "evidence_reason": "",
            "evidence_ready_at_ms": NOW_MS,
        }
    ]
    assert repo.successes == [{"evidence_job_id": "job-event-document-id", "finished_at_ms": NOW_MS}]
    assert repo.source_freshness == [{"source_id": "sec:MSFT", "evidence_ready_at_ms": NOW_MS}]
    assert wake_bus.documents_written == [("sec:MSFT", 1)]


def test_hydration_worker_terminalizes_reaped_stale_job_with_failed_artifact_and_wake() -> None:
    repo = _HydrationRepo(
        reaped_terminal_jobs=[
            {"evidence_job_id": "job-event-document-id", "event_document_id": "event-document-id"}
        ],
        claimed_jobs=[],
    )
    wake_bus = _WakeBus()
    worker = EquityEventEvidenceHydrationWorker(
        name="equity_event_evidence_hydration",
        settings=SimpleNamespace(
            batch_size=10,
            max_attempts=3,
            lease_ms=60_000,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert result.notes["reaped_stale"] == 1
    assert repo.replaced_artifacts[0]["event_document_id"] == "event-document-id"
    artifact = repo.replaced_artifacts[0]["artifacts"][0]
    assert artifact["extraction_status"] == "failed"
    assert artifact["failure_reason"] == "evidence_job_lease_expired"
    assert repo.marked_statuses == [
        {
            "event_document_id": "event-document-id",
            "evidence_status": "failed",
            "evidence_reason": "evidence_job_lease_expired",
            "evidence_ready_at_ms": None,
        }
    ]
    assert repo.terminals == [
        {
            "evidence_job_id": "job-event-document-id",
            "finished_at_ms": NOW_MS,
            "error": "evidence_job_lease_expired",
            "attempt_count": 1,
            "lease_owner": "equity_event_evidence_hydration",
            "event_document_id": "event-document-id",
            "content_hash": "content-hash",
        }
    ]
    terminal_order = [
        item
        for item in repo.call_order
        if item in {"replace_artifacts", "mark_status", "finish_terminal", "commit"}
    ]
    assert terminal_order[-4:] == ["replace_artifacts", "mark_status", "finish_terminal", "commit"]
    assert repo.source_freshness == [
        {"source_id": "sec:MSFT", "actionable_error": "evidence_job_lease_expired"}
    ]
    assert wake_bus.documents_written == [("sec:MSFT", 1)]


def test_hydration_worker_skips_stale_claim_after_document_reset() -> None:
    repo = _HydrationRepo(claim_current=False)
    wake_bus = _WakeBus()
    worker = EquityEventEvidenceHydrationWorker(
        name="equity_event_evidence_hydration",
        settings=SimpleNamespace(
            batch_size=10,
            max_attempts=3,
            lease_ms=60_000,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert result.notes["stale_claim"] == 1
    assert repo.claim_validations == [
        {
            "evidence_job_id": "job-event-document-id",
            "attempt_count": 1,
            "lease_owner": "equity_event_evidence_hydration",
            "event_document_id": "event-document-id",
            "content_hash": "content-hash",
        }
    ]
    assert repo.replaced_artifacts == []
    assert repo.marked_statuses == []
    assert repo.successes == []
    assert repo.terminals == []
    assert wake_bus.documents_written == []


def test_hydration_worker_retryable_exception_passes_document_claim_guard() -> None:
    repo = _HydrationRepo(claim_current=False)
    wake_bus = _WakeBus()
    worker = EquityEventEvidenceHydrationWorker(
        name="equity_event_evidence_hydration",
        settings=SimpleNamespace(
            batch_size=10,
            max_attempts=3,
            lease_ms=60_000,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_FailingProvider(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert repo.retryables == [
        {
            "evidence_job_id": "job-event-document-id",
            "attempt_count": 1,
            "lease_owner": "equity_event_evidence_hydration",
            "event_document_id": "event-document-id",
            "content_hash": "content-hash",
        }
    ]
    assert repo.replaced_artifacts == []
    assert repo.marked_statuses == []
    assert wake_bus.documents_written == []


def test_hydration_worker_missing_input_failure_does_not_finish_without_content_guard() -> None:
    repo = _HydrationRepo(load_payload={})
    wake_bus = _WakeBus()
    worker = EquityEventEvidenceHydrationWorker(
        name="equity_event_evidence_hydration",
        settings=SimpleNamespace(
            batch_size=10,
            max_attempts=3,
            lease_ms=60_000,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["input_missing_unrecoverable_without_content_guard"] == 1
    assert repo.terminals == []
    assert repo.retryables == []


def test_hydration_worker_defensive_exception_without_content_hash_does_not_finish() -> None:
    repo = _HydrationRepo(load_payload=_broken_payload(content_hash=None))
    wake_bus = _WakeBus()
    worker = EquityEventEvidenceHydrationWorker(
        name="equity_event_evidence_hydration",
        settings=SimpleNamespace(
            batch_size=10,
            max_attempts=3,
            lease_ms=60_000,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert result.notes["unguarded_failure_noop"] == 1
    assert repo.retryables == []
    assert repo.terminals == []
    assert wake_bus.documents_written == []


def test_hydration_worker_defensive_exception_with_content_hash_finishes_retryable() -> None:
    repo = _HydrationRepo(load_payload=_broken_payload(content_hash="content-hash"))
    wake_bus = _WakeBus()
    worker = EquityEventEvidenceHydrationWorker(
        name="equity_event_evidence_hydration",
        settings=SimpleNamespace(
            batch_size=10,
            max_attempts=3,
            lease_ms=60_000,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=wake_bus,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.failed == 1
    assert repo.retryables == [
        {
            "evidence_job_id": "job-event-document-id",
            "attempt_count": 1,
            "lease_owner": "equity_event_evidence_hydration",
            "event_document_id": "event-document-id",
            "content_hash": "content-hash",
        }
    ]
    assert repo.terminals == []
    assert wake_bus.documents_written == []


@dataclass
class _Provider:
    def hydrate_document_evidence(self, *, source: dict[str, Any], document: Any) -> EquityEvidenceHydrationResult:
        assert source["source_id"] == "sec:MSFT"
        assert document.event_document_id == "event-document-id"
        return EquityEvidenceHydrationResult(
            status_code=200,
            artifacts=[
                NormalizedEquityEvidenceArtifact(
                    evidence_artifact_id="artifact-id",
                    event_document_id="event-document-id",
                    provider_document_id="provider-document-id",
                    source_id="sec:MSFT",
                    artifact_kind="html_text",
                    extraction_status="ready",
                    source_url="https://sec.example/msft-10q.htm",
                    content_hash="evidence-hash",
                    content_text="Revenue grew.",
                    content_json={},
                    excerpt_text="Revenue grew.",
                    failure_reason=None,
                    fetched_at_ms=NOW_MS,
                    parsed_at_ms=NOW_MS,
                    created_at_ms=NOW_MS,
                    updated_at_ms=NOW_MS,
                )
            ],
        )


@dataclass
class _FailingProvider:
    def hydrate_document_evidence(self, *, source: dict[str, Any], document: Any) -> EquityEvidenceHydrationResult:
        raise RuntimeError("provider unavailable")


class _HydrationRepo:
    def __init__(
        self,
        *,
        reaped_terminal_jobs: list[dict[str, Any]] | None = None,
        claimed_jobs: list[dict[str, Any]] | None = None,
        load_payload: dict[str, Any] | None = None,
        claim_current: bool = True,
    ) -> None:
        self.call_order: list[str] = []
        self.conn = SimpleNamespace(commit=lambda: self.call_order.append("commit"))
        self.claim_current = claim_current
        self.reaped_terminal_jobs = [] if reaped_terminal_jobs is None else reaped_terminal_jobs
        self.claimed_jobs = (
            [
                {
                    "evidence_job_id": "job-event-document-id",
                    "event_document_id": "event-document-id",
                    "attempt_count": 1,
                    "lease_owner": "equity_event_evidence_hydration",
                }
            ]
            if claimed_jobs is None
            else claimed_jobs
        )
        self.load_payload = self._default_payload() if load_payload is None else load_payload
        self.reaped: list[dict[str, Any]] = []
        self.claims: list[dict[str, Any]] = []
        self.replaced_artifacts: list[dict[str, Any]] = []
        self.marked_statuses: list[dict[str, Any]] = []
        self.successes: list[dict[str, Any]] = []
        self.retryables: list[dict[str, Any]] = []
        self.terminals: list[dict[str, Any]] = []
        self.source_freshness: list[dict[str, Any]] = []
        self.claim_validations: list[dict[str, Any]] = []

    def reap_stale_evidence_jobs(
        self,
        *,
        now_ms: int,
        limit: int,
        lease_owner: str,
        lease_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        self.call_order.append("reap")
        self.reaped.append({"now_ms": now_ms, "limit": limit, "lease_owner": lease_owner, "lease_ms": lease_ms})
        return self.reaped_terminal_jobs

    def claim_due_evidence_jobs(self, *, now_ms: int, limit: int, lease_owner: str, **_: Any) -> list[dict[str, Any]]:
        self.call_order.append("claim")
        self.claims.append({"now_ms": now_ms, "limit": limit, "lease_owner": lease_owner})
        return self.claimed_jobs

    def load_evidence_hydration_input(self, *, evidence_job_id: str) -> dict[str, Any]:
        assert evidence_job_id == "job-event-document-id"
        return self.load_payload

    def _default_payload(self) -> dict[str, Any]:
        return {
            "job": {
                "evidence_job_id": "job-event-document-id",
                "event_document_id": "event-document-id",
                "attempt_count": 1,
                "max_attempts": 3,
                "lease_owner": "equity_event_evidence_hydration",
            },
            "source": {
                "source_id": "sec:MSFT",
                "provider_type": "sec_submissions",
                "source_role": "official_regulator",
            },
            "document": {
                "event_document_id": "event-document-id",
                "provider_document_id": "provider-document-id",
                "provider_document_key": "0000789019-26-000001:10-Q",
                "company_id": "market_instrument:us_equity:MSFT",
                "ticker": "MSFT",
                "cik": "0000789019",
                "document_url": "https://sec.example/msft-10q.htm",
                "payload_hash": "payload-hash",
                "raw_payload_json": {"accessionNumber": "0000789019-26-000001"},
                "fetched_at_ms": NOW_MS,
                "document_type": "sec_filing",
                "form_type": "10-Q",
                "accession_number": "0000789019-26-000001",
                "fiscal_period": "2026Q1",
                "event_time_ms": NOW_MS - 1_000,
                "content_hash": "content-hash",
            },
        }

    def evidence_job_claim_is_current(
        self,
        *,
        evidence_job_id: str,
        attempt_count: int,
        lease_owner: str,
        event_document_id: str,
        content_hash: str,
        **_: Any,
    ) -> bool:
        self.call_order.append("validate_claim")
        self.claim_validations.append(
            {
                "evidence_job_id": evidence_job_id,
                "attempt_count": attempt_count,
                "lease_owner": lease_owner,
                "event_document_id": event_document_id,
                "content_hash": content_hash,
            }
        )
        return self.claim_current

    def replace_evidence_artifacts(self, *, event_document_id: str, artifacts: list[dict[str, Any]], **_: Any) -> None:
        self.call_order.append("replace_artifacts")
        self.replaced_artifacts.append({"event_document_id": event_document_id, "artifacts": artifacts})

    def mark_event_document_evidence_status(self, **kwargs: Any) -> None:
        self.call_order.append("mark_status")
        self.marked_statuses.append(
            {
                "event_document_id": kwargs["event_document_id"],
                "evidence_status": kwargs["evidence_status"],
                "evidence_reason": kwargs["evidence_reason"],
                "evidence_ready_at_ms": kwargs["evidence_ready_at_ms"],
            }
        )

    def finish_evidence_job_success(self, *, evidence_job_id: str, finished_at_ms: int, **_: Any) -> None:
        self.call_order.append("finish_success")
        self.successes.append({"evidence_job_id": evidence_job_id, "finished_at_ms": finished_at_ms})

    def finish_evidence_job_retryable(
        self,
        *,
        evidence_job_id: str,
        attempt_count: int | None,
        lease_owner: str | None,
        event_document_id: str | None,
        content_hash: str | None,
        **_: Any,
    ) -> bool:
        assert attempt_count is not None
        assert lease_owner is not None
        self.call_order.append("finish_retryable")
        self.retryables.append(
            {
                "evidence_job_id": evidence_job_id,
                "attempt_count": attempt_count,
                "lease_owner": lease_owner,
                "event_document_id": event_document_id,
                "content_hash": content_hash,
            }
        )
        return self.claim_current

    def finish_evidence_job_terminal(
        self,
        *,
        evidence_job_id: str,
        finished_at_ms: int,
        error: str | None,
        attempt_count: int | None,
        lease_owner: str | None,
        event_document_id: str | None,
        content_hash: str | None,
        **_: Any,
    ) -> bool:
        assert attempt_count is not None
        assert lease_owner is not None
        self.call_order.append("finish_terminal")
        self.terminals.append(
            {
                "evidence_job_id": evidence_job_id,
                "finished_at_ms": finished_at_ms,
                "error": error,
                "attempt_count": attempt_count,
                "lease_owner": lease_owner,
                "event_document_id": event_document_id,
                "content_hash": content_hash,
            }
        )
        return self.claim_current

    def update_source_material_freshness(
        self,
        *,
        source_id: str,
        evidence_ready_at_ms: int | None = None,
        actionable_error: str | None = None,
        **_: Any,
    ) -> None:
        payload: dict[str, Any] = {"source_id": source_id}
        if evidence_ready_at_ms is not None:
            payload["evidence_ready_at_ms"] = evidence_ready_at_ms
        if actionable_error is not None:
            payload["actionable_error"] = actionable_error
        self.source_freshness.append(payload)


def _broken_payload(*, content_hash: str | None) -> dict[str, Any]:
    return {
        "job": {
            "evidence_job_id": "job-event-document-id",
            "event_document_id": "event-document-id",
            "attempt_count": 1,
            "max_attempts": 3,
            "lease_owner": "equity_event_evidence_hydration",
        },
        "source": {
            "source_id": "sec:MSFT",
            "provider_type": "sec_submissions",
            "source_role": "official_regulator",
        },
        "document": {
            "event_document_id": "event-document-id",
            "content_hash": content_hash,
        },
    }


class _Db:
    def __init__(self, repo: _HydrationRepo) -> None:
        self.repo = repo

    def worker_session(self, *_: Any, **__: Any) -> _Session:
        return _Session(self.repo)


class _Session:
    def __init__(self, repo: _HydrationRepo) -> None:
        self.equity_events = repo
        self.conn = repo.conn

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _WakeBus:
    def __init__(self) -> None:
        self.documents_written: list[tuple[str, int]] = []

    def notify_equity_event_document_written(self, *, source_id: str, count: int) -> None:
        self.documents_written.append((source_id, count))
