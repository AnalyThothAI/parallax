from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from parallax.integrations.model_execution.output_schema import StrictJsonOutputSchema
from parallax.integrations.model_execution.structured_json_strategy import (
    ChatJsonObjectStrategy,
    StructuredOutputContext,
)
from parallax.integrations.model_execution.usage import extract_model_usage
from parallax.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentExecutionCancelled,
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
from parallax.platform.agent_hashing import (
    artifact_hash_for,
    json_sha256,
    text_sha256,
    trace_id_for,
)
from parallax.platform.cancellation import cancellation_reason
from parallax.platform.validation import require_positive_int


@dataclass(slots=True)
class _LaneState:
    policy: AgentLanePolicy
    capacity: _CapacityGate
    capacity_denied_total: int = 0
    circuit_open_total: int = 0
    timeout_total: int = 0
    provider_running_count: int = 0
    rpm_waiting_count: int = 0
    last_denied_at_ms: int | None = None
    last_timeout_at_ms: int | None = None
    in_flight_started_at: list[float] = field(default_factory=list)
    failure_timestamps: list[float] = field(default_factory=list)
    circuit_open_until: float = 0


@dataclass(slots=True)
class _RateLimitState:
    max_rate: float
    time_period: float = 60.0
    level: float = 0.0
    last_check: float = field(default_factory=time.monotonic)

    def has_capacity(self, amount: float = 1.0) -> bool:
        self._leak()
        return self.level + amount <= self.max_rate

    def capacity_remaining(self) -> float:
        self._leak()
        return max(self.max_rate - self.level, 0.0)

    def acquire_nowait(self, amount: float = 1.0) -> bool:
        if not self.has_capacity(amount):
            return False
        self.level += amount
        return True

    def _leak(self) -> None:
        now = time.monotonic()
        if self.level:
            elapsed = max(0.0, now - self.last_check)
            decrement = elapsed * (self.max_rate / self.time_period)
            self.level = max(self.level - decrement, 0.0)
        self.last_check = now


@dataclass(slots=True)
class _CapacityGate:
    limit: int
    in_flight: int = 0

    def try_acquire(self) -> bool:
        if self.in_flight >= self.limit:
            return False
        self.in_flight += 1
        return True

    def release(self) -> None:
        if self.in_flight <= 0:
            raise RuntimeError("agent_capacity_release_without_reservation")
        self.in_flight -= 1


@dataclass(slots=True)
class _RateLimitReservationResult:
    reserved_units: int
    denied_lane: str = ""
    denied_reason: AgentExecutionErrorClass | None = None


_LLM_GATEWAY_FIELD_ERRORS = {
    "api_key": "agent_execution_llm_gateway_api_key_required",
    "base_url": "agent_execution_llm_gateway_base_url_required",
    "trace_export_enabled": "agent_execution_llm_gateway_trace_export_enabled_required",
}


