from __future__ import annotations

import inspect
import json
import time
from dataclasses import dataclass
from types import GetSetDescriptorType, MemberDescriptorType
from typing import Any, cast

from agents import (
    Agent,
    RunConfig,
    Runner,
)
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

from gmgn_twitter_intel.domains.pulse_lab.providers import (
    DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT,
    EvidenceDebateMemo,
    PulseAgentRuntimeContract,
    PulseDecisionRuntime,
    PulseEvidencePacket,
)
from gmgn_twitter_intel.domains.pulse_lab.services.agent_output_normalization import normalize_pulse_stage_output
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
from gmgn_twitter_intel.integrations.openai_agents.agent_model_settings import (
    default_agent_model_settings,
)
from gmgn_twitter_intel.integrations.openai_agents.agent_output_schema import StrictJsonOutputSchema
from gmgn_twitter_intel.integrations.openai_agents.instructor_safety_net import (
    InstructorSafetyNet,
    SafetyNetExhausted,
)

WORKFLOW_NAME = "gmgn-twitter-intel.pulse_decision"
AGENT_NAME = "PulseDecisionDesk"


@dataclass(frozen=True)
class PulseDecisionAgentResult:
    final_decision: FinalDecision
    run_audit: dict[str, Any]
    stage_audits: tuple[StageRunAudit, ...]


