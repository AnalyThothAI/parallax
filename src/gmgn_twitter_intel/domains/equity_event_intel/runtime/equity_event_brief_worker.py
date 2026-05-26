from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel.services.brief_input import (
    build_equity_event_brief_input_packet,
)
from gmgn_twitter_intel.domains.equity_event_intel.services.brief_validation import (
    validate_equity_event_brief_output,
)
from gmgn_twitter_intel.domains.equity_event_intel.types import (
    EQUITY_EVENT_BRIEF_LANE,
    EquityEventBriefAgentConfig,
    EquityEventBriefInputPacket,
    default_equity_event_brief_agent_config,
)
from gmgn_twitter_intel.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
)
from gmgn_twitter_intel.platform.agent_hashing import json_sha256

_OFFICIAL_SOURCE_ROLES = {"official_regulator", "official_issuer"}


class EquityEventBriefWorker(WorkerBase):
    def __init__(
        self,
        *,
        provider: Any | None = None,
        wake_bus: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        run_id_factory: Callable[[], str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.provider = provider
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms
        self.run_id_factory = run_id_factory or _default_run_id

    async def run_once(self) -> WorkerResult:
        if self.provider is None:
            return WorkerResult(skipped=1, notes={"reason": "missing_provider"})

        now = self.clock_ms()
        agent_config = default_equity_event_brief_agent_config(
            model=str(self.provider.model),
            artifact_version_hash=str(self.provider.artifact_version_hash),
        )
        claimed = await asyncio.to_thread(self._claim_targets, now_ms=now)
        if not claimed:
            return WorkerResult(skipped=1, notes={"reason": "no_due_brief_targets"})
        try:
            candidates = await asyncio.to_thread(self._load_candidates, claimed=claimed)
        except Exception as exc:
            await asyncio.to_thread(self._mark_targets_error, claimed, error=exc, retry_ms=self._retry_ms(), now_ms=now)
            return WorkerResult(failed=len(claimed), notes={"claimed": len(claimed), "load_failed": 1})

        candidates_by_id = {
            str(candidate.get("event", {}).get("company_event_id") or ""): candidate
            for candidate in candidates
            if isinstance(candidate.get("event"), Mapping)
        }

        notes = {
            "claimed": len(claimed),
            "ready": 0,
            "insufficient": 0,
            "failed": 0,
            "backpressure": 0,
            "validation_failed": 0,
            "no_official_evidence": 0,
            "missing_target": 0,
        }
        skipped = 0
        current_updates = 0

        for target in claimed:
            target_id = str(target.get("target_id") or "")
            candidate = candidates_by_id.get(target_id)
            packet: EquityEventBriefInputPacket | None = None
            source_updated_at_ms = now
            if candidate is None:
                notes["missing_target"] += 1
                await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                skipped += 1
                continue

            try:
                source_updated_at_ms = int(candidate.get("source_updated_at_ms") or now)
                packet = _packet_from_candidate(candidate, agent_config=agent_config)
                if _current_brief_is_fresh(candidate, packet=packet, agent_config=agent_config):
                    await asyncio.to_thread(
                        self._upsert_brief_readiness,
                        company_event_id=packet.current_event.company_event_id,
                        status=_fresh_current_brief_readiness_status(candidate),
                        reason_code="current_brief_fresh",
                        reason_detail="current brief matches current source input hash",
                        input_hash=packet.input_hash,
                        source_updated_at_ms=source_updated_at_ms,
                        next_retry_after_ms=None,
                        updated_at_ms=now,
                    )
                    await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                    skipped += 1
                    continue
                if not _has_official_evidence(packet):
                    outcome = await self._record_no_official_evidence(
                        packet=packet,
                        agent_config=agent_config,
                        source_updated_at_ms=source_updated_at_ms,
                    )
                    for key, value in outcome.notes.items():
                        notes[key] = int(notes.get(key, 0)) + int(value)
                    current_updates += outcome.current_updates
                    notes["no_official_evidence"] += 1
                    await asyncio.to_thread(
                        self._upsert_brief_readiness,
                        company_event_id=packet.current_event.company_event_id,
                        status=outcome.readiness_status,
                        reason_code=outcome.readiness_reason_code,
                        reason_detail=outcome.readiness_reason_detail,
                        input_hash=packet.input_hash,
                        source_updated_at_ms=source_updated_at_ms,
                        next_retry_after_ms=_next_retry_after_ms(now_ms=now, retry_ms=outcome.retry_ms),
                        updated_at_ms=now,
                    )
                    await asyncio.to_thread(self._complete_claimed_target, target, outcome=outcome, now_ms=now)
                    continue

                await asyncio.to_thread(
                    self._upsert_brief_readiness,
                    company_event_id=packet.current_event.company_event_id,
                    status="in_progress",
                    reason_code="agent_execution_started",
                    reason_detail="brief input is ready and agent execution is starting",
                    input_hash=packet.input_hash,
                    source_updated_at_ms=source_updated_at_ms,
                    next_retry_after_ms=None,
                    updated_at_ms=now,
                )
                outcome = await self._process_candidate(
                    packet=packet,
                    agent_config=agent_config,
                    now_ms=now,
                    source_updated_at_ms=source_updated_at_ms,
                )
            except Exception as exc:
                notes["failed"] += 1
                if packet is not None:
                    await asyncio.to_thread(
                        self._upsert_brief_readiness,
                        company_event_id=packet.current_event.company_event_id,
                        status="failed_retryable",
                        reason_code=type(exc).__name__,
                        reason_detail=str(exc)[:500],
                        input_hash=packet.input_hash,
                        source_updated_at_ms=source_updated_at_ms,
                        next_retry_after_ms=now + self._retry_ms(),
                        updated_at_ms=now,
                    )
                await asyncio.to_thread(
                    self._mark_targets_error,
                    [target],
                    error=exc,
                    retry_ms=self._retry_ms(),
                    now_ms=now,
                )
                continue
            for key, value in outcome.notes.items():
                notes[key] = int(notes.get(key, 0)) + int(value)
            current_updates += outcome.current_updates
            await asyncio.to_thread(
                self._upsert_brief_readiness,
                company_event_id=packet.current_event.company_event_id,
                status=outcome.readiness_status,
                reason_code=outcome.readiness_reason_code,
                reason_detail=outcome.readiness_reason_detail,
                input_hash=packet.input_hash,
                source_updated_at_ms=source_updated_at_ms,
                next_retry_after_ms=_next_retry_after_ms(now_ms=now, retry_ms=outcome.retry_ms),
                updated_at_ms=now,
            )
            await asyncio.to_thread(self._complete_claimed_target, target, outcome=outcome, now_ms=now)

        if current_updates > 0 and self.wake_bus is not None:
            self.wake_bus.notify_equity_event_brief_updated(count=current_updates)
        failed = int(notes["failed"])
        processed = int(notes["ready"]) + int(notes["insufficient"])
        skipped += int(notes["backpressure"])
        return WorkerResult(processed=processed, failed=failed, skipped=skipped, notes=notes)

    def run_once_sync(self) -> WorkerResult:
        return asyncio.run(self.run_once())

    async def _process_candidate(
        self,
        *,
        packet: EquityEventBriefInputPacket,
        agent_config: EquityEventBriefAgentConfig,
        now_ms: int,
        source_updated_at_ms: int,
    ) -> _CandidateOutcome:
        del now_ms
        run_id = self.run_id_factory()
        started_at_ms = self.clock_ms()
        provider = self.provider
        if provider is None:
            raise RuntimeError("equity event brief provider is required")
        try:
            request_audit = provider.request_audit(run_id=run_id, packet=packet)
        except Exception as exc:
            request_audit = _fallback_request_audit(
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                provider=provider,
            )
            return await self._record_provider_failure(
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                request_audit=request_audit,
                error=exc,
                started_at_ms=started_at_ms,
                execution_started=False,
            )

        try:
            reservation = provider.try_reserve_execution(EQUITY_EVENT_BRIEF_LANE)
        except Exception as exc:
            return await self._record_provider_failure(
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                request_audit=request_audit,
                error=exc,
                started_at_ms=started_at_ms,
                execution_started=False,
            )
        if not reservation.acquired:
            outcome = _backpressure_outcome(reservation)
            await asyncio.to_thread(
                self._insert_run,
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                audit=request_audit,
                started_at_ms=started_at_ms,
                finished_at_ms=self.clock_ms(),
                status="backpressure",
                outcome=outcome,
                error_class=_reason_value(reservation.reason),
                error=f"equity event brief execution deferred: {outcome}",
                request_json=_request_json(packet=packet, audit=request_audit),
                response_json=None,
                validation_errors=[],
                execution_started=False,
            )
            return _CandidateOutcome(
                notes={"backpressure": 1, outcome: 1},
                current_updates=0,
                retry_ms=self._backpressure_cooldown_ms(),
                retry_reason=outcome,
                readiness_status="pending_due",
                readiness_reason_code=outcome,
                readiness_reason_detail="brief execution deferred by capacity controls",
            )

        try:
            result = await provider.brief_event(run_id=run_id, packet=packet, reservation=reservation)
        except Exception as exc:
            if _is_no_start_backpressure_error(exc):
                return await self._record_execute_backpressure(
                    run_id=run_id,
                    packet=packet,
                    agent_config=agent_config,
                    request_audit=request_audit,
                    error=exc,
                    started_at_ms=started_at_ms,
                )
            return await self._record_provider_failure(
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                request_audit=request_audit,
                error=exc,
                started_at_ms=started_at_ms,
            )
        finally:
            await _release_reservation(reservation)

        payload = result.get("payload") if isinstance(result, Mapping) else None
        audit = _audit_dict(result.get("agent_run_audit") if isinstance(result, Mapping) else None) or request_audit
        validation = validate_equity_event_brief_output(payload=payload, packet=packet, audit=audit)
        finished_at_ms = self.clock_ms()
        current_source_updated_at_ms = await asyncio.to_thread(
            self._current_source_updated_at_ms,
            company_event_id=packet.current_event.company_event_id,
        )
        if current_source_updated_at_ms > int(source_updated_at_ms):
            errors = [
                {
                    "code": "source_changed_before_publish",
                    "message": (
                        "equity event source evidence changed after the brief input packet was built; "
                        "discarding stale agent output"
                    ),
                }
            ]
            await asyncio.to_thread(
                self._insert_run,
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                audit=audit,
                started_at_ms=started_at_ms,
                finished_at_ms=finished_at_ms,
                status="failed",
                outcome="failed",
                error_class="source_changed_before_publish",
                error=errors[0]["message"],
                request_json=_request_json(packet=packet, audit=request_audit),
                response_json=payload if isinstance(payload, Mapping) else {"payload": payload},
                validation_errors=errors,
                execution_started=True,
                output_hash=validation.output_hash or _output_hash(payload),
            )
            await asyncio.to_thread(
                self._upsert_failed_current,
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                errors=errors,
                computed_at_ms=int(source_updated_at_ms),
            )
            return _CandidateOutcome(
                notes={"failed": 1, "source_changed_before_publish": 1},
                current_updates=1,
                retry_ms=self._retry_ms(),
                retry_reason="source_changed_before_publish",
                readiness_status="failed_retryable",
                readiness_reason_code="source_changed_before_publish",
                readiness_reason_detail=errors[0]["message"],
            )
        if not validation.publishable:
            await asyncio.to_thread(
                self._insert_run,
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                audit=audit,
                started_at_ms=started_at_ms,
                finished_at_ms=finished_at_ms,
                status="failed",
                outcome="failed",
                error_class="domain_validation_failed",
                error="equity event brief validation failed",
                request_json=_request_json(packet=packet, audit=request_audit),
                response_json=payload if isinstance(payload, Mapping) else {"payload": payload},
                validation_errors=validation.errors,
                execution_started=True,
                output_hash=_output_hash(payload),
            )
            await asyncio.to_thread(
                self._upsert_failed_current,
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                errors=validation.errors,
                computed_at_ms=finished_at_ms,
            )
            return _CandidateOutcome(
                notes={"failed": 1, "validation_failed": 1},
                current_updates=1,
                retry_ms=self._retry_ms(),
                retry_reason="domain_validation_failed",
                retry_attempt_limited=True,
                readiness_status="failed_retryable",
                readiness_reason_code="domain_validation_failed",
                readiness_reason_detail="equity event brief validation failed",
            )

        payload_dict = validation.payload or {}
        await asyncio.to_thread(
            self._insert_run,
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            audit=audit,
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
            status="completed",
            outcome=str(validation.status),
            error_class=None,
            error=None,
            request_json=_request_json(packet=packet, audit=request_audit),
            response_json=payload_dict,
            validation_errors=[],
            execution_started=True,
            output_hash=validation.output_hash,
        )
        await asyncio.to_thread(
            self._upsert_current,
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            payload=payload_dict,
            validation_status="accepted" if str(validation.status) == "ready" else "attention",
            computed_at_ms=finished_at_ms,
        )
        status = str(validation.status)
        return _CandidateOutcome(
            notes={status: 1},
            current_updates=1,
            readiness_status=_brief_status_to_readiness_status(status),
            readiness_reason_code=f"brief_{status}",
            readiness_reason_detail=f"brief generation completed with status {status}",
        )

    async def _record_no_official_evidence(
        self,
        *,
        packet: EquityEventBriefInputPacket,
        agent_config: EquityEventBriefAgentConfig,
        source_updated_at_ms: int,
    ) -> _CandidateOutcome:
        provider = self.provider
        if provider is None:
            raise RuntimeError("equity event brief provider is required")
        run_id = self.run_id_factory()
        started_at_ms = self.clock_ms()
        finished_at_ms = started_at_ms
        request_audit = _fallback_request_audit(
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            provider=provider,
        )
        payload = _insufficient_no_official_evidence_brief(packet)
        await asyncio.to_thread(
            self._insert_run,
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            audit=request_audit,
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
            status="completed",
            outcome="insufficient",
            error_class=None,
            error=None,
            request_json=_request_json(packet=packet, audit=request_audit),
            response_json=payload,
            validation_errors=[],
            execution_started=False,
            output_hash=json_sha256(payload),
        )
        await asyncio.to_thread(
            self._upsert_current,
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            payload=payload,
            validation_status="attention",
            computed_at_ms=int(source_updated_at_ms),
        )
        return _CandidateOutcome(
            notes={"insufficient": 1},
            current_updates=1,
            readiness_status="insufficient",
            readiness_reason_code="no_official_evidence",
            readiness_reason_detail="event lacks official regulator or issuer evidence for a publishable brief",
        )

    async def _record_provider_failure(
        self,
        *,
        run_id: str,
        packet: EquityEventBriefInputPacket,
        agent_config: EquityEventBriefAgentConfig,
        request_audit: Mapping[str, Any],
        error: Exception,
        started_at_ms: int,
        execution_started: bool | None = None,
    ) -> _CandidateOutcome:
        audit = _provider_error_audit(error) or dict(request_audit)
        resolved_execution_started = (
            bool(execution_started) if execution_started is not None else _provider_execution_started(error)
        )
        finished_at_ms = self.clock_ms()
        await asyncio.to_thread(
            self._insert_run,
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            audit=audit,
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
            status="failed",
            outcome="failed",
            error_class=_provider_error_class(error),
            error=str(error),
            request_json=_request_json(packet=packet, audit=request_audit),
            response_json=None,
            validation_errors=[],
            execution_started=resolved_execution_started,
        )
        await asyncio.to_thread(
            self._upsert_failed_current,
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            errors=[{"code": _provider_error_class(error), "message": str(error)[:500]}],
            computed_at_ms=finished_at_ms,
        )
        return _CandidateOutcome(
            notes={"failed": 1},
            current_updates=1,
            retry_ms=self._retry_ms(),
            retry_reason=_provider_error_class(error),
            retry_attempt_limited=resolved_execution_started,
            readiness_status="failed_retryable",
            readiness_reason_code=_provider_error_class(error),
            readiness_reason_detail=str(error)[:500],
        )

    async def _record_execute_backpressure(
        self,
        *,
        run_id: str,
        packet: EquityEventBriefInputPacket,
        agent_config: EquityEventBriefAgentConfig,
        request_audit: Mapping[str, Any],
        error: Exception,
        started_at_ms: int,
    ) -> _CandidateOutcome:
        audit = _provider_error_audit(error) or dict(request_audit)
        outcome = _backpressure_outcome_for_reason(getattr(error, "error_class", None))
        finished_at_ms = self.clock_ms()
        await asyncio.to_thread(
            self._insert_run,
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            audit=audit,
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
            status="backpressure",
            outcome=outcome,
            error_class=_provider_error_class(error),
            error=str(error),
            request_json=_request_json(packet=packet, audit=request_audit),
            response_json=None,
            validation_errors=[],
            execution_started=False,
        )
        return _CandidateOutcome(
            notes={"backpressure": 1, outcome: 1},
            current_updates=0,
            retry_ms=self._backpressure_cooldown_ms(),
            retry_reason=outcome,
            readiness_status="pending_due",
            readiness_reason_code=outcome,
            readiness_reason_detail="brief execution deferred before provider start",
        )

    def _claim_targets(self, *, now_ms: int) -> list[dict[str, Any]]:
        with self._repository_session() as repos:
            rows = repos.equity_projection_dirty_targets.claim_due(
                limit=self._batch_size(),
                lease_ms=self._lease_ms(),
                now_ms=now_ms,
                lease_owner=self.name,
                projection_name="brief_input",
                target_kind="company_event",
            )
        return [dict(row) for row in rows]

    def _load_candidates(self, *, claimed: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        company_event_ids = _target_ids(claimed)
        if not company_event_ids:
            return []
        with self._repository_session() as repos:
            rows = repos.equity_events.load_events_for_brief_targets(company_event_ids=company_event_ids)
        return [dict(row) for row in rows]

    def _complete_claimed_target(
        self,
        target: Mapping[str, Any],
        *,
        outcome: _CandidateOutcome,
        now_ms: int,
    ) -> None:
        if outcome.retry_ms is not None and (
            not outcome.retry_attempt_limited or int(target.get("attempt_count") or 0) < self._max_attempts()
        ):
            self._mark_targets_error([target], error=outcome.retry_reason, retry_ms=outcome.retry_ms, now_ms=now_ms)
            return
        self._mark_targets_done([target], now_ms=now_ms)

    def _mark_targets_done(self, targets: Iterable[Mapping[str, Any]], *, now_ms: int) -> None:
        with self._repository_session() as repos:
            repos.equity_projection_dirty_targets.mark_done(targets, now_ms=now_ms)

    def _mark_targets_error(
        self,
        targets: Iterable[Mapping[str, Any]],
        *,
        error: Exception | str,
        retry_ms: int,
        now_ms: int,
    ) -> None:
        with self._repository_session() as repos:
            repos.equity_projection_dirty_targets.mark_error(
                targets,
                error=str(error),
                retry_ms=retry_ms,
                now_ms=now_ms,
            )

    def _insert_run(
        self,
        *,
        run_id: str,
        packet: EquityEventBriefInputPacket,
        agent_config: EquityEventBriefAgentConfig,
        audit: Mapping[str, Any],
        started_at_ms: int,
        finished_at_ms: int,
        status: str,
        outcome: str,
        error_class: str | None,
        error: str | None,
        request_json: Mapping[str, Any],
        response_json: Any | None,
        validation_errors: list[dict[str, str]],
        execution_started: bool,
        output_hash: str | None = None,
    ) -> None:
        provider = self.provider
        if provider is None:
            raise RuntimeError("equity event brief provider is required")
        with self._repository_session() as repos:
            repos.equity_events.insert_equity_event_agent_run(
                run_id=run_id,
                company_event_id=packet.current_event.company_event_id,
                provider=str(audit.get("provider") or provider.provider),
                model=str(audit.get("model") or agent_config.model),
                backend=str(audit.get("backend") or "openai_agents_sdk"),
                sdk_trace_id=audit.get("sdk_trace_id"),
                workflow_name=str(audit.get("workflow_name") or agent_config.workflow_name),
                agent_name=str(audit.get("agent_name") or agent_config.agent_name),
                lane=str(audit.get("lane") or agent_config.lane),
                artifact_version_hash=str(audit.get("artifact_version_hash") or agent_config.artifact_version_hash),
                prompt_version=str(audit.get("prompt_version") or agent_config.prompt_version),
                schema_version=str(audit.get("schema_version") or agent_config.schema_version),
                validator_version=agent_config.validator_version,
                guardrail_version=agent_config.guardrail_version,
                input_hash=str(audit.get("input_hash") or packet.input_hash),
                output_hash=output_hash or audit.get("output_hash"),
                execution_started=bool(execution_started),
                status=status,
                outcome=outcome,
                error_class=error_class,
                error=error,
                request_json=dict(request_json),
                response_json=response_json,
                validation_errors_json=validation_errors,
                trace_metadata_json=_dict(audit.get("trace_metadata")),
                usage_json=_dict(audit.get("usage")),
                latency_ms=int(float(audit.get("latency_ms") or 0)),
                started_at_ms=int(started_at_ms),
                finished_at_ms=int(finished_at_ms),
                created_at_ms=int(started_at_ms),
            )

    def _upsert_current(
        self,
        *,
        run_id: str,
        packet: EquityEventBriefInputPacket,
        agent_config: EquityEventBriefAgentConfig,
        payload: Mapping[str, Any],
        validation_status: str,
        computed_at_ms: int,
    ) -> None:
        with self._repository_session() as repos:
            company_event_id = packet.current_event.company_event_id
            repos.equity_events.upsert_equity_event_agent_brief(
                company_event_id=company_event_id,
                agent_run_id=run_id,
                status=str(payload["status"]),
                validation_status=validation_status,
                brief_json=dict(payload),
                input_hash=packet.input_hash,
                artifact_version_hash=agent_config.artifact_version_hash,
                prompt_version=agent_config.prompt_version,
                schema_version=agent_config.schema_version,
                validator_version=agent_config.validator_version,
                computed_at_ms=int(computed_at_ms),
                created_at_ms=int(computed_at_ms),
                updated_at_ms=int(computed_at_ms),
                commit=False,
            )
            repos.equity_projection_dirty_targets.enqueue_targets(
                _brief_dirty_targets(
                    company_event_id=company_event_id,
                    source_watermark_ms=int(computed_at_ms),
                ),
                reason="brief_updated",
                now_ms=int(computed_at_ms),
                commit=False,
            )
            repos.conn.commit()

    def _upsert_failed_current(
        self,
        *,
        run_id: str,
        packet: EquityEventBriefInputPacket,
        agent_config: EquityEventBriefAgentConfig,
        errors: list[dict[str, str]],
        computed_at_ms: int,
    ) -> None:
        self._upsert_current(
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            payload=_failed_brief(errors),
            validation_status="rejected",
            computed_at_ms=computed_at_ms,
        )

    def _upsert_brief_readiness(
        self,
        *,
        company_event_id: str,
        status: str,
        reason_code: str,
        reason_detail: str,
        input_hash: str,
        source_updated_at_ms: int,
        next_retry_after_ms: int | None,
        updated_at_ms: int,
    ) -> None:
        with self._repository_session() as repos:
            repos.equity_events.upsert_brief_state(
                company_event_id=company_event_id,
                brief_readiness_status=status,
                reason_code=reason_code,
                reason_detail=reason_detail,
                input_hash=input_hash,
                source_updated_at_ms=source_updated_at_ms,
                next_retry_after_ms=next_retry_after_ms,
                updated_at_ms=updated_at_ms,
            )

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 5)))

    def _max_attempts(self) -> int:
        return max(1, int(getattr(self.settings, "max_attempts", 3)))

    def _lease_ms(self) -> int:
        return max(1, int(getattr(self.settings, "lease_ms", 120_000)))

    def _retry_ms(self) -> int:
        return max(1, int(getattr(self.settings, "retry_ms", self._backpressure_cooldown_ms())))

    def _backpressure_cooldown_ms(self) -> int:
        return max(1, int(getattr(self.settings, "backpressure_cooldown_ms", 60_000)))

    def _current_source_updated_at_ms(self, *, company_event_id: str) -> int:
        with self._repository_session() as repos:
            return int(repos.equity_events.get_event_brief_source_updated_at(company_event_id=company_event_id))


