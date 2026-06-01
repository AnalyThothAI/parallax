from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel.services.news_item_agent_policy import (
    news_item_agent_brief_eligibility,
)
from parallax.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from parallax.domains.news_intel.services.news_item_brief_validation import (
    validate_news_item_brief_output,
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
)
from parallax.platform.agent_hashing import json_sha256


class NewsItemBriefWorker(WorkerBase):
    def __init__(
        self,
        *,
        provider: Any | None = None,
        wake_bus: Any | None = None,
        source_quality_windows: Iterable[str] | None = None,
        clock_ms: Callable[[], int] | None = None,
        run_id_factory: Callable[[], str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.provider = provider
        self.wake_bus = wake_bus
        self.source_quality_windows = _source_quality_windows(source_quality_windows)
        self.clock_ms = clock_ms or _now_ms
        self.run_id_factory = run_id_factory or _default_run_id

    async def run_once(self) -> WorkerResult:
        if self.provider is None:
            return WorkerResult(skipped=1, notes={"reason": "missing_provider"})

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
                candidates = await asyncio.to_thread(self._load_candidates, claimed=claimed)
            except Exception as exc:
                await asyncio.to_thread(
                    self._mark_targets_error,
                    claimed,
                    error=exc,
                    retry_ms=self._retry_ms(),
                    now_ms=now,
                )
                return WorkerResult(failed=len(claimed), notes={"claimed": len(claimed), "load_failed": 1})

            candidates_by_id = {
                str(candidate.get("item", {}).get("news_item_id") or ""): candidate
                for candidate in candidates
                if isinstance(candidate.get("item"), Mapping)
            }

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
                target_id = str(target.get("target_id") or "")
                candidate = candidates_by_id.get(target_id)
                if candidate is None:
                    notes["missing_target"] += 1
                    await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                    skipped += 1
                    continue
                eligibility = news_item_agent_brief_eligibility(
                    item=_dict(candidate.get("item") or candidate),
                    token_mentions=_list_of_dicts(candidate.get("token_mentions")),
                    fact_candidates=_list_of_dicts(candidate.get("fact_candidates")),
                    context_items=_list_of_dicts(candidate.get("context_items")),
                    now_ms=now,
                )
                if not eligibility.eligible:
                    notes["policy_skipped"] += 1
                    await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                    skipped += 1
                    continue
                try:
                    packet = _packet_from_candidate(candidate, agent_config=agent_config)
                    if _current_brief_is_fresh(candidate, packet=packet, agent_config=agent_config):
                        await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                        skipped += 1
                        continue

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

            if current_updates > 0 and self.wake_bus is not None:
                self.wake_bus.notify_news_item_brief_updated(count=current_updates)
            failed = int(notes["failed"])
            processed = int(notes["ready"]) + int(notes["insufficient"])
            skipped += int(notes["backpressure"])
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
        audit = _audit_dict(result.get("agent_run_audit") if isinstance(result, Mapping) else None) or request_audit
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
                retry_ms=self._retry_ms(),
                retry_reason="domain_validation_failed",
                retry_attempt_limited=True,
                retry_counts_attempt=True,
                terminal_run_id=run_id,
                terminal_errors=validation.errors,
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
            computed_at_ms=finished_at_ms,
        )
        status = str(validation.status)
        return _CandidateOutcome(notes={status: 1}, current_updates=1)

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
        return _CandidateOutcome(
            notes={"failed": 1},
            current_updates=0,
            retry_ms=self._retry_ms(),
            retry_reason=_provider_error_class(error),
            retry_attempt_limited=resolved_execution_started,
            retry_counts_attempt=resolved_execution_started,
            terminal_run_id=run_id,
            terminal_errors=[{"code": _provider_error_class(error), "message": str(error)[:500]}],
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
        outcome = _backpressure_outcome_for_reason(getattr(error, "error_class", None))
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
            return cast(
                list[dict[str, Any]],
                repos.news_projection_dirty_targets.claim_due(
                    limit=max(1, int(limit)),
                    lease_ms=self._lease_ms(),
                    now_ms=now_ms,
                    lease_owner=_claim_owner(self.name),
                    projection_name="brief_input",
                ),
            )

    def _queue_depth(self, *, now_ms: int | None = None) -> int:
        resolved_now_ms = self.clock_ms() if now_ms is None else int(now_ms)
        with self._repository_session() as repos:
            return int(
                repos.news_projection_dirty_targets.queue_depth(
                    now_ms=resolved_now_ms,
                    projection_name="brief_input",
                )
            )

    def _load_candidates(self, *, claimed: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        news_item_ids = _target_ids(claimed)
        if not news_item_ids:
            return []
        with self._repository_session() as repos:
            return cast(list[dict[str, Any]], repos.news.load_items_for_brief_targets(news_item_ids=news_item_ids))

    def _complete_claimed_target(
        self,
        target: Mapping[str, Any],
        *,
        outcome: _CandidateOutcome,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        now_ms: int,
    ) -> None:
        if outcome.force_terminal:
            terminalized_count = self._terminalize_claimed_target(
                target,
                outcome=outcome,
                packet=packet,
                now_ms=now_ms,
                terminal_attempt_count=max(1, int(target.get("attempt_count") or 0)),
            )
            if terminalized_count > 0 and outcome.terminal_run_id and outcome.terminal_errors:
                self._upsert_terminal_failed_current(
                    run_id=outcome.terminal_run_id,
                    packet=packet,
                    agent_config=agent_config,
                    errors=outcome.terminal_errors,
                    terminal_reason=outcome.retry_reason,
                    computed_at_ms=now_ms,
                )
            return
        if outcome.retry_ms is None:
            self._mark_targets_done([target], now_ms=now_ms)
            return
        attempted_now = 1 if outcome.retry_counts_attempt else 0
        attempt_after_failure = int(target.get("attempt_count") or 0) + attempted_now
        if not outcome.retry_attempt_limited or attempt_after_failure < self._max_attempts():
            self._mark_targets_error(
                [target],
                error=outcome.retry_reason,
                retry_ms=outcome.retry_ms,
                now_ms=now_ms,
                count_attempt=outcome.retry_counts_attempt,
            )
            return
        terminalized_count = self._terminalize_claimed_target(
            target,
            outcome=outcome,
            packet=packet,
            now_ms=now_ms,
            terminal_attempt_count=attempt_after_failure,
        )
        if terminalized_count <= 0:
            return
        if outcome.terminal_run_id and outcome.terminal_errors:
            self._upsert_terminal_failed_current(
                run_id=outcome.terminal_run_id,
                packet=packet,
                agent_config=agent_config,
                errors=outcome.terminal_errors,
                terminal_reason=outcome.retry_reason,
                computed_at_ms=now_ms,
            )

    def _mark_targets_done(self, targets: Iterable[Mapping[str, Any]], *, now_ms: int) -> None:
        with self._repository_session() as repos:
            repos.news_projection_dirty_targets.mark_done(targets, now_ms=now_ms)

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
            repos.news_projection_dirty_targets.mark_error(
                targets,
                error=str(error),
                retry_ms=retry_ms,
                now_ms=now_ms,
                count_attempt=count_attempt,
            )

    def _terminalize_claimed_target(
        self,
        target: Mapping[str, Any],
        *,
        outcome: _CandidateOutcome,
        packet: NewsItemBriefInputPacket,
        now_ms: int,
        terminal_attempt_count: int | None = None,
    ) -> int:
        with self._repository_session() as repos:
            return int(
                repos.news_projection_dirty_targets.terminalize_targets(
                    [target],
                    worker_name=self.name,
                    final_reason=outcome.retry_reason,
                    final_reason_bucket=outcome.retry_reason,
                    now_ms=now_ms,
                    semantic_payload_hash=packet.input_hash,
                    terminal_attempt_count=terminal_attempt_count,
                )
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
                provider=str(audit.get("provider") or self.provider.provider),
                model=str(audit.get("model") or agent_config.model),
                backend=str(audit.get("backend") or "litellm_sdk"),
                execution_trace_id=audit.get("execution_trace_id"),
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
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        payload: Mapping[str, Any],
        computed_at_ms: int,
    ) -> None:
        with self._repository_session() as repos, repos.conn.transaction():
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
            source_ids = repos.news.list_source_ids_for_news_items(
                news_item_ids=[packet.news_item.news_item_id],
            )
            repos.news_projection_dirty_targets.enqueue_targets(
                [
                    {
                        "projection_name": "page",
                        "target_kind": "news_item",
                        "target_id": packet.news_item.news_item_id,
                    },
                    *[
                        {
                            "projection_name": "source_quality",
                            "target_kind": "source",
                            "target_id": source_id,
                            "window": window,
                        }
                        for source_id in source_ids
                        for window in getattr(self, "source_quality_windows", ("24h", "7d"))
                    ],
                ],
                reason="news_item_brief_updated",
                now_ms=int(computed_at_ms),
                commit=False,
            )

    def _upsert_failed_current(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        errors: list[dict[str, str]],
        computed_at_ms: int,
    ) -> None:
        self._upsert_current(
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            payload=_failed_brief(errors),
            computed_at_ms=computed_at_ms,
        )

    def _upsert_terminal_failed_current(
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
            payload=_failed_brief(errors, terminal=True, terminal_reason=terminal_reason),
            computed_at_ms=computed_at_ms,
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


class _CandidateOutcome:
    def __init__(
        self,
        *,
        notes: Mapping[str, int],
        current_updates: int,
        retry_ms: int | None = None,
        retry_reason: str = "",
        retry_attempt_limited: bool = False,
        retry_counts_attempt: bool = True,
        force_terminal: bool = False,
        terminal_run_id: str = "",
        terminal_errors: list[dict[str, str]] | None = None,
    ) -> None:
        self.notes = dict(notes)
        self.current_updates = int(current_updates)
        self.retry_ms = int(retry_ms) if retry_ms is not None else None
        self.retry_reason = retry_reason or "agent_brief_retry"
        self.retry_attempt_limited = bool(retry_attempt_limited)
        self.retry_counts_attempt = bool(retry_counts_attempt)
        self.force_terminal = bool(force_terminal)
        self.terminal_run_id = str(terminal_run_id or "")
        self.terminal_errors = list(terminal_errors or [])


def _packet_from_candidate(
    candidate: Mapping[str, Any],
    *,
    agent_config: NewsItemBriefAgentConfig,
) -> NewsItemBriefInputPacket:
    return build_news_item_brief_input_packet(
        item=_dict(candidate.get("item") or candidate),
        token_mentions=_list_of_dicts(candidate.get("token_mentions")),
        fact_candidates=_list_of_dicts(candidate.get("fact_candidates")),
        context_items=_list_of_dicts(candidate.get("context_items")),
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
    status = str(current.get("status") or "")
    if status == "failed":
        return False
    if status not in {"ready", "insufficient", "failed"}:
        return False
    if str(current.get("input_hash") or "") != packet.input_hash:
        return False
    if str(current.get("artifact_version_hash") or "") != agent_config.artifact_version_hash:
        return False
    if str(current.get("prompt_version") or "") != agent_config.prompt_version:
        return False
    if str(current.get("schema_version") or "") != agent_config.schema_version:
        return False
    return str(current.get("validator_version") or "") == agent_config.validator_version

def _target_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    return _unique_values(
        [
            str(row.get("target_id") or "")
            for row in rows
            if str(row.get("projection_name") or "") == "brief_input"
            and str(row.get("target_kind") or "") == "news_item"
            and str(row.get("window") or "") == ""
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


def _request_json(*, packet: NewsItemBriefInputPacket, audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet": packet.model_dump(mode="json"),
        "audit": dict(audit),
    }


def _failed_brief(
    errors: list[dict[str, str]],
    *,
    terminal: bool = False,
    terminal_reason: str = "",
) -> dict[str, Any]:
    reason = "; ".join(str(error.get("message") or error.get("code") or "")[:120] for error in errors[:3])
    suffix = f"原因：{reason}" if reason else "已记录失败原因。"
    payload: dict[str, Any] = {
        "status": "failed",
        "direction": "neutral",
        "decision_class": "discard",
        "summary_zh": "",
        "market_read_zh": "",
        "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "affected_assets": [],
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
    if terminal:
        payload["terminal"] = True
        payload["terminal_reason"] = terminal_reason
    return payload


def _source_quality_windows(windows: Iterable[str] | None) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(window).strip().lower() for window in (windows or ()) if str(window).strip()))
    return normalized or ("24h", "7d")


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
    return f"news-item-agent-run-{uuid.uuid4().hex}"


def _claim_owner(worker_name: str) -> str:
    return f"{worker_name}:{uuid.uuid4().hex}"


__all__ = ["NewsItemBriefWorker"]