class OpenAIAgentsPulseDecisionClient:
    """Packet-only EvidenceDebate → DecisionMaker pulse decision client.

    Critical evidence acquisition is owned by the worker before this client is
    called. Both LLM stages receive the sealed evidence packet, the gate result,
    and the packet's allowed citation refs; neither stage registers tools.
    """

    provider = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        llm_gateway: Any,
        decision_runtime: PulseDecisionRuntime,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
        runner: Any | None = None,
        safety_net: InstructorSafetyNet | None = None,
        trace_enabled: bool = True,
        trace_include_sensitive_data: bool = False,
        workflow_name: str = WORKFLOW_NAME,
        decision_maker_max_turns: int = 3,
        evidence_debate_max_turns: int = 3,
    ) -> None:
        self.api_key = api_key
        self.model = str(model or "").strip()
        if not self.model:
            raise ValueError("llm.pulse_agent_model or llm.model is required")
        if llm_gateway is None:
            raise ValueError("llm_gateway is required")
        if decision_runtime is None:
            raise ValueError("decision_runtime is required")
        self._llm_gateway = llm_gateway
        self._decision_runtime = decision_runtime
        self.base_url = _api_base(base_url)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.workflow_name = str(workflow_name or "").strip() or WORKFLOW_NAME
        self.trace_enabled = bool(trace_enabled and getattr(self._llm_gateway, "trace_export_enabled", False))
        self.trace_include_sensitive_data = bool(trace_include_sensitive_data)
        self._runner = runner or Runner
        self._safety_net = safety_net
        self._model = None if runner is not None else self._build_model()
        self._decision_maker_max_turns = max(1, int(decision_maker_max_turns))
        self._evidence_debate_max_turns = max(1, int(evidence_debate_max_turns))

    @property
    def artifact_version_hash(self) -> str:
        return f"artifact:{self.model}"

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
            safety_net_enabled=self._safety_net is not None,
            evidence_packet_schema_version=DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT.evidence_packet_schema_version,
        )

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
    ) -> PulseDecisionAgentResult:
        audit = self._decision_runtime.request_audit(
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
        evidence_packet = _evidence_packet_from_context(context)
        evidence_gate = completeness

        debate_step = await self._run_evidence_debate(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
            run_id=run_id,
            audit=audit,
        )
        stage_audits: list[StageRunAudit] = [debate_step]
        if debate_step.status != "ok":
            if _is_model_contract_stage_failure(debate_step):
                final = _invalid_ref_abstain_decision(
                    route=route,
                    reason=debate_step.error or "evidence_debate_contract_failed",
                    evidence_packet=evidence_packet,
                )
                audit = self._decision_runtime.with_output_hash(audit, final=final)
                return PulseDecisionAgentResult(
                    final_decision=final,
                    run_audit=audit,
                    stage_audits=tuple(stage_audits),
                )
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
            final = _invalid_ref_abstain_decision(route=route, reason=str(exc), evidence_packet=evidence_packet)
            audit = self._decision_runtime.with_output_hash(audit, final=final)
            return PulseDecisionAgentResult(
                final_decision=final,
                run_audit=audit,
                stage_audits=tuple(stage_audits),
            )

        decision_step = await self._run_decision_maker(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
            debate_memo=debate_memo,
            run_id=run_id,
            audit=audit,
        )
        stage_audits.append(decision_step)
        if decision_step.status != "ok":
            if _is_model_contract_stage_failure(decision_step):
                final = _invalid_ref_abstain_decision(
                    route=route,
                    reason=decision_step.error or "decision_maker_contract_failed",
                    evidence_packet=evidence_packet,
                )
                audit = self._decision_runtime.with_output_hash(audit, final=final)
                return PulseDecisionAgentResult(
                    final_decision=final,
                    run_audit=audit,
                    stage_audits=tuple(stage_audits),
                )
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
            final = _invalid_ref_abstain_decision(route=route, reason=str(exc), evidence_packet=evidence_packet)

        # Evidence URL enrichment (best-effort JOIN against events).
        final = self._decision_runtime.enrich_evidence_urls(final)

        PulseDecisionPayload(final_decision=final, stage_audits=tuple(stage_audits))
        audit = self._decision_runtime.with_output_hash(audit, final=final)
        return PulseDecisionAgentResult(
            final_decision=final,
            run_audit=audit,
            stage_audits=tuple(stage_audits),
        )

    async def _run_evidence_debate(
        self,
        *,
        route: DecisionRoute,
        evidence_packet: PulseEvidencePacket,
        evidence_gate: dict[str, Any],
        run_id: str,
        audit: dict[str, Any],
    ) -> StageRunAudit:
        spec = self._decision_runtime.evidence_debate_stage_spec(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
        )
        agent = Agent[Any](
            name=f"PulseEvidenceDebate{_route_label(route)}",
            instructions=spec.prompt_text,
            output_type=StrictJsonOutputSchema(EvidenceDebateMemo),
            tools=[],
            model=self._model,
            model_settings=default_agent_model_settings(),
        )
        return await self._run_stage(
            stage="evidence_debate",
            route=route,
            agent=agent,
            output_type=EvidenceDebateMemo,
            input_payload=spec.input_payload,
            prompt=spec.prompt_text,
            audit=audit,
            max_turns=self._evidence_debate_max_turns,
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
    ) -> StageRunAudit:
        spec = self._decision_runtime.decision_maker_stage_spec(
            route=route,
            evidence_packet=evidence_packet,
            evidence_gate=evidence_gate,
            debate_memo=debate_memo,
            recommendation_constraints=_recommendation_constraints(route=route, completeness=evidence_gate),
        )
        agent = Agent[Any](
            name=f"PulseDecisionMaker{_route_label(route)}",
            instructions=spec.prompt_text,
            output_type=StrictJsonOutputSchema(FinalDecision),
            tools=[],
            model=self._model,
            model_settings=default_agent_model_settings(),
        )
        return await self._run_stage(
            stage="decision_maker",
            route=route,
            agent=agent,
            output_type=FinalDecision,
            input_payload=spec.input_payload,
            prompt=spec.prompt_text,
            audit=audit,
            max_turns=self._decision_maker_max_turns,
        )

    async def _run_stage(
        self,
        *,
        stage: str,
        route: DecisionRoute,
        agent: Agent[Any],
        output_type: type[Any],
        input_payload: dict[str, Any],
        prompt: str,
        audit: dict[str, Any],
        max_turns: int,
    ) -> StageRunAudit:
        stage_input = json.dumps(input_payload, ensure_ascii=False, sort_keys=True)
        base_trace_metadata = {**audit["trace_metadata"], "stage": stage, "route": route}
        run_config = RunConfig(
            workflow_name=self.workflow_name,
            trace_id=audit["sdk_trace_id"],
            group_id=_group_id(input_payload.get("evidence_packet")),
            trace_include_sensitive_data=self.trace_include_sensitive_data,
            tracing_disabled=not self.trace_enabled,
            trace_metadata=base_trace_metadata,
        )
        started = int(time.time() * 1000)
        raw_output: Any = None
        result_obj: Any = None
        audit_extra: dict[str, Any] = {
            "safety_net_used": False,
            "safety_net_retries": 0,
            "parse_mode": "strict",
            "usage": {},
        }
        try:
            if self._safety_net is not None:
                final_output, audit_extra, result_obj = await self._llm_gateway.run_with_limits(
                    "pulse_candidate",
                    stage,
                    self.timeout_seconds,
                    lambda: self._safety_net.run_with_safety_net(
                        agent=agent,
                        input_payload=stage_input,
                        run_config=run_config,
                        pydantic_output_type=output_type,
                        context=None,
                        max_turns=max_turns,
                        return_result=True,
                    ),
                )
                raw_output = final_output
            else:
                result_obj = await self._llm_gateway.run_with_limits(
                    "pulse_candidate",
                    stage,
                    self.timeout_seconds,
                    lambda: self._runner.run(
                        agent,
                        stage_input,
                        max_turns=max_turns,
                        run_config=run_config,
                        context=None,
                    ),
                )
                raw_output = getattr(result_obj, "final_output", None)
                audit_extra = {**audit_extra, "usage": _extract_usage(result_obj)}
            normalization_input = (
                raw_output.model_dump(mode="json") if isinstance(raw_output, output_type) else raw_output
            )
            normalized = normalize_pulse_stage_output(
                output_type=output_type,
                raw_output=normalization_input,
                evidence_packet=input_payload.get("evidence_packet"),
            )
            audit_extra = {**audit_extra, **normalized.trace_metadata}
            output = output_type.model_validate(normalized.payload)
        except SafetyNetExhausted as exhausted:
            finished = int(time.time() * 1000)
            audit_extra = exhausted.audit_extra
            trace_metadata_failed = {
                **base_trace_metadata,
                **audit_extra,
            }
            return _stage_audit(
                stage=stage,
                route=route,
                attempt_index=0,
                input_json=dict(input_payload),
                prompt_text=prompt,
                response_json=None,
                trace_metadata_json=trace_metadata_failed,
                usage_json=audit_extra.get("usage") or {},
                latency_ms=max(0, finished - started),
                started_at_ms=started,
                finished_at_ms=finished,
                status="failed",
                error=f"{type(exhausted.original).__name__}: {exhausted.original}"[:1000],
                safety_net_used=True,
                safety_net_retries=int(audit_extra.get("safety_net_retries") or 0),
                parse_mode=str(audit_extra.get("parse_mode") or "instructor_failed"),
            )
        except Exception as exc:
            finished = int(time.time() * 1000)
            status: StageStatus = "timeout" if isinstance(exc, TimeoutError) else "failed"
            trace_metadata_failed = {
                **base_trace_metadata,
                **audit_extra,
            }
            return _stage_audit(
                stage=stage,
                route=route,
                attempt_index=0,
                input_json=dict(input_payload),
                prompt_text=prompt,
                response_json={"raw_output": _truncate(raw_output)} if raw_output is not None else None,
                trace_metadata_json=trace_metadata_failed,
                usage_json=audit_extra.get("usage") or {},
                latency_ms=max(0, finished - started),
                started_at_ms=started,
                finished_at_ms=finished,
                status=status,
                error=f"{type(exc).__name__}: {exc}"[:1000],
                safety_net_used=bool(audit_extra.get("safety_net_used")),
                safety_net_retries=int(audit_extra.get("safety_net_retries") or 0),
                parse_mode=str(audit_extra.get("parse_mode") or "strict"),
            )
        finished = int(time.time() * 1000)
        trace_metadata_ok = {
            **base_trace_metadata,
            **audit_extra,
        }
        return _stage_audit(
            stage=stage,
            route=route,
            attempt_index=0,
            input_json=dict(input_payload),
            prompt_text=prompt,
            response_json=output.model_dump(mode="json"),
            trace_metadata_json=trace_metadata_ok,
            usage_json=audit_extra.get("usage") or {},
            latency_ms=max(0, finished - started),
            started_at_ms=started,
            finished_at_ms=finished,
            status="ok",
            error=None,
            safety_net_used=bool(audit_extra.get("safety_net_used")),
            safety_net_retries=int(audit_extra.get("safety_net_retries") or 0),
            parse_mode=str(audit_extra.get("parse_mode") or "strict"),
        )

    def _build_model(self):
        return OpenAIChatCompletionsModel(
            model=self.model,
            openai_client=self._llm_gateway.openai_client(
                model=self.model,
                base_url=self.base_url,
                timeout_s=self.timeout_seconds,
            ),
        )

    async def aclose(self) -> None:
        return None


def _route_label(route: DecisionRoute) -> str:
    return {"cex": "Cex", "meme": "Meme", "research_only": "ResearchOnly"}.get(str(route), "Cex")


def _stage_audit(**kwargs: Any) -> StageRunAudit:
    try:
        return StageRunAudit(**kwargs)
    except ValueError as exc:
        if kwargs.get("stage") == "evidence_debate" and "literal_error" in str(exc):
            return StageRunAudit.model_construct(**kwargs)
        raise


def _api_base(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    if not value:
        return "https://api.openai.com/v1"
    return value if value.endswith("/v1") else f"{value}/v1"


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


def _invalid_ref_abstain_decision(
    *,
    route: DecisionRoute,
    reason: str,
    evidence_packet: PulseEvidencePacket | dict[str, Any],
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
        abstain_reason="invalid_unknown_evidence_ref",
        summary_zh="模型输出引用了证据包外的 ref，本次不发布候选。",
        narrative_archetype="unclear",
        narrative_thesis_zh="模型输出包含证据包以外的引用，违反封闭证据合同；本次仅记录无效输出并等待下一轮有效证据综合。",
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
            "outside allowed_evidence_refs",
        )
    )


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


def _extract_usage(result: Any) -> dict[str, Any]:
    for candidate in _usage_candidates(result):
        payload = _usage_payload(candidate)
        if payload:
            return payload
    return {}


def _usage_candidates(result: Any) -> list[Any]:
    if result is None:
        return []
    candidates = [
        getattr(result, "usage", None),
        getattr(getattr(result, "context_wrapper", None), "usage", None),
    ]
    for attr in ("raw_response", "response", "final_response"):
        response = getattr(result, attr, None)
        candidates.append(getattr(response, "usage", None))
        candidates.append(response)
    responses = getattr(result, "raw_responses", None) or getattr(result, "responses", None)
    if isinstance(responses, list | tuple):
        for response in responses:
            candidates.append(getattr(response, "usage", None))
            candidates.append(response)
    return candidates


def _usage_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        data = model_dump(mode="json")
        if isinstance(data, dict):
            return cast(dict[str, Any], _json_safe_usage(data))
    data = _json_safe_usage(value)
    if isinstance(data, dict):
        return data
    return {}


def _json_safe_usage(value: Any, *, depth: int = 0) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if depth > 8:
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_usage(item, depth=depth + 1) for key, item in value.items() if item is not None}
    if isinstance(value, list | tuple):
        return [_json_safe_usage(item, depth=depth + 1) for item in value if item is not None]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        data = model_dump(mode="json")
        return _json_safe_usage(data, depth=depth + 1)
    object_values = _public_object_values(value)
    if object_values:
        return {key: _json_safe_usage(item, depth=depth + 1) for key, item in object_values.items() if item is not None}
    return str(value)