class _CandidateOutcome:
    def __init__(
        self,
        *,
        notes: Mapping[str, int],
        current_updates: int,
        retry_ms: int | None = None,
        retry_reason: str = "",
        retry_attempt_limited: bool = False,
        readiness_status: str = "",
        readiness_reason_code: str = "",
        readiness_reason_detail: str = "",
    ) -> None:
        self.notes = dict(notes)
        self.current_updates = int(current_updates)
        self.retry_ms = int(retry_ms) if retry_ms is not None else None
        self.retry_reason = retry_reason or "agent_brief_retry"
        self.retry_attempt_limited = bool(retry_attempt_limited)
        self.readiness_status = readiness_status or "pending_due"
        self.readiness_reason_code = readiness_reason_code or self.retry_reason
        self.readiness_reason_detail = readiness_reason_detail or self.readiness_reason_code


def _target_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _unique_values(
        [
            str(row.get("target_id") or "")
            for row in rows
            if str(row.get("projection_name") or "") == "brief_input"
            and str(row.get("target_kind") or "") == "company_event"
        ]
    )


def _unique_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _packet_from_candidate(
    candidate: Mapping[str, Any],
    *,
    agent_config: EquityEventBriefAgentConfig,
) -> EquityEventBriefInputPacket:
    return build_equity_event_brief_input_packet(
        event=_dict(candidate.get("event") or candidate),
        story=_optional_dict(candidate.get("story")),
        story_members=_list_of_dicts(candidate.get("story_members")),
        source_documents=_list_of_dicts(candidate.get("source_documents")),
        source_spans=_list_of_dicts(candidate.get("source_spans")),
        fact_candidates=_list_of_dicts(candidate.get("fact_candidates")),
        agent_config=agent_config,
    )


