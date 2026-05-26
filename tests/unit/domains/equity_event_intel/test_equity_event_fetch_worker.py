from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.provider_wiring.equity_events import EquityDocumentProviderFetchResult
from gmgn_twitter_intel.domains.equity_event_intel.runtime import equity_event_fetch_worker as fetch_module
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_fetch_worker import EquityEventFetchWorker
from gmgn_twitter_intel.domains.equity_event_intel.types import NormalizedEquityDocument

NOW_MS = 1_765_900_000_000


def test_fetch_worker_enqueues_evidence_jobs_without_hydrating(monkeypatch: pytest.MonkeyPatch) -> None:
    document = NormalizedEquityDocument(
        provider_document_key="0000789019-26-000001:10-Q",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        document_url="https://sec.example/msft-10q.htm",
        payload_hash="payload-hash",
        raw_payload_json={"accessionNumber": "0000789019-26-000001"},
        fetched_at_ms=NOW_MS,
        document_type="sec_filing",
        form_type="10-Q",
        accession_number="0000789019-26-000001",
        fiscal_period="2026Q1",
        event_time_ms=NOW_MS - 1_000,
        content_hash="content-hash",
    )
    monkeypatch.setattr(fetch_module, "_normalize_envelope", lambda **_: [document])
    repo = _FetchRepo()
    worker = EquityEventFetchWorker(
        name="equity_event_fetch",
        settings=SimpleNamespace(batch_size=20, statement_timeout_seconds=None),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=_WakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker._fetch_source(
        {
            "source_id": "sec:MSFT",
            "provider_type": "sec_submissions",
            "source_role": "official_regulator",
        },
        now_ms=NOW_MS,
    )

    assert result.processed == 1
    assert repo.enqueued_jobs == [
        {
            "event_document_id": "event-document-id",
            "source_id": "sec:MSFT",
            "priority": "P2",
            "due_at_ms": NOW_MS,
            "max_attempts": 3,
        }
    ]


def test_fetch_worker_uses_configured_evidence_job_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    document = NormalizedEquityDocument(
        provider_document_key="0000789019-26-000001:10-Q",
        company_id="market_instrument:us_equity:MSFT",
        ticker="MSFT",
        cik="0000789019",
        document_url="https://sec.example/msft-10q.htm",
        payload_hash="payload-hash",
        raw_payload_json={},
        fetched_at_ms=NOW_MS,
        content_hash="content-hash",
    )
    monkeypatch.setattr(fetch_module, "_normalize_envelope", lambda **_: [document])
    repo = _FetchRepo()
    worker = EquityEventFetchWorker(
        name="equity_event_fetch",
        settings=SimpleNamespace(
            batch_size=20,
            evidence_job_max_attempts=7,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=_WakeBus(),
        clock_ms=lambda: NOW_MS,
    )

    result = worker._fetch_source(
        {
            "source_id": "sec:MSFT",
            "provider_type": "sec_submissions",
            "source_role": "official_regulator",
        },
        now_ms=NOW_MS,
    )

    assert result.processed == 1
    assert repo.enqueued_jobs[0]["max_attempts"] == 7


@dataclass
class _Provider:
    def fetch_source(self, source: dict[str, Any]) -> EquityDocumentProviderFetchResult:
        return EquityDocumentProviderFetchResult(
            status_code=200,
            documents=[{"provider_type": "sec_submissions", "payload": {"filings": []}}],
            etag="etag-1",
            last_modified="Tue, 26 May 2026 00:00:00 GMT",
            not_modified=False,
        )

    def hydrate_document_evidence(self, **_: Any) -> None:
        raise AssertionError("fetch worker must not hydrate evidence")


class _FetchRepo:
    def __init__(self) -> None:
        self.enqueued_jobs: list[dict[str, Any]] = []
        self.conn = SimpleNamespace(commit=lambda: None)

    def start_fetch_run(self, *, source_id: str, started_at_ms: int, commit: bool = True) -> str:
        return "fetch-run-id"

    def upsert_provider_document(self, **kwargs: Any) -> dict[str, Any]:
        return {"provider_document_id": "provider-document-id", "status": "inserted"}

    def upsert_event_document(self, **kwargs: Any) -> dict[str, Any]:
        return {"event_document_id": "event-document-id", "status": "inserted"}

    def enqueue_evidence_job(self, **kwargs: Any) -> dict[str, Any]:
        self.enqueued_jobs.append(
            {
                "event_document_id": kwargs["event_document_id"],
                "source_id": kwargs["source_id"],
                "priority": kwargs["priority"],
                "due_at_ms": kwargs["due_at_ms"],
                "max_attempts": kwargs["max_attempts"],
            }
        )
        return {"evidence_job_id": kwargs["evidence_job_id"], "status": "pending"}

    def update_source_http_cache(self, **_: Any) -> None:
        return None

    def update_source_material_freshness(self, **_: Any) -> None:
        return None

    def finish_fetch_run(self, **_: Any) -> dict[str, Any]:
        return {}


class _Db:
    def __init__(self, repo: _FetchRepo) -> None:
        self.repo = repo

    def worker_session(self, *_: Any, **__: Any) -> _Session:
        return _Session(self.repo)


class _Session:
    def __init__(self, repo: _FetchRepo) -> None:
        self.equity_events = repo
        self.conn = repo.conn

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _WakeBus:
    def notify_equity_event_document_written(self, **_: Any) -> None:
        raise AssertionError("fetch worker must only wake the evidence worker")

    def notify_equity_event_evidence_job_written(self, **_: Any) -> None:
        return None