def _public_object_values(value: Any) -> dict[str, Any]:
    if not hasattr(value, "__dict__") and not hasattr(value, "__slots__"):
        return {}
    data = {}
    if hasattr(value, "__dict__"):
        data.update(
            {str(key): item for key, item in vars(value).items() if not str(key).startswith("_") and item is not None}
        )
    slot_names = set(_public_slot_names(value))
    for name in slot_names:
        if name in data:
            continue
        try:
            item = getattr(value, name)
        except AttributeError:
            continue
        if item is not None:
            data[name] = item
    for name, item in inspect.getmembers_static(value):
        if name.startswith("_") or name in data:
            continue
        if isinstance(item, property | classmethod | staticmethod):
            continue
        if isinstance(item, GetSetDescriptorType | MemberDescriptorType):
            continue
        if item is None or callable(item):
            continue
        if isinstance(item, type):
            continue
        data[name] = item
    return data


def _public_slot_names(value: Any) -> tuple[str, ...]:
    names: list[str] = []
    for cls in type(value).__mro__:
        slots = getattr(cls, "__slots__", ())
        if isinstance(slots, str):
            slot_items = (slots,)
        else:
            try:
                slot_items = tuple(slots)
            except TypeError:
                continue
        for name in slot_items:
            text = str(name)
            if text.startswith("_") or text in {"__dict__", "__weakref__"}:
                continue
            names.append(text)
    return tuple(names)


__all__ = [
    "AGENT_NAME",
    "WORKFLOW_NAME",
    "OpenAIAgentsPulseDecisionClient",
    "PulseDecisionAgentResult",
    "_extract_usage",
]
