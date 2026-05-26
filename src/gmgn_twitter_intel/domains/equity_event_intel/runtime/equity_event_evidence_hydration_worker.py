from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from inspect import isawaitable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel.providers import EquityEventDocumentProvider
from gmgn_twitter_intel.domains.equity_event_intel.services.sec_evidence import (
    build_failed_evidence_artifact,
    build_unavailable_evidence_artifact,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import (
    NormalizedEquityDocument,
    NormalizedEquityEvidenceArtifact,
)


class EquityEventEvidenceHydrationWorker(WorkerBase):
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
            reaped = repos.equity_events.reap_stale_evidence_jobs(now_ms=now, commit=False)
            jobs = repos.equity_events.claim_due_evidence_jobs(
                now_ms=now,
                limit=self._batch_size(),
                lease_owner=self.name,
                lease_ms=self._lease_ms(),
                commit=False,
            )
            repos.conn.commit()

        processed = 0
        failed = 0
        written = 0
        for job in jobs:
            result = self._hydrate_job(dict(job), now_ms=now)
            processed += result.processed
            failed += result.failed
            written += int(result.notes.get("terminal_written", 0))
        return WorkerResult(
            processed=processed,
            failed=failed,
            notes={"claimed": len(jobs), "reaped_stale": int(reaped or 0), "terminal_written": written},
        )

    def _hydrate_job(self, job: dict[str, Any], *, now_ms: int) -> WorkerResult:
        evidence_job_id = str(job["evidence_job_id"])
        try:
            with self._repository_session() as repos:
                payload = repos.equity_events.load_evidence_hydration_input(evidence_job_id=evidence_job_id)
            if not payload:
                self._finish_failure(
                    evidence_job_id=evidence_job_id,
                    error="evidence_hydration_input_missing",
                    now_ms=now_ms,
                    terminal=True,
                )
                return WorkerResult(failed=1, notes={"evidence_job_id": evidence_job_id})

            source = dict(payload["source"])
            document = _normalized_document_from_row(payload["document"])
            try:
                hydration = self.document_provider.hydrate_document_evidence(source=source, document=document)
                artifacts = list(hydration.artifacts)
            except Exception as exc:
                return self._handle_hydration_exception(payload=payload, error=exc, now_ms=now_ms)

            if not artifacts:
                artifacts = [
                    build_unavailable_evidence_artifact(
                        event_document_id=str(document.event_document_id),
                        provider_document_id=document.provider_document_id,
                        source_id=str(source["source_id"]),
                        artifact_kind="html_text",
                        source_url=document.document_url,
                        reason="evidence_hydration_empty",
                        fetched_at_ms=now_ms,
                        parsed_at_ms=now_ms,
                        now_ms=now_ms,
                    )
                ]
            return self._persist_terminal_result(
                payload=payload,
                artifacts=artifacts,
                now_ms=now_ms,
                job_status="success",
            )
        except Exception as exc:  # pragma: no cover - defensive path for DB/session failures.
            self._finish_failure(
                evidence_job_id=evidence_job_id,
                error=f"evidence_hydration_worker_exception:{type(exc).__name__}",
                now_ms=now_ms,
                terminal=False,
            )
            return WorkerResult(failed=1, notes={"evidence_job_id": evidence_job_id, "error": str(exc)})

    def _handle_hydration_exception(self, *, payload: Mapping[str, Any], error: Exception, now_ms: int) -> WorkerResult:
        job = dict(payload["job"])
        terminal = int(job.get("attempt_count") or 0) >= int(job.get("max_attempts") or self._max_attempts())
        reason = _hydration_exception_reason(error)
        if not terminal:
            self._finish_failure(
                evidence_job_id=str(job["evidence_job_id"]),
                error=reason,
                now_ms=now_ms,
                terminal=False,
            )
            return WorkerResult(failed=1, notes={"evidence_job_id": str(job["evidence_job_id"]), "error": reason})

        source = dict(payload["source"])
        document = _normalized_document_from_row(payload["document"])
        artifact = build_failed_evidence_artifact(
            event_document_id=str(document.event_document_id),
            provider_document_id=document.provider_document_id,
            source_id=str(source["source_id"]),
            artifact_kind="html_text",
            source_url=document.document_url,
            reason=reason,
            fetched_at_ms=now_ms,
            parsed_at_ms=now_ms,
            now_ms=now_ms,
        )
        return self._persist_terminal_result(
            payload=payload,
            artifacts=[artifact],
            now_ms=now_ms,
            job_status="failed_terminal",
            error=reason,
        )

    def _persist_terminal_result(
        self,
        *,
        payload: Mapping[str, Any],
        artifacts: list[NormalizedEquityEvidenceArtifact],
        now_ms: int,
        job_status: str,
        error: str | None = None,
    ) -> WorkerResult:
        job = dict(payload["job"])
        source = dict(payload["source"])
        document = dict(payload["document"])
        event_document_id = str(document["event_document_id"])
        source_id = str(source["source_id"])
        evidence_status, evidence_reason, evidence_ready_at_ms = _evidence_document_status(
            artifacts,
            fetched_at_ms=now_ms,
        )

        with self._repository_session() as repos:
            repos.equity_events.replace_evidence_artifacts(
                event_document_id=event_document_id,
                artifacts=_artifact_mappings(artifacts),
                now_ms=now_ms,
                commit=False,
            )
            repos.equity_events.mark_event_document_evidence_status(
                event_document_id=event_document_id,
                evidence_status=evidence_status,
                evidence_reason=evidence_reason,
                evidence_ready_at_ms=evidence_ready_at_ms,
                now_ms=now_ms,
                commit=False,
            )
            if job_status == "success":
                repos.equity_events.finish_evidence_job_success(
                    evidence_job_id=str(job["evidence_job_id"]),
                    finished_at_ms=now_ms,
                    commit=False,
                )
            else:
                repos.equity_events.finish_evidence_job_terminal(
                    evidence_job_id=str(job["evidence_job_id"]),
                    finished_at_ms=now_ms,
                    error=error or evidence_reason,
                    commit=False,
                )
            if evidence_status == "ready":
                repos.equity_events.update_source_material_freshness(
                    source_id=source_id,
                    evidence_ready_at_ms=now_ms,
                    now_ms=now_ms,
                    commit=False,
                )
            elif evidence_status == "failed" and evidence_reason:
                repos.equity_events.update_source_material_freshness(
                    source_id=source_id,
                    actionable_error=evidence_reason,
                    now_ms=now_ms,
                    commit=False,
                )
            repos.conn.commit()

        if evidence_status in {"ready", "unavailable", "failed"} and self.wake_bus is not None:
            self.wake_bus.notify_equity_event_document_written(source_id=source_id, count=1)
        return WorkerResult(processed=1, notes={"terminal_written": 1, "evidence_status": evidence_status})

    def _finish_failure(self, *, evidence_job_id: str, error: str, now_ms: int, terminal: bool) -> None:
        with self._repository_session() as repos:
            if terminal:
                repos.equity_events.finish_evidence_job_terminal(
                    evidence_job_id=evidence_job_id,
                    finished_at_ms=now_ms,
                    error=error,
                    commit=False,
                )
            else:
                repos.equity_events.finish_evidence_job_retryable(
                    evidence_job_id=evidence_job_id,
                    error=error,
                    due_at_ms=now_ms + self._retry_delay_ms(),
                    now_ms=now_ms,
                    commit=False,
                )
            repos.conn.commit()

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 20)))

    def _lease_ms(self) -> int:
        return max(1, int(getattr(self.settings, "lease_ms", getattr(self.settings, "claim_lease_ms", 60_000))))

    def _max_attempts(self) -> int:
        return max(1, int(getattr(self.settings, "max_attempts", 3)))

    def _retry_delay_ms(self) -> int:
        return max(1, int(getattr(self.settings, "retry_delay_ms", 60_000)))


