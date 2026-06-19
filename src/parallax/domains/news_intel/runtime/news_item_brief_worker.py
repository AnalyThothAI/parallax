from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel.runtime.news_projection_work import (
    ITEM_BRIEF_INPUT,
    claim_item_brief_work,
    enqueue_page_reprojection,
    item_brief_news_item_ids,
    mark_work_done,
    mark_work_error,
    queue_item_brief_depth,
)
from parallax.domains.news_intel.services.news_item_agent_admission import (
    decide_news_item_agent_admission,
)
from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from parallax.domains.news_intel.services.news_item_brief_validation import (
    NewsItemBriefValidationResult,
    validate_news_item_brief_output,
)
from parallax.domains.news_intel.types.news_item_agent_admission import (
    NewsItemAgentAdmission,
    NewsItemAgentAdmissionContext,
)
from parallax.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_LANE,
    NewsItemBriefAgentConfig,
    NewsItemBriefInputPacket,
    default_news_item_brief_agent_config,
)
from parallax.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentExecutionResultAudit,
)
from parallax.platform.agent_hashing import json_sha256


class NewsItemBriefWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: Any,
        db: Any,
        telemetry: Any,
        provider: Any,
        wake_waiter: Any | None = None,
        wake_emitter: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        run_id_factory: Callable[[], str] | None = None,
        name: str = "news_item_brief",
    ) -> None:
        if settings is None:
            raise RuntimeError("news_item_brief_settings_required")
        if db is None:
            raise RuntimeError("news_item_brief_db_required")
        if provider is None:
            raise RuntimeError("news_item_brief_provider_required")
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            wake_waiter=wake_waiter,
        )
        self.provider = provider
        self.wake_emitter = wake_emitter
        self.clock_ms = clock_ms or _now_ms
        self.run_id_factory = run_id_factory or _default_run_id

    async def run_once(self) -> WorkerResult:
        now = self.clock_ms()
        provider = self.provider
        agent_config = default_news_item_brief_agent_config(
            model=str(provider.model),
            artifact_version_hash=str(provider.artifact_version_hash),
        )
        queue_depth = await asyncio.to_thread(self._queue_depth, now_ms=now)
        if queue_depth <= 0:
            return WorkerResult(skipped=1, notes={"reason": "no_due_brief_targets"})

        rate_units = min(self._batch_size(), max(1, int(queue_depth)))
        try:
            reservation = provider.try_reserve_execution(NEWS_ITEM_BRIEF_LANE, rate_units=rate_units)
        except Exception as exc:
            return WorkerResult(
                skipped=1,
                notes={
                    "claimed": 0,
                    "queue_depth": queue_depth,
                    "backpressure": 1,
                    "agent_reservation_error": type(exc).__name__,
                },
            )
        if not reservation.acquired:
            backpressure_outcome = _backpressure_outcome(reservation)
            return WorkerResult(
                skipped=1,
                notes={
                    "claimed": 0,
                    "queue_depth": queue_depth,
                    "backpressure": 1,
                    backpressure_outcome: 1,
                },
            )

        try:
            claimed = await asyncio.to_thread(self._claim_targets, now_ms=now, limit=reservation.rate_units)
            if not claimed:
                return WorkerResult(skipped=1, notes={"reason": "no_due_brief_targets", "claimed": 0})
            try:
                candidates = await asyncio.to_thread(self._load_candidates, claimed=claimed, now_ms=now)
                candidates_by_id = _candidates_by_news_item_id(candidates, reason="load_candidate")
            except Exception as exc:
                await asyncio.to_thread(
                    self._mark_targets_error,
                    claimed,
                    error=exc,
                    retry_ms=self._retry_ms(),
                    now_ms=now,
                )
                return WorkerResult(failed=len(claimed), notes={"claimed": len(claimed), "load_failed": 1})

            notes = {
                "claimed": len(claimed),
                "ready": 0,
                "insufficient": 0,
                "failed": 0,
                "backpressure": 0,
                "validation_failed": 0,
                "missing_target": 0,
                "policy_skipped": 0,
            }
            skipped = 0
            current_updates = 0

            for target in claimed:
                try:
                    target_id = _required_item_brief_target_news_item_id(target)
                except Exception as exc:
                    notes["failed"] += 1
                    await asyncio.to_thread(
                        self._mark_targets_error,
                        [target],
                        error=exc,
                        retry_ms=self._retry_ms(),
                        now_ms=now,
                    )
                    continue
                candidate = candidates_by_id.get(target_id)
                if candidate is None:
                    notes["missing_target"] += 1
                    await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                    skipped += 1
                    continue
                admission = _admission_from_candidate(
                    candidate,
                    now_ms=now,
                )
                if not admission.eligible:
                    notes["policy_skipped"] += 1
                    await asyncio.to_thread(
                        self._complete_policy_skip,
                        target,
                        candidate=candidate,
                        admission=admission,
                        now_ms=now,
                    )
                    skipped += 1
                    continue
                try:
                    candidate = _candidate_with_agent_admission(candidate, admission)
                    packet = _packet_from_candidate(candidate, agent_config=agent_config)
                    if _current_brief_is_fresh(candidate, packet=packet, agent_config=agent_config):
                        await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                        skipped += 1
                        continue

                    completed_run = _fresh_completed_run(candidate, packet=packet, agent_config=agent_config)
                    if completed_run is not None:
                        await asyncio.to_thread(
                            self._restore_current_from_completed_run,
                            run=completed_run,
                            packet=packet,
                            agent_config=agent_config,
                            now_ms=now,
                        )
                        status = str(completed_run["outcome"])
                        outcome = _CandidateOutcome(
                            notes={status: 1, "restored_from_completed_run": 1},
                            current_updates=1,
                        )
                    else:
                        invalid_completed_run = _invalid_completed_run(
                            candidate,
                            packet=packet,
                            agent_config=agent_config,
                        )
                        if invalid_completed_run is not None:
                            outcome = await self._record_invalid_completed_run(
                                run=invalid_completed_run["run"],
                                packet=packet,
                                agent_config=agent_config,
                                errors=invalid_completed_run["errors"],
                                now_ms=now,
                            )
                        else:
                            failed_run = _fresh_failed_run(candidate, packet=packet, agent_config=agent_config)
                            if failed_run is not None:
                                outcome = _failed_run_outcome(failed_run)
                            else:
                                outcome = await self._process_candidate(
                                    candidate=candidate,
                                    packet=packet,
                                    agent_config=agent_config,
                                    now_ms=now,
                                    reservation=reservation,
                                )
                except Exception as exc:
                    notes["failed"] += 1
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
                    self._complete_claimed_target,
                    target,
                    outcome=outcome,
                    packet=packet,
                    agent_config=agent_config,
                    now_ms=now,
                )

            if current_updates > 0 and self.wake_emitter is not None:
                self.wake_emitter.notify_news_item_brief_updated(count=current_updates)
            failed = max(0, int(notes["failed"]) - int(notes["validation_failed"]))
            processed = int(notes["ready"]) + int(notes["insufficient"])
            skipped += int(notes["backpressure"])
            skipped += int(notes.get("restored_from_failed_run", 0))
            skipped += int(notes.get("invalid_completed_run", 0))
            return WorkerResult(processed=processed, failed=failed, skipped=skipped, notes=notes)
        finally:
            await _release_reservation(reservation)

    async def _process_candidate(
        self,
        *,
        candidate: Mapping[str, Any],
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        now_ms: int,
        reservation: AgentCapacityReservation,
    ) -> _CandidateOutcome:
        if self.provider is None:
            raise RuntimeError("news item brief provider is not configured")
        run_id = self.run_id_factory()
        started_at_ms = self.clock_ms()
        try:
            request_audit = self.provider.request_audit(run_id=run_id, packet=packet)
        except Exception as exc:
            return await self._record_request_audit_failure(error=exc)

        try:
            result = await self.provider.brief_item(run_id=run_id, packet=packet, reservation=reservation)
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

        payload = result.get("payload") if isinstance(result, Mapping) else None
        audit = _audit_dict(result.get("agent_run_audit") if isinstance(result, Mapping) else None)
        validation = validate_news_item_brief_output(payload=payload, packet=packet, audit=audit)
        finished_at_ms = self.clock_ms()
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
                error="news item brief validation failed",
                request_json=_request_json(packet=packet, audit=request_audit),
                response_json=payload if isinstance(payload, Mapping) else {"payload": payload},
                validation_errors=validation.errors,
                execution_started=True,
                output_hash=_output_hash(payload),
            )
            return _CandidateOutcome(
                notes={"failed": 1, "validation_failed": 1},
                current_updates=0,
                retry_reason="domain_validation_failed",
                failed_current_run_id=run_id,
                failed_current_errors=validation.errors,
            )

        payload_dict = _required_validation_payload(validation)
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
            computed_at_ms=finished_at_ms,
        )
        status = str(validation.status)
        return _CandidateOutcome(notes={status: 1}, current_updates=1)

    async def _record_invalid_completed_run(
        self,
        *,
        run: Mapping[str, Any],
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        errors: list[dict[str, str]],
        now_ms: int,
    ) -> _CandidateOutcome:
        run_id = self.run_id_factory()
        source_run_id = _required_run_id(run, reason="invalid_completed_source_run")
        audit = _invalid_completed_run_audit(
            run_id=run_id,
            source_run=run,
            source_run_id=source_run_id,
            packet=packet,
            agent_config=agent_config,
        )
        response_json = _dict(run.get("response_json"))
        await asyncio.to_thread(
            self._insert_run,
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            audit=audit,
            started_at_ms=now_ms,
            finished_at_ms=now_ms,
            status="failed",
            outcome="failed",
            error_class="domain_validation_failed",
            error="stored completed news item brief failed current validation",
            request_json={
                "packet": packet.model_dump(mode="json"),
                "audit": audit,
                "source_run_id": source_run_id,
                "reason": "invalid_completed_run",
            },
            response_json=response_json,
            validation_errors=errors,
            execution_started=False,
            output_hash=_output_hash(response_json),
        )
        return _CandidateOutcome(
            notes={"failed": 1, "validation_failed": 1, "invalid_completed_run": 1},
            current_updates=0,
            retry_reason="domain_validation_failed",
            retry_counts_attempt=False,
            failed_current_run_id=run_id,
            failed_current_errors=errors,
        )

    async def _record_provider_failure(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        request_audit: Mapping[str, Any],
        error: Exception,
        started_at_ms: int,
        execution_started: bool | None = None,
    ) -> _CandidateOutcome:
        if self.provider is None:
            raise RuntimeError("news item brief provider is not configured")
        resolved_execution_started = (
            bool(execution_started) if execution_started is not None else _provider_execution_started(error)
        )
        finished_at_ms = self.clock_ms()
        audit = _provider_error_audit(error)
        if audit is None:
            audit = dict(request_audit)
            audit["latency_ms"] = max(0, int(finished_at_ms) - int(started_at_ms))
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
        error_class = _provider_error_class(error)
        return _CandidateOutcome(
            notes={"failed": 1},
            current_updates=0,
            retry_reason=error_class,
            failed_current_run_id=run_id,
            failed_current_errors=[{"code": error_class, "message": str(error)[:500]}],
        )

    async def _record_execute_backpressure(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        request_audit: Mapping[str, Any],
        error: Exception,
        started_at_ms: int,
    ) -> _CandidateOutcome:
        del run_id, packet, agent_config, request_audit, started_at_ms
        outcome = _backpressure_outcome_for_error(error)
        return _CandidateOutcome(
            notes={"backpressure": 1, outcome: 1},
            current_updates=0,
            retry_ms=self._backpressure_cooldown_ms(),
            retry_reason=outcome,
            retry_counts_attempt=False,
        )

    async def _record_request_audit_failure(self, *, error: Exception) -> _CandidateOutcome:
        del error
        return _CandidateOutcome(
            notes={"backpressure": 1, "request_audit_failed": 1},
            current_updates=0,
            retry_ms=self._backpressure_cooldown_ms(),
            retry_reason="request_audit_failed",
            retry_counts_attempt=False,
        )

    def _claim_targets(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        with self._repository_session() as repos:
            return claim_item_brief_work(
                repos,
                limit=max(1, int(limit)),
                lease_ms=self._lease_ms(),
                now_ms=now_ms,
                lease_owner=_claim_owner(self.name),
            )

    def _queue_depth(self, *, now_ms: int | None = None) -> int:
        resolved_now_ms = self.clock_ms() if now_ms is None else int(now_ms)
        with self._repository_session() as repos:
            return queue_item_brief_depth(repos, now_ms=resolved_now_ms)

    def _load_candidates(self, *, claimed: Iterable[Mapping[str, Any]], now_ms: int) -> list[dict[str, Any]]:
        news_item_ids = _target_ids(claimed)
        if not news_item_ids:
            return []
        with self._repository_session() as repos:
            candidates = cast(
                list[dict[str, Any]],
                repos.news.load_items_for_brief_targets(news_item_ids=news_item_ids),
            )
            contexts = cast(
                list[dict[str, Any]],
                repos.news.load_agent_admission_contexts(news_item_ids=news_item_ids, now_ms=int(now_ms)),
            )
        contexts_by_id = _candidates_by_news_item_id(contexts, reason="admission_context")
        merged: list[dict[str, Any]] = []
        for candidate in candidates:
            item = _required_candidate_item(candidate, reason="load_candidate")
            news_item_id = _required_candidate_news_item_id(item, reason="load_candidate")
            context = contexts_by_id.get(news_item_id)
            if context is None:
                raise RuntimeError("news_item_brief_admission_context_required:load_candidate")
            merged_candidate = {
                **candidate,
                "entities": _required_admission_context_list(context, "entities", reason="load_candidate"),
                "token_mentions": _required_admission_context_list(context, "token_mentions", reason="load_candidate"),
                "fact_candidates": _required_admission_context_list(
                    context,
                    "fact_candidates",
                    reason="load_candidate",
                ),
                "agent_admission_context": context,
            }
            merged.append(merged_candidate)
        return merged

    def _complete_policy_skip(
        self,
        target: Mapping[str, Any],
        *,
        candidate: Mapping[str, Any],
        admission: NewsItemAgentAdmission,
        now_ms: int,
    ) -> None:
        item = _required_candidate_item(candidate, reason="policy_skip")
        news_item_id = _required_candidate_news_item_id(item, reason="policy_skip")
        with self._repository_session() as repos, repos.transaction():
            repos.news.update_item_agent_admission(
                news_item_id=news_item_id,
                admission=admission,
                now_ms=int(now_ms),
                commit=False,
            )
            enqueue_page_reprojection(
                repos,
                news_item_ids=[news_item_id],
                reason="news_item_agent_admission_updated",
                now_ms=int(now_ms),
                source_watermark_ms_by_news_item_id={news_item_id: _page_dirty_source_watermark_ms(target, item=item)},
                commit=False,
            )
            mark_work_done(repos, [target], now_ms=int(now_ms), commit=False)

    def _complete_claimed_target(
        self,
        target: Mapping[str, Any],
        *,
        outcome: _CandidateOutcome,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        now_ms: int,
    ) -> None:
        if outcome.retry_ms is None:
            if outcome.failed_current_run_id and outcome.failed_current_errors:
                self._upsert_failed_current(
                    run_id=outcome.failed_current_run_id,
                    packet=packet,
                    agent_config=agent_config,
                    errors=outcome.failed_current_errors,
                    terminal_reason=outcome.retry_reason,
                    computed_at_ms=now_ms,
                )
            self._mark_targets_done([target], now_ms=now_ms)
            return
        self._mark_targets_error(
            [target],
            error=outcome.retry_reason,
            retry_ms=outcome.retry_ms,
            now_ms=now_ms,
            count_attempt=outcome.retry_counts_attempt,
        )

    def _mark_targets_done(self, targets: Iterable[Mapping[str, Any]], *, now_ms: int) -> None:
        with self._repository_session() as repos:
            mark_work_done(repos, targets, now_ms=now_ms)

    def _mark_targets_error(
        self,
        targets: Iterable[Mapping[str, Any]],
        *,
        error: Exception | str,
        retry_ms: int,
        now_ms: int,
        count_attempt: bool = True,
    ) -> None:
        with self._repository_session() as repos:
            mark_work_error(
                repos,
                targets,
                error=str(error),
                retry_ms=retry_ms,
                now_ms=now_ms,
                count_attempt=count_attempt,
            )

    def _insert_run(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
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
        if self.provider is None:
            raise RuntimeError("news item brief provider is not configured")
        with self._repository_session() as repos:
            repos.news.insert_news_item_agent_run(
                run_id=run_id,
                news_item_id=packet.news_item.news_item_id,
                provider=_required_audit_text(audit, "provider"),
                model=_required_audit_text(audit, "model"),
                backend=_required_audit_text(audit, "backend"),
                execution_trace_id=audit.get("execution_trace_id"),
                workflow_name=_required_audit_text(audit, "workflow_name"),
                agent_name=_required_audit_text(audit, "agent_name"),
                lane=_required_audit_text(audit, "lane"),
                artifact_version_hash=agent_config.artifact_version_hash,
                prompt_version=_required_audit_text(audit, "prompt_version"),
                schema_version=_required_audit_text(audit, "schema_version"),
                validator_version=agent_config.validator_version,
                guardrail_version=agent_config.guardrail_version,
                input_hash=_required_audit_text(audit, "input_hash"),
                output_hash=output_hash,
                execution_started=bool(execution_started),
                status=status,
                outcome=outcome,
                error_class=error_class,
                error=error,
                request_json=dict(request_json),
                response_json=response_json,
                validation_errors_json=validation_errors,
                trace_metadata_json=_required_audit_mapping(audit, "trace_metadata"),
                usage_json=_required_audit_mapping(audit, "usage"),
                latency_ms=_required_audit_latency_ms(audit),
                started_at_ms=int(started_at_ms),
                finished_at_ms=int(finished_at_ms),
                created_at_ms=int(started_at_ms),
            )

    def _upsert_current(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        payload: Mapping[str, Any],
        computed_at_ms: int,
    ) -> None:
        with self._repository_session() as repos, repos.transaction():
            repos.news.upsert_news_item_agent_brief(
                news_item_id=packet.news_item.news_item_id,
                agent_run_id=run_id,
                status=str(payload["status"]),
                direction=str(payload["direction"]),
                decision_class=str(payload["decision_class"]),
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

    def _restore_current_from_completed_run(
        self,
        *,
        run: Mapping[str, Any],
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        now_ms: int,
    ) -> None:
        payload = _dict(run.get("response_json"))
        del now_ms
        computed_at_ms = _required_run_finished_at_ms(run, reason="completed_run")
        self._upsert_current(
            run_id=_required_run_id(run, reason="completed_run"),
            packet=packet,
            agent_config=agent_config,
            payload=payload,
            computed_at_ms=computed_at_ms,
        )

    def _upsert_failed_current(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        errors: list[dict[str, str]],
        terminal_reason: str,
        computed_at_ms: int,
    ) -> None:
        self._upsert_current(
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            payload=_failed_brief(errors, terminal_reason=terminal_reason),
            computed_at_ms=computed_at_ms,
        )

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        )

    def _batch_size(self) -> int:
        return max(1, int(self.settings.batch_size))

    def _lease_ms(self) -> int:
        return max(1, int(self.settings.lease_ms))

    def _retry_ms(self) -> int:
        return max(1, int(self.settings.retry_ms))

    def _backpressure_cooldown_ms(self) -> int:
        return max(1, int(self.settings.backpressure_cooldown_ms))


class _CandidateOutcome:
    def __init__(
        self,
        *,
        notes: Mapping[str, int],
        current_updates: int,
        retry_ms: int | None = None,
        retry_reason: str = "",
        retry_counts_attempt: bool = True,
        failed_current_run_id: str = "",
        failed_current_errors: list[dict[str, str]] | None = None,
    ) -> None:
        self.notes = dict(notes)
        self.current_updates = int(current_updates)
        self.retry_ms = int(retry_ms) if retry_ms is not None else None
        self.retry_reason = retry_reason or "agent_brief_retry"
        self.retry_counts_attempt = bool(retry_counts_attempt)
        self.failed_current_run_id = str(failed_current_run_id or "")
        self.failed_current_errors = list(failed_current_errors or [])


def _packet_from_candidate(
    candidate: Mapping[str, Any],
    *,
    agent_config: NewsItemBriefAgentConfig,
) -> NewsItemBriefInputPacket:
    return build_news_item_brief_input_packet(
        item=_required_candidate_item(candidate, reason="packet"),
        entities=_candidate_list_of_dicts(candidate.get("entities"), field="entities"),
        token_mentions=_candidate_list_of_dicts(candidate.get("token_mentions"), field="token_mentions"),
        fact_candidates=_candidate_list_of_dicts(candidate.get("fact_candidates"), field="fact_candidates"),
        agent_config=agent_config,
    )


def _current_brief_is_fresh(
    candidate: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
) -> bool:
    current = _optional_dict(candidate.get("current_brief"))
    if current is None:
        return False
    _required_current_status(current)
    if _required_current_text(current, "input_hash") != packet.input_hash:
        return False
    if _required_current_text(current, "artifact_version_hash") != agent_config.artifact_version_hash:
        return False
    if _required_current_text(current, "prompt_version") != agent_config.prompt_version:
        return False
    if _required_current_text(current, "schema_version") != agent_config.schema_version:
        return False
    return _required_current_text(current, "validator_version") == agent_config.validator_version


def _fresh_completed_run(
    candidate: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
) -> dict[str, Any] | None:
    completed = _completed_run_validation(candidate, packet=packet, agent_config=agent_config)
    if completed is None:
        return None
    run = completed.run
    validation = completed.validation
    outcome = _required_run_outcome(run, reason="completed_run", allowed={"ready", "insufficient"})
    if validation.publishable and validation.status == outcome:
        return run
    return None


def _invalid_completed_run(
    candidate: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
) -> dict[str, Any] | None:
    completed = _completed_run_validation(candidate, packet=packet, agent_config=agent_config)
    if completed is None:
        return None
    run = completed.run
    validation = completed.validation
    outcome = _required_run_outcome(run, reason="completed_run", allowed={"ready", "insufficient"})
    if validation.publishable and validation.status == outcome:
        return None
    errors = list(validation.errors)
    if not errors:
        errors = [
            {
                "code": "completed_run_outcome_mismatch",
                "message": "completed news item agent run response status does not match its recorded outcome",
            }
        ]
    return {"run": run, "errors": errors}


def _fresh_failed_run(
    candidate: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
) -> dict[str, Any] | None:
    run = _optional_dict(candidate.get("latest_run"))
    if run is None:
        return None
    if _required_run_status(run) != "failed":
        return None
    _required_run_outcome(run, reason="failed_run", allowed={"failed"})
    if not _required_run_execution_started(run, reason="failed_run"):
        return None
    if _required_run_text(run, "input_hash", reason="failed_run") != packet.input_hash:
        return None
    if _required_run_text(run, "artifact_version_hash", reason="failed_run") != agent_config.artifact_version_hash:
        return None
    if _required_run_text(run, "prompt_version", reason="failed_run") != agent_config.prompt_version:
        return None
    if _required_run_text(run, "schema_version", reason="failed_run") != agent_config.schema_version:
        return None
    if _required_run_text(run, "validator_version", reason="failed_run") != agent_config.validator_version:
        return None
    _required_run_id(run, reason="failed_run")
    return run


def _failed_run_outcome(run: Mapping[str, Any]) -> _CandidateOutcome:
    error_class = _required_failed_run_error_class(run)
    error = _required_failed_run_error(run)
    return _CandidateOutcome(
        notes={"restored_from_failed_run": 1},
        current_updates=0,
        retry_reason=error_class,
        failed_current_run_id=_required_run_id(run, reason="failed_run"),
        failed_current_errors=[{"code": error_class, "message": error[:500]}],
    )


@dataclass(frozen=True)
class _CompletedRunValidation:
    run: dict[str, Any]
    validation: NewsItemBriefValidationResult


def _completed_run_validation(
    candidate: Mapping[str, Any],
    *,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
) -> _CompletedRunValidation | None:
    run = _optional_dict(candidate.get("latest_run"))
    if run is None:
        return None
    if _required_run_status(run) != "completed":
        return None
    _required_run_outcome(run, reason="completed_run", allowed={"ready", "insufficient"})
    if _required_run_text(run, "input_hash", reason="completed_run") != packet.input_hash:
        return None
    if _required_run_text(run, "artifact_version_hash", reason="completed_run") != agent_config.artifact_version_hash:
        return None
    if _required_run_text(run, "prompt_version", reason="completed_run") != agent_config.prompt_version:
        return None
    if _required_run_text(run, "schema_version", reason="completed_run") != agent_config.schema_version:
        return None
    if _required_run_text(run, "validator_version", reason="completed_run") != agent_config.validator_version:
        return None
    payload = _optional_dict(run.get("response_json"))
    if payload is None:
        return None
    _required_run_id(run, reason="completed_run")
    validation = validate_news_item_brief_output(payload=payload, packet=packet, audit=run)
    return _CompletedRunValidation(run=run, validation=validation)


def _required_run_id(run: Mapping[str, Any], *, reason: str) -> str:
    try:
        value = run["run_id"]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_run_id_required:{reason}") from exc
    run_id = str(value).strip()
    if not run_id:
        raise RuntimeError(f"news_item_brief_run_id_required:{reason}")
    return run_id


def _required_validation_payload(validation: NewsItemBriefValidationResult) -> dict[str, Any]:
    payload = validation.payload
    if not isinstance(payload, Mapping):
        raise RuntimeError("news_item_brief_validation_payload_required")
    return dict(payload)


def _required_run_status(run: Mapping[str, Any]) -> str:
    try:
        value = run["status"]
    except KeyError as exc:
        raise RuntimeError("news_item_brief_run_status_required:latest_run") from exc
    status = str(value).strip()
    if status not in {"completed", "failed"}:
        raise RuntimeError("news_item_brief_run_status_required:latest_run")
    return status


def _required_run_text(run: Mapping[str, Any], field: str, *, reason: str) -> str:
    try:
        value = run[field]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_run_{field}_required:{reason}") from exc
    text = str(value).strip()
    if not text:
        raise RuntimeError(f"news_item_brief_run_{field}_required:{reason}")
    return text


def _required_run_execution_started(run: Mapping[str, Any], *, reason: str) -> bool:
    try:
        value = run["execution_started"]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_run_execution_started_required:{reason}") from exc
    if not isinstance(value, bool):
        raise RuntimeError(f"news_item_brief_run_execution_started_required:{reason}")
    return value


def _required_run_finished_at_ms(run: Mapping[str, Any], *, reason: str) -> int:
    try:
        value = run["finished_at_ms"]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_run_finished_at_ms_required:{reason}") from exc
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"news_item_brief_run_finished_at_ms_required:{reason}")
    if value <= 0:
        raise RuntimeError(f"news_item_brief_run_finished_at_ms_required:{reason}")
    return value


def _required_failed_run_error_class(run: Mapping[str, Any]) -> str:
    try:
        value = run["error_class"]
    except KeyError as exc:
        raise RuntimeError("news_item_brief_run_error_class_required:failed_run") from exc
    error_class = str(value).strip()
    if not error_class:
        raise RuntimeError("news_item_brief_run_error_class_required:failed_run")
    return error_class


def _required_failed_run_error(run: Mapping[str, Any]) -> str:
    try:
        value = run["error"]
    except KeyError as exc:
        raise RuntimeError("news_item_brief_run_error_required:failed_run") from exc
    error = str(value).strip()
    if not error:
        raise RuntimeError("news_item_brief_run_error_required:failed_run")
    return error


def _required_current_text(current: Mapping[str, Any], field: str) -> str:
    try:
        value = current[field]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_current_{field}_required") from exc
    text = str(value).strip()
    if not text:
        raise RuntimeError(f"news_item_brief_current_{field}_required")
    return text


def _required_current_status(current: Mapping[str, Any]) -> str:
    status = _required_current_text(current, "status")
    if status not in {"ready", "insufficient", "failed"}:
        raise RuntimeError("news_item_brief_current_status_required")
    return status


def _required_run_outcome(run: Mapping[str, Any], *, reason: str, allowed: set[str]) -> str:
    try:
        value = run["outcome"]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_run_outcome_required:{reason}") from exc
    outcome = str(value).strip()
    if outcome not in allowed:
        raise RuntimeError(f"news_item_brief_run_outcome_required:{reason}")
    return outcome


def _required_audit_latency_ms(audit: Mapping[str, Any]) -> int:
    try:
        value = audit["latency_ms"]
    except KeyError as exc:
        raise RuntimeError("news_item_brief_audit_latency_ms_required") from exc
    if isinstance(value, bool):
        raise RuntimeError("news_item_brief_audit_latency_ms_required")
    try:
        latency_ms = int(float(value))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("news_item_brief_audit_latency_ms_required") from exc
    if latency_ms < 0:
        raise RuntimeError("news_item_brief_audit_latency_ms_required")
    return latency_ms


def _required_audit_mapping(audit: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    try:
        value = audit[field_name]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_audit_{field_name}_required") from exc
    if not isinstance(value, Mapping):
        raise RuntimeError(f"news_item_brief_audit_{field_name}_required")
    return dict(value)


def _required_audit_text(audit: Mapping[str, Any], field_name: str) -> str:
    try:
        value = audit[field_name]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_audit_{field_name}_required") from exc
    text = str(value).strip()
    if not text:
        raise RuntimeError(f"news_item_brief_audit_{field_name}_required")
    return text


def _admission_from_candidate(candidate: Mapping[str, Any], *, now_ms: int) -> NewsItemAgentAdmission:
    context = _dict(candidate.get("agent_admission_context"))
    if not context:
        raise ValueError("news item brief candidate is missing repository admission context")
    return decide_news_item_agent_admission(
        item=_required_candidate_item(candidate, reason="admission"),
        entities=_candidate_list_of_dicts(candidate.get("entities"), field="entities"),
        token_mentions=_candidate_list_of_dicts(candidate.get("token_mentions"), field="token_mentions"),
        fact_candidates=_candidate_list_of_dicts(candidate.get("fact_candidates"), field="fact_candidates"),
        context=NewsItemAgentAdmissionContext.from_repository_context(context),
        now_ms=now_ms,
    )


def _candidate_with_agent_admission(
    candidate: Mapping[str, Any],
    admission: NewsItemAgentAdmission,
) -> dict[str, Any]:
    result = dict(candidate)
    item = _required_candidate_item(result, reason="agent_admission")
    admission_payload = _agent_admission_payload(admission)
    item["agent_admission_status"] = admission.status
    item["agent_admission_reason"] = admission.reason
    item["agent_admission_json"] = admission_payload
    item["agent_representative_news_item_id"] = admission.representative_news_item_id
    result["item"] = item
    return result


def _target_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return item_brief_news_item_ids(rows)


def _candidates_by_news_item_id(
    candidates: Iterable[Mapping[str, Any]],
    *,
    reason: str,
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for candidate in candidates:
        item = _required_candidate_item(candidate, reason=reason)
        news_item_id = _required_candidate_news_item_id(item, reason=reason)
        indexed[news_item_id] = candidate
    return indexed


def _required_candidate_item(candidate: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
    try:
        value = candidate["item"]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_candidate_item_required:{reason}") from exc
    if not isinstance(value, Mapping):
        raise RuntimeError(f"news_item_brief_candidate_item_required:{reason}")
    return dict(value)


def _required_candidate_news_item_id(item: Mapping[str, Any], *, reason: str) -> str:
    try:
        value = item["news_item_id"]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_candidate_news_item_id_required:{reason}") from exc
    if not isinstance(value, str):
        raise RuntimeError(f"news_item_brief_candidate_news_item_id_required:{reason}")
    news_item_id = value.strip()
    if not news_item_id:
        raise RuntimeError(f"news_item_brief_candidate_news_item_id_required:{reason}")
    return news_item_id


def _required_admission_context_list(
    context: Mapping[str, Any],
    field_name: str,
    *,
    reason: str,
) -> list[dict[str, Any]]:
    try:
        value = context[field_name]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_admission_context_{field_name}_required:{reason}") from exc
    if not isinstance(value, list):
        raise RuntimeError(f"news_item_brief_admission_context_{field_name}_required:{reason}")
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise RuntimeError(f"news_item_brief_admission_context_{field_name}_required:{reason}")
        rows.append(dict(row))
    return rows


def _required_item_brief_target_news_item_id(target: Mapping[str, Any]) -> str:
    _require_claim_text(target, field="projection_name", expected=ITEM_BRIEF_INPUT)
    _require_claim_text(target, field="target_kind", expected="news_item")
    _require_claim_empty_window(target)
    return _require_claim_text(target, field="target_id")


def _require_claim_text(target: Mapping[str, Any], *, field: str, expected: str | None = None) -> str:
    try:
        value = target[field]
    except KeyError as exc:
        raise RuntimeError(f"news_item_brief_claim_{field}_required") from exc
    if not isinstance(value, str):
        raise RuntimeError(f"news_item_brief_claim_{field}_required")
    text = value.strip()
    if not text:
        raise RuntimeError(f"news_item_brief_claim_{field}_required")
    if expected is not None and text != expected:
        raise RuntimeError(f"news_item_brief_claim_{field}_required")
    return text


def _require_claim_empty_window(target: Mapping[str, Any]) -> None:
    try:
        value = target["window"]
    except KeyError as exc:
        raise RuntimeError("news_item_brief_claim_window_empty_required") from exc
    if value != "":
        raise RuntimeError("news_item_brief_claim_window_empty_required")


def _backpressure_outcome(reservation: AgentCapacityReservation) -> str:
    return _backpressure_outcome_for_reason(reservation.reason)


def _backpressure_outcome_for_reason(reason: Any) -> str:
    if reason == AgentExecutionErrorClass.CIRCUIT_OPEN:
        return "backpressure_circuit_open"
    if reason == AgentExecutionErrorClass.RATE_LIMITED:
        return "backpressure_rate_limited"
    if reason == AgentExecutionErrorClass.QUOTA_EXHAUSTED:
        return "backpressure_quota_exhausted"
    return "backpressure_capacity_denied"


def _backpressure_outcome_for_error(error: Exception) -> str:
    if not isinstance(error, AgentExecutionError):
        raise RuntimeError("news_item_brief_agent_backpressure_error_contract_required")
    return _backpressure_outcome_for_reason(error.error_class)


def _request_json(*, packet: NewsItemBriefInputPacket, audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet": packet.model_dump(mode="json"),
        "audit": dict(audit),
    }


def _invalid_completed_run_audit(
    *,
    run_id: str,
    source_run: Mapping[str, Any],
    source_run_id: str,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
) -> dict[str, Any]:
    return {
        "provider": _required_run_text(source_run, "provider", reason="invalid_completed_source_run"),
        "backend": "deterministic_validation",
        "model": _required_run_text(source_run, "model", reason="invalid_completed_source_run"),
        "lane": agent_config.lane,
        "workflow_name": agent_config.workflow_name,
        "agent_name": agent_config.agent_name,
        "prompt_version": agent_config.prompt_version,
        "schema_version": agent_config.schema_version,
        "artifact_version_hash": agent_config.artifact_version_hash,
        "input_hash": packet.input_hash,
        "output_hash": _output_hash(source_run.get("response_json")),
        "usage": {},
        "latency_ms": 0,
        "trace_metadata": {
            "run_id": run_id,
            "news_item_id": packet.news_item.news_item_id,
            "source_run_id": source_run_id,
            "deterministic_policy": "invalid_completed_run",
        },
    }


def _failed_brief(
    errors: list[dict[str, str]],
    *,
    terminal_reason: str = "",
) -> dict[str, Any]:
    reason = "; ".join(str(error.get("message") or error.get("code") or "")[:120] for error in errors[:3])
    details = []
    if terminal_reason:
        details.append(f"终态原因：{str(terminal_reason)[:120]}")
    if reason:
        details.append(f"原因：{reason}")
    suffix = "；".join(details) if details else "已记录失败原因。"
    payload: dict[str, Any] = {
        "status": "failed",
        "direction": "neutral",
        "decision_class": "discard",
        "event_type": None,
        "summary_zh": "",
        "market_read_zh": "",
        "market_domains": [],
        "transmission_paths": [],
        "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "affected_entities": [],
        "watch_triggers": [],
        "invalidation_conditions": [],
        "data_gaps": [
            {
                "description_zh": f"新闻条目智能摘要不可发布，{suffix}",
                "severity": "high",
            }
        ],
        "evidence_refs": [],
    }
    return payload


def _provider_error_audit(error: Exception) -> dict[str, Any] | None:
    if not isinstance(error, AgentExecutionError):
        return None
    audit = error.audit
    if audit is None:
        return None
    if not isinstance(audit, AgentExecutionRequestAudit | AgentExecutionResultAudit):
        raise RuntimeError("news_item_brief_agent_error_audit_contract_required")
    return audit.model_dump(mode="json")


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
        AgentExecutionErrorClass.QUOTA_EXHAUSTED,
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
    if not isinstance(value, Mapping):
        raise RuntimeError("news_item_brief_agent_run_audit_contract_required")
    return {str(key): child for key, child in value.items()}


def _optional_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return _dict(value)


def _dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _page_dirty_source_watermark_ms(
    target: Mapping[str, Any],
    *,
    item: Mapping[str, Any] | None = None,
    published_at_ms: int | None = None,
) -> int:
    if "source_watermark_ms" in target:
        return _positive_watermark(target["source_watermark_ms"])
    item_payload = _dict(item)
    for value in (published_at_ms, item_payload.get("published_at_ms"), item_payload.get("fetched_at_ms")):
        if value is not None:
            return _positive_watermark(value)
    raise ValueError("news_item_brief_page_dirty_source_watermark_required")


def _positive_watermark(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("news_item_brief_page_dirty_source_watermark_required")
    watermark = int(value)
    if watermark <= 0:
        raise ValueError("news_item_brief_page_dirty_source_watermark_required")
    return watermark


def _agent_admission_payload(value: NewsItemAgentAdmission) -> dict[str, Any]:
    if not isinstance(value, NewsItemAgentAdmission):
        raise RuntimeError("news_item_brief_agent_admission_contract_required")
    return {
        "eligible": bool(value.eligible),
        "status": value.status,
        "reason": value.reason,
        "representative_news_item_id": value.representative_news_item_id,
        "basis": dict(value.basis),
        "version": value.version,
    }


def _candidate_list_of_dicts(value: Any, *, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        raise RuntimeError(f"news_item_brief_candidate_{field}_array_required")
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise RuntimeError(f"news_item_brief_candidate_{field}_row_object_required")
        rows.append(dict(row))
    return rows


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_run_id() -> str:
    return f"news-item-agent-run-{uuid.uuid4().hex}"


def _claim_owner(worker_name: str) -> str:
    return f"{worker_name}:{uuid.uuid4().hex}"


__all__ = ["NewsItemBriefWorker"]
