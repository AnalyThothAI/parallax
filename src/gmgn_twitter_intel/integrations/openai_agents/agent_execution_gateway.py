from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from agents import Agent, RunConfig, Runner
from agents.exceptions import ModelBehaviorError
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from aiolimiter import AsyncLimiter
from pydantic import ValidationError

from gmgn_twitter_intel.integrations.openai_agents.agent_execution_types import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentExecutionResult,
    AgentExecutionResultAudit,
    AgentExecutionStatus,
    AgentLanePolicy,
    AgentRuntimePolicy,
    AgentStageSpec,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_hashing import (
    artifact_hash_for,
    json_sha256,
    trace_id_for,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_model_settings import (
    default_agent_model_settings,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import (
    InstructorSafetyNet,
    SafetyNetExhausted,
    extract_sdk_usage,
)


@dataclass(slots=True)
class _LaneState:
    policy: AgentLanePolicy
    semaphore: asyncio.BoundedSemaphore
    capacity_denied_total: int = 0
    circuit_open_total: int = 0
    timeout_total: int = 0
    failure_timestamps: list[float] = field(default_factory=list)
    circuit_open_until: float = 0


class AgentExecutionGateway:
    def __init__(
        self,
        *,
        llm_gateway: Any,
        base_url: str,
        trace_enabled: bool,
        trace_include_sensitive_data: bool,
        policy: AgentRuntimePolicy,
        runner: Any | None = None,
        safety_net: InstructorSafetyNet | None = None,
    ) -> None:
        if llm_gateway is None:
            raise ValueError("llm_gateway is required")
        self._llm_gateway = llm_gateway
        self._base_url = _api_base(base_url)
        self._trace_enabled = bool(trace_enabled and getattr(llm_gateway, "trace_export_enabled", False))
        self._trace_include_sensitive_data = bool(trace_include_sensitive_data)
        self._policy = policy
        self._runner = runner or Runner
        self._safety_net = safety_net
        self._global_semaphore = asyncio.BoundedSemaphore(policy.global_max_concurrency)
        self._global_limiter = AsyncLimiter(policy.global_rpm_limit, 60)
        self._lanes: dict[str, _LaneState] = {
            lane: _LaneState(
                policy=lane_policy,
                semaphore=asyncio.BoundedSemaphore(lane_policy.max_concurrency),
            )
            for lane, lane_policy in policy.lanes.items()
        }

    def request_audit(self, stage: AgentStageSpec) -> AgentExecutionRequestAudit:
        output_schema = StrictJsonOutputSchema(stage.output_type)
        artifact_version_hash = artifact_hash_for(
            model=stage.model,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(output_schema.json_schema()),
        )
        trace_source = json_sha256(
            {
                "lane": stage.lane,
                "stage": stage.stage,
                "model": stage.model,
                "workflow_name": stage.workflow_name,
                "agent_name": stage.agent_name,
                "group_id": stage.group_id,
                "prompt_version": stage.prompt_version,
                "schema_version": stage.schema_version,
                "artifact_version_hash": artifact_version_hash,
                "input_hash": stage.input_hash,
            }
        )
        return AgentExecutionRequestAudit.from_stage(
            stage,
            trace_id=trace_id_for(trace_source),
            artifact_version_hash=artifact_version_hash,
        )

    def try_reserve(self, lane: str) -> AgentCapacityReservation:
        lane_key = str(lane)
        lane_state = self._lane_state(lane_key)
        if self._is_circuit_open(lane_key, lane_state):
            lane_state.circuit_open_total += 1
            return AgentCapacityReservation(
                lane=lane_key,
                acquired=False,
                reason=AgentExecutionErrorClass.CIRCUIT_OPEN,
            )
        if not _try_acquire_nowait(self._global_semaphore):
            lane_state.capacity_denied_total += 1
            return AgentCapacityReservation(
                lane=lane_key,
                acquired=False,
                reason=AgentExecutionErrorClass.CAPACITY_DENIED,
            )
        if not _try_acquire_nowait(lane_state.semaphore):
            self._global_semaphore.release()
            lane_state.capacity_denied_total += 1
            return AgentCapacityReservation(
                lane=lane_key,
                acquired=False,
                reason=AgentExecutionErrorClass.CAPACITY_DENIED,
            )

        released = False

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            lane_state.semaphore.release()
            self._global_semaphore.release()

        return AgentCapacityReservation(lane=lane_key, acquired=True, _release=release)

    async def execute(self, stage: AgentStageSpec) -> AgentExecutionResult:
        audit = self.request_audit(stage)
        lane_state = self._lane_state(stage.lane)
        if self._is_circuit_open(stage.lane, lane_state):
            lane_state.circuit_open_total += 1
            raise AgentExecutionError(
                AgentExecutionErrorClass.CIRCUIT_OPEN,
                f"agent lane circuit is open: {stage.lane}",
                audit=audit,
                execution_started=False,
            )

        reservation = self.try_reserve(stage.lane)
        if not reservation.acquired:
            error_class = reservation.reason or AgentExecutionErrorClass.CAPACITY_DENIED
            raise AgentExecutionError(
                error_class,
                f"agent lane unavailable: {stage.lane}",
                audit=audit,
                execution_started=False,
            )

        started = time.perf_counter()
        runner_entered = {"value": False}
        try:
            async with self._global_limiter:
                try:
                    final_output, raw_result, audit_extra = await asyncio.wait_for(
                        self._run_stage(stage, audit, runner_entered=runner_entered),
                        timeout=float(lane_state.policy.timeout_seconds),
                    )
                except TimeoutError as exc:
                    runner_entered["value"] = True
                    lane_state.timeout_total += 1
                    self.record_lane_failure(stage.lane)
                    failed = self._failed_audit(
                        audit,
                        started=started,
                        error_class=AgentExecutionErrorClass.TIMEOUT,
                        message=f"agent lane timed out after {lane_state.policy.timeout_seconds:g}s",
                        execution_started=True,
                    )
                    raise AgentExecutionError(
                        AgentExecutionErrorClass.TIMEOUT,
                        failed.error_message or "agent execution timed out",
                        audit=failed,
                        execution_started=True,
                    ) from exc
            result_audit = AgentExecutionResultAudit(
                **_audit_base(audit),
                status=AgentExecutionStatus.DONE,
                execution_started=True,
                latency_ms=_latency_ms(started),
                usage=dict(audit_extra.get("usage") or extract_sdk_usage(raw_result)),
                parse_mode=str(audit_extra.get("parse_mode") or "strict"),
                safety_net={
                    "safety_net_used": bool(audit_extra.get("safety_net_used", False)),
                    "safety_net_retries": int(audit_extra.get("safety_net_retries") or 0),
                },
                trace_metadata={**audit.trace_metadata, **_audit_trace_extra(audit_extra)},
                output_hash=json_sha256(final_output),
            )
            return AgentExecutionResult(final_output=final_output, audit=result_audit, raw_result=raw_result)
        except AgentExecutionError:
            raise
        except SafetyNetExhausted as exc:
            self.record_lane_failure(stage.lane)
            audit_extra = exc.audit_extra
            failed = self._failed_audit(
                audit,
                started=started,
                error_class=AgentExecutionErrorClass.SCHEMA_INVALID,
                message=str(exc),
                execution_started=True,
                audit_extra=audit_extra,
            )
            raise AgentExecutionError(
                AgentExecutionErrorClass.SCHEMA_INVALID,
                str(exc),
                audit=failed,
                execution_started=True,
            ) from exc
        except (ModelBehaviorError, ValidationError) as exc:
            self.record_lane_failure(stage.lane)
            failed = self._failed_audit(
                audit,
                started=started,
                error_class=AgentExecutionErrorClass.SCHEMA_INVALID,
                message=str(exc),
                execution_started=True,
            )
            raise AgentExecutionError(
                AgentExecutionErrorClass.SCHEMA_INVALID,
                str(exc),
                audit=failed,
                execution_started=True,
            ) from exc
        except Exception as exc:
            error_class = _classify_provider_error(exc)
            self.record_lane_failure(stage.lane)
            failed = self._failed_audit(
                audit,
                started=started,
                error_class=error_class,
                message=str(exc),
                execution_started=runner_entered["value"],
            )
            raise AgentExecutionError(
                error_class,
                str(exc),
                audit=failed,
                execution_started=runner_entered["value"],
            ) from exc
        finally:
            await reservation.release()

    def record_lane_failure(self, lane: str) -> None:
        now = time.monotonic()
        lane_state = self._lane_state(lane)
        breaker = lane_state.policy.circuit_breaker
        window_start = now - float(breaker.window_seconds)
        lane_state.failure_timestamps = [stamp for stamp in lane_state.failure_timestamps if stamp >= window_start]
        lane_state.failure_timestamps.append(now)
        if len(lane_state.failure_timestamps) >= breaker.failure_threshold:
            lane_state.circuit_open_until = now + float(breaker.open_seconds)

    def status_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        lanes: dict[str, Any] = {}
        for lane, lane_state in self._lanes.items():
            lanes[lane] = {
                "max_concurrency": lane_state.policy.max_concurrency,
                "timeout_seconds": float(lane_state.policy.timeout_seconds),
                "in_flight": _in_flight(lane_state.semaphore),
                "circuit_state": "open" if lane_state.circuit_open_until > now else "closed",
                "capacity_denied_total": lane_state.capacity_denied_total,
                "circuit_open_total": lane_state.circuit_open_total,
                "timeout_total": lane_state.timeout_total,
            }
        return {
            "global_max_concurrency": self._policy.global_max_concurrency,
            "global_in_flight": _in_flight(self._global_semaphore),
            "lanes": lanes,
        }

    async def aclose(self) -> None:
        if self._safety_net is not None:
            await self._safety_net.aclose()

    async def _run_stage(
        self,
        stage: AgentStageSpec,
        audit: AgentExecutionRequestAudit,
        *,
        runner_entered: dict[str, bool],
    ) -> tuple[Any, Any | None, dict[str, Any]]:
        lane_policy = self._lane_state(stage.lane).policy
        output_schema = StrictJsonOutputSchema(stage.output_type)
        model = OpenAIChatCompletionsModel(
            model=stage.model,
            openai_client=self._llm_gateway.openai_client(
                model=stage.model,
                base_url=self._base_url,
                timeout_s=float(lane_policy.timeout_seconds),
            ),
        )
        agent = Agent(
            name=stage.agent_name,
            instructions=stage.instructions,
            output_type=output_schema,
            tools=stage.tools,
            model=model,
            model_settings=default_agent_model_settings(),
        )
        run_config = RunConfig(
            workflow_name=stage.workflow_name,
            trace_id=audit.sdk_trace_id,
            group_id=stage.group_id,
            trace_include_sensitive_data=self._trace_include_sensitive_data,
            tracing_disabled=not self._trace_enabled,
            trace_metadata=audit.trace_metadata,
        )
        if self._safety_net is not None:
            runner_entered["value"] = True
            final_output, audit_extra, raw_result = await self._safety_net.run_with_safety_net(
                agent=agent,
                input_payload=stage.input_payload,
                run_config=run_config,
                pydantic_output_type=getattr(output_schema, "output_type", stage.output_type),
                context=None,
                max_turns=stage.max_turns,
                return_result=True,
            )
            return final_output, raw_result, dict(audit_extra)

        runner_entered["value"] = True
        raw_result = await self._runner.run(
            agent,
            stage.input_payload,
            max_turns=stage.max_turns,
            run_config=run_config,
        )
        return (
            getattr(raw_result, "final_output", None),
            raw_result,
            {
                "safety_net_used": False,
                "safety_net_retries": 0,
                "parse_mode": "strict",
                "usage": extract_sdk_usage(raw_result),
            },
        )

    def _lane_state(self, lane: str) -> _LaneState:
        lane_key = str(lane)
        state = self._lanes.get(lane_key)
        if state is None:
            lane_policy = self._policy.lane_for(lane_key)
            state = _LaneState(
                policy=lane_policy,
                semaphore=asyncio.BoundedSemaphore(lane_policy.max_concurrency),
            )
            self._lanes[lane_key] = state
        return state

    def _is_circuit_open(self, lane: str, lane_state: _LaneState | None = None) -> bool:
        state = lane_state or self._lane_state(lane)
        return state.circuit_open_until > time.monotonic()

    def _failed_audit(
        self,
        audit: AgentExecutionRequestAudit,
        *,
        started: float,
        error_class: AgentExecutionErrorClass,
        message: str,
        execution_started: bool,
        audit_extra: dict[str, Any] | None = None,
    ) -> AgentExecutionResultAudit:
        audit_extra = audit_extra or {}
        return AgentExecutionResultAudit(
            **_audit_base(audit),
            status=AgentExecutionStatus.FAILED,
            execution_started=execution_started,
            latency_ms=_latency_ms(started),
            usage=dict(audit_extra.get("usage") or {}),
            parse_mode=audit_extra.get("parse_mode"),
            safety_net={
                "safety_net_used": bool(audit_extra.get("safety_net_used", False)),
                "safety_net_retries": int(audit_extra.get("safety_net_retries") or 0),
            },
            trace_metadata={**audit.trace_metadata, **_audit_trace_extra(audit_extra)},
            error_class=error_class,
            error_message=str(message or "")[:1000],
        )


def _api_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        return "https://api.openai.com/v1"
    return value if value.endswith("/v1") else f"{value}/v1"


def _audit_base(audit: AgentExecutionRequestAudit) -> dict[str, Any]:
    return audit.model_dump(
        exclude={
            "status",
            "execution_started",
            "latency_ms",
            "usage",
            "parse_mode",
            "safety_net",
            "trace_metadata",
            "output_hash",
            "error_class",
            "error_message",
        }
    )


def _try_acquire_nowait(semaphore: asyncio.BoundedSemaphore) -> bool:
    if semaphore.locked() or getattr(semaphore, "_value", 0) <= 0:
        return False
    semaphore._value -= 1
    return True


def _in_flight(semaphore: asyncio.BoundedSemaphore) -> int:
    return int(getattr(semaphore, "_bound_value", 0) - getattr(semaphore, "_value", 0))


def _latency_ms(started: float) -> float:
    return max(0.0, (time.perf_counter() - started) * 1000)


def _audit_trace_extra(audit_extra: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in audit_extra.items()
        if key in {"safety_net_used", "safety_net_retries", "parse_mode"}
    }


def _classify_provider_error(exc: Exception) -> AgentExecutionErrorClass:
    name = type(exc).__name__.lower()
    if "ratelimit" in name or "rate_limit" in name:
        return AgentExecutionErrorClass.RATE_LIMITED
    if "timeout" in name or "transport" in name or "connection" in name:
        return AgentExecutionErrorClass.TRANSPORT_ERROR
    return AgentExecutionErrorClass.PROVIDER_ERROR


__all__ = ["AgentExecutionGateway"]