def _normalized_document_from_row(row: Mapping[str, Any]) -> NormalizedEquityDocument:
    return NormalizedEquityDocument(
        event_document_id=str(row["event_document_id"]),
        provider_document_id=_optional_str(row.get("provider_document_id")),
        provider_document_key=str(row["provider_document_key"]),
        company_id=str(row["company_id"]),
        ticker=str(row["ticker"]),
        cik=_optional_str(row.get("cik")),
        document_url=str(row["document_url"]),
        payload_hash=str(row["payload_hash"]),
        raw_payload_json=dict(row.get("raw_payload_json") or {}),
        fetched_at_ms=int(row.get("fetched_at_ms") or 0),
        document_type=str(row.get("document_type") or "unknown"),
        form_type=_optional_str(row.get("form_type")),
        accession_number=_optional_str(row.get("accession_number")),
        fiscal_period=_optional_str(row.get("fiscal_period")),
        event_time_ms=int(row["event_time_ms"]) if row.get("event_time_ms") is not None else None,
        content_hash=_optional_str(row.get("content_hash")),
    )


def _evidence_document_status(
    artifacts: list[NormalizedEquityEvidenceArtifact],
    *,
    fetched_at_ms: int,
) -> tuple[str, str, int | None]:
    ready_reasons = [
        str(artifact.failure_reason or "").strip() for artifact in artifacts if artifact.extraction_status == "ready"
    ]
    if ready_reasons:
        reason = next((value for value in ready_reasons if value), "") if all(ready_reasons) else ""
        return "ready", reason, int(fetched_at_ms)

    reasons = [str(artifact.failure_reason or "").strip() for artifact in artifacts]
    reason = next((value for value in reasons if value), "")
    statuses = {str(artifact.extraction_status) for artifact in artifacts}
    if statuses == {"failed"}:
        return "failed", reason, None
    return "unavailable", reason, None


def _artifact_mappings(artifacts: list[NormalizedEquityEvidenceArtifact]) -> list[Mapping[str, Any]]:
    return [asdict(artifact) if is_dataclass(artifact) else artifact for artifact in artifacts]


def _hydration_exception_reason(exc: Exception) -> str:
    class_name = type(exc).__name__.strip() or "Exception"
    return f"evidence_hydration_exception:{class_name}"[:240]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _now_ms() -> int:
    return int(time.time() * 1000)
