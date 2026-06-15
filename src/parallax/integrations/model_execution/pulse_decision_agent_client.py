from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.interfaces import (
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
)
from parallax.domains.pulse_lab.providers import (
    DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT,
    PULSE_DECISION_LANE,
    EvidenceCompletenessGateResult,
    PulseAgentRuntimeContract,
    PulseDecisionRuntime,
    PulseDecisionStageSpec,
    PulseEvidencePacket,
)
from parallax.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    DecisionRoute,
    FinalDecision,
    PulseStageFailure,
    StageRunAudit,
    StageStatus,
    TradePlaybook,
)
from parallax.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentExecutionResult,
    AgentExecutionResultAudit,
    AgentStageSpec,
)
from parallax.platform.agent_hashing import artifact_hash_for, json_sha256

WORKFLOW_NAME = "parallax.pulse_decision"
AGENT_NAME = "PulseDecisionDesk"


@dataclass(frozen=True)
class PulseDecisionAgentResult:
    final_decision: FinalDecision
    agent_run_audit: dict[str, Any]
    stage_audits: tuple[StageRunAudit, ...]


@dataclass(frozen=True, slots=True)
class _PulseStageRequestAudit:
    run_id: str
    trace_metadata: dict[str, Any]


class LiteLLMPulseDecisionClient:
    """Packet-only single-stage Pulse decision client."""

    provider = "litellm"

    def __init__(
        self,
        *,
        agent_gateway: Any,
        decision_runtime: PulseDecisionRuntime,
        workflow_name: str = WORKFLOW_NAME,
    ) -> None:
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        if decision_runtime is None:
            raise ValueError("decision_runtime is required")
        self._agent_gateway = agent_gateway
        self._decision_runtime = decision_runtime
        self.workflow_name = _workflow_name(workflow_name)

    @property
    def model(self) -> str:
        return self._agent_gateway.model_for_lane(PULSE_DECISION_LANE)

    def model_for_lane(self, lane: str) -> str:
        return self._agent_gateway.model_for_lane(lane)

    @property
    def artifact_version_hash(self) -> str:
        return artifact_hash_for(
            model=self._agent_gateway.model_for_lane(PULSE_DECISION_LANE),
            prompt_version=PULSE_DECISION_PROMPT_VERSION,
            schema_version=PULSE_DECISION_SCHEMA_VERSION,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256({"pulse_decision": FinalDecision.model_json_schema()}),
            prompt_text_hash=self._decision_runtime.prompt_text_hash(),
        )

    @property
    def runtime_contract(self) -> PulseAgentRuntimeContract:
        return PulseAgentRuntimeContract(
            stage_names=("pulse_decision",),
            evidence_packet_schema_version=DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT.evidence_packet_schema_version,
        )

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        rate_units: int = 1,
        scope: str = "execution",
    ) -> AgentCapacityReservation:
        return self._agent_gateway.try_reserve(lane, child_lanes=child_lanes, rate_units=rate_units, scope=scope)

    def request_audit(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        evidence_gate = _evidence_gate_from_completeness(completeness)
        return self._decision_runtime.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=evidence_gate,
            runtime_manifest=runtime_manifest,
            model=self._pipeline_model_manifest(),
            artifact_version_hash=self.artifact_version_hash,
            workflow_name=self.workflow_name,
            agent_name=AGENT_NAME,
        )

    async def run_decision_pipeline(
        self,
        *,
        context: dict[str, Any],
        run_id: str,
        job: dict[str, Any],
        route: DecisionRoute,
        completeness: dict[str, Any],
        runtime_manifest: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> PulseDecisionAgentResult:
        audit = self.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
        )
        evidence_packet = _evidence_packet_from_context(context)

        if not _decision_allowed(context):
            final = _stage_failure_abstain_decision(
                route=route,
                reason="pulse_decision_not_required",
                evidence_packet=evidence_packet,
                abstain_reason="cost_guard_decision_skipped",
            )
            audit = self._decision_runtime.with_output_hash(audit, final=final)
            return PulseDecisionAgentResult(
                final_decision=final,
                agent_run_audit=audit,
                stage_audits=(),
            )

        evidence_gate = _evidence_gate_from_completeness(completeness)
        decision_step = await self._run_pulse_decision(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
            run_id=run_id,
            audit=audit,
            parent_reservation=parent_reservation,
        )
        stage_audits: list[StageRunAudit] = [decision_step]
        if decision_step.status != "ok":
            if _is_model_contract_stage_failure(decision_step):
                final = _stage_failure_abstain_decision(
                    route=route,
                    reason=decision_step.error or "pulse_decision_contract_failed",
                    evidence_packet=evidence_packet,
                    abstain_reason=_abstain_reason_for_stage_failure(decision_step),
                )
                audit = self._decision_runtime.with_output_hash(audit, final=final)
                return PulseDecisionAgentResult(
                    final_decision=final,
                    agent_run_audit=audit,
                    stage_audits=tuple(stage_audits),
                )
            raise PulseStageFailure(
                f"pulse_decision stage {decision_step.status}: {decision_step.error}",
                audits=tuple(stage_audits),
            )
        final = FinalDecision.model_validate(decision_step.response_json)
        try:
            self._decision_runtime.validate_final_evidence_refs(
                final,
                evidence_packet=evidence_packet,
            )
        except ValueError as exc:
            failed_step = self._decision_runtime.mark_step_failed(decision_step, error=str(exc))
            stage_audits[-1] = failed_step
            final = _stage_failure_abstain_decision(
                route=route,
                reason=str(exc),
                evidence_packet=evidence_packet,
                abstain_reason="invalid_unknown_evidence_ref",
            )

        audit = self._decision_runtime.with_output_hash(audit, final=final)
        return PulseDecisionAgentResult(
            final_decision=final,
            agent_run_audit=audit,
            stage_audits=tuple(stage_audits),
        )

    async def _run_pulse_decision(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: EvidenceCompletenessGateResult,
        run_id: str,
        audit: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> StageRunAudit:
        spec = self._decision_runtime.pulse_decision_stage_spec(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
            recommendation_constraints=_recommendation_constraints(route=route, evidence_gate=evidence_gate),
        )
        return await self._run_stage(
            spec=spec,
            route=route,
            output_type=FinalDecision,
            evidence_packet=evidence_packet,
            run_id=run_id,
            audit=audit,
            parent_reservation=parent_reservation,
        )

    async def _run_stage(
        self,
        *,
        spec: PulseDecisionStageSpec,
        route: DecisionRoute,
        output_type: type[Any],
        evidence_packet: PulseEvidencePacket,
        run_id: str,
        audit: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> StageRunAudit:
        stage_spec = self._agent_stage_spec(
            spec=spec,
            route=route,
            output_type=output_type,
            run_id=run_id,
            audit=audit,
        )
        raw_output: Any = None
        execution_audit: AgentExecutionResultAudit | None = None
        try:
            if parent_reservation is None:
                execution = await self._agent_gateway.execute(stage_spec)
            else:
                execution = await self._agent_gateway.execute(
                    stage_spec,
                    parent_reservation=parent_reservation,
                )
            execution = _require_execution_result(execution)
            execution_audit = execution.audit
            raw_output = execution.final_output
            normalization_input = (
                raw_output.model_dump(mode="json") if isinstance(raw_output, output_type) else raw_output
            )
            normalized = self._decision_runtime.normalize_stage_output(
                output_type=output_type,
                raw_output=normalization_input,
                evidence_packet=evidence_packet,
            )
            output = output_type.model_validate(normalized.payload)
            return _stage_audit_from_execution(
                stage_spec=stage_spec,
                route=route,
                prompt=spec.prompt_text,
                response_json=output.model_dump(mode="json"),
                execution_audit=execution.audit,
                status="ok",
                error=None,
                trace_extra=normalized.trace_metadata,
            )
        except AgentExecutionError as exc:
            if _is_no_start_agent_backpressure(exc):
                raise
            return _stage_audit_from_execution_error(
                stage_spec=stage_spec,
                route=route,
                prompt=spec.prompt_text,
                exc=exc,
            )
        except Exception as exc:
            if _is_execution_contract_error(exc):
                raise
            return _stage_audit_from_execution(
                stage_spec=stage_spec,
                route=route,
                prompt=spec.prompt_text,
                response_json={"raw_output": _truncate(raw_output)} if raw_output is not None else None,
                execution_audit=execution_audit,
                status="failed",
                error=f"{type(exc).__name__}: {exc}"[:1000],
                trace_extra={},
            )

    def _agent_stage_spec(
        self,
        *,
        spec: PulseDecisionStageSpec,
        route: DecisionRoute,
        output_type: type[Any],
        run_id: str,
        audit: dict[str, Any],
    ) -> AgentStageSpec:
        request_audit = _stage_request_audit(audit, run_id=run_id)
        return AgentStageSpec(
            lane=_stage_lane(spec.stage),
            stage=spec.stage,
            instructions=spec.prompt_text,
            input_payload=spec.input_payload,
            output_type=output_type,
            prompt_version=PULSE_DECISION_PROMPT_VERSION,
            schema_version=PULSE_DECISION_SCHEMA_VERSION,
            workflow_name=self.workflow_name,
            agent_name=_stage_agent_name(spec.stage, route),
            group_id=_stage_group_id(spec.input_payload),
            knowledge_refs=spec.knowledge_refs,
            read_only_tool_refs=spec.read_only_tool_refs,
            trace_metadata={
                **request_audit.trace_metadata,
                "run_id": request_audit.run_id,
                "stage": spec.stage,
                "route": route,
                "lane": _stage_lane(spec.stage),
            },
        )

    def _pipeline_model_manifest(self) -> str:
        return self._agent_gateway.model_for_lane(PULSE_DECISION_LANE)

    async def aclose(self) -> None:
        return None


def _stage_lane(stage: str) -> str:
    if stage != "pulse_decision":
        raise ValueError(f"unsupported pulse stage: {stage}")
    return PULSE_DECISION_LANE


def _stage_agent_name(stage: str, route: DecisionRoute) -> str:
    if stage == "pulse_decision":
        return f"PulseDecisionDesk{_route_label(route)}"
    return AGENT_NAME


def _route_label(route: DecisionRoute) -> str:
    return {"cex": "Cex", "meme": "Meme", "research_only": "ResearchOnly"}.get(str(route), "Cex")


def _stage_audit_from_execution(
    *,
    stage_spec: AgentStageSpec,
    route: DecisionRoute,
    prompt: str,
    response_json: dict[str, Any] | None,
    execution_audit: AgentExecutionRequestAudit | AgentExecutionResultAudit | None,
    status: StageStatus,
    error: str | None,
    trace_extra: dict[str, Any],
) -> StageRunAudit:
    audit = _require_execution_audit(execution_audit)
    safety = dict(audit.safety_net or {})
    input_hash = str(audit.input_hash)
    output_hash = audit.output_hash
    trace_metadata = {
        **_stage_trace_metadata(audit),
        **dict(trace_extra or {}),
        "input_hash": input_hash,
        "output_hash": output_hash,
    }
    if audit.error_class is not None:
        trace_metadata["error_class"] = str(audit.error_class)
    return _stage_audit(
        stage=stage_spec.stage,
        route=route,
        attempt_index=0,
        input_json=_input_json(stage_spec.input_payload),
        prompt_text=prompt,
        response_json=response_json,
        trace_metadata_json=trace_metadata,
        usage_json=dict(audit.usage or {}),
        latency_ms=_latency_ms(audit.latency_ms),
        started_at_ms=None,
        finished_at_ms=None,
        status=status,
        error=error,
        safety_net_used=bool(safety.get("safety_net_used", False)),
        safety_net_retries=int(safety.get("safety_net_retries") or 0),
        parse_mode=str(audit.parse_mode or "strict"),
        input_hash=input_hash,
        output_hash=output_hash,
    )


def _stage_audit_from_execution_error(
    *,
    stage_spec: AgentStageSpec,
    route: DecisionRoute,
    prompt: str,
    exc: AgentExecutionError,
) -> StageRunAudit:
    audit = _require_execution_audit(exc.audit)
    status: StageStatus = "timeout" if exc.error_class == AgentExecutionErrorClass.TIMEOUT else "failed"
    error = str(audit.error_message or exc)[:1000]
    return _stage_audit_from_execution(
        stage_spec=stage_spec,
        route=route,
        prompt=prompt,
        response_json=None,
        execution_audit=audit,
        status=status,
        error=error,
        trace_extra={},
    )


def _stage_trace_metadata(audit: AgentExecutionRequestAudit | AgentExecutionResultAudit) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in dict(audit.trace_metadata or {}).items()
        if str(key) not in {"safety_net", "safety_net_used", "safety_net_retries", "parse_mode"}
    }


def _is_no_start_agent_backpressure(exc: AgentExecutionError) -> bool:
    return exc.execution_started is False and exc.error_class in {
        AgentExecutionErrorClass.CAPACITY_DENIED,
        AgentExecutionErrorClass.CIRCUIT_OPEN,
        AgentExecutionErrorClass.RATE_LIMITED,
        AgentExecutionErrorClass.QUOTA_EXHAUSTED,
    }


def _require_execution_result(value: Any) -> AgentExecutionResult:
    if not isinstance(value, AgentExecutionResult):
        raise TypeError("pulse_decision_execution_result_contract_required")
    return value


def _require_execution_audit(
    value: AgentExecutionRequestAudit | AgentExecutionResultAudit | None,
) -> AgentExecutionRequestAudit | AgentExecutionResultAudit:
    if not isinstance(value, AgentExecutionRequestAudit):
        raise TypeError("pulse_decision_execution_audit_contract_required")
    return value


def _is_execution_contract_error(exc: Exception) -> bool:
    return str(exc) in {
        "pulse_decision_execution_result_contract_required",
        "pulse_decision_execution_audit_contract_required",
    }


def _stage_audit(**kwargs: Any) -> StageRunAudit:
    return StageRunAudit(**kwargs)


def _input_json(input_payload: Any) -> dict[str, Any]:
    if isinstance(input_payload, dict):
        return dict(input_payload)
    return {"input_payload": input_payload}


def _stage_request_audit(audit: Mapping[str, Any], *, run_id: str) -> _PulseStageRequestAudit:
    try:
        trace_raw = audit["trace_metadata"]
    except KeyError as exc:
        raise ValueError("pulse_decision_stage_request_audit_trace_metadata_required") from exc
    if not isinstance(trace_raw, Mapping) or not trace_raw:
        raise ValueError("pulse_decision_stage_request_audit_trace_metadata_required")
    trace_metadata = dict(trace_raw)
    run_id_value = _required_identity_text(run_id, "pulse_decision_stage_request_audit_run_id_required")
    try:
        trace_run_id = _required_identity_text(
            trace_metadata["run_id"],
            "pulse_decision_stage_request_audit_run_id_required",
        )
    except KeyError as exc:
        raise ValueError("pulse_decision_stage_request_audit_run_id_required") from exc
    if trace_run_id != run_id_value:
        raise ValueError("pulse_decision_stage_request_audit_run_id_mismatch")
    return _PulseStageRequestAudit(run_id=run_id_value, trace_metadata=trace_metadata)


def _stage_group_id(input_payload: Mapping[str, Any]) -> str:
    try:
        packet = input_payload["evidence_packet"]
    except KeyError as exc:
        raise ValueError("pulse_decision_stage_group_id_required") from exc
    group_id = _group_id(packet)
    if not group_id:
        raise ValueError("pulse_decision_stage_group_id_required")
    return group_id


def _group_id(context: Any) -> str | None:
    if not isinstance(context, dict):
        return None
    candidate_id = _context_string(context, "candidate_id")
    if candidate_id:
        return candidate_id
    return _context_string(context, "subject_key")


def _evidence_packet_from_context(context: dict[str, Any]) -> PulseEvidencePacket:
    packet = context.get("evidence_packet") if isinstance(context, dict) else None
    if not isinstance(packet, dict):
        raise ValueError("pulse_decision_evidence_packet_contract_required")
    try:
        return PulseEvidencePacket.model_validate(packet)
    except ValueError as exc:
        raise ValueError("pulse_decision_evidence_packet_contract_required") from exc


def _evidence_gate_from_completeness(completeness: dict[str, Any]) -> EvidenceCompletenessGateResult:
    if not isinstance(completeness, dict):
        raise ValueError("pulse_decision_evidence_gate_contract_required")
    try:
        return EvidenceCompletenessGateResult(
            evidence_status=_required_text(completeness, "evidence_status"),
            hard_blocked=_required_bool(completeness, "hard_blocked"),
            blocked_reason=_optional_text(completeness.get("blocked_reason")),
            max_decision_status=_required_text(completeness, "max_decision_status"),
            required_ref_ids=_string_tuple(completeness["required_ref_ids"]),
            missing_ref_types=_string_tuple(completeness["missing_ref_types"]),
            data_gaps=_mapping_tuple(completeness["data_gaps"]),
            public_allowed=_required_bool(completeness, "public_allowed"),
            display_status=_required_text(completeness, "display_status"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("pulse_decision_evidence_gate_contract_required") from exc


def _recommendation_constraints(
    *,
    route: DecisionRoute,
    evidence_gate: EvidenceCompletenessGateResult,
) -> dict[str, Any]:
    return {
        "route": route,
        "gate_status": evidence_gate.evidence_status,
        "non_abstain_requires_allowed_evidence_refs": True,
        "high_conviction_requires_multiple_supporting_refs": True,
        "when_fact_absent": "lower_confidence_or_abstain",
    }


def _decision_allowed(context: dict[str, Any]) -> bool:
    cost_guard = context.get("cost_guard") if isinstance(context, dict) else None
    if not isinstance(cost_guard, dict):
        return True
    decision = cost_guard.get("decision")
    if not isinstance(decision, dict):
        return True
    return bool(decision.get("decision_allowed", True))


def _required_text(payload: dict[str, Any], field: str) -> str:
    text = str(payload[field]).strip()
    if not text:
        raise ValueError(field)
    return text


def _required_identity_text(value: Any, error_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(error_name)
    return text


def _workflow_name(value: str) -> str:
    return _required_identity_text(value, "pulse_decision_workflow_name_required")


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_bool(payload: dict[str, Any], field: str) -> bool:
    value = payload[field]
    if type(value) is not bool:
        raise ValueError(field)
    return value


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("string_tuple")
    return tuple(str(item).strip() for item in value if str(item or "").strip())


def _mapping_tuple(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list | tuple):
        raise ValueError("mapping_tuple")
    return tuple(dict(item) for item in value if isinstance(item, dict))


def _stage_failure_abstain_decision(
    *,
    route: DecisionRoute,
    reason: str,
    evidence_packet: PulseEvidencePacket,
    abstain_reason: str,
) -> FinalDecision:
    gate_refs = tuple(
        ref.ref_id for ref in evidence_packet.allowed_evidence_refs if ref.ref_type == "gate" and ref.ref_id.strip()
    )
    return FinalDecision(
        route=route,
        recommendation="abstain",
        confidence=0.0,
        abstain_reason=abstain_reason,
        summary_zh=_stage_failure_summary(abstain_reason),
        narrative_archetype="unclear",
        narrative_thesis_zh=_stage_failure_thesis(abstain_reason),
        bull_view=BullBearView(strength="absent"),
        bear_view=BullBearView(strength="absent"),
        playbook=TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon="1h",
        ),
        invalidation_conditions=[],
        residual_risks=[reason[:240]],
        evidence_event_ids=[],
        data_gap_refs=gate_refs,
    )


def _is_model_contract_stage_failure(step: StageRunAudit) -> bool:
    if step.status == "timeout":
        return True
    if step.status != "failed":
        return False
    text = str(step.error or "").lower()
    return any(
        marker in text
        for marker in (
            "validation error",
            "modelbehaviorerror",
            "trading execution language",
            "invalid json",
            "schema_invalid",
            "outside allowed_evidence_refs",
        )
    )


def _abstain_reason_for_stage_failure(step: StageRunAudit) -> str:
    if step.status == "timeout":
        return "stage_timeout"
    text = str(step.error or "").lower()
    if "outside allowed_evidence_refs" in text:
        return "invalid_unknown_evidence_ref"
    return "invalid_model_output"


def _stage_failure_summary(abstain_reason: str) -> str:
    if abstain_reason == "cost_guard_decision_skipped":
        return "成本门控跳过单阶段决策，本次不发布候选。"
    if abstain_reason == "stage_timeout":
        return "LLM agent 阶段超时，本次不发布候选。"
    if abstain_reason == "invalid_model_output":
        return "模型输出不符合结构化合同，本次不发布候选。"
    return "模型输出引用了证据包外的 ref，本次不发布候选。"


def _stage_failure_thesis(abstain_reason: str) -> str:
    if abstain_reason == "cost_guard_decision_skipped":
        return "确定性成本门控判定该样本不需要运行 Pulse 决策；系统保留审计并等待下一轮公开资格确认。"
    if abstain_reason == "stage_timeout":
        return "LLM 阶段超过实时预算，没有形成可验证的完整结论；本次仅记录超时并等待下一轮有效证据综合。"
    if abstain_reason == "invalid_model_output":
        return "模型输出未通过结构化合同校验，无法形成可靠结论；本次仅记录无效输出并等待下一轮有效证据综合。"
    return "模型输出包含证据包以外的引用，违反封闭证据合同；本次仅记录无效输出并等待下一轮有效证据综合。"


def _context_string(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: Any, *, limit: int = 4000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit]


def _latency_ms(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


__all__ = [
    "AGENT_NAME",
    "WORKFLOW_NAME",
    "LiteLLMPulseDecisionClient",
    "PulseDecisionAgentResult",
]
