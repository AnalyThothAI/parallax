from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import Any, cast

from gmgn_twitter_intel.domains.pulse_lab.interfaces import (
    AGENT_NAME,
    BACKEND,
    PULSE_DECISION_PROMPT_VERSION,
    PULSE_DECISION_SCHEMA_VERSION,
    PULSE_GATE_VERSION,
    PULSE_PLAYBOOK_VERSION,
    PULSE_VERSION,
    WORKFLOW_NAME,
)
from gmgn_twitter_intel.domains.pulse_lab.providers import (
    DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT,
    PulseAgentRuntimeContract,
    PulseDecisionProvider,
)
from gmgn_twitter_intel.domains.pulse_lab.services.agent_eval import (
    build_pulse_deterministic_eval_case,
    build_pulse_failed_eval_case,
    grade_pulse_deterministic_eval_case,
)
from gmgn_twitter_intel.domains.pulse_lab.services.agent_routing import compute_completeness, route_decision_context
from gmgn_twitter_intel.domains.pulse_lab.services.agent_runtime import (
    PULSE_AGENT_STRATEGY,
    PULSE_FAILURE_TAXONOMY_VERSION,
    build_pulse_runtime_manifest,
    pulse_runtime_hash,
)
from gmgn_twitter_intel.domains.pulse_lab.services.decision_mapping import candidate_fields_from_decision
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import (
    PulseGateResult,
    PulseGateThresholds,
)
from gmgn_twitter_intel.domains.pulse_lab.services.recommendation_clipper import clip_recommendation
from gmgn_twitter_intel.domains.pulse_lab.services.write_gate import PulseWriteGate
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BullBearView,
    DecisionRoute,
    FinalDecision,
    PulseStageFailure,
    StageRunAudit,
    TradePlaybook,
)
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext

_PLAYBOOK_STATUSES = {"trade_candidate", "token_watch", "risk_rejected_high_info"}


