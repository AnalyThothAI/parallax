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


def test_fetch_worker_reaps_stale_fetch_runs_before_claiming_sources() -> None:
    repo = _FetchRepo()
    repo.stale_fetch_runs = [{"fetch_run_id": "stale-fetch-run"}]
    repo.due_sources = []
    worker = EquityEventFetchWorker(
        name="equity_event_fetch",
        settings=SimpleNamespace(
            batch_size=20,
            hard_timeout_seconds=240,
            statement_timeout_seconds=None,
        ),
        db=_Db(repo),
        telemetry=SimpleNamespace(),
        document_provider=_Provider(),
        wake_bus=None,
        clock_ms=lambda: NOW_MS,
    )

    result = worker.run_once_sync()

    assert result.notes["stale_fetch_runs_reaped"] == 1
    assert result.notes["due_sources"] == 0
    assert repo.calls == ["reap_stale_fetch_runs", "claim_due_sources", "commit"]
    assert repo.reap_payload == {
        "stale_before_ms": NOW_MS - 900_000,
        "now_ms": NOW_MS,
        "limit": 1_000,
        "commit": False,
    }


def test_fetch_worker_skips_side_effects_when_fetch_run_was_reaped(monkeypatch: pytest.MonkeyPatch) -> None:
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
    repo.running_fetch_run = False
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

    assert result.skipped == 1
    assert result.notes["skip_reason"] == "fetch_run_no_longer_running"
    assert repo.enqueued_jobs == []
    assert "upsert_provider_document" not in repo.calls
    assert "update_source_http_cache" not in repo.calls
    assert "update_source_material_freshness" not in repo.calls
    assert repo.calls == ["start_fetch_run", "commit", "lock_running_fetch_run", "commit"]


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
        self.calls: list[str] = []
        self.due_sources: list[dict[str, Any]] = []
        self.stale_fetch_runs: list[dict[str, Any]] = []
        self.reap_payload: dict[str, Any] = {}
        self.running_fetch_run = True
        self.conn = SimpleNamespace(commit=self._commit)

    def _commit(self) -> None:
        self.calls.append("commit")

    def reap_stale_fetch_runs(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append("reap_stale_fetch_runs")
        self.reap_payload = dict(kwargs)
        return list(self.stale_fetch_runs)

    def claim_due_sources(self, **_: Any) -> list[dict[str, Any]]:
        self.calls.append("claim_due_sources")
        return list(self.due_sources)

    def lock_running_fetch_run(self, **_: Any) -> bool:
        self.calls.append("lock_running_fetch_run")
        return self.running_fetch_run

    def start_fetch_run(self, *, source_id: str, started_at_ms: int, commit: bool = True) -> str:
        self.calls.append("start_fetch_run")
        if commit:
            self._commit()
        return "fetch-run-id"

    def upsert_provider_document(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("upsert_provider_document")
        return {"provider_document_id": "provider-document-id", "status": "inserted"}

    def upsert_event_document(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("upsert_event_document")
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
        self.calls.append("update_source_http_cache")

    def update_source_material_freshness(self, **_: Any) -> None:
        self.calls.append("update_source_material_freshness")

    def finish_fetch_run(self, **_: Any) -> dict[str, Any]:
        self.calls.append("finish_fetch_run")
        return {"fetch_run_id": "fetch-run-id"}


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
