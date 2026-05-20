from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import (
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
)
from gmgn_twitter_intel.domains.pulse_lab.providers import (
    DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT,
    EvidenceDebateMemo,
    PulseAgentRuntimeContract,
    PulseDecisionRuntime,
    PulseDecisionStageSpec,
    PulseEvidencePacket,
)
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    DecisionRoute,
    FinalDecision,
    PulseDecisionPayload,
    PulseStageFailure,
    StageRunAudit,
    StageStatus,
    TradePlaybook,
)
from gmgn_twitter_intel.platform.agent_execution import (
    RUNTIME_VERSION,
    AgentCapacityReservation,
    AgentExecutionError,
    AgentExecutionErrorClass,
    AgentExecutionRequestAudit,
    AgentExecutionResultAudit,
    AgentStageSpec,
)
from gmgn_twitter_intel.platform.agent_hashing import artifact_hash_for, json_sha256

WORKFLOW_NAME = "gmgn-twitter-intel.pulse_decision"
AGENT_NAME = "PulseDecisionDesk"
_DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class PulseDecisionAgentResult:
    final_decision: FinalDecision
    run_audit: dict[str, Any]
    stage_audits: tuple[StageRunAudit, ...]


class OpenAIAgentsPulseDecisionClient:
    """Packet-only EvidenceDebate -> DecisionMaker pulse decision client."""

    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        agent_gateway: Any,
        decision_runtime: PulseDecisionRuntime,
        workflow_name: str = WORKFLOW_NAME,
        decision_maker_max_turns: int = 1,
        evidence_debate_max_turns: int = 1,
    ) -> None:
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("llm.pulse_agent_model or llm.model is required")
        if agent_gateway is None:
            raise ValueError("agent_gateway is required")
        if decision_runtime is None:
            raise ValueError("decision_runtime is required")
        self._agent_gateway = agent_gateway
        self._decision_runtime = decision_runtime
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        self._decision_maker_max_turns = max(1, int(decision_maker_max_turns))
        self._evidence_debate_max_turns = max(1, int(evidence_debate_max_turns))

    @property
    def timeout_seconds(self) -> float:
        return _DEFAULT_TIMEOUT_SECONDS

    @property
    def artifact_version_hash(self) -> str:
        return artifact_hash_for(
            model=self.model,
            prompt_version=PULSE_DECISION_PROMPT_VERSION,
            schema_version=PULSE_DECISION_SCHEMA_VERSION,
            runtime_version=RUNTIME_VERSION,
            output_schema_hash=json_sha256(
                {
                    "evidence_debate": EvidenceDebateMemo.model_json_schema(),
                    "decision_maker": FinalDecision.model_json_schema(),
                }
            ),
        )

    @property
    def runtime_contract(self) -> PulseAgentRuntimeContract:
        return PulseAgentRuntimeContract(
            stage_names=("evidence_debate", "decision_maker"),
            max_turns_per_stage={
                "evidence_debate": self._evidence_debate_max_turns,
                "decision_maker": self._decision_maker_max_turns,
            },
            tool_names_by_stage={
                "evidence_debate": (),
                "decision_maker": (),
            },
            safety_net_enabled=True,
            evidence_packet_schema_version=DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT.evidence_packet_schema_version,
        )

    def try_reserve_execution(
        self,
        lane: str,
        *,
        child_lanes: tuple[str, ...] = (),
        scope: str = "execution",
    ) -> AgentCapacityReservation:
        return self._agent_gateway.try_reserve(lane, child_lanes=child_lanes, scope=scope)

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
        return self._decision_runtime.request_audit(
            context=context,
            run_id=run_id,
            job=job,
            route=route,
            completeness=completeness,
            runtime_manifest=runtime_manifest,
            model=self.model,
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
        evidence_gate = completeness

        debate_step = await self._run_evidence_debate(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
            run_id=run_id,
            audit=audit,
            parent_reservation=parent_reservation,
        )
        stage_audits: list[StageRunAudit] = [debate_step]
        if debate_step.status != "ok":
            if _is_model_contract_stage_failure(debate_step):
                final = _stage_failure_abstain_decision(
                    route=route,
                    reason=debate_step.error or "evidence_debate_contract_failed",
                    evidence_packet=evidence_packet,
                    abstain_reason=_abstain_reason_for_stage_failure(debate_step),
                )
                audit = self._decision_runtime.with_output_hash(audit, final=final)
                return PulseDecisionAgentResult(final_decision=final, run_audit=audit, stage_audits=tuple(stage_audits))
            raise PulseStageFailure(
                f"evidence_debate stage {debate_step.status}: {debate_step.error}",
                audits=tuple(stage_audits),
            )
        debate_memo = EvidenceDebateMemo.model_validate(debate_step.response_json)

        try:
            self._decision_runtime.validate_debate_refs(
                debate_memo,
                evidence_packet=evidence_packet,
            )
        except ValueError as exc:
            failed_step = self._decision_runtime.mark_step_failed(debate_step, error=str(exc))
            stage_audits[-1] = failed_step
            final = _stage_failure_abstain_decision(
                route=route,
                reason=str(exc),
                evidence_packet=evidence_packet,
                abstain_reason="invalid_unknown_evidence_ref",
            )
            audit = self._decision_runtime.with_output_hash(audit, final=final)
            return PulseDecisionAgentResult(final_decision=final, run_audit=audit, stage_audits=tuple(stage_audits))

        decision_step = await self._run_decision_maker(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
            debate_memo=debate_memo,
            run_id=run_id,
            audit=audit,
            parent_reservation=parent_reservation,
        )
        stage_audits.append(decision_step)
        if decision_step.status != "ok":
            if _is_model_contract_stage_failure(decision_step):
                final = _stage_failure_abstain_decision(
                    route=route,
                    reason=decision_step.error or "decision_maker_contract_failed",
                    evidence_packet=evidence_packet,
                    abstain_reason=_abstain_reason_for_stage_failure(decision_step),
                )
                audit = self._decision_runtime.with_output_hash(audit, final=final)
                return PulseDecisionAgentResult(final_decision=final, run_audit=audit, stage_audits=tuple(stage_audits))
            raise PulseStageFailure(
                f"decision_maker stage {decision_step.status}: {decision_step.error}",
                audits=tuple(stage_audits),
            )
        final = FinalDecision.model_validate(decision_step.response_json)
        try:
            self._decision_runtime.validate_final_evidence_refs(
                final,
                evidence_packet=evidence_packet,
                debate_memo=debate_memo,
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

        final = self._decision_runtime.enrich_evidence_urls(final)

        PulseDecisionPayload(final_decision=final, stage_audits=tuple(stage_audits))
        audit = self._decision_runtime.with_output_hash(audit, final=final)
        return PulseDecisionAgentResult(final_decision=final, run_audit=audit, stage_audits=tuple(stage_audits))

    async def _run_evidence_debate(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: dict[str, Any],
        run_id: str,
        audit: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> StageRunAudit:
        spec = self._decision_runtime.evidence_debate_stage_spec(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
        )
        return await self._run_stage(
            spec=spec,
            route=route,
            output_type=EvidenceDebateMemo,
            max_turns=self._evidence_debate_max_turns,
            run_id=run_id,
            audit=audit,
            parent_reservation=parent_reservation,
        )

    async def _run_decision_maker(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: dict[str, Any],
        debate_memo: EvidenceDebateMemo,
        run_id: str,
        audit: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> StageRunAudit:
        spec = self._decision_runtime.decision_maker_stage_spec(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
            debate_memo=debate_memo,
            recommendation_constraints=_recommendation_constraints(route=route, completeness=evidence_gate),
        )
        return await self._run_stage(
            spec=spec,
            route=route,
            output_type=FinalDecision,
            max_turns=self._decision_maker_max_turns,
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
        max_turns: int,
        run_id: str,
        audit: dict[str, Any],
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> StageRunAudit:
        stage_spec = self._agent_stage_spec(
            spec=spec,
            route=route,
            output_type=output_type,
            max_turns=max_turns,
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
            execution_audit = execution.audit
            raw_output = execution.final_output
            normalization_input = (
                raw_output.model_dump(mode="json") if isinstance(raw_output, output_type) else raw_output
            )
            normalized = self._decision_runtime.normalize_stage_output(
                output_type=output_type,
                raw_output=normalization_input,
                evidence_packet=spec.input_payload.get("evidence_packet"),
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
        max_turns: int,
        run_id: str,
        audit: dict[str, Any],
    ) -> AgentStageSpec:
        return AgentStageSpec(
            lane=_stage_lane(spec.stage),
            stage=spec.stage,
            model=self.model,
            instructions=spec.prompt_text,
            input_payload=spec.input_payload,
            output_type=output_type,
            prompt_version=PULSE_DECISION_PROMPT_VERSION,
            schema_version=PULSE_DECISION_SCHEMA_VERSION,
            workflow_name=self.workflow_name,
            agent_name=_stage_agent_name(spec.stage, route),
            group_id=_group_id(spec.input_payload.get("evidence_packet")) or str(run_id or ""),
            trace_metadata={
                **dict(audit.get("trace_metadata") or {}),
                "run_id": str(run_id or ""),
                "stage": spec.stage,
                "route": route,
                "lane": _stage_lane(spec.stage),
            },
            max_turns=max_turns,
        )

    async def aclose(self) -> None:
        return None


def _stage_lane(stage: str) -> str:
    if stage == "evidence_debate":
        return "pulse.evidence_debate"
    if stage == "decision_maker":
        return "pulse.decision_maker"
    raise ValueError(f"unsupported pulse stage: {stage}")


def _stage_agent_name(stage: str, route: DecisionRoute) -> str:
    if stage == "evidence_debate":
        return f"PulseEvidenceDebate{_route_label(route)}"
    if stage == "decision_maker":
        return f"PulseDecisionMaker{_route_label(route)}"
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
    audit = execution_audit
    safety = dict(getattr(audit, "safety_net", {}) or {}) if audit is not None else {}
    input_hash = str(getattr(audit, "input_hash", None) or stage_spec.input_hash)
    output_hash = getattr(audit, "output_hash", None) if audit is not None else None
    trace_metadata = {
        **dict(getattr(audit, "trace_metadata", {}) or {}),
        **dict(trace_extra or {}),
        "input_hash": input_hash,
        "output_hash": output_hash,
        "safety_net": safety,
    }
    if getattr(audit, "error_class", None):
        trace_metadata["error_class"] = str(audit.error_class)
    return _stage_audit(
        stage=stage_spec.stage,
        route=route,
        attempt_index=0,
        input_json=_input_json(stage_spec.input_payload),
        prompt_text=prompt,
        response_json=response_json,
        trace_metadata_json=trace_metadata,
        usage_json=dict(getattr(audit, "usage", {}) or {}),
        latency_ms=_latency_ms(getattr(audit, "latency_ms", None)),
        started_at_ms=None,
        finished_at_ms=None,
        status=status,
        error=error,
        safety_net_used=bool(safety.get("safety_net_used", False)),
        safety_net_retries=int(safety.get("safety_net_retries") or 0),
        parse_mode=str(getattr(audit, "parse_mode", None) or "strict"),
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
    audit = exc.audit
    status: StageStatus = "timeout" if exc.error_class == AgentExecutionErrorClass.TIMEOUT else "failed"
    error = str(getattr(audit, "error_message", None) or exc)[:1000]
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


def _is_no_start_agent_backpressure(exc: AgentExecutionError) -> bool:
    return (
        bool(getattr(exc, "execution_started", True)) is False
        and exc.error_class
        in {
            AgentExecutionErrorClass.CAPACITY_DENIED,
            AgentExecutionErrorClass.CIRCUIT_OPEN,
            AgentExecutionErrorClass.RATE_LIMITED,
        }
    )


def _stage_audit(**kwargs: Any) -> StageRunAudit:
    try:
        return StageRunAudit(**kwargs)
    except ValueError as exc:
        if kwargs.get("stage") == "evidence_debate" and "literal_error" in str(exc):
            return StageRunAudit.model_construct(**kwargs)
        raise


def _input_json(input_payload: Any) -> dict[str, Any]:
    if isinstance(input_payload, dict):
        return dict(input_payload)
    return {"input_payload": input_payload}


def _group_id(context: Any) -> str | None:
    if not isinstance(context, dict):
        return None
    candidate_id = _context_string(context, "candidate_id")
    if candidate_id:
        return candidate_id
    return _context_string(context, "subject_key")


def _evidence_packet_from_context(context: dict[str, Any]) -> dict[str, Any]:
    packet = context.get("evidence_packet") if isinstance(context, dict) else None
    if isinstance(packet, dict):
        return dict(packet)
    model_dump = getattr(packet, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        return payload if isinstance(payload, dict) else {}
    if isinstance(context, dict) and context.get("evidence_packet_hash"):
        return dict(context)
    return dict(context)


def _recommendation_constraints(*, route: DecisionRoute, completeness: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": route,
        "gate_status": completeness.get("status") if isinstance(completeness, dict) else None,
        "non_abstain_requires_allowed_evidence_refs": True,
        "high_conviction_requires_multiple_supporting_refs": True,
        "when_fact_absent": "lower_confidence_or_abstain",
    }


def _stage_failure_abstain_decision(
    *,
    route: DecisionRoute,
    reason: str,
    evidence_packet: PulseEvidencePacket | dict[str, Any],
    abstain_reason: str,
) -> FinalDecision:
    gate_refs = tuple(
        ref_id
        for ref in _allowed_refs_from_packet(evidence_packet)
        if (ref_id := _ref_value(ref, "ref_id")) and _ref_value(ref, "ref_type") == "gate"
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
            "instructorretryexception",
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
    if abstain_reason == "stage_timeout":
        return "LLM 证据辩论阶段超时，本次不发布候选。"
    if abstain_reason == "invalid_model_output":
        return "模型输出不符合结构化合同，本次不发布候选。"
    return "模型输出引用了证据包外的 ref，本次不发布候选。"


def _stage_failure_thesis(abstain_reason: str) -> str:
    if abstain_reason == "stage_timeout":
        return "LLM 阶段超过实时预算，没有形成可验证的完整结论；本次仅记录超时并等待下一轮有效证据综合。"
    if abstain_reason == "invalid_model_output":
        return "模型输出未通过结构化合同校验，无法形成可靠结论；本次仅记录无效输出并等待下一轮有效证据综合。"
    return "模型输出包含证据包以外的引用，违反封闭证据合同；本次仅记录无效输出并等待下一轮有效证据综合。"


def _allowed_refs_from_packet(packet: PulseEvidencePacket | dict[str, Any]) -> tuple[Any, ...]:
    if isinstance(packet, dict):
        refs = packet.get("allowed_evidence_refs")
    else:
        refs = getattr(packet, "allowed_evidence_refs", ())
    return tuple(refs) if isinstance(refs, list | tuple) else tuple()


def _ref_value(ref: Any, key: str) -> str:
    value = ref.get(key) if isinstance(ref, dict) else getattr(ref, key, None)
    return str(value or "").strip()


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
    "OpenAIAgentsPulseDecisionClient",
    "PulseDecisionAgentResult",
]