class PulseCandidateJobService:
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        decision_client: PulseDecisionProvider,
        gate_func: Callable[..., PulseGateResult],
        gate_thresholds: PulseGateThresholds,
    ) -> None:
        self.name = name
        self.settings = settings
        self.db = db
        self.decision_client = decision_client
        self.gate_func = gate_func
        self.gate_thresholds = gate_thresholds

    async def run_job(self, job: dict[str, Any], context: PulseCandidateContext, *, now_ms: int) -> None:
        run_id = ""
        audit: dict[str, Any] | None = None
        agent_context: dict[str, Any] = {}
        route: DecisionRoute = "research_only"
        completeness_json: dict[str, Any] = {}
        runtime_hash = ""
        run_started = False
        try:
            run_id = _prefixed_id(
                "pulse-run",
                str(job.get("job_id") or ""),
                str(job.get("trigger_signature") or ""),
                str(job.get("timeline_signature") or ""),
                str(job.get("attempt_count") or 0),
                str(now_ms),
            )
            gate = self.gate_func(
                factor_snapshot=context.factor_snapshot,
                thresholds=self.gate_thresholds,
            )
            context = _context_with_gate(context, gate)
            agent_context = context.agent_context()
            route = route_decision_context(agent_context)
            completeness = compute_completeness(context.factor_snapshot, route=route)
            completeness_json = {
                "route": completeness.route,
                "score": completeness.score,
                "hard_blocked": completeness.hard_blocked,
                "missing_fields": list(completeness.missing_fields),
                "stale_fields": list(completeness.stale_fields),
                "blockers": list(completeness.blockers),
            }
            provider = getattr(self.decision_client, "provider", "openai")
            model = getattr(self.decision_client, "model", "")
            artifact_version_hash = _artifact_hash(self.decision_client)
            runtime_manifest = build_pulse_runtime_manifest(
                provider=provider,
                model=model,
                artifact_version_hash=artifact_version_hash,
                timeout_seconds=float(getattr(self.decision_client, "timeout_seconds", 30.0) or 30.0),
                **_runtime_contract_from_client(self.decision_client),
            )
            runtime_hash = pulse_runtime_hash(runtime_manifest)
            audit = self.decision_client.request_audit(
                context=agent_context,
                run_id=run_id,
                job=job,
                route=route,
                completeness=completeness_json,
                runtime_manifest=runtime_manifest,
            )
            with self._repository_session() as repos, _transaction(repos.conn):
                repos.pulse_agent_eval.upsert_agent_runtime_version(
                    runtime_version=str(runtime_manifest["runtime_version"]),
                    runtime_hash=runtime_hash,
                    strategy=PULSE_AGENT_STRATEGY,
                    provider=provider,
                    model=model,
                    prompt_version=PULSE_DECISION_PROMPT_VERSION,
                    schema_version=PULSE_DECISION_SCHEMA_VERSION,
                    manifest_json=runtime_manifest,
                    created_at_ms=now_ms,
                    commit=False,
                )
                repos.pulse_runs.insert_agent_run(
                    run_id=run_id,
                    job_id=str(job["job_id"]),
                    candidate_id=context.candidate_id,
                    provider=provider,
                    model=model,
                    backend=str(audit.get("backend") or BACKEND),
                    sdk_trace_id=audit.get("sdk_trace_id"),
                    workflow_name=str(audit.get("workflow_name") or WORKFLOW_NAME),
                    agent_name=str(audit.get("agent_name") or AGENT_NAME),
                    artifact_version_hash=str(
                        audit.get("artifact_version_hash") or _artifact_hash(self.decision_client)
                    ),
                    prompt_version=str(audit.get("prompt_version") or PULSE_DECISION_PROMPT_VERSION),
                    schema_version=str(audit.get("schema_version") or PULSE_DECISION_SCHEMA_VERSION),
                    runtime_version=str(runtime_manifest["runtime_version"]),
                    runtime_hash=runtime_hash,
                    input_hash=str(audit.get("input_hash") or _stable_hash(agent_context)),
                    trace_metadata_json=audit.get("trace_metadata") or {},
                    usage_json=audit.get("usage") or {},
                    status="running",
                    outcome="running",
                    decision_route=route,
                    decision_stage_count=0,
                    request_json=agent_context,
                    started_at_ms=now_ms,
                    commit=False,
                )
            run_started = True
            if completeness.hard_blocked:
                gate_step_started_at_ms = _now_ms()
                final_decision = _abstain_decision(
                    route=route,
                    reason=(completeness.blockers[0] if completeness.blockers else "data_completeness_blocked"),
                    summary_zh="数据完整度不足，未进入资产决策。",
                    residual_risks=list(completeness.blockers),
                )
                gate_step_finished_at_ms = _now_ms()
                stage_audits: tuple[StageRunAudit, ...] = (
                    StageRunAudit(
                        stage="research_only_gate",
                        route=route,
                        attempt_index=0,
                        input_json={"context": agent_context, "completeness": completeness_json},
                        prompt_text="deterministic completeness gate",
                        response_json=final_decision.model_dump(mode="json"),
                        trace_metadata_json=audit.get("trace_metadata") or {},
                        usage_json={},
                        latency_ms=max(0, gate_step_finished_at_ms - gate_step_started_at_ms),
                        started_at_ms=gate_step_started_at_ms,
                        finished_at_ms=gate_step_finished_at_ms,
                        status="skipped",
                        error=None,
                    ),
                )
                result_audit = audit
            else:
                timeout_seconds = max(0.1, float(getattr(self.decision_client, "timeout_seconds", 30.0) or 30.0))
                try:
                    result = await asyncio.wait_for(
                        self.decision_client.run_decision_pipeline(
                            context=agent_context,
                            run_id=run_id,
                            job=job,
                            route=route,
                            completeness=completeness_json,
                            runtime_manifest=runtime_manifest,
                        ),
                        timeout=timeout_seconds,
                    )
                except TimeoutError as exc:
                    raise TimeoutError(f"Agents SDK request timed out after {timeout_seconds:g}s") from exc
                final_decision = result.final_decision
                stage_audits = result.stage_audits
                result_audit = result.agent_run_audit or audit
            final_decision = clip_recommendation(final_decision, gate=gate)
            finished_at_ms = _now_ms()
            decision_fields = candidate_fields_from_decision(final_decision, stage_count=len(stage_audits))
            decision_fields.pop("score_band", None)
            outcome = _run_outcome(final_decision, completeness_blocked=completeness.hard_blocked)
            investigation_tool_calls_count = _investigation_tool_calls_count(stage_audits)
            run_usage_json = dict(result_audit.get("usage") or _aggregate_stage_usage(stage_audits))
            run_usage_json["investigation_tool_calls_count"] = investigation_tool_calls_count
            with self._repository_session() as repos, _transaction(repos.conn):
                for stage_audit in stage_audits:
                    repos.pulse_runs.insert_agent_run_step(
                        step_id=_stable_id(run_id, stage_audit.stage, str(stage_audit.attempt_index)),
                        run_id=run_id,
                        stage=stage_audit.stage,
                        route=stage_audit.route,
                        attempt_index=stage_audit.attempt_index,
                        provider=getattr(self.decision_client, "provider", "openai"),
                        model=getattr(self.decision_client, "model", ""),
                        prompt_version=str(audit.get("prompt_version") or PULSE_DECISION_PROMPT_VERSION),
                        schema_version=str(audit.get("schema_version") or PULSE_DECISION_SCHEMA_VERSION),
                        input_json=stage_audit.input_json,
                        prompt_text=stage_audit.prompt_text,
                        response_json=stage_audit.response_json,
                        trace_metadata_json=stage_audit.trace_metadata_json,
                        usage_json=stage_audit.usage_json,
                        latency_ms=stage_audit.latency_ms,
                        status=stage_audit.status,
                        error=stage_audit.error,
                        started_at_ms=_stage_started_at_ms(stage_audit, fallback_finished_at_ms=finished_at_ms),
                        finished_at_ms=_stage_finished_at_ms(stage_audit, fallback_finished_at_ms=finished_at_ms),
                        created_at_ms=finished_at_ms,
                        safety_net_used=stage_audit.safety_net_used,
                        safety_net_retries=stage_audit.safety_net_retries,
                        parse_mode=stage_audit.parse_mode,
                        commit=False,
                    )
                repos.pulse_runs.finish_agent_run(
                    run_id,
                    "done",
                    response_json=final_decision.model_dump(mode="json"),
                    output_hash=result_audit.get("output_hash") or _stable_hash(final_decision.model_dump(mode="json")),
                    usage_json=run_usage_json,
                    outcome=outcome,
                    decision_route=route,
                    decision_stage_count=len(stage_audits),
                    finished_at_ms=finished_at_ms,
                    commit=False,
                )
                eval_case = build_pulse_deterministic_eval_case(
                    run_id=run_id,
                    runtime_hash=runtime_hash,
                    context=agent_context,
                    route=route,
                    completeness=completeness_json,
                    final_decision=final_decision,
                    stage_audits=tuple(stage_audits),
                )
                stored_eval_case = repos.pulse_agent_eval.insert_agent_eval_case(
                    **eval_case,
                    status="active",
                    created_at_ms=finished_at_ms,
                    commit=False,
                )
                eval_result = grade_pulse_deterministic_eval_case(stored_eval_case)
                write_gate_decision = PulseWriteGate().evaluate(
                    final_decision=final_decision,
                    eval_result=eval_result,
                    gate=gate,
                )
                eval_result = _eval_result_with_write_gate(eval_result, write_gate_decision.to_json())
                repos.pulse_agent_eval.upsert_agent_eval_result(
                    **eval_result,
                    created_at_ms=finished_at_ms,
                    commit=False,
                )
                if write_gate_decision.public_write_allowed:
                    repos.pulse_candidates.upsert_candidate(
                        candidate_id=context.candidate_id,
                        candidate_type=context.candidate_type,
                        subject_key=context.subject_key,
                        target_type=context.target_type,
                        target_id=context.target_id,
                        symbol=context.symbol,
                        window=context.window,
                        scope=context.scope,
                        pulse_status=gate.pulse_status,
                        verdict=gate.verdict,
                        social_phase=_social_phase_from_snapshot(context.factor_snapshot),
                        candidate_score=gate.candidate_score,
                        score_band=gate.score_band,
                        trigger_signature=context.trigger_signature,
                        timeline_signature=context.timeline_signature,
                        factor_snapshot_json=context.factor_snapshot,
                        gate_json={**gate.to_json(), "write_gate": write_gate_decision.to_json()},
                        **decision_fields,
                        gate_reasons_json=gate.gate_reasons,
                        risk_reasons_json=gate.risk_reasons,
                        evidence_event_ids_json=list(final_decision.evidence_event_ids or context.evidence_event_ids),
                        source_event_ids_json=context.source_event_ids,
                        last_edge_events_json=list(context.edge_events),
                        agent_run_id=run_id,
                        pulse_version=PULSE_VERSION,
                        gate_version=PULSE_GATE_VERSION,
                        prompt_version=PULSE_DECISION_PROMPT_VERSION,
                        schema_version=PULSE_DECISION_SCHEMA_VERSION,
                        updated_at_ms=finished_at_ms,
                        commit=False,
                    )
                if write_gate_decision.playbook_write_allowed:
                    repos.pulse_playbooks.upsert_playbook_snapshot(
                        **_playbook_snapshot_payload(
                            context=context,
                            gate=gate,
                            final_decision=final_decision,
                            now_ms=now_ms,
                        ),
                        commit=False,
                    )
                repos.pulse_admission.mark_edge_run_finished(
                    candidate_id=context.candidate_id,
                    agent_run_id=run_id,
                    processed_state_json=context.edge_state or {},
                    edge_events_json=list(context.edge_events),
                    finished_at_ms=finished_at_ms,
                    commit=False,
                )
                repos.pulse_jobs.mark_job_succeeded(str(job["job_id"]), now_ms=finished_at_ms, commit=False)
        except Exception as exc:
            failed_at_ms = _now_ms()
            failure_reason = _normalized_failure_reason(exc)
            compact_error = _compact_error(exc)
            failed_audits: tuple[StageRunAudit, ...] = ()
            if isinstance(exc, PulseStageFailure):
                failed_audits = exc.audits
            with self._repository_session() as repos, _transaction(repos.conn):
                for stage_audit in failed_audits:
                    repos.pulse_runs.insert_agent_run_step(
                        step_id=_stable_id(run_id, stage_audit.stage, str(stage_audit.attempt_index)),
                        run_id=run_id,
                        stage=stage_audit.stage,
                        route=stage_audit.route,
                        attempt_index=stage_audit.attempt_index,
                        provider=getattr(self.decision_client, "provider", "openai"),
                        model=getattr(self.decision_client, "model", ""),
                        prompt_version=str(audit.get("prompt_version") if audit else PULSE_DECISION_PROMPT_VERSION),
                        schema_version=str(audit.get("schema_version") if audit else PULSE_DECISION_SCHEMA_VERSION),
                        input_json=stage_audit.input_json,
                        prompt_text=stage_audit.prompt_text,
                        response_json=stage_audit.response_json,
                        trace_metadata_json=stage_audit.trace_metadata_json,
                        usage_json=stage_audit.usage_json,
                        latency_ms=stage_audit.latency_ms,
                        status=stage_audit.status,
                        error=stage_audit.error,
                        started_at_ms=_stage_started_at_ms(stage_audit, fallback_finished_at_ms=failed_at_ms),
                        finished_at_ms=_stage_finished_at_ms(stage_audit, fallback_finished_at_ms=failed_at_ms),
                        created_at_ms=failed_at_ms,
                        safety_net_used=stage_audit.safety_net_used,
                        safety_net_retries=stage_audit.safety_net_retries,
                        parse_mode=stage_audit.parse_mode,
                        commit=False,
                    )
                if audit is not None and run_started:
                    repos.pulse_runs.finish_agent_run(
                        run_id,
                        "failed",
                        error=compact_error,
                        outcome="failed",
                        trace_metadata_json_patch={"failure_reason": failure_reason},
                        finished_at_ms=failed_at_ms,
                        commit=False,
                    )
                    eval_case = build_pulse_failed_eval_case(
                        run_id=run_id,
                        runtime_hash=runtime_hash,
                        context=agent_context,
                        route=route,
                        completeness=completeness_json,
                        stage_audits=failed_audits,
                        failure_reason=failure_reason,
                    )
                    stored_eval_case = repos.pulse_agent_eval.insert_agent_eval_case(
                        **eval_case,
                        status="active",
                        created_at_ms=failed_at_ms,
                        commit=False,
                    )
                    eval_result = grade_pulse_deterministic_eval_case(stored_eval_case)
                    repos.pulse_agent_eval.upsert_agent_eval_result(
                        **eval_result,
                        created_at_ms=failed_at_ms,
                        commit=False,
                    )
                repos.pulse_jobs.mark_job_failed(
                    job,
                    compact_error,
                    now_ms=failed_at_ms,
                    failure_reason=failure_reason,
                    commit=False,
                )
            raise

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _runtime_contract_from_client(client: Any) -> dict[str, Any]:
    contract = getattr(client, "runtime_contract", DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT)
    if callable(contract):
        contract = contract()
    if not isinstance(contract, PulseAgentRuntimeContract):
        contract = DEFAULT_PULSE_AGENT_RUNTIME_CONTRACT
    kwargs = contract.manifest_kwargs()
    if not kwargs.get("failure_taxonomy_version"):
        kwargs["failure_taxonomy_version"] = PULSE_FAILURE_TAXONOMY_VERSION
    return kwargs


