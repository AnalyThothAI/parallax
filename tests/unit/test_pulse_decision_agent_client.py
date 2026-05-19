"""Execution gateway tests for the packet-only pulse decision client.

Coverage focus:
- ``StrictJsonOutputSchema`` strict + jsonref flattening (qwen3.6 / llama.cpp).
- Pulse stages route through ``AgentExecutionGateway`` stage specs.
- Pulse public runtime no longer registers critical data-acquisition tools.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from gmgn_twitter_intel.domains.pulse_lab.providers import EvidenceDebateMemo
from gmgn_twitter_intel.domains.pulse_lab.services.agent_runtime import build_pulse_runtime_manifest
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_decision_runtime import (
    PulseDecisionRuntimeService,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    FinalDecision,
    PulseStageFailure,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.openai_agents.pulse_decision_agent_client import (
    OpenAIAgentsPulseDecisionClient,
)
from gmgn_twitter_intel.platform.agent_execution import (
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentExecutionResult,
    AgentExecutionResultAudit,
    AgentExecutionStatus,
)


class _FakeAgentGateway:
    def __init__(self, outputs: dict[str, object] | None = None) -> None:
        self.outputs = outputs or {}
        self.execute_calls = []

    def request_audit(self, stage):
        return AgentExecutionRequestAudit(
            model=stage.model,
            lane=stage.lane,
            stage=stage.stage,
            workflow_name=stage.workflow_name,
            agent_name=stage.agent_name,
            sdk_trace_id=f"trace-{stage.stage}",
            group_id=stage.group_id,
            prompt_version=stage.prompt_version,
            schema_version=stage.schema_version,
            artifact_version_hash=f"artifact:{stage.model}",
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


def test_json_output_schema_enables_strict_and_flattens_refs() -> None:
    schema = StrictJsonOutputSchema(EvidenceDebateMemo)
    assert schema.is_strict_json_schema() is True
    assert schema.is_plain_text() is False
    flat = schema.json_schema()
    assert "type" in flat
    # jsonref.replace_refs must strip $ref/$defs so llama.cpp grammar conversion
    # does not silent-fail-open (llama.cpp issue #21228).
    serialized = json.dumps(flat)
    assert "$ref" not in serialized
    assert "$defs" not in serialized
    # Expose underlying Pydantic class for InstructorSafetyNet fallback path.
    assert schema.output_type is EvidenceDebateMemo


def test_json_output_schema_final_decision_also_flattens_refs() -> None:
    schema = StrictJsonOutputSchema(FinalDecision)
    serialized = json.dumps(schema.json_schema())
    assert "$ref" not in serialized
    assert "$defs" not in serialized


def test_pulse_client_requires_decision_runtime_only() -> None:
    import pytest

    with pytest.raises(ValueError, match="decision_runtime is required"):
        OpenAIAgentsPulseDecisionClient(
            model="gpt-test",
            agent_gateway=_FakeAgentGateway(),
            decision_runtime=None,  # type: ignore[arg-type]
        )


def test_pulse_client_runtime_contract_is_packet_only_without_tools() -> None:
    client = OpenAIAgentsPulseDecisionClient(
        model="gpt-test",
        agent_gateway=_FakeAgentGateway(),
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
    )

    contract = client.runtime_contract

    assert contract.stage_names == ("evidence_debate", "decision_maker")
    assert contract.tool_names_by_stage == {"evidence_debate": (), "decision_maker": ()}
    assert contract.safety_net_enabled is True
    assert contract.manifest_kwargs()["tool_names_by_stage"] == {
        "evidence_debate": (),
        "decision_maker": (),
    }
    assert "route_tool_budgets" not in contract.manifest_kwargs()


def test_pulse_runtime_manifest_declares_packet_schema_and_no_tools() -> None:
    manifest = build_pulse_runtime_manifest(
        provider="openai",
        model="gpt-test",
        artifact_version_hash="artifact:gpt-test",
        timeout_seconds=20.0,
    )

    assert manifest["runtime"]["stages"] == ["evidence_debate", "decision_maker"]
    assert manifest["runtime"]["tool_names_by_stage"] == {
        "evidence_debate": [],
        "decision_maker": [],
    }
    assert "route_tool_budgets" not in manifest["runtime"]
    assert manifest["contracts"]["evidence_packet_schema_version"]


def test_evidence_debate_stage_input_contains_packet_hash_and_allowed_refs() -> None:
    runtime = PulseDecisionRuntimeService(db_pool=object())
    packet = {
        "evidence_packet_id": "pkt-1",
        "evidence_packet_hash": "sha256:packet",
        "schema_version": "pulse-evidence-packet-v1",
        "candidate_id": "candidate-1",
        "target_id": "asset:pepe",
        "allowed_evidence_refs": [
            {"ref_id": "event:evt-1", "summary_zh": "高粉账号提及"},
            {"ref_id": "metric:market:price_usd", "summary_zh": "价格快照"},
        ],
    }

    spec = runtime.evidence_debate_stage_spec(
        route="meme",
        evidence_packet=packet,
        evidence_gate={"status": "complete"},
    )

    assert spec.stage == "evidence_debate"
    assert spec.input_payload["evidence_packet_hash"] == "sha256:packet"
    assert spec.input_payload["allowed_evidence_ref_ids"] == [
        "event:evt-1",
        "metric:market:price_usd",
    ]


def test_pulse_client_routes_stages_through_gateway_and_preserves_stage_audit_fields() -> None:
    gateway = _FakeAgentGateway(
        {
            "evidence_debate": _evidence_debate_raw(["event:event-1"]),
            "decision_maker": _final_decision_raw(
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
    client = OpenAIAgentsPulseDecisionClient(
        model="gpt-test",
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
        evidence_debate_max_turns=2,
        decision_maker_max_turns=4,
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

    assert [call["stage"].lane for call in gateway.execute_calls] == [
        "pulse.evidence_debate",
        "pulse.decision_maker",
    ]
    assert [call["stage"].stage for call in gateway.execute_calls] == ["evidence_debate", "decision_maker"]
    assert gateway.execute_calls[0]["stage"].output_type is EvidenceDebateMemo
    assert gateway.execute_calls[1]["stage"].output_type is FinalDecision
    assert [call["stage"].max_turns for call in gateway.execute_calls] == [2, 4]
    assert isinstance(gateway.execute_calls[0]["stage"].input_payload, dict)
    assert result.stage_audits[0].usage_json == {"input_tokens": 11, "output_tokens": 5}
    assert result.stage_audits[0].parse_mode == "safety_net_repaired"
    assert result.stage_audits[0].safety_net_used is True
    assert result.stage_audits[0].safety_net_retries == 1
    assert result.stage_audits[0].input_hash == gateway.execute_calls[0]["stage"].input_hash
    assert result.stage_audits[0].output_hash == "sha256:output-evidence_debate"
    assert result.stage_audits[1].output_hash == "sha256:output-decision_maker"


def test_pulse_client_passes_parent_reservation_to_stage_execution() -> None:
    gateway = _FakeAgentGateway(
        {
            "evidence_debate": _evidence_debate_raw(["event:event-1"]),
            "decision_maker": _final_decision_raw(
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
    client = OpenAIAgentsPulseDecisionClient(
        model="gpt-test",
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
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

    assert [call["kwargs"] for call in gateway.execute_calls] == [
        {"parent_reservation": parent},
        {"parent_reservation": parent},
    ]


def test_pulse_client_omits_parent_reservation_keyword_for_legacy_gateway() -> None:
    gateway = _FakeAgentGateway(
        {
            "evidence_debate": _evidence_debate_raw(["event:event-1"]),
            "decision_maker": _final_decision_raw(
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
    client = OpenAIAgentsPulseDecisionClient(
        model="gpt-test",
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
    )

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

    assert [call["kwargs"] for call in gateway.execute_calls] == [{}, {}]


def test_pulse_client_normalizes_gateway_output_before_domain_ref_validation() -> None:
    gateway = _FakeAgentGateway(
        {
            "evidence_debate": _evidence_debate_raw(["event:event-l"]),
            "decision_maker": _final_decision_raw(
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
    client = OpenAIAgentsPulseDecisionClient(
        model="gpt-test",
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
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

    assert result.stage_audits[0].status == "ok"
    assert result.stage_audits[0].response_json["allowed_evidence_ref_ids"] == ["event:event-1"]
    assert result.stage_audits[1].response_json["supporting_evidence_refs"] == ["event:event-1"]
    assert result.stage_audits[1].response_json["playbook"]["watch_signals"] == []
    assert result.stage_audits[1].response_json["playbook"]["exit_triggers"] == []
    assert result.stage_audits[1].trace_metadata_json["evidence_ref_canonicalization"]["corrections"] == [
        {
            "path": "supporting_evidence_refs[0]",
            "from": "event:event-l",
            "to": "event:event-1",
            "ref_type": "event",
            "reason": "unique_same_type_edit_distance_1",
        }
    ]
    assert result.stage_audits[1].trace_metadata_json["schema_normalization"]["repairs"] == [
        {"path": "playbook.watch_signals", "action": "cleared", "reason": "playbook_has_playbook_false"},
        {"path": "playbook.exit_triggers", "action": "cleared", "reason": "playbook_has_playbook_false"},
    ]


def test_invalid_evidence_refs_remain_pulse_domain_failures_not_gateway_failures() -> None:
    gateway = _FakeAgentGateway({"evidence_debate": _evidence_debate_raw(["event:outside"])})
    client = OpenAIAgentsPulseDecisionClient(
        model="gpt-test",
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
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
    assert result.stage_audits[0].status == "failed"
    assert "outside allowed_evidence_refs" in (result.stage_audits[0].error or "")


def test_gateway_execution_error_becomes_failed_stage_audit() -> None:
    gateway = _FailingAgentGateway()
    client = OpenAIAgentsPulseDecisionClient(
        model="gpt-test",
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
    )

    import pytest

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

    assert exc.value.audits[0].stage == "evidence_debate"
    assert exc.value.audits[0].status == "timeout"
    assert exc.value.audits[0].error == "agent lane timed out"
    assert exc.value.audits[0].usage_json == {"input_tokens": 2}
    assert exc.value.audits[0].input_hash == gateway.execute_calls[0]["stage"].input_hash


def test_no_start_agent_execution_error_is_not_collapsed_into_stage_failure() -> None:
    gateway = _NoStartBackpressureGateway()
    client = OpenAIAgentsPulseDecisionClient(
        model="gpt-test",
        agent_gateway=gateway,
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
    )

    import pytest

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


def _pipeline_context() -> dict:
    return {
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


def _evidence_debate_raw(refs: list[str]) -> dict:
    return {
        "bull_claims": [{"claim": "社交证据形成早期扩散。", "evidence_refs": refs, "stance": "bull"}],
        "bear_claims": [],
        "rebuttal_claims": [],
        "data_gap_claims": [],
        "summary_zh": "证据显示社交扩散开始出现，但仍需要观察市场确认。",
        "allowed_evidence_ref_ids": refs,
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
