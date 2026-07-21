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
    AGENT_RUNTIME_LANE,
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentExecutionCancelled,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentExecutionResult,
    AgentExecutionResultAudit,
    AgentExecutionStatus,
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
class _RuntimeState:
    capacity: _CapacityGate
    capacity_denied_total: int = 0
    circuit_open_total: int = 0
    timeout_total: int = 0
    provider_running_count: int = 0
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

    def reserve_up_to(self, requested_units: int) -> int:
        self._leak()
        available_units = int(max(self.max_rate - self.level, 0.0))
        reserved_units = max(0, min(requested_units, available_units))
        self.level += float(reserved_units)
        return reserved_units

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


class AgentExecutionGateway:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        policy: AgentRuntimePolicy,
        telemetry: Any | None = None,
    ) -> None:
        self._base_url = _model_base(base_url)
        self._policy = policy
        self._telemetry = telemetry
        self._json_object_strategy = ChatJsonObjectStrategy(
            api_key=str(api_key or "").strip(),
            base_url=self._base_url,
        )
        self._reservation_owner_token = object()
        self._state = _RuntimeState(
            capacity=_CapacityGate(policy.max_concurrency),
        )
        self._rpm_limiter = _RateLimitState(float(policy.rpm_limit), 60.0)

    def request_audit(self, stage: AgentStageSpec) -> AgentExecutionRequestAudit:
        model_name = self.model
        capability_profile = self._policy.capability_profile()
        request_options_hash = json_sha256(capability_profile.request_options)
        artifact_version_hash = self.artifact_version_hash(
            output_type=stage.output_type,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            instructions=stage.instructions,
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

    def artifact_version_hash(
        self,
        *,
        output_type: type[Any],
        prompt_version: str,
        schema_version: str,
        instructions: str,
    ) -> str:
        capability_profile = self._policy.capability_profile()
        return artifact_hash_for(
            model=self.model,
            provider_family=capability_profile.provider_family.value,
            output_strategy="json_object",
            schema_enforcement="client_validate",
            request_options_hash=json_sha256(capability_profile.request_options),
            prompt_version=prompt_version,
            schema_version=schema_version,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(StrictJsonOutputSchema(output_type).json_schema()),
            prompt_text_hash=text_sha256(instructions),
        )

    @property
    def model(self) -> str:
        return self._policy.model

    def try_reserve(
        self,
        *,
        rate_units: int = 1,
    ) -> AgentCapacityReservation:
        rate_unit_count = require_positive_int(
            rate_units,
            error_code="agent_execution_rate_units_required",
        )
        state = self._state
        if self._is_circuit_open():
            state.circuit_open_total += 1
            self._record_backpressure(AgentExecutionErrorClass.CIRCUIT_OPEN)
            return AgentCapacityReservation(
                acquired=False,
                reason=AgentExecutionErrorClass.CIRCUIT_OPEN,
                rate_units=rate_unit_count,
            )
        if not state.capacity.try_acquire():
            state.capacity_denied_total += 1
            self._record_backpressure(AgentExecutionErrorClass.CAPACITY_DENIED)
            return AgentCapacityReservation(
                acquired=False,
                reason=AgentExecutionErrorClass.CAPACITY_DENIED,
                rate_units=rate_unit_count,
            )
        acquired_at = time.monotonic()
        state.in_flight_started_at.append(acquired_at)

        reserved_rate_units = self._rpm_limiter.reserve_up_to(rate_unit_count)
        if reserved_rate_units <= 0:
            _release_capacity(state, acquired_at)
            self._record_backpressure(AgentExecutionErrorClass.RATE_LIMITED)
            return AgentCapacityReservation(
                acquired=False,
                reason=AgentExecutionErrorClass.RATE_LIMITED,
                rate_units=rate_unit_count,
            )

        released = False

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            _release_capacity(state, acquired_at)

        return AgentCapacityReservation(
            acquired=True,
            rate_units=reserved_rate_units,
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
        state = self._state
        release_reservation = reservation is None
        if reservation is not None:
            self._validate_external_reservation(stage, reservation)
        else:
            reservation = self.try_reserve()

        if not reservation.acquired:
            error_class = reservation.reason or AgentExecutionErrorClass.CAPACITY_DENIED
            raise AgentExecutionError(
                error_class,
                "agent execution unavailable",
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
                    timeout=float(self._policy.timeout_seconds),
                )
            except TimeoutError as exc:
                runner_entered["value"] = True
                state.timeout_total += 1
                state.last_timeout_at_ms = _epoch_ms()
                self.record_failure()
                failed = self._failed_audit(
                    audit,
                    started=started,
                    error_class=AgentExecutionErrorClass.TIMEOUT,
                    message=f"agent execution timed out after {self._policy.timeout_seconds:g}s",
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
            self.record_failure()
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
                self.open_circuit()
            else:
                self.record_failure()
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

    def record_failure(self) -> None:
        now = time.monotonic()
        state = self._state
        breaker = self._policy.circuit_breaker
        window_start = now - float(breaker.window_seconds)
        state.failure_timestamps = [stamp for stamp in state.failure_timestamps if stamp >= window_start]
        state.failure_timestamps.append(now)
        if len(state.failure_timestamps) >= breaker.failure_threshold:
            state.circuit_open_until = now + float(breaker.open_seconds)

    def open_circuit(self) -> None:
        now = time.monotonic()
        state = self._state
        breaker = self._policy.circuit_breaker
        state.failure_timestamps.append(now)
        state.circuit_open_until = max(
            state.circuit_open_until,
            now + float(breaker.open_seconds),
        )

    def status_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        state = self._state
        capability_profile = self._policy.capability_profile()
        return {
            "lane": AGENT_RUNTIME_LANE,
            "model": self.model,
            "provider_family": capability_profile.provider_family.value,
            "output_strategy": "json_object",
            "schema_enforcement": "client_validate",
            "max_concurrency": self._policy.max_concurrency,
            "rpm_limit": self._policy.rpm_limit,
            "timeout_seconds": float(self._policy.timeout_seconds),
            "in_flight": state.capacity.in_flight,
            "provider_running": state.provider_running_count,
            "circuit_state": "open" if state.circuit_open_until > now else "closed",
            "circuit_open_until_ms": _monotonic_deadline_to_epoch_ms(state.circuit_open_until),
            "capacity_denied_total": state.capacity_denied_total,
            "circuit_open_total": state.circuit_open_total,
            "timeout_total": state.timeout_total,
            "last_denied_at_ms": state.last_denied_at_ms,
            "last_timeout_at_ms": state.last_timeout_at_ms,
            "oldest_in_flight_age_ms": _oldest_in_flight_age_ms(state, now=now),
        }

    async def _run_stage(
        self,
        stage: AgentStageSpec,
        audit: AgentExecutionRequestAudit,
        *,
        runner_entered: dict[str, bool],
    ) -> tuple[Any, Any | None, dict[str, Any]]:
        model_name = self.model
        capability_profile = self._policy.capability_profile()
        runner_entered["value"] = True
        outcome = await self._json_object_strategy.run(
            StructuredOutputContext(
                stage=stage,
                model_name=model_name,
                timeout_seconds=float(self._policy.timeout_seconds),
                capability_profile=capability_profile,
            )
        )
        return outcome.final_output, outcome.raw_result, dict(outcome.audit_extra)

    def _is_circuit_open(self) -> bool:
        return self._state.circuit_open_until > time.monotonic()

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
            trace_metadata={**audit.trace_metadata, **_audit_trace_extra(audit_extra)},
            error_class=error_class,
            error_message=str(message or "")[:1000],
        )

    def _validate_external_reservation(
        self,
        _stage: AgentStageSpec,
        reservation: AgentCapacityReservation,
    ) -> None:
        if not reservation.acquired:
            raise ValueError("execute requires an active acquired reservation")
        if reservation._owner_token is not self._reservation_owner_token:
            raise ValueError("reservation was not issued by this gateway")
        if not reservation.active:
            raise ValueError("execute requires an active acquired reservation")

    def _record_provider_running(self, stage: AgentStageSpec, *, delta: int) -> None:
        self._state.provider_running_count = max(0, self._state.provider_running_count + delta)
        telemetry = self._telemetry
        if telemetry is None:
            return
        method_name = "increment_agent_execution_in_flight" if delta > 0 else "decrement_agent_execution_in_flight"
        method = getattr(telemetry, method_name, None)
        if callable(method):
            method(lane=stage.lane, stage=stage.stage)

    def _record_backpressure(self, reason: AgentExecutionErrorClass) -> None:
        self._state.last_denied_at_ms = _epoch_ms()
        telemetry = self._telemetry
        method = getattr(telemetry, "record_agent_execution_backpressure", None)
        if callable(method):
            method(lane=AGENT_RUNTIME_LANE, reason=str(reason.value))

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
                model=self.model,
                status=str(status.value),
                error_class=error_class.value if error_class is not None else None,
                seconds=max(0.0, time.perf_counter() - started),
            )


def _model_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    return value


def _audit_base(audit: AgentExecutionRequestAudit) -> dict[str, Any]:
    return audit.model_dump(
        exclude={
            "status",
            "execution_started",
            "latency_ms",
            "usage",
            "parse_mode",
            "trace_metadata",
            "output_hash",
            "error_class",
            "error_message",
        }
    )


def _remove_in_flight_start(state: _RuntimeState, acquired_at: float) -> None:
    try:
        state.in_flight_started_at.remove(acquired_at)
    except ValueError:
        return


def _release_capacity(state: _RuntimeState, acquired_at: float) -> None:
    _remove_in_flight_start(state, acquired_at)
    state.capacity.release()


def _oldest_in_flight_age_ms(state: _RuntimeState, *, now: float) -> float | None:
    if not state.in_flight_started_at:
        return None
    return max(0.0, (now - min(state.in_flight_started_at)) * 1000)


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


def _audit_trace_extra(audit_extra: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in audit_extra.items() if key in {"parse_mode", "schema_enforcement"}}


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