def _eval_result_with_write_gate(eval_result: dict[str, Any], write_gate: dict[str, Any]) -> dict[str, Any]:
    details = dict(eval_result.get("details_json") or {})
    details["write_gate"] = write_gate
    return {**eval_result, "details_json": details}


def _stage_finished_at_ms(stage_audit: StageRunAudit, *, fallback_finished_at_ms: int) -> int:
    value = stage_audit.finished_at_ms
    if value is not None:
        return int(value)
    return int(fallback_finished_at_ms)


def _stage_started_at_ms(stage_audit: StageRunAudit, *, fallback_finished_at_ms: int) -> int:
    value = stage_audit.started_at_ms
    if value is not None:
        return int(value)
    finished_at_ms = _stage_finished_at_ms(stage_audit, fallback_finished_at_ms=fallback_finished_at_ms)
    return max(0, finished_at_ms - int(stage_audit.latency_ms or 0))


def _aggregate_stage_usage(stage_audits: tuple[StageRunAudit, ...]) -> dict[str, Any]:
    totals: dict[str, int | float] = {}
    for stage_audit in stage_audits:
        for key, value in stage_audit.usage_json.items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            totals[key] = totals.get(key, 0) + value
    return totals


def _investigation_tool_calls_count(stage_audits: tuple[StageRunAudit, ...]) -> int:
    if not stage_audits:
        return 0
    investigator = stage_audits[0]
    if investigator.stage != "investigator":
        return 0
    payload = investigator.input_json if isinstance(investigator.input_json, dict) else None
    tool_calls = payload.get("tool_calls") if payload else None
    if isinstance(tool_calls, list):
        return len(tool_calls)
    return 0


