"""Execution gateway tests for the packet-only pulse decision client."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from parallax.domains.pulse_lab.interfaces import (
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
)
from parallax.domains.pulse_lab.services.agent_runtime import build_pulse_runtime_manifest
from parallax.domains.pulse_lab.services.prompt_loader import pulse_decision_prompt_text_hash
from parallax.domains.pulse_lab.services.pulse_decision_runtime import PulseDecisionRuntimeService
from parallax.domains.pulse_lab.types.agent_decision import FinalDecision, PulseStageFailure
from parallax.integrations.model_execution.output_schema import StrictJsonOutputSchema
from parallax.integrations.model_execution.pulse_decision_agent_client import LiteLLMPulseDecisionClient
from parallax.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentExecutionResult,
    AgentExecutionResultAudit,
    AgentExecutionStatus,
)
from parallax.platform.agent_hashing import artifact_hash_for, json_sha256


class _FakeAgentGateway:
    def __init__(self, outputs: dict[str, object] | None = None) -> None:
        self.outputs = outputs or {}
        self.execute_calls = []

    def model_for_lane(self, lane: str) -> str:
        return {"pulse.decision": "gpt-pulse"}.get(lane, "gpt-test")

    def request_audit(self, stage):
        model = self.model_for_lane(stage.lane)
        return AgentExecutionRequestAudit(
            model=model,
            lane=stage.lane,
            stage=stage.stage,
            workflow_name=stage.workflow_name,
            agent_name=stage.agent_name,
            execution_trace_id=f"trace-{stage.stage}",
            group_id=stage.group_id,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            artifact_version_hash=f"artifact:{model}",
            input_hash=stage.input_hash,
            trace_metadata={
                "stage": stage.stage,
                "lane": stage.lane,
                "input_hash": stage.input_hash,
            },
        )

    async def execute(self, stage, **kwargs):
        self.execute_calls.append({"stage": stage, "kwargs": kwargs})
        request_audit = self.request_audit(stage)
        output = self.outputs[stage.stage]
        return AgentExecutionResult(
            final_output=output,
            audit=AgentExecutionResultAudit(
                **_request_audit_base(request_audit),
                status=AgentExecutionStatus.DONE,
                execution_started=True,
                latency_ms=17.0,
                usage={"input_tokens": 11, "output_tokens": 5},
                parse_mode="safety_net_repaired",
                safety_net={"safety_net_used": True, "safety_net_retries": 1},
                output_hash=f"sha256:output-{stage.stage}",
                trace_metadata={
                    **request_audit.trace_metadata,
                    "parse_mode": "safety_net_repaired",
                    "safety_net_used": True,
                },
            ),
            raw_result=SimpleNamespace(final_output=output),
        )


class _FailingAgentGateway(_FakeAgentGateway):
    async def execute(self, stage, **kwargs):
        self.execute_calls.append({"stage": stage, "kwargs": kwargs})
        request_audit = self.request_audit(stage)
        failed = AgentExecutionResultAudit(
            **_request_audit_base(request_audit),
            status=AgentExecutionStatus.FAILED,
            execution_started=True,
            latency_ms=23.0,
            usage={"input_tokens": 2},
            parse_mode="strict",
            safety_net={"safety_net_used": False, "safety_net_retries": 0},
            error_class=AgentExecutionErrorClass.TIMEOUT,
            error_message="agent lane timed out",
        )
        raise AgentExecutionError(
            AgentExecutionErrorClass.TIMEOUT,
            "agent lane timed out",
            audit=failed,
            execution_started=True,
        )


class _TransportFailingAgentGateway(_FakeAgentGateway):
    async def execute(self, stage, **kwargs):
        self.execute_calls.append({"stage": stage, "kwargs": kwargs})
        request_audit = self.request_audit(stage)
        failed = AgentExecutionResultAudit(
            **_request_audit_base(request_audit),
            status=AgentExecutionStatus.FAILED,
            execution_started=True,
            latency_ms=31.0,
            usage={"input_tokens": 3},
            parse_mode="strict",
            safety_net={"safety_net_used": False, "safety_net_retries": 0},
            error_class=AgentExecutionErrorClass.TRANSPORT_ERROR,
            error_message="connection reset by provider",
        )
        raise AgentExecutionError(
            AgentExecutionErrorClass.TRANSPORT_ERROR,
            "connection reset by provider",
            audit=failed,
            execution_started=True,
        )


class _NoStartBackpressureGateway(_FakeAgentGateway):
    async def execute(self, stage, **kwargs):
        self.execute_calls.append({"stage": stage, "kwargs": kwargs})
        request_audit = self.request_audit(stage)
        audit = AgentExecutionResultAudit(
            **_request_audit_base(request_audit),
            status=AgentExecutionStatus.FAILED,
            execution_started=False,
            latency_ms=0.0,
            usage={},
            parse_mode="strict",
            safety_net={},
            error_class=AgentExecutionErrorClass.CAPACITY_DENIED,
            error_message="agent lane unavailable",
        )
        raise AgentExecutionError(
            AgentExecutionErrorClass.CAPACITY_DENIED,
            "agent lane unavailable",
            audit=audit,
            execution_started=False,
        )


def _request_audit_base(audit: AgentExecutionRequestAudit) -> dict:
    return audit.model_dump(
        mode="json",
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
        },
    )


def test_json_output_schema_final_decision_flattens_refs() -> None:
    schema = StrictJsonOutputSchema(FinalDecision)
    serialized = json.dumps(schema.json_schema())
    assert schema.is_strict_json_schema() is True
    assert schema.is_plain_text() is False
    assert "$ref" not in serialized
    assert "$defs" not in serialized
    assert schema.output_type is FinalDecision


def test_pulse_client_requires_decision_runtime_only() -> None:
    with pytest.raises(ValueError, match="decision_runtime is required"):
        LiteLLMPulseDecisionClient(
            agent_gateway=_FakeAgentGateway(),
            decision_runtime=None,  # type: ignore[arg-type]
        )


def test_pulse_client_runtime_contract_is_packet_only() -> None:
    client = LiteLLMPulseDecisionClient(
        agent_gateway=_FakeAgentGateway(),
        decision_runtime=PulseDecisionRuntimeService(),
    )

    contract = client.runtime_contract

    assert contract.stage_names == ("pulse_decision",)
    assert not hasattr(contract, "safety_net_enabled")
    assert "safety_net_enabled" not in contract.manifest_kwargs()
    assert "max_turns_per_stage" not in contract.manifest_kwargs()
    assert "tool_names_by_stage" not in contract.manifest_kwargs()
    assert "route_tool_budgets" not in contract.manifest_kwargs()


def test_pulse_runtime_manifest_declares_single_packet_stage_and_no_tools() -> None:
    manifest = build_pulse_runtime_manifest(
        provider="litellm",
        model="gpt-test",
        artifact_version_hash="artifact:gpt-test",
        timeout_seconds=20.0,
    )

    assert manifest["runtime"]["stages"] == ["pulse_decision"]
    assert manifest["runtime"]["orchestration"] == "single_stage_runner"
    assert "safety_net_enabled" not in manifest["runtime"]
    assert "tool_names_by_stage" not in manifest["runtime"]
    assert "max_turns_per_stage" not in manifest["runtime"]
    assert "evidence_debate" not in json.dumps(manifest)
    assert "decision_maker" not in json.dumps(manifest)
    assert "route_tool_budgets" not in manifest["runtime"]
    assert manifest["contracts"]["evidence_packet_schema_version"]


def test_pulse_client_artifact_hash_includes_prompt_text_hash() -> None:
    client = LiteLLMPulseDecisionClient(
        agent_gateway=_FakeAgentGateway(),
        decision_runtime=PulseDecisionRuntimeService(),
    )
    model_manifest = "gpt-pulse"
    output_schema_hash = json_sha256({"pulse_decision": FinalDecision.model_json_schema()})

    expected = artifact_hash_for(
        model=model_manifest,
        prompt_version=PULSE_DECISION_PROMPT_VERSION,
        schema_version=PULSE_DECISION_SCHEMA_VERSION,
        runtime_version=RUNTIME_VERSION,
        output_schema_hash=output_schema_hash,
        prompt_text_hash=pulse_decision_prompt_text_hash(),
    )
    old_no_prompt_hash = artifact_hash_for(
        model=model_manifest,
        prompt_version=PULSE_DECISION_PROMPT_VERSION,
        schema_version=PULSE_DECISION_SCHEMA_VERSION,
        runtime_version=RUNTIME_VERSION,
        output_schema_hash=output_schema_hash,
    )

    assert client.artifact_version_hash == expected
    assert client.artifact_version_hash != old_no_prompt_hash


def test_pulse_decision_stage_input_contains_packet_hash_and_allowed_refs() -> None:
    runtime = PulseDecisionRuntimeService()
    packet = {
        "evidence_packet_id": "pkt-1",
        "evidence_packet_hash": "sha256:packet",
        "schema_version": "pulse-evidence-packet-v1",
        "candidate_id": "candidate-1",
        "target_id": "asset:pepe",
        "summary_json": {"social_rows": [{"unref_field": "must stay out of agent prompt"}]},
        "admission_context": {"factor_snapshot": {"social_heat": {"watched_seed_strength": 10}}},
        "allowed_evidence_refs": [
            {"ref_id": "event:evt-1", "summary_zh": "高粉账号提及"},
            {"ref_id": "metric:market:price_usd", "summary_zh": "价格快照"},
        ],
    }

    spec = runtime.pulse_decision_stage_spec(
        route="meme",
        evidence_packet=packet,
        evidence_gate={"status": "complete"},
        recommendation_constraints={"route": "meme"},
    )

    assert spec.stage == "pulse_decision"
    assert spec.input_payload["evidence_packet_hash"] == "sha256:packet"
    assert spec.input_payload["allowed_evidence_ref_ids"] == [
        "event:evt-1",
        "metric:market:price_usd",
    ]
    assert "summary_json" not in spec.input_payload["evidence_packet"]
    assert "admission_context" not in spec.input_payload["evidence_packet"]
    assert spec.knowledge_refs == ("market_research_harness",)
    assert spec.read_only_tool_refs == ("token_radar.current_rows", "pulse.current_candidates")
    assert "## Loaded Knowledge: Market Research Harness" in spec.prompt_text


def test_pulse_client_routes_single_stage_through_gateway_and_preserves_stage_audit_fields() -> None:
    gateway = _FakeAgentGateway(
        {
            "pulse_decision": _final_decision_raw(
                supporting_refs=["event:event-1"],
                playbook={
                    "has_playbook": True,
                    "watch_signals": ["成交量继续扩张"],
                    "exit_triggers": ["叙事降温"],
                    "monitoring_horizon": "4h",
                },
            ),
        }
    )
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_pipeline_context(),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"status": "complete"},
            runtime_manifest={"runtime_version": "test"},
        )
    )

    assert [call["stage"].lane for call in gateway.execute_calls] == ["pulse.decision"]
    assert [call["stage"].stage for call in gateway.execute_calls] == ["pulse_decision"]
    assert gateway.execute_calls[0]["stage"].output_type is FinalDecision
    assert isinstance(gateway.execute_calls[0]["stage"].input_payload, dict)
    assert gateway.execute_calls[0]["stage"].knowledge_refs == ("market_research_harness",)
    assert gateway.execute_calls[0]["stage"].read_only_tool_refs == (
        "token_radar.current_rows",
        "pulse.current_candidates",
    )
    assert len(result.stage_audits) == 1
    assert result.stage_audits[0].usage_json == {"input_tokens": 11, "output_tokens": 5}
    assert result.stage_audits[0].parse_mode == "safety_net_repaired"
    assert result.stage_audits[0].safety_net_used is True
    assert result.stage_audits[0].safety_net_retries == 1
    assert "safety_net" not in result.stage_audits[0].trace_metadata_json
    assert "safety_net_used" not in result.stage_audits[0].trace_metadata_json
    assert result.stage_audits[0].input_hash == gateway.execute_calls[0]["stage"].input_hash
    assert result.stage_audits[0].output_hash == "sha256:output-pulse_decision"


def test_pulse_client_cost_guard_skip_decision_skips_llm() -> None:
    gateway = _FakeAgentGateway()
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_pipeline_context(
                cost_guard={"decision": {"action": "skip_decision", "decision_allowed": False}}
            ),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"status": "complete"},
            runtime_manifest={"runtime_version": "test"},
        )
    )

    assert gateway.execute_calls == []
    assert result.stage_audits == ()
    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.abstain_reason == "cost_guard_decision_skipped"


def test_pulse_client_cost_guard_run_decision_runs_single_stage() -> None:
    gateway = _FakeAgentGateway(
        {
            "pulse_decision": _final_decision_raw(
                supporting_refs=["event:event-1"],
                playbook={
                    "has_playbook": False,
                    "watch_signals": [],
                    "exit_triggers": [],
                    "monitoring_horizon": "4h",
                },
            ),
        }
    )
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    asyncio.run(
        client.run_decision_pipeline(
            context=_pipeline_context(
                cost_guard={
                    "decision": {"action": "run_decision", "decision_allowed": True}
                }
            ),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"status": "complete"},
            runtime_manifest={"runtime_version": "test"},
        )
    )

    assert [call["stage"].lane for call in gateway.execute_calls] == ["pulse.decision"]


def test_pulse_client_passes_parent_reservation_to_stage_execution() -> None:
    gateway = _FakeAgentGateway(
        {
            "pulse_decision": _final_decision_raw(
                supporting_refs=["event:event-1"],
                playbook={
                    "has_playbook": False,
                    "watch_signals": [],
                    "exit_triggers": [],
                    "monitoring_horizon": "4h",
                },
            ),
        }
    )
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )
    parent = object()

    asyncio.run(
        client.run_decision_pipeline(
            context=_pipeline_context(),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"status": "complete"},
            runtime_manifest={"runtime_version": "test"},
            parent_reservation=parent,
        )
    )

    assert [call["kwargs"] for call in gateway.execute_calls] == [{"parent_reservation": parent}]


def test_pulse_client_rejects_typo_refs_instead_of_canonicalizing_gateway_output() -> None:
    gateway = _FakeAgentGateway(
        {
            "pulse_decision": _final_decision_raw(
                supporting_refs=["event:event-l"],
                playbook={
                    "has_playbook": False,
                    "watch_signals": ["继续观察链上流动性"],
                    "exit_triggers": ["叙事降温"],
                    "monitoring_horizon": "4h",
                },
            ),
        }
    )
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_pipeline_context(),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"status": "complete"},
            runtime_manifest={"runtime_version": "test"},
        )
    )

    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.abstain_reason == "invalid_unknown_evidence_ref"
    assert result.stage_audits[0].status == "failed"
    assert result.stage_audits[0].response_json["supporting_evidence_refs"] == ["event:event-l"]
    assert result.stage_audits[0].response_json["playbook"]["watch_signals"] == []
    assert result.stage_audits[0].response_json["playbook"]["exit_triggers"] == []
    assert "supporting_evidence_refs contains refs outside allowed_evidence_refs" in (
        result.stage_audits[0].error or ""
    )
    assert "evidence_ref_canonicalization" not in result.stage_audits[0].trace_metadata_json


def test_invalid_evidence_refs_remain_pulse_domain_failures_not_gateway_failures() -> None:
    gateway = _FakeAgentGateway(
        {"pulse_decision": _final_decision_raw(supporting_refs=["event:outside"], playbook=_empty_playbook())}
    )
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_pipeline_context(),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"status": "complete"},
            runtime_manifest={"runtime_version": "test"},
        )
    )

    assert len(gateway.execute_calls) == 1
    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.abstain_reason == "invalid_unknown_evidence_ref"
    assert result.stage_audits[0].status == "failed"
    assert "outside allowed_evidence_refs" in (result.stage_audits[0].error or "")


def test_schema_invalid_pulse_decision_returns_invalid_model_output_abstain() -> None:
    invalid_output = _final_decision_raw(supporting_refs=["event:event-1"], playbook=_empty_playbook())
    invalid_output.pop("narrative_thesis_zh")
    gateway = _FakeAgentGateway(
        {
            "pulse_decision": invalid_output,
        }
    )
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_pipeline_context(),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"status": "complete"},
            runtime_manifest={"runtime_version": "test"},
        )
    )

    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.abstain_reason == "invalid_model_output"
    assert result.stage_audits[0].status == "failed"
    assert "ValidationError" in (result.stage_audits[0].error or "")


def test_provider_transport_failure_preserves_error_class_without_unknown_ref_label() -> None:
    gateway = _TransportFailingAgentGateway()
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    with pytest.raises(PulseStageFailure) as exc:
        asyncio.run(
            client.run_decision_pipeline(
                context=_pipeline_context(),
                run_id="run-1",
                job={"job_id": "job-1", "attempt_count": 1},
                route="meme",
                completeness={"status": "complete"},
                runtime_manifest={"runtime_version": "test"},
            )
        )

    failed = exc.value.audits[0]
    assert failed.status == "failed"
    assert failed.trace_metadata_json["error_class"] == "transport_error"
    assert "invalid_unknown_evidence_ref" not in str(exc.value)


def test_gateway_execution_timeout_degrades_to_abstain_without_retrying_job() -> None:
    gateway = _FailingAgentGateway()
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    result = asyncio.run(
        client.run_decision_pipeline(
            context=_pipeline_context(),
            run_id="run-1",
            job={"job_id": "job-1", "attempt_count": 1},
            route="meme",
            completeness={"status": "complete"},
            runtime_manifest={"runtime_version": "test"},
        )
    )

    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.abstain_reason == "stage_timeout"
    assert result.stage_audits[0].stage == "pulse_decision"
    assert result.stage_audits[0].status == "timeout"
    assert result.stage_audits[0].error == "agent lane timed out"
    assert result.stage_audits[0].usage_json == {"input_tokens": 2}
    assert result.stage_audits[0].input_hash == gateway.execute_calls[0]["stage"].input_hash


def test_no_start_agent_execution_error_is_not_collapsed_into_stage_failure() -> None:
    gateway = _NoStartBackpressureGateway()
    client = LiteLLMPulseDecisionClient(
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(),
    )

    with pytest.raises(AgentExecutionError) as exc:
        asyncio.run(
            client.run_decision_pipeline(
                context=_pipeline_context(),
                run_id="run-1",
                job={"job_id": "job-1", "attempt_count": 1},
                route="meme",
                completeness={"status": "complete"},
                runtime_manifest={"runtime_version": "test"},
            )
        )

    assert exc.value.error_class is AgentExecutionErrorClass.CAPACITY_DENIED
    assert exc.value.execution_started is False


def _pipeline_context(*, cost_guard: dict | None = None) -> dict:
    context = {
        "candidate_id": "candidate-1",
        "candidate_type": "token_target",
        "subject_key": "pepe",
        "target_type": "Asset",
        "target_id": "asset:pepe",
        "evidence_packet": {
            "evidence_packet_id": "pkt-1",
            "evidence_packet_hash": "sha256:packet",
            "schema_version": "pulse-evidence-packet-v1",
            "candidate_id": "candidate-1",
            "target_id": "asset:pepe",
            "source_event_ids": ["event-1"],
            "allowed_evidence_refs": [{"ref_id": "event:event-1", "ref_type": "event", "summary_zh": "高粉账号提及"}],
        },
    }
    if cost_guard is not None:
        context["cost_guard"] = cost_guard
    return context


def _empty_playbook() -> dict:
    return {
        "has_playbook": False,
        "watch_signals": [],
        "exit_triggers": [],
        "monitoring_horizon": "4h",
    }


def _final_decision_raw(*, supporting_refs: list[str], playbook: dict) -> dict:
    return {
        "route": "meme",
        "recommendation": "trade_candidate",
        "confidence": 0.63,
        "abstain_reason": None,
        "summary_zh": "社交与市场证据形成观察。",
        "narrative_archetype": "memetic",
        "narrative_thesis_zh": "社交扩散与市场反馈形成同步观察，但仍需要继续监控证据质量和后续确认。",
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "社交流量与市场反馈同步增强。",
            "supporting_event_ids": ["event-1"],
        },
        "bear_view": {
            "strength": "weak",
            "thesis_zh": "流动性仍然偏薄，需要观察延续性。",
            "supporting_event_ids": ["event-1"],
        },
        "playbook": playbook,
        "evidence_event_ids": ["event-1"],
        "supporting_evidence_refs": supporting_refs,
        "risk_evidence_refs": [],
        "data_gap_refs": [],
        "invalidation_conditions": [],
        "residual_risks": [],
    }