def _current_brief_is_fresh(
    candidate: Mapping[str, Any],
    *,
    packet: EquityEventBriefInputPacket,
    agent_config: EquityEventBriefAgentConfig,
) -> bool:
    current = _optional_dict(candidate.get("current_brief"))
    if current is None:
        return False
    if str(current.get("status") or "") == "failed":
        return False
    if str(current.get("input_hash") or "") != packet.input_hash:
        return False
    if str(current.get("artifact_version_hash") or "") != agent_config.artifact_version_hash:
        return False
    return int(current.get("computed_at_ms") or 0) >= int(candidate.get("source_updated_at_ms") or 0)


def _fresh_current_brief_readiness_status(candidate: Mapping[str, Any]) -> str:
    current = _optional_dict(candidate.get("current_brief"))
    status = str((current or {}).get("status") or "")
    return _brief_status_to_readiness_status(status)


def _brief_status_to_readiness_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "ready":
        return "ready"
    if normalized == "insufficient":
        return "insufficient"
    if normalized == "failed":
        return "failed_retryable"
    return "pending_due"


def _next_retry_after_ms(*, now_ms: int, retry_ms: int | None) -> int | None:
    return int(now_ms) + int(retry_ms) if retry_ms is not None else None


def _brief_dirty_targets(*, company_event_id: str, source_watermark_ms: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_name": projection_name,
            "target_kind": "company_event",
            "target_id": str(company_event_id),
            "source_watermark_ms": int(source_watermark_ms),
        }
        for projection_name in ("page", "timeline", "alert")
    ]