def _compact_error(exc: Exception, *, limit: int = 500) -> str:
    text = " ".join(str(exc).split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _normalized_failure_reason(exc: Exception) -> str:
    text = str(exc).lower()
    if "unknown evidence" in text or "unknown final evidence" in text or "unknown event ids" in text:
        return "unknown_evidence_id"
    if "model_validate" in text or "validation" in text or "schema" in text:
        return "schema_validation_failed"
    if "budget exceeded" in text:
        return "tool_budget_exceeded"
    if isinstance(exc, TimeoutError) or "timed out" in text:
        return "timeout"
    if "rate limit" in text or "429" in text:
        return "provider_rate_limited"
    if "provider unavailable" in text or "503" in text:
        return "provider_unavailable"
    if "stale_running_timeout" in text:
        return "stale_running_timeout"
    return "unexpected_exception"


def _playbook_snapshot_payload(
    *,
    context: PulseCandidateContext,
    gate: PulseGateResult,
    final_decision: FinalDecision,
    now_ms: int,
) -> dict[str, Any]:
    horizon = context.window
    return {
        "playbook_id": _stable_id("pulse-playbook", context.candidate_id, horizon, PULSE_PLAYBOOK_VERSION),
        "candidate_id": context.candidate_id,
        "target_type": context.target_type,
        "target_id": context.target_id,
        "horizon": horizon,
        "decision_time_ms": now_ms,
        "playbook_status": "shadow_only",
        "side": _playbook_side(gate.pulse_status),
        "setup": {
            "pulse_status": gate.pulse_status,
            "recommendation": final_decision.recommendation,
            "confidence": final_decision.confidence,
            "candidate_score": gate.candidate_score,
            "score_band": gate.score_band,
            "summary_zh": final_decision.summary_zh,
        },
        "confirmation": {
            "invalidation_conditions": list(final_decision.invalidation_conditions),
        },
        "invalidation": {
            "invalidation_conditions": list(final_decision.invalidation_conditions),
        },
        "risk": {
            "residual_risks": list(final_decision.residual_risks),
            "risk_reasons": gate.risk_reasons,
            "hard_risks": gate.hard_risks,
        },
        "entry_market": _entry_market(context.factor_snapshot),
        "playbook_version": PULSE_PLAYBOOK_VERSION,
        "outcome_status": "pending",
        "created_at_ms": now_ms,
    }


def _abstain_decision(
    *,
    route: str,
    reason: str,
    summary_zh: str,
    residual_risks: list[str],
) -> FinalDecision:
    return FinalDecision(
        route=route,
        recommendation="abstain",
        confidence=0.0,
        abstain_reason=reason,
        summary_zh=summary_zh,
        narrative_archetype="unclear",
        narrative_thesis_zh=(
            "当前数据完整度不足，无法形成可靠叙事判断；本次仅记录确定性门控结果，等待更多事实信号后再评估。"
        ),
        bull_view=BullBearView(strength="absent"),
        bear_view=BullBearView(strength="absent"),
        playbook=TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon="1h",
        ),
        invalidation_conditions=[],
        residual_risks=residual_risks or [reason],
        evidence_event_ids=[],
    )


