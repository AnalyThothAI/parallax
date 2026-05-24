from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel.services.news_item_brief_input import (
    build_news_item_brief_input_packet,
)
from gmgn_twitter_intel.domains.news_intel.services.news_item_brief_validation import (
    validate_news_item_brief_output,
)
from gmgn_twitter_intel.domains.news_intel.types.news_item_brief import (
    NEWS_ITEM_BRIEF_LANE,
    NewsItemBriefAgentConfig,
    NewsItemBriefInputPacket,
    default_news_item_brief_agent_config,
)
from gmgn_twitter_intel.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
)
from gmgn_twitter_intel.platform.agent_hashing import json_sha256


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
        with self._repository_session() as repos:
            candidates = repos.news.list_items_for_brief(
                limit=self._batch_size(),
                now_ms=now,
                backpressure_cooldown_ms=self._backpressure_cooldown_ms(),
                artifact_version_hash=agent_config.artifact_version_hash,
                max_attempts=self._max_attempts(),
            )
        if not candidates:
            return WorkerResult(skipped=1, notes={"reason": "no_items_for_brief"})

        notes = {
            "claimed": len(candidates),
            "ready": 0,
            "insufficient": 0,
            "failed": 0,
            "backpressure": 0,
            "validation_failed": 0,
        }
        skipped = 0
        current_updates = 0

        for candidate in candidates:
            packet = _packet_from_candidate(candidate, agent_config=agent_config)
            if _current_brief_is_fresh(candidate, packet=packet, agent_config=agent_config):
                skipped += 1
                continue

            outcome = await self._process_candidate(
                candidate=candidate,
                packet=packet,
                agent_config=agent_config,
                now_ms=now,
            )
            for key, value in outcome.notes.items():
                notes[key] = int(notes.get(key, 0)) + int(value)
            current_updates += outcome.current_updates

        if current_updates > 0 and self.wake_bus is not None:
            self.wake_bus.notify_news_item_brief_updated(count=current_updates)
        failed = int(notes["failed"])
        processed = int(notes["ready"]) + int(notes["insufficient"])
        skipped += int(notes["backpressure"])
        return WorkerResult(processed=processed, failed=failed, skipped=skipped, notes=notes)

    async def _process_candidate(
        self,
        *,
        candidate: Mapping[str, Any],
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        now_ms: int,
    ) -> _CandidateOutcome:
        if self.provider is None:
            raise RuntimeError("news item brief provider is not configured")
        run_id = self.run_id_factory()
        started_at_ms = self.clock_ms()
        try:
            request_audit = self.provider.request_audit(run_id=run_id, packet=packet)
        except Exception as exc:
            request_audit = _fallback_request_audit(
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                provider=self.provider,
            )
            return self._record_provider_failure(
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                request_audit=request_audit,
                error=exc,
                started_at_ms=started_at_ms,
                execution_started=False,
            )

        try:
            reservation = self.provider.try_reserve_execution(NEWS_ITEM_BRIEF_LANE)
        except Exception as exc:
            return self._record_provider_failure(
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
            self._insert_run(
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                audit=request_audit,
                started_at_ms=started_at_ms,
                finished_at_ms=self.clock_ms(),
                status="backpressure",
                outcome=outcome,
                error_class=_reason_value(reservation.reason),
                error=f"news item brief execution deferred: {outcome}",
                request_json=_request_json(packet=packet, audit=request_audit),
                response_json=None,
                validation_errors=[],
                execution_started=False,
            )
            return _CandidateOutcome(notes={"backpressure": 1, outcome: 1}, current_updates=0)

        try:
            result = await self.provider.brief_item(run_id=run_id, packet=packet, reservation=reservation)
        except Exception as exc:
            if _is_no_start_backpressure_error(exc):
                return self._record_execute_backpressure(
                    run_id=run_id,
                    packet=packet,
                    agent_config=agent_config,
                    request_audit=request_audit,
                    error=exc,
                    started_at_ms=started_at_ms,
                )
            return self._record_provider_failure(
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
        validation = validate_news_item_brief_output(payload=payload, packet=packet, audit=audit)
        finished_at_ms = self.clock_ms()
        if not validation.publishable:
            self._insert_run(
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
            self._upsert_failed_current(
                run_id=run_id,
                packet=packet,
                agent_config=agent_config,
                errors=validation.errors,
                computed_at_ms=finished_at_ms,
            )
            return _CandidateOutcome(notes={"failed": 1, "validation_failed": 1}, current_updates=1)

        payload_dict = validation.payload or {}
        self._insert_run(
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
        self._upsert_current(
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            payload=payload_dict,
            computed_at_ms=finished_at_ms,
        )
        status = str(validation.status)
        return _CandidateOutcome(notes={status: 1}, current_updates=1)

    def _record_provider_failure(
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
            execution_started=resolved_execution_started,
        )
        self._upsert_failed_current(
            run_id=run_id,
            packet=packet,
            agent_config=agent_config,
            errors=[{"code": _provider_error_class(error), "message": str(error)[:500]}],
            computed_at_ms=finished_at_ms,
        )
        return _CandidateOutcome(notes={"failed": 1}, current_updates=1)

    def _record_execute_backpressure(
        self,
        *,
        run_id: str,
        packet: NewsItemBriefInputPacket,
        agent_config: NewsItemBriefAgentConfig,
        request_audit: Mapping[str, Any],
        error: Exception,
        started_at_ms: int,
    ) -> _CandidateOutcome:
        audit = _provider_error_audit(error) or dict(request_audit)
        outcome = _backpressure_outcome_for_reason(getattr(error, "error_class", None))
        finished_at_ms = self.clock_ms()
        self._insert_run(
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
        return _CandidateOutcome(notes={"backpressure": 1, outcome: 1}, current_updates=0)

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

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 5)))

    def _max_attempts(self) -> int:
        return max(1, int(getattr(self.settings, "max_attempts", 3)))

    def _backpressure_cooldown_ms(self) -> int:
        return max(1, int(getattr(self.settings, "backpressure_cooldown_ms", 60_000)))


class _CandidateOutcome:
    def __init__(self, *, notes: Mapping[str, int], current_updates: int) -> None:
        self.notes = dict(notes)
        self.current_updates = int(current_updates)


def _packet_from_candidate(
    candidate: Mapping[str, Any],
    *,
    agent_config: NewsItemBriefAgentConfig,
) -> NewsItemBriefInputPacket:
    return build_news_item_brief_input_packet(
        item=_dict(candidate.get("item") or candidate),
        story=_optional_dict(candidate.get("story")),
        token_mentions=_list_of_dicts(candidate.get("token_mentions")),
        fact_candidates=_list_of_dicts(candidate.get("fact_candidates")),
        story_members=_list_of_dicts(candidate.get("story_members")),
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
    if str(current.get("status") or "") == "failed":
        return False
    if str(current.get("input_hash") or "") != packet.input_hash:
        return False
    if str(current.get("artifact_version_hash") or "") != agent_config.artifact_version_hash:
        return False
    return int(current.get("computed_at_ms") or 0) >= int(candidate.get("source_updated_at_ms") or 0)


def _backpressure_outcome(reservation: AgentCapacityReservation) -> str:
    return _backpressure_outcome_for_reason(reservation.reason)


def _backpressure_outcome_for_reason(reason: Any) -> str:
    if reason == AgentExecutionErrorClass.CIRCUIT_OPEN:
        return "backpressure_circuit_open"
    if reason == AgentExecutionErrorClass.RATE_LIMITED:
        return "backpressure_rate_limited"
    return "backpressure_capacity_denied"


def _request_json(*, packet: NewsItemBriefInputPacket, audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "packet": packet.model_dump(mode="json"),
        "audit": dict(audit),
    }


def _fallback_request_audit(
    *,
    run_id: str,
    packet: NewsItemBriefInputPacket,
    agent_config: NewsItemBriefAgentConfig,
    provider: Any,
) -> dict[str, Any]:
    return {
        "provider": str(getattr(provider, "provider", agent_config.provider) or agent_config.provider),
        "backend": "openai_agents_sdk",
        "model": agent_config.model,
        "lane": agent_config.lane,
        "stage": "news_item_brief",
        "workflow_name": agent_config.workflow_name,
        "agent_name": agent_config.agent_name,
        "sdk_trace_id": None,
        "group_id": f"news_item:{packet.news_item.news_item_id}",
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
        "market_read_zh": "",
        "bull_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "bear_view": {"strength": "absent", "thesis_zh": "", "evidence_refs": []},
        "affected_assets": [],
        "watch_triggers": [],
        "invalidation_conditions": [],
        "data_gaps": [
            {
                "description_zh": f"新闻条目智能摘要暂不可发布，{suffix}",
                "severity": "high",
            }
        ],
        "evidence_refs": [],
    }


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


__all__ = ["NewsItemBriefWorker"]