def _has_official_evidence(packet: EquityEventBriefInputPacket) -> bool:
    if any(document.source_role in _OFFICIAL_SOURCE_ROLES for document in packet.source_documents):
        return True
    return any(fact.source_role in _OFFICIAL_SOURCE_ROLES for fact in packet.fact_lanes)


def _backpressure_outcome(reservation: AgentCapacityReservation) -> str:
    return _backpressure_outcome_for_reason(reservation.reason)


def _backpressure_outcome_for_reason(reason: Any) -> str:
    if reason == AgentExecutionErrorClass.CIRCUIT_OPEN:
        return "backpressure_circuit_open"
    if reason == AgentExecutionErrorClass.RATE_LIMITED:
        return "backpressure_rate_limited"
    return "backpressure_capacity_denied"


def _request_json(*, packet: EquityEventBriefInputPacket, audit: Mapping[str, Any]) -> dict[str, Any]:
    return {"packet": packet.model_dump(mode="json"), "audit": dict(audit)}


def _fallback_request_audit(
    *,
    run_id: str,
    packet: EquityEventBriefInputPacket,
    agent_config: EquityEventBriefAgentConfig,
    provider: Any,
) -> dict[str, Any]:
    story_or_event_id = (
        packet.story_context.story_id if packet.story_context is not None else packet.current_event.company_event_id
    )
    return {
        "provider": str(getattr(provider, "provider", agent_config.provider) or agent_config.provider),
        "backend": "openai_agents_sdk",
        "model": agent_config.model,
        "lane": agent_config.lane,
        "stage": "equity_event_brief",
        "workflow_name": agent_config.workflow_name,
        "agent_name": agent_config.agent_name,
        "sdk_trace_id": None,
        "group_id": f"equity_event:{story_or_event_id}",
        "prompt_version": agent_config.prompt_version,
        "schema_version": agent_config.schema_version,
        "runtime_version": RUNTIME_VERSION,
        "artifact_version_hash": agent_config.artifact_version_hash,
        "input_hash": packet.input_hash,
        "output_hash": None,
        "latency_ms": None,
        "usage": {},
        "trace_metadata": {},
        "execution_started": False,
        "status": "planned",
        "error_class": None,
        "error_message": None,
    }


