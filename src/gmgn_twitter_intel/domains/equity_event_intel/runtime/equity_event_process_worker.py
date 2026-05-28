from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel.services.company_identity import validate_company_identity
from gmgn_twitter_intel.domains.equity_event_intel.services.event_classifier import classify_equity_event
from gmgn_twitter_intel.domains.equity_event_intel.services.fact_candidates import (
    build_fact_candidates,
    build_source_spans,
    ready_evidence_texts,
)


class EquityEventProcessWorker(WorkerBase):
    def __init__(
        self,
        *,
        wake_bus: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        runtime_context = self._runtime_context()
        with runtime_context.claim_session() as repos:
            expired = repos.equity_events.expire_stale_process_jobs(
                now_ms=now,
                limit=self._batch_size(),
                commit=False,
            )
            claims = repos.equity_events.claim_due_process_jobs(
                now_ms=now,
                limit=self._batch_size(),
                lease_owner=self.name,
                lease_ms=self._lease_ms(),
                commit=False,
            )
            repos.conn.commit()
        runtime_context.mark_claimed(count=len(claims))
        if not claims:
            return WorkerResult(
                skipped=1,
                notes={"reason": "no_due_process_jobs", "expired": len(expired)},
            )

        with runtime_context.payload_session() as repos:
            packets = repos.equity_events.load_process_packets_for_claims(claims=claims)

        processed = 0
        failed = 0
        stale_claims = max(0, len(claims) - len(packets))
        for packet in packets:
            try:
                materials = self._build_packet_materials(packet, now_ms=now)
                self._persist_packet_success(
                    packet=packet,
                    materials=materials,
                    now_ms=now,
                    runtime_context=runtime_context,
                )
                processed += 1
            except _StaleProcessJobClaim:
                stale_claims += 1
            except Exception as exc:  # pragma: no cover - defensive worker path.
                try:
                    self._persist_packet_failure(
                        packet=packet,
                        error=exc,
                        now_ms=now,
                        runtime_context=runtime_context,
                    )
                except _StaleProcessJobClaim:
                    stale_claims += 1
                except Exception:
                    failed += 1
                else:
                    failed += 1

        if processed > 0 and self.wake_bus is not None:
            self.wake_bus.notify_equity_event_processed(count=processed)
        return WorkerResult(
            processed=processed,
            failed=failed,
            notes={
                "claimed": len(claims),
                "loaded": len(packets),
                "expired": len(expired),
                "stale_claim": stale_claims,
            },
        )

    def _build_packet_materials(self, packet: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
        event_document_id = _required_packet_text(packet, "event_document_id")
        identity = validate_company_identity(packet)
        event = classify_equity_event(packet)
        evidence_artifacts = _evidence_artifacts(packet)
        evidence_status = str(packet.get("evidence_status") or "pending")
        evidence_reason = str(packet.get("evidence_reason") or "")
        artifact_texts = ready_evidence_texts(evidence_artifacts) if evidence_status == "ready" else []
        spans = build_source_spans(
            company_event_id=event.company_event_id,
            event_document_id=event_document_id,
            evidence_artifacts=evidence_artifacts if evidence_status == "ready" else [],
            now_ms=now_ms,
        )
        candidates = []
        for span, artifact_text in zip(spans, artifact_texts, strict=True):
            candidates.extend(
                build_fact_candidates(
                    company_event_id=event.company_event_id,
                    event_document_id=event_document_id,
                    source_span_id=span.span_id,
                    company_id=event.company_id,
                    ticker=event.ticker,
                    event_type=event.event_type,
                    period=event.fiscal_period,
                    source_role=event.source_role,
                    evidence_text=artifact_text["text"],
                    now_ms=now_ms,
                )
            )
        fact_status, fact_reason, fact_extracted_at_ms = _fact_extraction_status(
            evidence_status=evidence_status,
            evidence_reason=evidence_reason,
            has_evidence_text=bool(artifact_texts),
            candidates=candidates,
            now_ms=now_ms,
        )
        return {
            "identity": identity,
            "event": event,
            "evidence_status": evidence_status,
            "evidence_reason": evidence_reason,
            "spans": spans,
            "candidates": candidates,
            "fact_status": fact_status,
            "fact_reason": fact_reason,
            "fact_extracted_at_ms": fact_extracted_at_ms,
        }

    def _persist_packet_success(
        self,
        *,
        packet: dict[str, Any],
        materials: dict[str, Any],
        now_ms: int,
        runtime_context: Any | None = None,
    ) -> None:
        context = runtime_context or self._runtime_context()
        event_document_id, lease_owner, attempt_count, input_payload_hash = _process_job_guard(packet)
        identity = materials["identity"]
        event = materials["event"]
        with context.transaction_session() as repos:
            old_company_event_ids = repos.equity_events.company_event_ids_for_document(
                event_document_id=event_document_id
            )
            repos.equity_events.clear_story_members_for_document(
                event_document_id=event_document_id,
                active_company_event_id=event.company_event_id,
                now_ms=now_ms,
                commit=False,
            )
            repos.equity_events.upsert_company_event(
                company_event_id=event.company_event_id,
                company_id=event.company_id,
                ticker=event.ticker,
                primary_document_id=event.primary_document_id,
                event_type=event.event_type,
                priority=event.priority,
                source_role=event.source_role,
                fiscal_period=event.fiscal_period,
                event_time_ms=event.event_time_ms,
                discovered_at_ms=event.discovered_at_ms,
                lifecycle_status=event.lifecycle_status,
                validation_status=identity.validation_status,
                summary=event.summary,
                now_ms=now_ms,
                commit=False,
            )
            repos.equity_events.mark_event_document_evidence_status(
                event_document_id=event_document_id,
                evidence_status=materials["evidence_status"],
                evidence_reason=materials["evidence_reason"],
                evidence_ready_at_ms=packet.get("evidence_ready_at_ms"),
                now_ms=now_ms,
                commit=False,
            )
            repos.equity_events.replace_source_spans(
                event_document_id=event_document_id,
                company_event_id=event.company_event_id,
                spans=materials["spans"],
                commit=False,
            )
            repos.equity_events.replace_fact_candidates(
                event_document_id=event_document_id,
                company_event_id=event.company_event_id,
                candidates=materials["candidates"],
                commit=False,
            )
            repos.equity_events.mark_event_document_fact_extraction_status(
                event_document_id=event_document_id,
                fact_extraction_status=materials["fact_status"],
                fact_extraction_reason=materials["fact_reason"],
                fact_extracted_at_ms=materials["fact_extracted_at_ms"],
                now_ms=now_ms,
                commit=False,
            )
            repos.equity_events.mark_event_document_processed(
                event_document_id=event_document_id,
                processed_at_ms=now_ms,
                commit=False,
            )
            company_event_ids = _unique_ids([event.company_event_id, *old_company_event_ids])
            expected_event_ids = repos.equity_events.matching_expected_event_ids_for_company_events(
                company_event_ids=company_event_ids
            )
            dirty_targets = _company_event_dirty_targets(
                company_event_ids=company_event_ids,
                source_watermark_ms=now_ms,
            )
            dirty_targets.extend(
                _expected_event_dirty_targets(
                    expected_event_ids=expected_event_ids,
                    source_watermark_ms=now_ms,
                )
            )
            repos.equity_projection_dirty_targets.enqueue_targets(
                dirty_targets,
                reason="event_processed",
                now_ms=now_ms,
                commit=False,
            )
            finished = repos.equity_events.finish_process_job_success(
                event_document_id=event_document_id,
                lease_owner=lease_owner,
                attempt_count=attempt_count,
                input_payload_hash=input_payload_hash,
                now_ms=now_ms,
                commit=False,
            )
            if not finished:
                raise _StaleProcessJobClaim(event_document_id)

    def _persist_packet_failure(
        self,
        *,
        packet: dict[str, Any],
        error: Exception,
        now_ms: int,
        runtime_context: Any | None = None,
    ) -> None:
        context = runtime_context or self._runtime_context()
        event_document_id, lease_owner, attempt_count, input_payload_hash = _process_job_guard(packet)
        with context.transaction_session() as repos:
            repos.equity_events.mark_event_document_process_failed(
                event_document_id=event_document_id,
                error=str(error)[:2_000],
                now_ms=now_ms,
                commit=False,
            )
            finished = repos.equity_events.finish_process_job_failure(
                event_document_id=event_document_id,
                lease_owner=lease_owner,
                attempt_count=attempt_count,
                input_payload_hash=input_payload_hash,
                error=str(error)[:2_000],
                now_ms=now_ms,
                retry_ms=self._retry_ms(),
                commit=False,
            )
            if not finished:
                raise _StaleProcessJobClaim(event_document_id)

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))

    def _lease_ms(self) -> int:
        return max(1, int(getattr(self.settings, "lease_ms", getattr(self.settings, "claim_lease_ms", 60_000))))

    def _retry_ms(self) -> int:
        return max(1, int(getattr(self.settings, "retry_ms", getattr(self.settings, "retry_delay_ms", 60_000))))


