from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_manifest import require_worker_manifest
from gmgn_twitter_intel.app.runtime.worker_space import contract_from_manifest
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_process_worker import (
    EquityEventProcessWorker,
)

NOW_MS = 1_765_900_000_000


def test_process_worker_returns_idle_without_document_scan() -> None:
    repo = _ProcessRepo(claimed_jobs=[])
    worker = _worker(repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 0
    assert repo.claims == [{"now_ms": NOW_MS, "limit": 10, "lease_owner": "equity_event_process"}]
    assert repo.loaded_claims == []


def test_process_worker_loads_only_claimed_packets() -> None:
    claim = _claim(event_document_id="event-doc-claimed")
    repo = _ProcessRepo(claimed_jobs=[claim])
    worker = _worker(repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert repo.loaded_claims == [[claim]]


def test_process_worker_persists_inside_unit_of_work() -> None:
    repo = _ProcessRepo()
    worker = _worker(repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert repo.company_event_writes_inside_unit_of_work == 1
    assert repo.unit_of_work_entered is True


def test_process_worker_finishes_job_with_lease_attempt_and_hash() -> None:
    claim = _claim(
        event_document_id="event-doc-finish",
        lease_owner="process-worker-lease",
        attempt_count=2,
        input_payload_hash="payload-hash-finish",
    )
    repo = _ProcessRepo(claimed_jobs=[claim])
    worker = _worker(repo)

    result = worker.run_once_sync(now_ms=NOW_MS)

    assert result.processed == 1
    assert repo.successes == [
        {
            "event_document_id": "event-doc-finish",
            "lease_owner": "process-worker-lease",
            "attempt_count": 2,
            "input_payload_hash": "payload-hash-finish",
            "now_ms": NOW_MS,
        }
    ]


def _worker(repo: _ProcessRepo) -> EquityEventProcessWorker:
    return EquityEventProcessWorker(
        name="equity_event_process",
        settings=SimpleNamespace(
            batch_size=10,
            lease_ms=60_000,
            retry_ms=30_000,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        wake_bus=_WakeBus(),
        clock_ms=lambda: NOW_MS,
        worker_space_contract=contract_from_manifest(require_worker_manifest("equity_event_process")),
    )


def _claim(
    *,
    event_document_id: str = "event-doc-1",
    lease_owner: str = "equity_event_process",
    attempt_count: int = 1,
    input_payload_hash: str = "payload-hash-1",
) -> dict[str, Any]:
    return {
        "event_document_id": event_document_id,
        "lease_owner": lease_owner,
        "attempt_count": attempt_count,
        "input_payload_hash": input_payload_hash,
        "status": "running",
    }


def _packet_from_claim(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        **claim,
        "event_document_id": claim["event_document_id"],
        "provider_document_id": "provider-doc-1",
        "provider_document_key": "0000789019-26-000001:10-Q",
        "company_id": "market_instrument:us_equity:MSFT",
        "ticker": "MSFT",
        "cik": "0000789019",
        "source_id": "sec:MSFT",
        "source_role": "official_regulator",
        "document_type": "sec_filing",
        "form_type": "10-Q",
        "accession_number": "0000789019-26-000001",
        "fiscal_period": "2026Q1",
        "document_url": "https://sec.example/msft-10q.htm",
        "primary_document_url": "https://sec.example/msft-10q.htm",
        "provider_title": "MSFT 10-Q",
        "provider_summary": "Quarterly report",
        "title": "MSFT 10-Q",
        "event_time_ms": NOW_MS - 1_000,
        "discovered_at_ms": NOW_MS - 900,
        "content_hash": "content-hash",
        "evidence_status": "ready",
        "evidence_reason": "",
        "evidence_ready_at_ms": NOW_MS - 500,
        "evidence_artifacts": [
            {
                "id": "artifact-1",
                "evidence_artifact_id": "artifact-1",
                "artifact_kind": "html_text",
                "source_id": "sec:MSFT",
                "source_url": "https://sec.example/msft-10q.htm",
                "content_hash": "artifact-content-hash",
                "content_text": "Revenue was $10 million. Diluted EPS was $1.23.",
                "excerpt_text": "Revenue was $10 million.",
                "extraction_status": "ready",
                "artifact_payload_hash": "artifact-payload-hash",
            }
        ],
    }


class _ProcessRepo:
    def __init__(self, *, claimed_jobs: list[dict[str, Any]] | None = None) -> None:
        self.conn = SimpleNamespace(commit=lambda: None)
        self.claimed_jobs = [_claim()] if claimed_jobs is None else claimed_jobs
        self.claims: list[dict[str, Any]] = []
        self.loaded_claims: list[list[dict[str, Any]]] = []
        self.successes: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.unit_of_work_entered = False
        self._unit_of_work_active = False
        self.company_event_writes_inside_unit_of_work = 0

    def expire_stale_process_jobs(self, *, now_ms: int, limit: int, **_: Any) -> list[dict[str, Any]]:
        assert now_ms == NOW_MS
        assert limit == 10
        return []

    def claim_due_process_jobs(self, *, now_ms: int, limit: int, lease_owner: str, **_: Any) -> list[dict[str, Any]]:
        self.claims.append({"now_ms": now_ms, "limit": limit, "lease_owner": lease_owner})
        return self.claimed_jobs

    def load_process_packets_for_claims(self, *, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.loaded_claims.append(list(claims))
        return [_packet_from_claim(claim) for claim in claims]

    def list_event_documents_for_processing(self, **_: Any) -> list[dict[str, Any]]:
        raise AssertionError("process worker must not scan equity_event_documents")

    def company_event_ids_for_document(self, **_: Any) -> list[str]:
        self._assert_unit_of_work_active()
        return []

    def clear_story_members_for_document(self, **_: Any) -> None:
        self._assert_unit_of_work_active()

    def upsert_company_event(self, **_: Any) -> None:
        self._assert_unit_of_work_active()
        self.company_event_writes_inside_unit_of_work += 1

    def mark_event_document_evidence_status(self, **_: Any) -> None:
        self._assert_unit_of_work_active()

    def replace_source_spans(self, **_: Any) -> None:
        self._assert_unit_of_work_active()

    def replace_fact_candidates(self, **_: Any) -> None:
        self._assert_unit_of_work_active()

    def mark_event_document_fact_extraction_status(self, **_: Any) -> None:
        self._assert_unit_of_work_active()

    def mark_event_document_processed(self, **_: Any) -> None:
        self._assert_unit_of_work_active()

    def matching_expected_event_ids_for_company_events(self, **_: Any) -> list[str]:
        self._assert_unit_of_work_active()
        return []

    def mark_event_document_process_failed(self, **_: Any) -> None:
        self._assert_unit_of_work_active()

    def finish_process_job_success(
        self,
        *,
        event_document_id: str,
        lease_owner: str,
        attempt_count: int,
        input_payload_hash: str,
        now_ms: int,
        **_: Any,
    ) -> bool:
        self._assert_unit_of_work_active()
        self.successes.append(
            {
                "event_document_id": event_document_id,
                "lease_owner": lease_owner,
                "attempt_count": attempt_count,
                "input_payload_hash": input_payload_hash,
                "now_ms": now_ms,
            }
        )
        return True

    def finish_process_job_failure(self, **kwargs: Any) -> bool:
        self._assert_unit_of_work_active()
        self.failures.append(dict(kwargs))
        return True

    def _assert_unit_of_work_active(self) -> None:
        assert self._unit_of_work_active, "persist writes must run inside repos.unit_of_work()"

    @contextmanager
    def unit_of_work(self):
        self.unit_of_work_entered = True
        self._unit_of_work_active = True
        try:
            yield
        finally:
            self._unit_of_work_active = False


class _ProjectionDirtyTargets:
    def __init__(self, repo: _ProcessRepo) -> None:
        self.repo = repo
        self.enqueued: list[dict[str, Any]] = []

    def enqueue_targets(self, targets: list[dict[str, Any]], **_: Any) -> None:
        self.repo._assert_unit_of_work_active()
        self.enqueued.extend(targets)


class _Db:
    def __init__(self, repo: _ProcessRepo) -> None:
        self.repo = repo

    def worker_session(self, *_: Any, **__: Any) -> _Session:
        return _Session(self.repo)


class _Session:
    def __init__(self, repo: _ProcessRepo) -> None:
        self.equity_events = repo
        self.equity_projection_dirty_targets = _ProjectionDirtyTargets(repo)
        self.conn = repo.conn

    def unit_of_work(self):
        return self.equity_events.unit_of_work()

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _WakeBus:
    def __init__(self) -> None:
        self.processed: list[int] = []

    def notify_equity_event_processed(self, *, count: int) -> None:
        self.processed.append(count)