def _failed_brief(errors: list[dict[str, str]]) -> dict[str, Any]:
    reason = "; ".join(str(error.get("message") or error.get("code") or "")[:120] for error in errors[:3])
    suffix = f"原因：{reason}" if reason else "已记录失败原因供后续重试。"
    return {
        "status": "failed",
        "direction": "neutral",
        "decision_class": "discard",
        "summary_zh": "",
        "event_read_zh": "",
        "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "company_impacts": [],
        "watch_triggers": [],
        "invalidation_conditions": [],
        "data_gaps": [{"description_zh": f"公司事件智能简报暂不可发布，{suffix}", "severity": "high"}],
        "evidence_refs": [],
    }


def _insufficient_no_official_evidence_brief(packet: EquityEventBriefInputPacket) -> dict[str, Any]:
    return {
        "status": "insufficient",
        "direction": "neutral",
        "decision_class": "watch",
        "summary_zh": "",
        "event_read_zh": "",
        "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "company_impacts": [],
        "watch_triggers": [],
        "invalidation_conditions": [],
        "data_gaps": [
            {
                "description_zh": (
                    f"{packet.current_event.ticker} 事件缺少监管文件或发行人官方证据，暂不生成可发布智能简报。"
                ),
                "severity": "high",
            }
        ],
        "evidence_refs": ["event:summary"] if "event:summary" in packet.evidence_refs else [],
    }


