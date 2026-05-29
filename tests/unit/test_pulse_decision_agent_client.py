"""Execution gateway tests for the packet-only pulse decision client.

Coverage focus:
- ``StrictJsonOutputSchema`` strict + jsonref flattening (qwen3.6 / llama.cpp).
- Pulse stages route through ``AgentExecutionGateway`` stage specs.
- Pulse public runtime keeps provider mechanics outside the stage contract.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from gmgn_twitter_intel.domains.pulse_lab.providers import BearCaseMemo, PulseStagePlan, SignalAnalystMemo
from gmgn_twitter_intel.domains.pulse_lab.services.agent_runtime import build_pulse_runtime_manifest
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_decision_runtime import (
    PulseDecisionRuntimeService,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    FinalDecision,
    PulseStageFailure,
)
from gmgn_twitter_intel.integrations.model_execution.output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.model_execution.pulse_decision_agent_client import (
    LiteLLMPulseDecisionClient,
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

    def model_for_lane(self, lane: str) -> str:
        return {
            "pulse.signal_analyst": "gpt-signal",
            "pulse.bear_case": "gpt-bear",
            "pulse.risk_portfolio_judge": "gpt-judge",
        }.get(lane, "gpt-test")

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


def test_json_output_schema_enables_strict_and_flattens_refs() -> None:
    schema = StrictJsonOutputSchema(SignalAnalystMemo)
    assert schema.is_strict_json_schema() is True
    assert schema.is_plain_text() is False
    flat = schema.json_schema()
    assert "type" in flat
    # jsonref.replace_refs must strip $ref/$defs so llama.cpp grammar conversion
    # does not silent-fail-open (llama.cpp issue #21228).
    serialized = json.dumps(flat)
    assert "$ref" not in serialized
    assert "$defs" not in serialized
    # Expose underlying Pydantic class for application-side validation.
    assert schema.output_type is SignalAnalystMemo


def test_json_output_schema_bear_case_also_flattens_refs() -> None:
    schema = StrictJsonOutputSchema(BearCaseMemo)
    serialized = json.dumps(schema.json_schema())
    assert "$ref" not in serialized
    assert "$defs" not in serialized


def test_json_output_schema_final_decision_also_flattens_refs() -> None:
    schema = StrictJsonOutputSchema(FinalDecision)
    serialized = json.dumps(schema.json_schema())
    assert "$ref" not in serialized
    assert "$defs" not in serialized


def test_pulse_client_requires_decision_runtime_only() -> None:
    import pytest

    with pytest.raises(ValueError, match="decision_runtime is required"):
        LiteLLMPulseDecisionClient(
            agent_gateway=_FakeAgentGateway(),
            decision_runtime=None,  # type: ignore[arg-type]
        )


def test_pulse_client_runtime_contract_is_packet_only() -> None:
    client = LiteLLMPulseDecisionClient(
        agent_gateway=_FakeAgentGateway(),
        decision_runtime=PulseDecisionRuntimeService(db_pool=object()),
    )

    contract = client.runtime_contract

    assert contract.stage_names == ("signal_analyst", "bear_case", "risk_portfolio_judge")
    assert contract.safety_net_enabled is True
    assert "max_turns_per_stage" not in contract.manifest_kwargs()
    assert "tool_names_by_stage" not in contract.manifest_kwargs()
    assert "route_tool_budgets" not in contract.manifest_kwargs()


def test_pulse_runtime_manifest_declares_packet_schema_and_no_tools() -> None:
    manifest = build_pulse_runtime_manifest(
        provider="litellm",
        model="gpt-test",
        artifact_version_hash="artifact:gpt-test",
        timeout_seconds=20.0,
    )

    assert manifest["runtime"]["stages"] == ["signal_analyst", "bear_case", "risk_portfolio_judge"]
    assert "tool_names_by_stage" not in manifest["runtime"]
    assert "max_turns_per_stage" not in manifest["runtime"]
    assert "evidence_debate" not in json.dumps(manifest)
    assert "decision_maker" not in json.dumps(manifest)
    assert "route_tool_budgets" not in manifest["runtime"]
    assert manifest["contracts"]["evidence_packet_schema_version"]


def test_signal_analyst_stage_input_contains_packet_hash_and_allowed_refs() -> None:
    runtime = PulseDecisionRuntimeService(db_pool=object())
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

    spec = runtime.signal_analyst_stage_spec(
        route="meme",
        evidence_packet=packet,
        evidence_gate={"status": "complete"},
    )

    assert spec.stage == "signal_analyst"
    assert spec.input_payload["evidence_packet_hash"] == "sha256:packet"
    assert spec.input_payload["allowed_evidence_ref_ids"] == [
        "event:evt-1",
        "metric:market:price_usd",
    ]
    assert "summary_json" not in spec.input_payload["evidence_packet"]
    assert "admission_context" not in spec.input_payload["evidence_packet"]


def test_pulse_client_routes_stages_through_gateway_and_preserves_stage_audit_fields() -> None:
    gateway = _FakeAgentGateway(
        {
            "signal_analyst": _signal_analyst_raw(["event:event-1"]),
            "bear_case": _bear_case_raw(["event:event-1"]),
            "risk_portfolio_judge": _final_decision_raw(
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

    assert [call["stage"].lane for call in gateway.execute_calls] == [
        "pulse.signal_analyst",
        "pulse.bear_case",
        "pulse.risk_portfolio_judge",
    ]
    assert [call["stage"].stage for call in gateway.execute_calls] == [
        "signal_analyst",
        "bear_case",
        "risk_portfolio_judge",
    ]
    assert gateway.execute_calls[0]["stage"].output_type is SignalAnalystMemo
    assert gateway.execute_calls[1]["stage"].output_type is BearCaseMemo
    assert gateway.execute_calls[2]["stage"].output_type is FinalDecision
    assert isinstance(gateway.execute_calls[0]["stage"].input_payload, dict)
    assert result.stage_audits[0].usage_json == {"input_tokens": 11, "output_tokens": 5}
    assert result.stage_audits[0].parse_mode == "safety_net_repaired"
    assert result.stage_audits[0].safety_net_used is True
    assert result.stage_audits[0].safety_net_retries == 1
    assert result.stage_audits[0].input_hash == gateway.execute_calls[0]["stage"].input_hash
    assert result.stage_audits[0].output_hash == "sha256:output-signal_analyst"
    assert result.stage_audits[1].output_hash == "sha256:output-bear_case"
    assert result.stage_audits[2].output_hash == "sha256:output-risk_portfolio_judge"


def test_pulse_client_stage_plan_research_only_skips_public_judge() -> None:
    gateway = _FakeAgentGateway(
        {
            "signal_analyst": _signal_analyst_raw(["event:event-1"]),
            "bear_case": _bear_case_raw(["event:event-1"]),
        }
    )
    client = LiteLLMPulseDecisionClient(
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
            stage_plan=PulseStagePlan(
                run_signal_analyst=True,
                run_bear_case=True,
                run_risk_portfolio_judge=False,
                signal_model="qwen3.6",
                bear_model="qwen3.6",
                judge_model=None,
            ),
        )
    )

    assert [call["stage"].lane for call in gateway.execute_calls] == [
        "pulse.signal_analyst",
        "pulse.bear_case",
    ]
    assert "pulse.risk_portfolio_judge" not in [call["stage"].lane for call in gateway.execute_calls]
    assert [audit.stage for audit in result.stage_audits] == ["signal_analyst", "bear_case"]
    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.abstain_reason == "cost_guard_research_only"


def test_pulse_client_stage_plan_public_judge_runs_all_three_stages() -> None:
    gateway = _FakeAgentGateway(
        {
            "signal_analyst": _signal_analyst_raw(["event:event-1"]),
            "bear_case": _bear_case_raw(["event:event-1"]),
            "risk_portfolio_judge": _final_decision_raw(
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
            stage_plan=PulseStagePlan(
                run_signal_analyst=True,
                run_bear_case=True,
                run_risk_portfolio_judge=True,
                signal_model="qwen3.6",
                bear_model="qwen3.6",
                judge_model="deepseek-v4-flash",
            ),
        )
    )

    assert [call["stage"].lane for call in gateway.execute_calls] == [
        "pulse.signal_analyst",
        "pulse.bear_case",
        "pulse.risk_portfolio_judge",
    ]


def test_pulse_client_passes_parent_reservation_to_stage_execution() -> None:
    gateway = _FakeAgentGateway(
        {
            "signal_analyst": _signal_analyst_raw(["event:event-1"]),
            "bear_case": _bear_case_raw(["event:event-1"]),
            "risk_portfolio_judge": _final_decision_raw(
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
        {"parent_reservation": parent},
    ]


def test_pulse_client_normalizes_gateway_output_before_domain_ref_validation() -> None:
    gateway = _FakeAgentGateway(
        {
            "signal_analyst": _signal_analyst_raw(["event:event-l"]),
            "bear_case": _bear_case_raw(["event:event-l"]),
            "risk_portfolio_judge": _final_decision_raw(
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
    assert result.stage_audits[1].response_json["allowed_evidence_ref_ids"] == ["event:event-1"]
    assert result.stage_audits[2].response_json["supporting_evidence_refs"] == ["event:event-1"]
    assert result.stage_audits[2].response_json["playbook"]["watch_signals"] == []
    assert result.stage_audits[2].response_json["playbook"]["exit_triggers"] == []
    assert result.stage_audits[2].trace_metadata_json["evidence_ref_canonicalization"]["corrections"] == [
        {
            "path": "supporting_evidence_refs[0]",
            "from": "event:event-l",
            "to": "event:event-1",
            "ref_type": "event",
            "reason": "unique_same_type_edit_distance_1",
        }
    ]
    assert result.stage_audits[2].trace_metadata_json["schema_normalization"]["repairs"] == [
        {"path": "playbook.watch_signals", "action": "cleared", "reason": "playbook_has_playbook_false"},
        {"path": "playbook.exit_triggers", "action": "cleared", "reason": "playbook_has_playbook_false"},
    ]


def test_invalid_evidence_refs_remain_pulse_domain_failures_not_gateway_failures() -> None:
    gateway = _FakeAgentGateway({"signal_analyst": _signal_analyst_raw(["event:outside"])})
    client = LiteLLMPulseDecisionClient(
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
    assert result.final_decision.abstain_reason == "invalid_unknown_evidence_ref"
    assert result.stage_audits[0].status == "failed"
    assert "outside allowed_evidence_refs" in (result.stage_audits[0].error or "")


def test_schema_invalid_signal_analyst_returns_invalid_model_output_abstain() -> None:
    gateway = _FakeAgentGateway(
        {
            "signal_analyst": {
                "bull_claims": [
                    {
                        "claim": "建议买入并设置止损。",
                        "evidence_refs": ["event:event-1"],
                        "stance": "bull",
                    }
                ],
                "allowed_evidence_ref_ids": ["event:event-1"],
            }
        }
    )
    client = LiteLLMPulseDecisionClient(
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

    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.abstain_reason == "invalid_model_output"
    assert result.stage_audits[0].status == "failed"
    assert "ValidationError" in (result.stage_audits[0].error or "")


def test_provider_transport_failure_preserves_error_class_without_unknown_ref_label() -> None:
    gateway = _TransportFailingAgentGateway()
    client = LiteLLMPulseDecisionClient(
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

    failed = exc.value.audits[0]
    assert failed.status == "failed"
    assert failed.trace_metadata_json["error_class"] == "transport_error"
    assert "invalid_unknown_evidence_ref" not in str(exc.value)


def test_gateway_execution_timeout_degrades_to_abstain_without_retrying_job() -> None:
    gateway = _FailingAgentGateway()
    client = LiteLLMPulseDecisionClient(
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

    assert result.final_decision.recommendation == "abstain"
    assert result.final_decision.abstain_reason == "stage_timeout"
    assert result.stage_audits[0].stage == "signal_analyst"
    assert result.stage_audits[0].status == "timeout"
    assert result.stage_audits[0].error == "agent lane timed out"
    assert result.stage_audits[0].usage_json == {"input_tokens": 2}
    assert result.stage_audits[0].input_hash == gateway.execute_calls[0]["stage"].input_hash


def test_no_start_agent_execution_error_is_not_collapsed_into_stage_failure() -> None:
    gateway = _NoStartBackpressureGateway()
    client = LiteLLMPulseDecisionClient(
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


def _signal_analyst_raw(refs: list[str]) -> dict:
    return {
        "bull_claims": [{"claim": "社交证据形成早期扩散。", "evidence_refs": refs, "stance": "bull"}],
        "what_changed_zh": "证据显示社交扩散开始出现，但仍需要观察市场确认。",
        "allowed_evidence_ref_ids": refs,
    }


def _bear_case_raw(refs: list[str]) -> dict:
    return {
        "risk_claims": [{"claim": "流动性仍然偏薄。", "evidence_refs": refs, "stance": "risk"}],
        "confidence_ceiling": 0.72,
        "missing_fact_impacts": [],
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