def _run_outcome(final_decision: FinalDecision, *, completeness_blocked: bool) -> str:
    if final_decision.recommendation == "abstain":
        if completeness_blocked:
            return "abstain_insufficient_data"
        return "abstain"
    return "completed"


def _playbook_side(status: str) -> str:
    if status == "trade_candidate":
        return "LONG_BIAS"
    if status == "risk_rejected_high_info":
        return "RISK_OFF"
    if status == "blocked_low_information":
        return "FLAT"
    return "OBSERVE_ONLY"


def _context_with_gate(
    context: PulseCandidateContext,
    gate: PulseGateResult,
    *,
    edge_state: dict[str, Any] | None = None,
    edge_events: list[str] | tuple[str, ...] | None = None,
) -> PulseCandidateContext:
    return PulseCandidateContext(
        candidate_id=context.candidate_id,
        candidate_type=context.candidate_type,
        subject_key=context.subject_key,
        window=context.window,
        scope=context.scope,
        trigger_signature=context.trigger_signature,
        timeline_signature=context.timeline_signature,
        priority=context.priority,
        target_type=context.target_type,
        target_id=context.target_id,
        symbol=context.symbol,
        factor_snapshot=context.factor_snapshot,
        selected_posts=context.selected_posts,
        gate_result=gate.to_json(),
        edge_state=edge_state if edge_state is not None else context.edge_state,
        edge_events=tuple(edge_events if edge_events is not None else context.edge_events),
        source_event_ids=context.source_event_ids,
        evidence_event_ids=context.evidence_event_ids,
    )


