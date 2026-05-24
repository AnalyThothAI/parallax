from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable, Mapping
from inspect import isawaitable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel.providers import EquityEventDocumentProvider
from gmgn_twitter_intel.domains.equity_event_intel.services.sec_submission_normalizer import (
    normalize_sec_submission_documents,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import NormalizedEquityDocument


class EquityEventFetchWorker(WorkerBase):
    def __init__(
        self,
        *,
        document_provider: EquityEventDocumentProvider,
        wake_bus: Any | None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.document_provider = document_provider
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms

    async def on_close(self) -> None:
        close = getattr(self.document_provider, "close", None)
        if close is None:
            return
        result = close()
        if isawaitable(result):
            await result

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos:
            due_sources = repos.equity_events.claim_due_sources(now_ms=now, limit=self._batch_size())

        processed = 0
        failed = 0
        for source in due_sources:
            result = self._fetch_source(dict(source), now_ms=now)
            processed += result.processed
            failed += result.failed
        return WorkerResult(
            processed=processed,
            failed=failed,
            notes={"due_sources": len(due_sources)},
        )

    def _fetch_source(self, source: dict[str, Any], *, now_ms: int) -> WorkerResult:
        source_id = str(source["source_id"])
        fetch_run_id = ""
        try:
            with self._repository_session() as repos:
                fetch_run_id = repos.equity_events.start_fetch_run(source_id=source_id, started_at_ms=now_ms)

            if str(source.get("provider_type") or "") != "sec_submissions":
                raise ValueError(f"unsupported_provider_type:{source.get('provider_type')}")

            fetch_result = self.document_provider.fetch_source(source)
            failed_document = _failed_fetch_document(fetch_result.documents)
            if failed_document is not None:
                reason = _failed_fetch_reason(failed_document)
                with self._repository_session() as repos:
                    repos.equity_events.finish_fetch_run(
                        fetch_run_id=fetch_run_id,
                        source_id=source_id,
                        status="failed",
                        finished_at_ms=now_ms,
                        http_status=fetch_result.status_code,
                        error=reason,
                        extra_json={
                            "error_code": reason,
                            "provider_document": dict(failed_document),
                        },
                    )
                return WorkerResult(failed=1, notes={"source_id": source_id, "error": reason})

            with self._repository_session() as repos:
                if fetch_result.not_modified:
                    repos.equity_events.update_source_http_cache(
                        source_id=source_id,
                        etag=fetch_result.etag,
                        last_modified=fetch_result.last_modified,
                        now_ms=now_ms,
                        commit=False,
                    )
                    repos.equity_events.finish_fetch_run(
                        fetch_run_id=fetch_run_id,
                        source_id=source_id,
                        status="success",
                        finished_at_ms=now_ms,
                        http_status=fetch_result.status_code,
                        commit=False,
                    )
                    repos.conn.commit()
                    return WorkerResult(processed=0)

                counts = self._persist_documents(
                    repos.equity_events,
                    source=source,
                    fetch_run_id=fetch_run_id,
                    documents=fetch_result.documents,
                    fetched_at_ms=now_ms,
                )
                repos.equity_events.update_source_http_cache(
                    source_id=source_id,
                    etag=fetch_result.etag,
                    last_modified=fetch_result.last_modified,
                    now_ms=now_ms,
                    commit=False,
                )
                repos.equity_events.finish_fetch_run(
                    fetch_run_id=fetch_run_id,
                    source_id=source_id,
                    status="success",
                    finished_at_ms=now_ms,
                    fetched_count=counts["fetched"],
                    inserted_count=counts["inserted"],
                    updated_count=counts["updated"],
                    duplicate_count=counts["duplicate"],
                    http_status=fetch_result.status_code,
                    commit=False,
                )
                repos.conn.commit()

            written = counts["inserted"] + counts["updated"]
            if written > 0 and self.wake_bus is not None:
                self.wake_bus.notify_equity_event_document_written(source_id=source_id, count=written)
            return WorkerResult(processed=written)
        except Exception as exc:  # pragma: no cover - exercised through integration failures.
            self._mark_source_failed(source_id=source_id, fetch_run_id=fetch_run_id, now_ms=now_ms, error=exc)
            return WorkerResult(failed=1, notes={"source_id": source_id, "error": str(exc)})

    def _persist_documents(
        self,
        repository: Any,
        *,
        source: Mapping[str, Any],
        fetch_run_id: str,
        documents: list[dict[str, Any]],
        fetched_at_ms: int,
    ) -> dict[str, int]:
        counts = {"fetched": 0, "inserted": 0, "updated": 0, "duplicate": 0}
        for envelope in documents:
            for normalized in _normalize_envelope(source=source, envelope=envelope, fetched_at_ms=fetched_at_ms):
                counts["fetched"] += 1
                provider = repository.upsert_provider_document(
                    provider_document_id=_stable_id("equity-provider-document", source["source_id"], normalized),
                    source_id=str(source["source_id"]),
                    fetch_run_id=fetch_run_id,
                    provider_document_key=normalized.provider_document_key,
                    company_id=normalized.company_id,
                    ticker=normalized.ticker,
                    cik=normalized.cik,
                    document_url=normalized.document_url,
                    payload_hash=normalized.payload_hash,
                    raw_payload_json=normalized.raw_payload_json,
                    fetched_at_ms=normalized.fetched_at_ms,
                    commit=False,
                )
                event = repository.upsert_event_document(
                    event_document_id=_stable_id("equity-event-document", source["source_id"], normalized),
                    provider_document_id=provider["provider_document_id"],
                    company_id=normalized.company_id,
                    ticker=normalized.ticker,
                    cik=normalized.cik,
                    source_id=str(source["source_id"]),
                    source_role=str(source["source_role"]),
                    document_type=normalized.document_type,
                    form_type=normalized.form_type,
                    accession_number=normalized.accession_number,
                    fiscal_period=normalized.fiscal_period,
                    document_url=normalized.document_url,
                    event_time_ms=normalized.event_time_ms or fetched_at_ms,
                    discovered_at_ms=fetched_at_ms,
                    content_hash=normalized.content_hash or normalized.payload_hash,
                    now_ms=fetched_at_ms,
                    commit=False,
                )
                status = str(event.get("status") or provider.get("status") or "duplicate")
                if status in counts:
                    counts[status] += 1
        return counts

    def _mark_source_failed(self, *, source_id: str, fetch_run_id: str, now_ms: int, error: Exception) -> None:
        if not fetch_run_id:
            return
        try:
            with self._repository_session() as repos:
                repos.equity_events.finish_fetch_run(
                    fetch_run_id=fetch_run_id,
                    source_id=source_id,
                    status="failed",
                    finished_at_ms=now_ms,
                    error=str(error),
                )
        except Exception:
            return

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 20)))


def _normalize_envelope(
    *,
    source: Mapping[str, Any],
    envelope: Mapping[str, Any],
    fetched_at_ms: int,
) -> list[NormalizedEquityDocument]:
    provider_type = str(envelope.get("provider_type") or source.get("provider_type") or "")
    if provider_type == "sec_submissions":
        payload = envelope.get("payload")
        if isinstance(payload, Mapping):
            return normalize_sec_submission_documents(source=source, payload=payload, fetched_at_ms=fetched_at_ms)
    return []


def _failed_fetch_document(documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    for document in documents:
        if str(document.get("status") or "") == "failed":
            return document
    return None


def _failed_fetch_reason(document: Mapping[str, Any]) -> str:
    return str(document.get("error_code") or document.get("error") or "provider_failed")


def _stable_id(prefix: str, source_id: Any, document: NormalizedEquityDocument) -> str:
    digest = hashlib.sha256(f"{source_id}:{document.provider_document_key}".encode()).hexdigest()
    return f"{prefix}-{digest[:32]}"


def _now_ms() -> int:
    return int(time.time() * 1000)