def _provider_error_audit(error: Exception) -> dict[str, Any] | None:
    audit = getattr(error, "audit", None)
    if audit is None:
        return None
    dump = getattr(audit, "model_dump", None)
    if dump is not None:
        return dict(dump(mode="json"))
    if isinstance(audit, Mapping):
        return dict(audit)
    return None


def _provider_error_class(error: Exception) -> str:
    if isinstance(error, AgentExecutionError):
        return _reason_value(error.error_class) or "provider_error"
    return type(error).__name__


def _provider_execution_started(error: Exception) -> bool:
    if isinstance(error, AgentExecutionError):
        return bool(error.execution_started)
    return True


def _is_no_start_backpressure_error(error: Exception) -> bool:
    if not isinstance(error, AgentExecutionError) or error.execution_started:
        return False
    return error.error_class in {
        AgentExecutionErrorClass.CAPACITY_DENIED,
        AgentExecutionErrorClass.CIRCUIT_OPEN,
        AgentExecutionErrorClass.RATE_LIMITED,
    }


def _reason_value(reason: Any) -> str | None:
    value = getattr(reason, "value", reason)
    return str(value) if value else None


def _output_hash(payload: Any) -> str | None:
    try:
        return json_sha256(payload)
    except TypeError:
        return None


async def _release_reservation(reservation: AgentCapacityReservation) -> None:
    await reservation.release()


def _audit_dict(value: Any) -> dict[str, Any]:
    return _dict(value)


def _optional_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _dict(value)


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if dump is not None:
        return dict(dump(mode="json"))
    return {}


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [_dict(row) for row in value]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_run_id() -> str:
    return f"equity-event-agent-run-{uuid.uuid4().hex}"


__all__ = ["EquityEventBriefWorker"]
