from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from parallax.platform.agent_capabilities import (
    AgentCapabilityProfile,
    AgentProviderFamily,
    resolve_agent_capability_profile,
)
from parallax.platform.agent_hashing import json_sha256

RUNTIME_VERSION = "litellm-execution-plane-v1"
PULSE_DECISION_LANE = "pulse.decision"


class AgentExecutionErrorClass(StrEnum):
    CANCELLED = "cancelled"
    CAPACITY_DENIED = "capacity_denied"
    CIRCUIT_OPEN = "circuit_open"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    TRANSPORT_ERROR = "transport_error"
    PROVIDER_ERROR = "provider_error"
    SCHEMA_INVALID = "schema_invalid"
    DOMAIN_VALIDATION_FAILED = "domain_validation_failed"
    DETERMINISTIC_NO_INPUT = "deterministic_no_input"


class AgentExecutionStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentCircuitBreakerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_threshold: int = Field(default=5, ge=1)
    window_seconds: int = Field(default=300, ge=1)
    open_seconds: int = Field(default=120, ge=1)


class AgentLanePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    provider_family: AgentProviderFamily | None = None
    client_validation_retries: int | None = Field(default=None, ge=0)
    priority: str = "normal"
    max_concurrency: int = Field(default=1, ge=1)
    timeout_seconds: float = Field(default=180.0, ge=1)
    rpm_limit: int | None = Field(default=None, ge=1)
    circuit_breaker: AgentCircuitBreakerPolicy = Field(default_factory=AgentCircuitBreakerPolicy)

    @field_validator("model", mode="before")
    @classmethod
    def parse_optional_model(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class AgentRuntimeDefaultsPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "qwen3.6"
    provider_family: AgentProviderFamily | None = None
    client_validation_retries: int | None = Field(default=None, ge=0)
    disable_thinking: bool = True
    include_usage: bool = True

    @field_validator("model", mode="before")
    @classmethod
    def parse_model(cls, value: Any) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("agent_runtime.defaults.model is required")
        return normalized


class AgentRuntimePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: AgentRuntimeDefaultsPolicy = Field(default_factory=AgentRuntimeDefaultsPolicy)
    global_max_concurrency: int = Field(default=4, ge=1)
    global_rpm_limit: int = Field(default=60, ge=1)
    lanes: dict[str, AgentLanePolicy] = Field(default_factory=dict)

    def lane_for(self, lane: str) -> AgentLanePolicy:
        return self.lanes.get(str(lane), AgentLanePolicy())

    def model_for_lane(self, lane: str) -> str:
        lane_model = self.lane_for(lane).model
        return str(lane_model or self.defaults.model).strip()

    def capability_for_lane(self, lane: str) -> AgentCapabilityProfile:
        lane_policy = self.lane_for(lane)
        model = self.model_for_lane(lane)
        if _lane_has_capability_override(lane_policy):
            return resolve_agent_capability_profile(
                model=model,
                override=_capability_profile_from_parts(
                    provider_family=lane_policy.provider_family or self.defaults.provider_family,
                    client_validation_retries=_first_non_none(
                        lane_policy.client_validation_retries,
                        self.defaults.client_validation_retries,
                    ),
                ),
            )
        if _defaults_have_capability_override(self.defaults):
            return resolve_agent_capability_profile(
                model=model,
                override=_capability_profile_from_parts(
                    provider_family=self.defaults.provider_family,
                    client_validation_retries=self.defaults.client_validation_retries,
                ),
            )
        return resolve_agent_capability_profile(model=model)


class AgentStageSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    lane: str
    stage: str
    instructions: str
    input_payload: Any
    output_type: Any
    prompt_version: str
    schema_version: str
    workflow_name: str
    agent_name: str
    group_id: str = ""
    knowledge_refs: tuple[str, ...] = ()
    read_only_tool_refs: tuple[str, ...] = ()
    trace_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def input_hash(self) -> str:
        return json_sha256(self.input_payload)


class AgentExecutionRequestAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "litellm"
    backend: str = "litellm_sdk"
    provider_family: str = "litellm"
    output_strategy: str = "json_object"
    schema_enforcement: str = "client_validate"
    request_options_hash: str = Field(default_factory=lambda: json_sha256({}))
    model: str
    lane: str
    stage: str
    workflow_name: str
    agent_name: str
    execution_trace_id: str
    group_id: str
    prompt_version: str
    schema_version: str
    runtime_version: str = RUNTIME_VERSION
    artifact_version_hash: str
    input_hash: str
    output_hash: str | None = None
    latency_ms: float | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    parse_mode: str | None = None
    safety_net: dict[str, Any] = Field(default_factory=dict)
    trace_metadata: dict[str, Any] = Field(default_factory=dict)
    execution_started: bool = False
    status: AgentExecutionStatus = AgentExecutionStatus.PLANNED
    error_class: AgentExecutionErrorClass | None = None
    error_message: str | None = None

    @classmethod
    def from_stage(
        cls,
        stage: AgentStageSpec,
        *,
        trace_id: str,
        artifact_version_hash: str,
        model: str,
        capability_profile: AgentCapabilityProfile | None = None,
    ) -> AgentExecutionRequestAudit:
        profile = capability_profile or AgentCapabilityProfile()
        request_options_hash = json_sha256(profile.request_options)
        trace_metadata = {
            **stage.trace_metadata,
            "backend": "litellm_sdk",
            "model": model,
            "provider_family": profile.provider_family.value,
            "output_strategy": "json_object",
            "schema_enforcement": "client_validate",
            "request_options_hash": request_options_hash,
            "request_option_keys": profile.request_options.option_keys(),
            "lane": stage.lane,
            "stage": stage.stage,
            "prompt_version": stage.prompt_version,
            "schema_version": stage.schema_version,
            "runtime_version": RUNTIME_VERSION,
            "artifact_version_hash": artifact_version_hash,
            "input_hash": stage.input_hash,
            "knowledge_refs": stage.knowledge_refs,
            "read_only_tool_refs": stage.read_only_tool_refs,
        }
        return cls(
            provider_family=profile.provider_family.value,
            output_strategy="json_object",
            schema_enforcement="client_validate",
            request_options_hash=request_options_hash,
            model=model,
            lane=stage.lane,
            stage=stage.stage,
            workflow_name=stage.workflow_name,
            agent_name=stage.agent_name,
            execution_trace_id=trace_id,
            group_id=stage.group_id,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            artifact_version_hash=artifact_version_hash,
            input_hash=stage.input_hash,
            trace_metadata=trace_metadata,
        )


class AgentExecutionResultAudit(AgentExecutionRequestAudit):
    status: AgentExecutionStatus


class AgentExecutionResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    final_output: Any
    audit: AgentExecutionResultAudit
    raw_result: Any | None = None


class AgentExecutionError(Exception):
    def __init__(
        self,
        error_class: AgentExecutionErrorClass,
        message: str,
        *,
        audit: AgentExecutionRequestAudit | AgentExecutionResultAudit | None = None,
        execution_started: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.audit = audit
        self.execution_started = bool(execution_started)


class AgentExecutionCancelled(asyncio.CancelledError):
    def __init__(
        self,
        message: str = "agent execution cancelled",
        *,
        audit: AgentExecutionResultAudit | None = None,
        execution_started: bool = False,
        cancellation_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.audit = audit
        self.execution_started = bool(execution_started)
        self.cancellation_reason = cancellation_reason


ReleaseCallback = Callable[[], None | Awaitable[None]]


def _lane_has_capability_override(lane_policy: AgentLanePolicy) -> bool:
    return lane_policy.provider_family is not None or lane_policy.client_validation_retries is not None


def _defaults_have_capability_override(defaults: AgentRuntimeDefaultsPolicy) -> bool:
    return defaults.provider_family is not None or defaults.client_validation_retries is not None


def _capability_profile_from_parts(
    *,
    provider_family: AgentProviderFamily | None,
    client_validation_retries: int | None,
) -> AgentCapabilityProfile:
    payload: dict[str, Any] = {}
    if provider_family is not None:
        payload["provider_family"] = provider_family
    if client_validation_retries is not None:
        payload["client_validation_retries"] = client_validation_retries
    return AgentCapabilityProfile(**payload)


def _first_non_none(*values: int | None) -> int | None:
    for value in values:
        if value is not None:
            return value
    return None


@dataclass(slots=True)
class AgentCapacityReservation:
    lane: str
    acquired: bool
    reason: AgentExecutionErrorClass | None = None
    owns_global: bool = True
    child_lanes: tuple[str, ...] = ()
    scope: str = "execution"
    rate_units: int = 1
    _release: ReleaseCallback | None = None
    _owner_token: object | None = None

    @property
    def active(self) -> bool:
        return self.acquired and self._release is not None

    async def release(self) -> None:
        if self._release is None:
            self.acquired = False
            return
        release = self._release
        self._release = None
        self.acquired = False
        result = release()
        if result is not None:
            await result


__all__ = [
    "RUNTIME_VERSION",
    "AgentCapabilityProfile",
    "AgentCapacityReservation",
    "AgentCircuitBreakerPolicy",
    "AgentExecutionCancelled",
    "AgentExecutionError",
    "AgentExecutionErrorClass",
    "AgentExecutionRequestAudit",
    "AgentExecutionResult",
    "AgentExecutionResultAudit",
    "AgentExecutionStatus",
    "AgentLanePolicy",
    "AgentRuntimeDefaultsPolicy",
    "AgentRuntimePolicy",
    "AgentStageSpec",
]