class AgentExecutionGateway:
    def __init__(
        self,
        *,
        llm_gateway: Any,
        base_url: str,
        trace_enabled: bool,
        trace_include_sensitive_data: bool,
        policy: AgentRuntimePolicy,
        telemetry: Any | None = None,
    ) -> None:
        if llm_gateway is None:
            raise ValueError("llm_gateway is required")
        self._llm_gateway = llm_gateway
        self._base_url = _model_base(base_url)
        llm_api_key = _llm_gateway_text(llm_gateway, "api_key")
        llm_base_url = _llm_gateway_text(llm_gateway, "base_url")
        trace_export_enabled = _llm_gateway_bool(llm_gateway, "trace_export_enabled")
        self._trace_enabled = bool(trace_enabled and trace_export_enabled)
        self._trace_include_sensitive_data = bool(trace_include_sensitive_data)
        self._policy = policy
        self._telemetry = telemetry
        self._json_object_strategy = ChatJsonObjectStrategy(
            api_key=llm_api_key,
            base_url=self._base_url or llm_base_url,
        )
        self._reservation_owner_token = object()
        self._global_capacity = _CapacityGate(policy.global_max_concurrency)
        self._global_limiter = _RateLimitState(float(policy.global_rpm_limit), 60.0)
        self._lane_limiters = {
            lane: _RateLimitState(float(lane_policy.rpm_limit), 60.0)
            for lane, lane_policy in policy.lanes.items()
            if lane_policy.rpm_limit is not None
        }
        self._lanes: dict[str, _LaneState] = {
            lane: _LaneState(
                policy=lane_policy,
                capacity=_CapacityGate(lane_policy.max_concurrency),
            )
            for lane, lane_policy in policy.lanes.items()
        }

    def request_audit(self, stage: AgentStageSpec) -> AgentExecutionRequestAudit:
        model_name = self.model_for_lane(stage.lane)
        capability_profile = self._policy.capability_for_lane(stage.lane)
        request_options_hash = json_sha256(capability_profile.request_options)
        output_schema = StrictJsonOutputSchema(stage.output_type)
        artifact_version_hash = artifact_hash_for(
            model=model_name,
            provider_family=capability_profile.provider_family.value,
            output_strategy="json_object",
            schema_enforcement="client_validate",
            request_options_hash=request_options_hash,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(output_schema.json_schema()),
            prompt_text_hash=text_sha256(stage.instructions),
        )
        trace_source = json_sha256(
            {
                "lane": stage.lane,
                "stage": stage.stage,
                "model": model_name,
                "provider_family": capability_profile.provider_family.value,
                "output_strategy": "json_object",
                "schema_enforcement": "client_validate",
                "request_options_hash": request_options_hash,
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
            model=model_name,
            capability_profile=capability_profile,
        )

    def model_for_lane(self, lane: str) -> str:
        model_name = self._policy.model_for_lane(lane)
        if not model_name:
            raise ValueError(f"agent model is required for lane: {lane}")
        return model_name

    def try_reserve(
        self,
        lane: str,
        *,
        rate_units: int = 1,
    ) -> AgentCapacityReservation:
        lane_key = str(lane)
        rate_unit_count = require_positive_int(
            rate_units,
            error_code="agent_execution_rate_units_required",
        )
        lane_state = self._lane_state(lane_key)
        if self._is_circuit_open(lane_key, lane_state):
            lane_state.circuit_open_total += 1
            self._record_backpressure(lane_key, AgentExecutionErrorClass.CIRCUIT_OPEN)
            return AgentCapacityReservation(
                lane=lane_key,
                acquired=False,
                reason=AgentExecutionErrorClass.CIRCUIT_OPEN,
                rate_units=rate_unit_count,
            )
        if not self._global_capacity.try_acquire():
            lane_state.capacity_denied_total += 1
            self._record_backpressure(lane_key, AgentExecutionErrorClass.CAPACITY_DENIED)
            return AgentCapacityReservation(
                lane=lane_key,
                acquired=False,
                reason=AgentExecutionErrorClass.CAPACITY_DENIED,
                rate_units=rate_unit_count,
            )

        if not lane_state.capacity.try_acquire():
            self._global_capacity.release()
            lane_state.capacity_denied_total += 1
            self._record_backpressure(lane_key, AgentExecutionErrorClass.CAPACITY_DENIED)
            return AgentCapacityReservation(
                lane=lane_key,
                acquired=False,
                reason=AgentExecutionErrorClass.CAPACITY_DENIED,
                rate_units=rate_unit_count,
            )
        acquired_at = time.monotonic()
        lane_state.in_flight_started_at.append(acquired_at)
        acquired_lanes = [(lane_key, lane_state, acquired_at)]

        rate_limit_result = self._try_acquire_rate_limits((lane_key,), requested_rate_units=rate_unit_count)
        if rate_limit_result.denied_reason is not None:
            self._release_acquired_lane_capacity(acquired_lanes)
            self._global_capacity.release()
            self._record_backpressure(rate_limit_result.denied_lane, rate_limit_result.denied_reason)
            return AgentCapacityReservation(
                lane=lane_key,
                acquired=False,
                reason=rate_limit_result.denied_reason,
                rate_units=rate_unit_count,
            )

        released = False

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            self._release_acquired_lane_capacity(acquired_lanes)
            self._global_capacity.release()

        return AgentCapacityReservation(
            lane=lane_key,
            acquired=True,
            rate_units=rate_limit_result.reserved_units,
            _release=release,
            _owner_token=self._reservation_owner_token,
        )

    async def execute(
        self,
        stage: AgentStageSpec,
        *,
        reservation: AgentCapacityReservation | None = None,
    ) -> AgentExecutionResult:
        audit = self.request_audit(stage)
        lane_state = self._lane_state(stage.lane)
        release_reservation = reservation is None
        if reservation is not None:
            self._validate_external_reservation(stage, reservation)
        else:
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
        provider_running_recorded = False
        try:
            self._record_provider_running(stage, delta=1)
            provider_running_recorded = True
            try:
                final_output, raw_result, audit_extra = await asyncio.wait_for(
                    self._run_stage(stage, audit, runner_entered=runner_entered),
                    timeout=float(lane_state.policy.timeout_seconds),
                )
            except TimeoutError as exc:
                runner_entered["value"] = True
                lane_state.timeout_total += 1
                lane_state.last_timeout_at_ms = _epoch_ms()
                self.record_lane_failure(stage.lane)
                failed = self._failed_audit(
                    audit,
                    started=started,
                    error_class=AgentExecutionErrorClass.TIMEOUT,
                    message=f"agent lane timed out after {lane_state.policy.timeout_seconds:g}s",
                    execution_started=True,
                )
                self._record_execution_call(
                    stage,
                    status=failed.status,
                    error_class=failed.error_class,
                    started=started,
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
                usage=dict(audit_extra.get("usage") or extract_model_usage(raw_result)),
                parse_mode=str(audit_extra.get("parse_mode") or "strict"),
                safety_net={
                    "safety_net_used": bool(audit_extra.get("safety_net_used", False)),
                    "safety_net_retries": _safety_net_retries(audit_extra),
                },
                trace_metadata={**audit.trace_metadata, **_audit_trace_extra(audit_extra)},
                output_hash=json_sha256(final_output),
            )
            self._record_execution_call(
                stage,
                status=result_audit.status,
                error_class=result_audit.error_class,
                started=started,
            )
            return AgentExecutionResult(final_output=final_output, audit=result_audit, raw_result=raw_result)
        except asyncio.CancelledError as exc:
            execution_started = runner_entered["value"]
            failed = self._failed_audit(
                audit,
                started=started,
                error_class=AgentExecutionErrorClass.CANCELLED,
                message="agent execution cancelled",
                execution_started=execution_started,
            )
            self._record_execution_call(
                stage,
                status=failed.status,
                error_class=failed.error_class,
                started=started,
            )
            raise AgentExecutionCancelled(
                failed.error_message or "agent execution cancelled",
                audit=failed,
                execution_started=execution_started,
                cancellation_reason=cancellation_reason(exc),
            ) from exc
        except AgentExecutionError:
            raise
        except (ValidationError, ValueError) as exc:
            self.record_lane_failure(stage.lane)
            failed = self._failed_audit(
                audit,
                started=started,
                error_class=AgentExecutionErrorClass.SCHEMA_INVALID,
                message=str(exc),
                execution_started=True,
            )
            self._record_execution_call(
                stage,
                status=failed.status,
                error_class=failed.error_class,
                started=started,
            )
            raise AgentExecutionError(
                AgentExecutionErrorClass.SCHEMA_INVALID,
                str(exc),
                audit=failed,
                execution_started=True,
            ) from exc
        except Exception as exc:
            error_class = _classify_provider_error(exc)
            execution_started = error_class not in {AgentExecutionErrorClass.QUOTA_EXHAUSTED}
            if error_class is AgentExecutionErrorClass.QUOTA_EXHAUSTED:
                self.open_lane_circuit(stage.lane)
            else:
                self.record_lane_failure(stage.lane)
            failed = self._failed_audit(
                audit,
                started=started,
                error_class=error_class,
                message=str(exc),
                execution_started=execution_started,
            )
            self._record_execution_call(
                stage,
                status=failed.status,
                error_class=failed.error_class,
                started=started,
            )
            raise AgentExecutionError(
                error_class,
                str(exc),
                audit=failed,
                execution_started=execution_started,
            ) from exc
        finally:
            if provider_running_recorded:
                self._record_provider_running(stage, delta=-1)
            if release_reservation:
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

    def open_lane_circuit(self, lane: str) -> None:
        now = time.monotonic()
        lane_state = self._lane_state(lane)
        breaker = lane_state.policy.circuit_breaker
        lane_state.failure_timestamps.append(now)
        lane_state.circuit_open_until = max(
            lane_state.circuit_open_until,
            now + float(breaker.open_seconds),
        )

    def status_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        lanes: dict[str, Any] = {}
        for lane, lane_state in self._lanes.items():
            capability_profile = self._policy.capability_for_lane(lane)
            lanes[lane] = {
                "model": self.model_for_lane(lane),
                "provider_family": capability_profile.provider_family.value,
                "output_strategy": "json_object",
                "schema_enforcement": "client_validate",
                "priority_label": lane_state.policy.priority,
                "rpm_limit": lane_state.policy.rpm_limit,
                "max_concurrency": lane_state.policy.max_concurrency,
                "timeout_seconds": float(lane_state.policy.timeout_seconds),
                "in_flight": lane_state.capacity.in_flight,
                "provider_running": lane_state.provider_running_count,
                "rpm_waiting_count": lane_state.rpm_waiting_count,
                "circuit_state": "open" if lane_state.circuit_open_until > now else "closed",
                "circuit_open_until_ms": _monotonic_deadline_to_epoch_ms(lane_state.circuit_open_until),
                "capacity_denied_total": lane_state.capacity_denied_total,
                "circuit_open_total": lane_state.circuit_open_total,
                "timeout_total": lane_state.timeout_total,
                "last_denied_at_ms": lane_state.last_denied_at_ms,
                "last_timeout_at_ms": lane_state.last_timeout_at_ms,
                "oldest_in_flight_age_ms": _oldest_in_flight_age_ms(lane_state, now=now),
            }
        return {
            "global_max_concurrency": self._policy.global_max_concurrency,
            "global_rpm_limit": self._policy.global_rpm_limit,
            "global_in_flight": self._global_capacity.in_flight,
            "lanes": lanes,
        }

    async def aclose(self) -> None:
        return None

    async def _run_stage(
        self,
        stage: AgentStageSpec,
        audit: AgentExecutionRequestAudit,
        *,
        runner_entered: dict[str, bool],
    ) -> tuple[Any, Any | None, dict[str, Any]]:
        lane_policy = self._lane_state(stage.lane).policy
        model_name = self.model_for_lane(stage.lane)
        capability_profile = self._policy.capability_for_lane(stage.lane)
        runner_entered["value"] = True
        outcome = await self._json_object_strategy.run(
            StructuredOutputContext(
                stage=stage,
                model_name=model_name,
                timeout_seconds=float(lane_policy.timeout_seconds),
                capability_profile=capability_profile,
            )
        )
        return outcome.final_output, outcome.raw_result, dict(outcome.audit_extra)

    def _lane_state(self, lane: str) -> _LaneState:
        lane_key = str(lane)
        state = self._lanes.get(lane_key)
        if state is None:
            lane_policy = self._policy.lane_for(lane_key)
            state = _LaneState(
                policy=lane_policy,
                capacity=_CapacityGate(lane_policy.max_concurrency),
            )
            self._lanes[lane_key] = state
        return state

    def _try_acquire_rate_limits(
        self,
        lanes: tuple[str, ...],
        *,
        requested_rate_units: int,
    ) -> _RateLimitReservationResult:
        lane_keys = _unique_lanes(lanes)
        reserved_units = self._reservable_rate_units(lane_keys, requested_rate_units=requested_rate_units)
        if reserved_units <= 0:
            return _RateLimitReservationResult(
                reserved_units=0,
                denied_lane=lane_keys[0] if lane_keys else "",
                denied_reason=AgentExecutionErrorClass.RATE_LIMITED,
            )
        tokens_per_lane = float(reserved_units)
        required_global_tokens = float(max(1, len(lane_keys))) * tokens_per_lane
        if not self._global_limiter.has_capacity(required_global_tokens):
            return _RateLimitReservationResult(
                reserved_units=0,
                denied_lane=lane_keys[0] if lane_keys else "",
                denied_reason=AgentExecutionErrorClass.RATE_LIMITED,
            )
        for lane in lane_keys:
            lane_limiter = self._lane_limiters.get(lane)
            if lane_limiter is not None and not lane_limiter.has_capacity(tokens_per_lane):
                return _RateLimitReservationResult(
                    reserved_units=0,
                    denied_lane=lane,
                    denied_reason=AgentExecutionErrorClass.RATE_LIMITED,
                )
        if not self._global_limiter.acquire_nowait(required_global_tokens):
            return _RateLimitReservationResult(
                reserved_units=0,
                denied_lane=lane_keys[0] if lane_keys else "",
                denied_reason=AgentExecutionErrorClass.RATE_LIMITED,
            )
        for lane in lane_keys:
            lane_limiter = self._lane_limiters.get(lane)
            if lane_limiter is not None and not lane_limiter.acquire_nowait(tokens_per_lane):
                raise RuntimeError(f"agent_rate_limit_reservation_race:{lane}")
        return _RateLimitReservationResult(reserved_units=reserved_units)

    def _reservable_rate_units(self, lanes: tuple[str, ...], *, requested_rate_units: int) -> int:
        lane_count = max(1, len(lanes))
        requested_units = require_positive_int(
            requested_rate_units,
            error_code="agent_execution_rate_units_required",
        )
        reservable = min(requested_units, int(self._global_limiter.capacity_remaining() // lane_count))
        for lane in lanes:
            lane_limiter = self._lane_limiters.get(lane)
            if lane_limiter is not None:
                reservable = min(reservable, int(lane_limiter.capacity_remaining()))
        return max(0, reservable)

    def _release_acquired_lane_capacity(
        self,
        acquired_lanes: list[tuple[str, _LaneState, float]],
    ) -> None:
        for _lane, lane_state, acquired_at in reversed(acquired_lanes):
            _remove_in_flight_start(lane_state, acquired_at)
            lane_state.capacity.release()
        acquired_lanes.clear()

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
                "safety_net_retries": _safety_net_retries(audit_extra),
            },
            trace_metadata={**audit.trace_metadata, **_audit_trace_extra(audit_extra)},
            error_class=error_class,
            error_message=str(message or "")[:1000],
        )

    def _validate_external_reservation(
        self,
        stage: AgentStageSpec,
        reservation: AgentCapacityReservation,
    ) -> None:
        if reservation.lane != stage.lane:
            raise ValueError(f"reservation lane {reservation.lane!r} does not match stage lane {stage.lane!r}")
        if not reservation.acquired:
            raise ValueError("execute requires an active acquired reservation")
        if reservation._owner_token is not self._reservation_owner_token:
            raise ValueError("reservation was not issued by this gateway")
        if not reservation.active:
            raise ValueError("execute requires an active acquired reservation")

    def _record_provider_running(self, stage: AgentStageSpec, *, delta: int) -> None:
        lane_state = self._lane_state(stage.lane)
        lane_state.provider_running_count = max(0, lane_state.provider_running_count + delta)
        telemetry = self._telemetry
        if telemetry is None:
            return
        method_name = "increment_agent_execution_in_flight" if delta > 0 else "decrement_agent_execution_in_flight"
        method = getattr(telemetry, method_name, None)
        if callable(method):
            method(lane=stage.lane, stage=stage.stage)

    def _record_backpressure(self, lane: str, reason: AgentExecutionErrorClass) -> None:
        lane_state = self._lane_state(lane)
        lane_state.last_denied_at_ms = _epoch_ms()
        telemetry = self._telemetry
        method = getattr(telemetry, "record_agent_execution_backpressure", None)
        if callable(method):
            method(lane=lane, reason=str(reason.value))

    def _record_execution_call(
        self,
        stage: AgentStageSpec,
        *,
        status: AgentExecutionStatus,
        error_class: AgentExecutionErrorClass | None,
        started: float,
    ) -> None:
        telemetry = self._telemetry
        method = getattr(telemetry, "record_agent_execution_call", None)
        if callable(method):
            method(
                lane=stage.lane,
                stage=stage.stage,
                model=self.model_for_lane(stage.lane),
                status=str(status.value),
                error_class=error_class.value if error_class is not None else None,
                seconds=max(0.0, time.perf_counter() - started),
            )


def _model_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    return value


def _llm_gateway_text(llm_gateway: Any, field_name: str) -> str:
    error_code = _llm_gateway_field_error(field_name)
    try:
        value = getattr(llm_gateway, field_name)
    except AttributeError as exc:
        raise ValueError(error_code) from exc
    if not isinstance(value, str):
        raise ValueError(error_code)
    return value.strip()


def _llm_gateway_bool(llm_gateway: Any, field_name: str) -> bool:
    error_code = _llm_gateway_field_error(field_name)
    try:
        value = getattr(llm_gateway, field_name)
    except AttributeError as exc:
        raise ValueError(error_code) from exc
    if not isinstance(value, bool):
        raise ValueError(error_code)
    return value


def _llm_gateway_field_error(field_name: str) -> str:
    try:
        return _LLM_GATEWAY_FIELD_ERRORS[field_name]
    except KeyError as exc:
        raise ValueError("agent_execution_llm_gateway_unknown_field") from exc


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


def _unique_lanes(lanes: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(lane) for lane in lanes if str(lane).strip()))