def _social_phase_from_snapshot(factor_snapshot: dict[str, Any]) -> str:
    semantic_facts = _mapping(_nested(factor_snapshot, "families", "semantic_catalyst", "facts"))
    timing_facts = _mapping(_nested(factor_snapshot, "families", "timing_risk", "facts"))
    return (
        _clean(semantic_facts.get("phase"))
        or _clean(semantic_facts.get("dominant_phase"))
        or _clean(timing_facts.get("phase"))
        or "unknown"
    )


def _entry_market(factor_snapshot: dict[str, Any]) -> dict[str, Any]:
    subject = _mapping(factor_snapshot.get("subject"))
    data_health = _mapping(factor_snapshot.get("data_health"))
    return {
        "target_market_type": subject.get("target_market_type"),
        "market_data_health": data_health.get("market"),
        "identity_data_health": data_health.get("identity"),
    }


def _nested(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    if hasattr(conn, "transaction"):
        return cast(AbstractContextManager[Any], conn.transaction())
    return nullcontext()


def _artifact_hash(client: Any) -> str:
    return str(getattr(client, "artifact_version_hash", "") or f"artifact:{getattr(client, 'model', '')}")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stable_id(*parts: str) -> str:
    return "pulse-" + hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:40]


def _prefixed_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:" + hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:40]


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
