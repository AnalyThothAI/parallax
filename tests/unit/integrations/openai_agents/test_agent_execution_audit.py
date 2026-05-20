from __future__ import annotations

import asyncio
import math

import pytest
from pydantic import BaseModel, ValidationError

from gmgn_twitter_intel.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentCircuitBreakerPolicy,
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
from gmgn_twitter_intel.platform.agent_hashing import (
    artifact_hash_for,
    json_sha256,
    text_sha256,
    trace_id_for,
)


class _HashPayload(BaseModel):
    name: str
    count: int


def test_hash_helpers_are_stable() -> None:
    assert json_sha256({"b": 2, "a": 1}) == json_sha256({"a": 1, "b": 2})
    assert text_sha256("alpha") == text_sha256("alpha")
    assert trace_id_for("run-1").startswith("trace_")
    assert len(trace_id_for("run-1", length=4)) == len("trace_") + 8
    assert artifact_hash_for(
        model="qwen3.6",
        prompt_version="p1",
        schema_version="s1",
        runtime_version="r1",
        output_schema_hash="schema-hash",
    ).startswith("sha256:")


def test_artifact_hash_changes_when_runtime_behavior_changes() -> None:
    base = artifact_hash_for(
        model="qwen3.6",
        prompt_version="p1",
        schema_version="s1",
        runtime_version="r1",
        output_schema_hash="schema-hash",
    )
    changed = artifact_hash_for(
        model="qwen3.6",
        prompt_version="p1",
        schema_version="s1",
        runtime_version="r2",
        output_schema_hash="schema-hash",
    )

    assert base != changed


def test_json_sha256_rejects_unsupported_objects_and_sets() -> None:
    with pytest.raises(TypeError):
        json_sha256(object())

    with pytest.raises(TypeError):
        json_sha256({"unsupported": {1, 2, 3}})


def test_json_sha256_rejects_nan_values() -> None:
    with pytest.raises(ValueError):
        json_sha256({"score": math.nan})


def test_json_sha256_handles_pydantic_model_payloads_explicitly() -> None:
    payload = _HashPayload(name="alpha", count=2)

    assert json_sha256(payload) == json_sha256({"name": "alpha", "count": 2})


def test_agent_stage_spec_request_audit_shape() -> None:
    spec = AgentStageSpec(
        lane="social.event_enrichment",
        stage="social_event",
        instructions="Return JSON.",
        input_payload={"event_id": "e1"},
        output_type=dict,
        prompt_version="p1",
        schema_version="s1",
        workflow_name="workflow",
        agent_name="agent",
        group_id="e1",
        trace_metadata={"event_id": "e1"},
    )
    audit = AgentExecutionRequestAudit.from_stage(
        spec,
        trace_id="trace_abc",
        artifact_version_hash="sha256:abc",
        model="qwen3.6",
    )

    assert audit.provider == "openai"
    assert audit.backend == "openai_agents_sdk"
    assert audit.lane == "social.event_enrichment"
    assert audit.stage == "social_event"
    assert audit.runtime_version == RUNTIME_VERSION
    assert audit.input_hash == json_sha256({"event_id": "e1"})
    assert audit.execution_started is False
    assert audit.status is AgentExecutionStatus.PLANNED
    assert audit.model_dump(mode="json")["status"] == "planned"
    assert audit.usage == {}
    assert audit.safety_net == {}
    assert audit.trace_metadata["event_id"] == "e1"
    assert audit.trace_metadata["artifact_version_hash"] == "sha256:abc"


def test_runtime_policy_uses_default_lane_when_missing() -> None:
    policy = AgentRuntimePolicy(
        global_max_concurrency=2,
        global_rpm_limit=30,
        lanes={"known": AgentLanePolicy(priority="high", max_concurrency=1, timeout_seconds=15)},
    )

    known = policy.lane_for("known")
    missing = policy.lane_for("missing")

    assert known.timeout_seconds == 15
    assert missing.timeout_seconds == 180
    assert policy.model_for_lane("known") == "qwen3.6"
    assert missing is not policy.lane_for("missing")
    assert AgentExecutionErrorClass.TIMEOUT.value == "timeout"


def test_policy_models_forbid_extra_fields_and_invalid_non_positive_values() -> None:
    for model, kwargs in (
        (AgentCircuitBreakerPolicy, {"failure_threshold": 0}),
        (AgentLanePolicy, {"max_concurrency": 0}),
        (AgentRuntimePolicy, {"global_rpm_limit": 0}),
        (AgentStageSpec, {"lane": "x", "unknown": True}),
    ):
        with pytest.raises(ValidationError):
            model(**kwargs)


def test_result_audit_and_result_keep_execution_facts_separate() -> None:
    audit = AgentExecutionResultAudit(
        model="qwen3.6",
        lane="lane",
        stage="stage",
        workflow_name="workflow",
        agent_name="agent",
        sdk_trace_id="trace_abc",
        group_id="g1",
        prompt_version="p1",
        schema_version="s1",
        artifact_version_hash="sha256:artifact",
        input_hash="sha256:input",
        output_hash="sha256:output",
        latency_ms=12.5,
        usage={"input_tokens": 10},
        status=AgentExecutionStatus.DONE,
        execution_started=True,
        error_class=AgentExecutionErrorClass.TIMEOUT,
    )
    result = AgentExecutionResult(final_output={"ok": True}, audit=audit, raw_result={"id": "r1"})

    assert result.audit.status is AgentExecutionStatus.DONE
    assert result.audit.error_class is AgentExecutionErrorClass.TIMEOUT
    assert result.audit.model_dump(mode="json")["status"] == "done"
    assert result.audit.model_dump(mode="json")["error_class"] == "timeout"
    assert result.audit.output_hash == "sha256:output"
    assert result.final_output == {"ok": True}


def test_audit_rejects_invalid_status_and_error_class() -> None:
    base = {
        "model": "qwen3.6",
        "lane": "lane",
        "stage": "stage",
        "workflow_name": "workflow",
        "agent_name": "agent",
        "sdk_trace_id": "trace_abc",
        "group_id": "g1",
        "prompt_version": "p1",
        "schema_version": "s1",
        "artifact_version_hash": "sha256:artifact",
        "input_hash": "sha256:input",
    }

    with pytest.raises(ValidationError):
        AgentExecutionResultAudit(**base, status="succeeded")

    with pytest.raises(ValidationError):
        AgentExecutionRequestAudit(**base, error_class="unknown")


def test_execution_error_carries_class_audit_and_started_flag() -> None:
    error = AgentExecutionError(
        AgentExecutionErrorClass.CIRCUIT_OPEN,
        "lane circuit is open",
        execution_started=False,
    )

    assert str(error) == "lane circuit is open"
    assert error.error_class is AgentExecutionErrorClass.CIRCUIT_OPEN
    assert error.audit is None
    assert error.execution_started is False


def test_capacity_reservation_release_is_idempotent() -> None:
    calls: list[str] = []
    reservation = AgentCapacityReservation(
        lane="lane",
        acquired=True,
        _release=lambda: calls.append("released"),
    )

    asyncio.run(reservation.release())
    asyncio.run(reservation.release())

    assert calls == ["released"]
    assert reservation.acquired is False
