from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gmgn_twitter_intel.platform.agent_hashing import json_sha256

RUNTIME_VERSION = "agent-execution-plane-v1"


class AgentExecutionErrorClass(StrEnum):
    CAPACITY_DENIED = "capacity_denied"
    CIRCUIT_OPEN = "circuit_open"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
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

    priority: str = "normal"
    max_concurrency: int = Field(default=1, ge=1)
    timeout_seconds: float = Field(default=120.0, ge=1)
    rpm_limit: int | None = Field(default=None, ge=1)
    circuit_breaker: AgentCircuitBreakerPolicy = Field(default_factory=AgentCircuitBreakerPolicy)


class AgentRuntimePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_max_concurrency: int = Field(default=4, ge=1)
    global_rpm_limit: int = Field(default=60, ge=1)
    lanes: dict[str, AgentLanePolicy] = Field(default_factory=dict)

    def lane_for(self, lane: str) -> AgentLanePolicy:
        return self.lanes.get(str(lane), AgentLanePolicy())


class AgentStageSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    lane: str
    stage: str
    model: str
    instructions: str
    input_payload: Any
    output_type: Any
    prompt_version: str
    schema_version: str
    workflow_name: str
    agent_name: str
    group_id: str = ""
    trace_metadata: dict[str, Any] = Field(default_factory=dict)
    max_turns: int = Field(default=1, ge=1)
    tools: list[Any] = Field(default_factory=list)

    @property
    def input_hash(self) -> str:
        return json_sha256(self.input_payload)


class AgentExecutionRequestAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "openai"
    backend: str = "openai_agents_sdk"
    model: str
    lane: str
    stage: str
    workflow_name: str
    agent_name: str
    sdk_trace_id: str
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
    ) -> AgentExecutionRequestAudit:
        trace_metadata = {
            **stage.trace_metadata,
            "backend": "openai_agents_sdk",
            "model": stage.model,
            "lane": stage.lane,
            "stage": stage.stage,
            "prompt_version": stage.prompt_version,
            "schema_version": stage.schema_version,
            "runtime_version": RUNTIME_VERSION,
            "artifact_version_hash": artifact_version_hash,
            "input_hash": stage.input_hash,
        }
        return cls(
            model=stage.model,
            lane=stage.lane,
            stage=stage.stage,
            workflow_name=stage.workflow_name,
            agent_name=stage.agent_name,
            sdk_trace_id=trace_id,
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


ReleaseCallback = Callable[[], None | Awaitable[None]]


@dataclass(slots=True)
class AgentCapacityReservation:
    lane: str
    acquired: bool
    reason: AgentExecutionErrorClass | None = None
    owns_global: bool = True
    child_lanes: tuple[str, ...] = ()
    scope: str = "execution"
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
    "AgentCapacityReservation",
    "AgentCircuitBreakerPolicy",
    "AgentExecutionError",
    "AgentExecutionErrorClass",
    "AgentExecutionRequestAudit",
    "AgentExecutionResult",
    "AgentExecutionResultAudit",
    "AgentExecutionStatus",
    "AgentLanePolicy",
    "AgentRuntimePolicy",
    "AgentStageSpec",
]