def _now_ms() -> int:
    return int(time.time() * 1000)


class _StaleProcessJobClaim(Exception):
    pass


def _evidence_artifacts(document: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = document.get("evidence_artifacts")
    if not isinstance(artifacts, list):
        return []
    return [dict(artifact) for artifact in artifacts if isinstance(artifact, dict)]


def _process_job_guard(packet: dict[str, Any]) -> tuple[str, str, int, str]:
    return (
        _required_packet_text(packet, "event_document_id"),
        _required_packet_text(packet, "lease_owner"),
        int(packet["attempt_count"]),
        _required_packet_text(packet, "input_payload_hash"),
    )


def _required_packet_text(packet: dict[str, Any], key: str) -> str:
    value = str(packet.get(key) or "").strip()
    if not value:
        raise ValueError(f"equity process packet missing {key}")
    return value


def _fact_extraction_status(
    *,
    evidence_status: str,
    evidence_reason: str,
    has_evidence_text: bool,
    candidates: list[Any],
    now_ms: int,
) -> tuple[str, str, int | None]:
    if evidence_status != "ready":
        return "no_evidence", evidence_reason or evidence_status, None
    if not has_evidence_text:
        return "no_evidence", evidence_reason or "no_ready_evidence_text", None
    if candidates:
        return "ready", "", int(now_ms)
    return "no_extractable_facts", "no_revenue_or_eps_facts", None


def _company_event_dirty_targets(*, company_event_ids: list[str], source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": projection_name,
            "target_kind": "company_event",
            "target_id": company_event_id,
            "source_watermark_ms": int(source_watermark_ms),
        }
        for company_event_id in company_event_ids
        for projection_name in ("story", "brief_input", "page", "timeline", "alert")
    ]


def _expected_event_dirty_targets(*, expected_event_ids: list[str], source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": "calendar",
            "target_kind": "expected_event",
            "target_id": expected_event_id,
            "source_watermark_ms": int(source_watermark_ms),
        }
        for expected_event_id in expected_event_ids
    ]


def _unique_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


__all__ = ["EquityEventProcessWorker"]
