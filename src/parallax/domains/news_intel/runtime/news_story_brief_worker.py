from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel.runtime.news_projection_work import (
    STORY_BRIEF_INPUT,
    claim_story_brief_work,
    enqueue_page_reprojection,
    mark_work_done,
    mark_work_error,
    queue_story_brief_depth,
    story_brief_story_keys,
)
from parallax.domains.news_intel.services.news_item_brief_validation import validate_news_item_brief_output
from parallax.domains.news_intel.services.news_story_brief_input import build_news_story_brief_input_packet
from parallax.domains.news_intel.types.news_story_brief import (
    NEWS_STORY_BRIEF_LANE,
    NewsStoryBriefAgentConfig,
    NewsStoryBriefInputPacket,
    default_news_story_brief_agent_config,
)
from parallax.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentExecutionResultAudit,
)
from parallax.platform.agent_hashing import json_sha256


class NewsStoryBriefWorker(WorkerBase):
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
        name: str = "news_story_brief",
    ) -> None:
        if settings is None:
            raise RuntimeError("news_story_brief_settings_required")
        if db is None:
            raise RuntimeError("news_story_brief_db_required")
        if provider is None:
            raise RuntimeError("news_story_brief_provider_required")
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
        agent_config = default_news_story_brief_agent_config(
            model=str(provider.story_model),
            artifact_version_hash=str(provider.story_artifact_version_hash),
        )
        queue_depth = await asyncio.to_thread(self._queue_depth, now_ms=now)
        if queue_depth <= 0:
            return WorkerResult(skipped=1, notes={"reason": "no_due_story_brief_targets"})

        rate_units = min(self._batch_size(), max(1, int(queue_depth)))
        try:
            reservation = provider.try_reserve_execution(NEWS_STORY_BRIEF_LANE, rate_units=rate_units)
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
                return WorkerResult(skipped=1, notes={"reason": "no_due_story_brief_targets", "claimed": 0})
            try:
                candidates = await asyncio.to_thread(self._load_candidates, claimed=claimed)
                candidates_by_story_key = _candidates_by_story_key(candidates)
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
                "missing_target": 0,
            }
            skipped = 0
            current_updates = 0

            for target in claimed:
                try:
                    story_key = _required_story_brief_target_story_key(target)
                    candidate = candidates_by_story_key.get(story_key)
                    if candidate is None:
                        notes["missing_target"] += 1
                        await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                        skipped += 1
                        continue
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
                            source_watermark_ms=_target_source_watermark_ms(target),
                        )
                        status = str(completed_run["outcome"])
                        notes["restored_from_completed_run"] = int(notes.get("restored_from_completed_run", 0)) + 1
                    else:
                        failed_run = _fresh_failed_run(candidate, packet=packet, agent_config=agent_config)
                        if failed_run is not None:
                            await asyncio.to_thread(
                                self._restore_current_from_failed_run,
                                run=failed_run,
                                packet=packet,
                                agent_config=agent_config,
                                source_watermark_ms=_target_source_watermark_ms(target),
                            )
                            notes["restored_from_failed_run"] = int(notes.get("restored_from_failed_run", 0)) + 1
                            skipped += 1
                            current_updates += 1
                            await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                            continue
                        status = await self._process_candidate(
                            packet=packet,
                            agent_config=agent_config,
                            reservation=reservation,
                            source_watermark_ms=_target_source_watermark_ms(target),
                        )
                    notes[status] = int(notes.get(status, 0)) + 1
                    current_updates += 1
                    await asyncio.to_thread(self._mark_targets_done, [target], now_ms=now)
                except _NoStartBackpressure as exc:
                    notes["backpressure"] += 1
                    notes[exc.outcome] = int(notes.get(exc.outcome, 0)) + 1
                    await asyncio.to_thread(
                        self._mark_targets_error,
                        [target],
                        error=exc.outcome,
                        retry_ms=self._backpressure_cooldown_ms(),
                        now_ms=now,
                        count_attempt=False,
                    )
                    skipped += 1
                except Exception as exc:
                    notes["failed"] += 1
                    await asyncio.to_thread(
                        self._mark_targets_error,
                        [target],
                        error=exc,
                        retry_ms=self._retry_ms(),
                        now_ms=now,
                    )

            if current_updates > 0 and self.wake_emitter is not None:
                self.wake_emitter.notify_news_story_brief_updated(count=current_updates)
            return WorkerResult(
                processed=int(notes["ready"]) + int(notes["insufficient"]),
                failed=int(notes["failed"]),
                skipped=skipped,
                notes=notes,
            )
        finally:
            await _release_reservation(reservation)

    async def _process_candidate(
        self,
        *,
        packet: NewsStoryBriefInputPacket,
        agent_config: NewsStoryBriefAgentConfig,
        reservation: AgentCapacityReservation,
        source_watermark_ms: int,
    ) -> str:
        run_id = self.run_id_factory()
        started_at_ms = self.clock_ms()
        try:
            request_audit = self.provider.request_story_audit(run_id=run_id, packet=packet)
        except Exception as exc:
            raise _NoStartBackpressure("request_audit_failed") from exc

        try:
            result = await self.provider.brief_story(run_id=run_id, packet=packet, reservation=reservation)
        except Exception as exc:
            if _is_no_start_backpressure_error(exc):
                raise _NoStartBackpressure(_backpressure_outcome_for_error(exc)) from exc
            await asyncio.to_thread(
                self._insert_failed_provider_run,
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                request_audit=request_audit,
                error=exc,
                started_at_ms=started_at_ms,
                finished_at_ms=self.clock_ms(),
            )
            raise RuntimeError("news_story_brief_provider_failed") from exc

        if not isinstance(result, Mapping):
            raise RuntimeError("news_story_brief_result_mapping_required")
        payload = result.get("payload")
        audit = _required_agent_run_audit(result.get("agent_run_audit"))
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
                error="news story brief validation failed",
                request_json=_request_json(packet=packet, audit=request_audit),
                response_json=payload if isinstance(payload, Mapping) else {"payload": payload},
                validation_errors=validation.errors,
                execution_started=True,
                output_hash=_output_hash(payload),
            )
            raise RuntimeError("news_story_brief_validation_failed")

        payload_dict = validation.payload
        if payload_dict is None:
            raise RuntimeError("news_story_brief_validation_payload_required")
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
            source_watermark_ms=source_watermark_ms,
        )
        return str(validation.status)

    def _insert_failed_provider_run(
        self,
        *,
        run_id: str,
        packet: NewsStoryBriefInputPacket,
        agent_config: NewsStoryBriefAgentConfig,
        request_audit: Mapping[str, Any],
        error: Exception,
        started_at_ms: int,
        finished_at_ms: int,
    ) -> None:
        audit = _provider_error_audit(error)
        if audit is None:
            audit = dict(request_audit)
            audit["latency_ms"] = max(0, int(finished_at_ms) - int(started_at_ms))
        self._insert_run(
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
            execution_started=_provider_execution_started(error),
        )

    def _claim_targets(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        with self._repository_session() as repos:
            return claim_story_brief_work(
                repos,
                limit=max(1, int(limit)),
                lease_ms=self._lease_ms(),
                now_ms=now_ms,
                lease_owner=_claim_owner(self.name),
            )

    def _queue_depth(self, *, now_ms: int | None = None) -> int:
        resolved_now_ms = self.clock_ms() if now_ms is None else int(now_ms)
        with self._repository_session() as repos:
            return queue_story_brief_depth(repos, now_ms=resolved_now_ms)

    def _load_candidates(self, *, claimed: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        story_keys = story_brief_story_keys(claimed)
        if not story_keys:
            return []
        with self._repository_session() as repos:
            return cast(list[dict[str, Any]], repos.news.load_story_brief_targets(story_keys=story_keys))

    def _restore_current_from_completed_run(
        self,
        *,
        run: Mapping[str, Any],
        packet: NewsStoryBriefInputPacket,
        agent_config: NewsStoryBriefAgentConfig,
        source_watermark_ms: int,
    ) -> None:
        outcome = _required_run_outcome(run, reason="completed_run", allowed={"ready", "insufficient"})
        payload = _required_completed_run_payload(run, outcome=outcome)
        computed_at_ms = _required_run_finished_at_ms(run, reason="completed_run")
        self._upsert_current(
            run_id=_required_run_id(run, reason="completed_run"),
            packet=packet,
            agent_config=agent_config,
            payload=payload,
            computed_at_ms=computed_at_ms,
            source_watermark_ms=source_watermark_ms,
        )

    def _restore_current_from_failed_run(
        self,
        *,
        run: Mapping[str, Any],
        packet: NewsStoryBriefInputPacket,
        agent_config: NewsStoryBriefAgentConfig,
        source_watermark_ms: int,
    ) -> None:
        error_class = _required_failed_run_error_class(run)
        computed_at_ms = _required_run_finished_at_ms(run, reason="failed_run")
        self._upsert_current(
            run_id=_required_run_id(run, reason="failed_run"),
            packet=packet,
            agent_config=agent_config,
            payload=_failed_brief(_failed_run_errors(run), terminal_reason=error_class),
            computed_at_ms=computed_at_ms,
            source_watermark_ms=source_watermark_ms,
        )

    def _upsert_current(
        self,
        *,
        run_id: str,
        packet: NewsStoryBriefInputPacket,
        agent_config: NewsStoryBriefAgentConfig,
        payload: Mapping[str, Any],
        computed_at_ms: int,
        source_watermark_ms: int,
    ) -> None:
        with self._repository_session() as repos, repos.transaction():
            repos.news.upsert_news_story_agent_brief(
                story_brief_key=packet.story_brief_key,
                story_key=packet.story_key,
                story_identity_version=packet.story_identity_version,
                representative_news_item_id=packet.representative_news_item_id,
                member_news_item_ids_json=list(packet.member_news_item_ids),
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
            enqueue_page_reprojection(
                repos,
                news_item_ids=list(packet.member_news_item_ids),
                reason="news_story_brief_updated",
                now_ms=int(computed_at_ms),
                source_watermark_ms_by_news_item_id={
                    news_item_id: source_watermark_ms for news_item_id in packet.member_news_item_ids
                },
                commit=False,
            )

    def _insert_run(
        self,
        *,
        run_id: str,
        packet: NewsStoryBriefInputPacket,
        agent_config: NewsStoryBriefAgentConfig,
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
        with self._repository_session() as repos:
            repos.news.insert_news_story_agent_run(
                run_id=run_id,
                story_brief_key=packet.story_brief_key,
                story_key=packet.story_key,
                story_identity_version=packet.story_identity_version,
                representative_news_item_id=packet.representative_news_item_id,
                member_news_item_ids_json=list(packet.member_news_item_ids),
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


class _NoStartBackpressure(Exception):
    def __init__(self, outcome: str) -> None:
        super().__init__(outcome)
        self.outcome = str(outcome)


def _packet_from_candidate(
    candidate: Mapping[str, Any],
    *,
    agent_config: NewsStoryBriefAgentConfig,
) -> NewsStoryBriefInputPacket:
    return build_news_story_brief_input_packet(
        story=_candidate_dict(candidate.get("story"), field="story"),
        representative_item=_candidate_dict(candidate.get("item"), field="item"),
        member_items=_candidate_list_of_dicts(candidate.get("member_items"), field="member_items"),
        entities=_candidate_list_of_dicts(candidate.get("entities"), field="entities"),
        token_mentions=_candidate_list_of_dicts(candidate.get("token_mentions"), field="token_mentions"),
        fact_candidates=_candidate_list_of_dicts(candidate.get("fact_candidates"), field="fact_candidates"),
        agent_config=agent_config,
    )


def _candidates_by_story_key(candidates: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_story_key: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        candidate_payload = _candidate_dict(candidate, field="candidate")
        story = _candidate_dict(candidate_payload.get("story"), field="story")
        story_key = _required_candidate_text(story, field="story_key")
        by_story_key[story_key] = candidate_payload
    return by_story_key


def _required_candidate_text(candidate: Mapping[str, Any], *, field: str) -> str:
    try:
        value = candidate[field]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_candidate_{field}_required") from exc
    text = str(value).strip()
    if not text:
        raise RuntimeError(f"news_story_brief_candidate_{field}_required")
    return text


def _required_story_brief_target_story_key(target: Mapping[str, Any]) -> str:
    _require_claim_text(target, field="projection_name", expected=STORY_BRIEF_INPUT)
    _require_claim_text(target, field="target_kind", expected="story")
    _require_claim_empty_window(target)
    return _require_claim_text(target, field="target_id")


def _require_claim_text(target: Mapping[str, Any], *, field: str, expected: str | None = None) -> str:
    try:
        value = target[field]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_claim_{field}_required") from exc
    if not isinstance(value, str):
        raise RuntimeError(f"news_story_brief_claim_{field}_required")
    text = value.strip()
    if not text:
        raise RuntimeError(f"news_story_brief_claim_{field}_required")
    if expected is not None and text != expected:
        raise RuntimeError(f"news_story_brief_claim_{field}_required")
    return text


def _require_claim_empty_window(target: Mapping[str, Any]) -> None:
    try:
        value = target["window"]
    except KeyError as exc:
        raise RuntimeError("news_story_brief_claim_window_empty_required") from exc
    if value != "":
        raise RuntimeError("news_story_brief_claim_window_empty_required")


def _current_brief_is_fresh(
    candidate: Mapping[str, Any],
    *,
    packet: NewsStoryBriefInputPacket,
    agent_config: NewsStoryBriefAgentConfig,
) -> bool:
    current = _optional_dict(candidate.get("current_brief"))
    if current is None:
        return False
    _required_current_text(current, "story_brief_key", expected=packet.story_brief_key)
    _required_current_text(current, "agent_run_id")
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
    packet: NewsStoryBriefInputPacket,
    agent_config: NewsStoryBriefAgentConfig,
) -> dict[str, Any] | None:
    run = _optional_dict(candidate.get("latest_run"))
    if run is None:
        return None
    if _required_run_status(run) != "completed":
        return None
    _required_run_text(run, "story_brief_key", reason="completed_run", expected=packet.story_brief_key)
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
    outcome = _required_run_outcome(run, reason="completed_run", allowed={"ready", "insufficient"})
    _required_completed_run_payload(run, outcome=outcome)
    _required_run_id(run, reason="completed_run")
    return run


def _fresh_failed_run(
    candidate: Mapping[str, Any],
    *,
    packet: NewsStoryBriefInputPacket,
    agent_config: NewsStoryBriefAgentConfig,
) -> dict[str, Any] | None:
    run = _optional_dict(candidate.get("latest_run"))
    if run is None:
        return None
    if _required_run_status(run) != "failed":
        return None
    _required_run_text(run, "story_brief_key", reason="failed_run", expected=packet.story_brief_key)
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
    _required_run_outcome(run, reason="failed_run", allowed={"failed"})
    if not _required_run_execution_started(run, reason="failed_run"):
        return None
    _required_run_id(run, reason="failed_run")
    return run


def _publishable_summary(payload: Mapping[str, Any]) -> bool:
    try:
        summary = payload["summary_zh"]
    except KeyError:
        return False
    return isinstance(summary, str) and bool(summary.strip())


def _request_json(*, packet: NewsStoryBriefInputPacket, audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet": packet.model_dump(mode="json"),
        "audit": dict(audit),
    }


def _output_hash(payload: Any) -> str | None:
    try:
        return json_sha256(payload)
    except TypeError:
        return None


def _failed_run_errors(run: Mapping[str, Any]) -> list[dict[str, str]]:
    error_class = _required_failed_run_error_class(run)
    error = _required_failed_run_error(run)
    return [{"code": error_class, "message": error[:500]}]


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
    return {
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
                "description_zh": f"新闻故事智能摘要不可发布，{suffix}",
                "severity": "high",
            }
        ],
        "evidence_refs": [],
    }


def _required_run_id(run: Mapping[str, Any], *, reason: str) -> str:
    try:
        value = run["run_id"]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_run_id_required:{reason}") from exc
    run_id = str(value).strip()
    if not run_id:
        raise RuntimeError(f"news_story_brief_run_id_required:{reason}")
    return run_id


def _required_current_text(current: Mapping[str, Any], field: str, *, expected: str | None = None) -> str:
    try:
        value = current[field]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_current_{field}_required") from exc
    text = str(value).strip()
    if not text:
        raise RuntimeError(f"news_story_brief_current_{field}_required")
    if expected is not None and text != expected:
        raise RuntimeError(f"news_story_brief_current_{field}_required")
    return text


def _required_current_status(current: Mapping[str, Any]) -> str:
    status = _required_current_text(current, "status")
    if status not in {"ready", "insufficient", "failed"}:
        raise RuntimeError("news_story_brief_current_status_required")
    return status


def _required_run_status(run: Mapping[str, Any]) -> str:
    status = _required_run_text(run, "status", reason="latest_run")
    if status not in {"completed", "failed"}:
        raise RuntimeError("news_story_brief_run_status_required:latest_run")
    return status


def _required_run_text(
    run: Mapping[str, Any],
    field: str,
    *,
    reason: str,
    expected: str | None = None,
) -> str:
    try:
        value = run[field]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_run_{field}_required:{reason}") from exc
    text = str(value).strip()
    if not text:
        raise RuntimeError(f"news_story_brief_run_{field}_required:{reason}")
    if expected is not None and text != expected:
        raise RuntimeError(f"news_story_brief_run_{field}_required:{reason}")
    return text


def _required_completed_run_payload(run: Mapping[str, Any], *, outcome: str) -> dict[str, Any]:
    try:
        value = run["response_json"]
    except KeyError as exc:
        raise RuntimeError("news_story_brief_run_response_json_required:completed_run") from exc
    if not isinstance(value, Mapping):
        raise RuntimeError("news_story_brief_run_response_json_required:completed_run")
    payload = dict(value)
    try:
        status_value = payload["status"]
    except KeyError as exc:
        raise RuntimeError("news_story_brief_run_response_status_required:completed_run") from exc
    if str(status_value).strip() != outcome:
        raise RuntimeError("news_story_brief_run_response_status_required:completed_run")
    if outcome == "ready" and not _publishable_summary(payload):
        raise RuntimeError("news_story_brief_run_publishable_summary_required:completed_run")
    return payload


def _required_run_finished_at_ms(run: Mapping[str, Any], *, reason: str) -> int:
    try:
        value = run["finished_at_ms"]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_run_finished_at_ms_required:{reason}") from exc
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"news_story_brief_run_finished_at_ms_required:{reason}")
    if value <= 0:
        raise RuntimeError(f"news_story_brief_run_finished_at_ms_required:{reason}")
    return value


def _required_run_outcome(run: Mapping[str, Any], *, reason: str, allowed: set[str]) -> str:
    try:
        value = run["outcome"]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_run_outcome_required:{reason}") from exc
    outcome = str(value).strip()
    if outcome not in allowed:
        raise RuntimeError(f"news_story_brief_run_outcome_required:{reason}")
    return outcome


def _required_run_execution_started(run: Mapping[str, Any], *, reason: str) -> bool:
    try:
        value = run["execution_started"]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_run_execution_started_required:{reason}") from exc
    if not isinstance(value, bool):
        raise RuntimeError(f"news_story_brief_run_execution_started_required:{reason}")
    return value


def _required_failed_run_error_class(run: Mapping[str, Any]) -> str:
    try:
        value = run["error_class"]
    except KeyError as exc:
        raise RuntimeError("news_story_brief_run_error_class_required:failed_run") from exc
    error_class = str(value).strip()
    if not error_class:
        raise RuntimeError("news_story_brief_run_error_class_required:failed_run")
    return error_class


def _required_failed_run_error(run: Mapping[str, Any]) -> str:
    try:
        value = run["error"]
    except KeyError as exc:
        raise RuntimeError("news_story_brief_run_error_required:failed_run") from exc
    error = str(value).strip()
    if not error:
        raise RuntimeError("news_story_brief_run_error_required:failed_run")
    return error


def _target_source_watermark_ms(target: Mapping[str, Any]) -> int:
    return _positive_watermark(target.get("source_watermark_ms"))


def _positive_watermark(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("news_story_brief_page_dirty_source_watermark_required")
    watermark = int(value)
    if watermark <= 0:
        raise ValueError("news_story_brief_page_dirty_source_watermark_required")
    return watermark


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
        return "backpressure_capacity_denied"
    return _backpressure_outcome_for_reason(error.error_class)


async def _release_reservation(reservation: AgentCapacityReservation) -> None:
    await reservation.release()


def _required_agent_run_audit(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError("news_story_brief_agent_run_audit_contract_required")
    return {str(key): child for key, child in value.items()}


def _optional_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise RuntimeError("news_story_brief_candidate_optional_object_required")
    return dict(value)


def _candidate_dict(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError(f"news_story_brief_candidate_{field}_object_required")
    return dict(value)


def _candidate_list_of_dicts(value: Any, *, field: str) -> list[dict[str, Any]]:
    if value is None:
        raise RuntimeError(f"news_story_brief_candidate_{field}_array_required")
    if not isinstance(value, list | tuple):
        raise RuntimeError(f"news_story_brief_candidate_{field}_array_required")
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise RuntimeError(f"news_story_brief_candidate_{field}_row_object_required")
        rows.append(dict(row))
    return rows


def _now_ms() -> int:
    return int(time.time() * 1000)


def _default_run_id() -> str:
    return f"news-story-agent-run-{uuid.uuid4().hex}"


def _provider_error_audit(error: Exception) -> dict[str, Any] | None:
    if not isinstance(error, AgentExecutionError):
        return None
    audit = error.audit
    if audit is None:
        return None
    if not isinstance(audit, AgentExecutionRequestAudit | AgentExecutionResultAudit):
        raise RuntimeError("news_story_brief_agent_error_audit_contract_required")
    return audit.model_dump(mode="json")


def _provider_error_class(error: Exception) -> str:
    if isinstance(error, AgentExecutionError):
        return _reason_value(error.error_class)
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


def _reason_value(reason: AgentExecutionErrorClass) -> str:
    return reason.value


def _required_audit_text(audit: Mapping[str, Any], field_name: str) -> str:
    try:
        value = audit[field_name]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_audit_{field_name}_required") from exc
    text = str(value).strip()
    if not text:
        raise RuntimeError(f"news_story_brief_audit_{field_name}_required")
    return text


def _required_audit_mapping(audit: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    try:
        value = audit[field_name]
    except KeyError as exc:
        raise RuntimeError(f"news_story_brief_audit_{field_name}_required") from exc
    if not isinstance(value, Mapping):
        raise RuntimeError(f"news_story_brief_audit_{field_name}_required")
    return dict(value)


def _required_audit_latency_ms(audit: Mapping[str, Any]) -> int:
    try:
        value = audit["latency_ms"]
    except KeyError as exc:
        raise RuntimeError("news_story_brief_audit_latency_ms_required") from exc
    if isinstance(value, bool):
        raise RuntimeError("news_story_brief_audit_latency_ms_required")
    try:
        latency_ms = int(float(value))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("news_story_brief_audit_latency_ms_required") from exc
    if latency_ms < 0:
        raise RuntimeError("news_story_brief_audit_latency_ms_required")
    return latency_ms


def _claim_owner(worker_name: str) -> str:
    return f"{worker_name}:{uuid.uuid4().hex}"


__all__ = ["NewsStoryBriefWorker"]