def _remove_in_flight_start(lane_state: _LaneState, acquired_at: float) -> None:
    try:
        lane_state.in_flight_started_at.remove(acquired_at)
    except ValueError:
        return


def _oldest_in_flight_age_ms(lane_state: _LaneState, *, now: float) -> float | None:
    if not lane_state.in_flight_started_at:
        return None
    return max(0.0, (now - min(lane_state.in_flight_started_at)) * 1000)


def _epoch_ms() -> int:
    return int(time.time() * 1000)


def _monotonic_deadline_to_epoch_ms(deadline: float) -> int | None:
    if deadline <= 0:
        return None
    now = time.monotonic()
    if deadline <= now:
        return None
    return int(time.time() * 1000 + (deadline - now) * 1000)


def _latency_ms(started: float) -> float:
    return max(0.0, (time.perf_counter() - started) * 1000)


def _safety_net_retries(audit_extra: dict[str, Any]) -> int:
    if "safety_net_retries" not in audit_extra:
        return 0
    value = audit_extra["safety_net_retries"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("agent_execution_safety_net_retries_required")
    return int(value)


def _audit_trace_extra(audit_extra: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in audit_extra.items()
        if key in {"safety_net_used", "safety_net_retries", "parse_mode", "schema_enforcement"}
    }


def _classify_provider_error(exc: Exception) -> AgentExecutionErrorClass:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    text = f"{name} {message}"
    if "ratelimit" in text or "rate_limit" in text or "rate limit" in text:
        return AgentExecutionErrorClass.RATE_LIMITED
    if "timeout" in text or "transport" in text or "connection" in text:
        return AgentExecutionErrorClass.TRANSPORT_ERROR
    quota_markers = (
        "insufficient balance",
        "insufficient_quota",
        "quota",
        "quota exceeded",
        "quota_exceeded",
        "billing",
        "payment",
        "payment required",
        "402",
        "account balance",
        "no credit",
    )
    auth_markers = (
        "invalid api key",
        "unauthorized",
        "authentication",
        "permission denied",
        "401",
        "403",
    )
    config_markers = (
        "missing api key",
        "api key required",
        "credentials",
        "invalid credentials",
    )
    if any(marker in text for marker in (*quota_markers, *auth_markers, *config_markers)):
        return AgentExecutionErrorClass.QUOTA_EXHAUSTED
    return AgentExecutionErrorClass.PROVIDER_ERROR


__all__ = ["AgentExecutionGateway"]
