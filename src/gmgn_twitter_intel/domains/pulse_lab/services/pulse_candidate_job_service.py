from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from decimal import Decimal
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
    PulseAgentRuntimeContract,
    PulseDecisionProvider,
)
from gmgn_twitter_intel.domains.pulse_lab.services.agent_eval import (
    build_pulse_deterministic_eval_case,
    build_pulse_failed_eval_case,
    grade_pulse_deterministic_eval_case,
)
from gmgn_twitter_intel.domains.pulse_lab.services.agent_routing import route_decision_context
from gmgn_twitter_intel.domains.pulse_lab.services.agent_runtime import (
    PULSE_AGENT_STRATEGY,
    build_pulse_runtime_manifest,
    pulse_runtime_hash,
)
from gmgn_twitter_intel.domains.pulse_lab.services.claim_evidence_verifier import ClaimEvidenceVerifier
from gmgn_twitter_intel.domains.pulse_lab.services.decision_mapping import candidate_fields_from_decision
from gmgn_twitter_intel.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGate,
    EvidenceCompletenessGateResult,
)
from gmgn_twitter_intel.domains.pulse_lab.services.evidence_packet_builder import PulseEvidenceBuilder
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_agent_cost_guard import (
    PulseCostGuardDecision,
    decide_pulse_agent_cost,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import (
    PulseGateResult,
    PulseGateThresholds,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_freshness_health import PulseFreshnessHealthService
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_source_quality import PulseSourceQuality
from gmgn_twitter_intel.domains.pulse_lab.services.recommendation_clipper import clip_recommendation
from gmgn_twitter_intel.domains.pulse_lab.services.write_gate import PulseWriteGate
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import (
    BearCaseMemo,
    BullBearView,
    DecisionRoute,
    FinalDecision,
    PulseStageFailure,
    SignalAnalystMemo,
    StageRunAudit,
    TradePlaybook,
)
from gmgn_twitter_intel.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_state import run_outcome_from_failure
from gmgn_twitter_intel.platform.agent_execution import (
    AgentCapacityReservation,
    AgentExecutionErrorClass,
)
from gmgn_twitter_intel.platform.cancellation import is_worker_hard_timeout_cancelled

_PLAYBOOK_STATUSES = {"trade_candidate", "token_watch", "risk_rejected_high_info"}
_NO_START_BACKPRESSURE_CLASSES = {
    AgentExecutionErrorClass.CAPACITY_DENIED,
    AgentExecutionErrorClass.CIRCUIT_OPEN,
    AgentExecutionErrorClass.RATE_LIMITED,
    AgentExecutionErrorClass.PROVIDER_ERROR,
    AgentExecutionErrorClass.TRANSPORT_ERROR,
}
_FINGERPRINT_REUSE_TTL_MS = 24 * 60 * 60 * 1000


class PulseAgentBackpressureReleased(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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

    async def run_job(
        self,
        job: dict[str, Any],
        context: PulseCandidateContext,
        *,
        now_ms: int,
        parent_reservation: AgentCapacityReservation | None = None,
    ) -> None:
        run_id = ""
        audit: dict[str, Any] | None = None
        agent_context: dict[str, Any] = {}
        route: DecisionRoute = "research_only"
        completeness_json: dict[str, Any] = {}
        runtime_hash = ""
        run_started = False
        evidence_packet: PulseEvidencePacket | None = None
        evidence_gate: EvidenceCompletenessGateResult | None = None
        cost_guard: PulseCostGuardDecision | None = None
        terminal_run: dict[str, Any] | None = None
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
            route = route_decision_context(context.agent_context())
            provider = self.decision_client.provider
            lane_models = _pulse_lane_models(self.decision_client)
            model = lane_models["pulse.pipeline"]
            artifact_version_hash = _artifact_hash(self.decision_client)
            runtime_manifest = build_pulse_runtime_manifest(
                provider=provider,
                model=model,
                artifact_version_hash=artifact_version_hash,
                timeout_seconds=float(self.decision_client.timeout_seconds),
                **_runtime_contract_from_client(self.decision_client),
            )
            runtime_hash = pulse_runtime_hash(runtime_manifest)
            pre_stage_audits: tuple[StageRunAudit, ...]
            with self._repository_session() as repos, _transaction(repos.conn):
                evidence_packet = PulseEvidenceBuilder(repos.pulse_evidence_sources).build(
                    context,
                    run_id=run_id,
                    now_ms=now_ms,
                )
                evidence_gate = EvidenceCompletenessGate().evaluate(evidence_packet)
                source_quality = PulseSourceQuality().evaluate(
                    factor_snapshot=context.factor_snapshot,
                    window=context.window,
                    scope=context.scope,
                )
                completeness_json = {**evidence_gate.to_json(), "route": route}
                agent_context_base = {
                    **context.agent_context(),
                    "evidence_packet": evidence_packet.model_dump(mode="json"),
                    "evidence_packet_hash": evidence_packet.evidence_packet_hash,
                    "evidence_gate": completeness_json,
                }
                preliminary_cost_guard = decide_pulse_agent_cost(
                    context=context,
                    evidence_gate=evidence_gate,
                    gate=gate,
                    source_quality=source_quality,
                    runtime_hash=runtime_hash,
                    evidence_packet_hash=evidence_packet.evidence_packet_hash,
                    lane_models=lane_models,
                    terminal_fingerprint_found=False,
                    provider_cooldown_until_ms=None,
                    now_ms=now_ms,
                )
                terminal_run = repos.pulse_runs.terminal_run_for_fingerprint(
                    candidate_id=context.candidate_id,
                    fingerprint_json=preliminary_cost_guard.fingerprint.to_json(),
                    since_ms=max(0, int(now_ms) - _FINGERPRINT_REUSE_TTL_MS),
                )
                cost_guard = decide_pulse_agent_cost(
                    context=context,
                    evidence_gate=evidence_gate,
                    gate=gate,
                    source_quality=source_quality,
                    runtime_hash=runtime_hash,
                    evidence_packet_hash=evidence_packet.evidence_packet_hash,
                    lane_models=lane_models,
                    terminal_fingerprint_found=terminal_run is not None,
                    provider_cooldown_until_ms=None,
                    now_ms=now_ms,
                )
                agent_context = {
                    **agent_context_base,
                    "cost_guard": _cost_guard_request_json(cost_guard, terminal_run=terminal_run),
                }
                audit = self.decision_client.request_audit(
                    context=agent_context,
                    run_id=run_id,
                    job=job,
                    route=route,
                    completeness=completeness_json,
                    runtime_manifest=runtime_manifest,
                )
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
                repos.pulse_evidence.upsert_packet(evidence_packet, commit=False)
                pre_stage_audits = (
                    _deterministic_stage_audit(
                        stage="evidence_pack",
                        route=route,
                        input_json={"candidate_id": context.candidate_id, "source_event_ids": context.source_event_ids},
                        response_json=evidence_packet.model_dump(mode="json"),
                        trace_metadata_json=audit.get("trace_metadata") or {},
                        started_at_ms=now_ms,
                        finished_at_ms=now_ms,
                    ),
                    _deterministic_stage_audit(
                        stage="evidence_completeness_gate",
                        route=route,
                        input_json={"evidence_packet_hash": evidence_packet.evidence_packet_hash},
                        response_json=completeness_json,
                        trace_metadata_json=audit.get("trace_metadata") or {},
                        started_at_ms=now_ms,
                        finished_at_ms=now_ms,
                    ),
                )
                for stage_audit in pre_stage_audits:
                    repos.pulse_runs.insert_agent_run_step(
                        step_id=_stable_id(run_id, stage_audit.stage, str(stage_audit.attempt_index)),
                        run_id=run_id,
                        stage=stage_audit.stage,
                        route=stage_audit.route,
                        attempt_index=stage_audit.attempt_index,
                        provider=provider,
                        model=model,
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
                        started_at_ms=stage_audit.started_at_ms,
                        finished_at_ms=stage_audit.finished_at_ms,
                        created_at_ms=now_ms,
                        commit=False,
                    )
            run_started = True
            stage_audits: tuple[StageRunAudit, ...]
            if cost_guard is not None and cost_guard.action == "no_llm_finalize":
                final_decision = _abstain_decision(
                    route=route,
                    reason=evidence_gate.blocked_reason or "evidence_completeness_blocked",
                    summary_zh="数据完整度不足，未进入资产决策。",
                    residual_risks=list(evidence_gate.missing_ref_types),
                    data_gap_refs=_packet_gate_refs(evidence_packet),
                )
                stage_audits = pre_stage_audits
                result_audit = audit
            elif cost_guard is not None and cost_guard.action == "reuse_terminal_run" and terminal_run is not None:
                final_decision = FinalDecision.model_validate(terminal_run.get("response_json") or {})
                stage_audits = pre_stage_audits
                result_audit = {**dict(audit or {}), "output_hash": terminal_run.get("output_hash"), "usage": {}}
            else:
                result = await self.decision_client.run_decision_pipeline(
                    context=agent_context,
                    run_id=run_id,
                    job=job,
                    route=route,
                    completeness=completeness_json,
                    runtime_manifest=runtime_manifest,
                    parent_reservation=parent_reservation,
                    stage_plan=cost_guard.stage_plan if cost_guard is not None else None,
                )
                final_decision = result.final_decision
                stage_audits = (*pre_stage_audits, *result.stage_audits)
                result_audit = result.agent_run_audit or audit
            final_decision = _preserve_gate_ceiling_decision(
                final_decision,
                gate=gate,
                route=route,
                evidence_packet=evidence_packet,
            )
            final_decision = clip_recommendation(final_decision, gate=gate, evidence_gate=evidence_gate)
            signal_memo, bear_memo = _committee_memos_from_stage_audits(stage_audits)
            claim_verification = ClaimEvidenceVerifier().verify(evidence_packet, signal_memo, bear_memo, final_decision)
            finished_at_ms = _now_ms()
            claim_stage = _deterministic_stage_audit(
                stage="claim_verifier",
                route=route,
                input_json={"evidence_packet_hash": evidence_packet.evidence_packet_hash},
                response_json=claim_verification.to_json(),
                trace_metadata_json=audit.get("trace_metadata") or {},
                started_at_ms=finished_at_ms,
                finished_at_ms=finished_at_ms,
            )
            clip_stage = _deterministic_stage_audit(
                stage="recommendation_clipper",
                route=route,
                input_json={"evidence_status": evidence_gate.evidence_status},
                response_json=final_decision.model_dump(mode="json"),
                trace_metadata_json=audit.get("trace_metadata") or {},
                started_at_ms=finished_at_ms,
                finished_at_ms=finished_at_ms,
            )
            stage_audits = (*stage_audits, claim_stage, clip_stage)
            decision_fields = candidate_fields_from_decision(final_decision, stage_count=len(stage_audits))
            decision_fields.pop("score_band", None)
            outcome = _run_outcome(
                final_decision,
                evidence_gate=evidence_gate,
                claim_verification_valid=claim_verification.valid,
                claim_verification=claim_verification,
            )
            run_usage_json = dict(result_audit.get("usage") or _aggregate_stage_usage(stage_audits))
            with self._repository_session() as repos, _transaction(repos.conn):
                for stage_audit in stage_audits[len(pre_stage_audits) :]:
                    repos.pulse_runs.insert_agent_run_step(
                        step_id=_stable_id(run_id, stage_audit.stage, str(stage_audit.attempt_index)),
                        run_id=run_id,
                        stage=stage_audit.stage,
                        route=stage_audit.route,
                        attempt_index=stage_audit.attempt_index,
                        provider=self.decision_client.provider,
                        model=_model_for_stage(stage_audit.stage, lane_models),
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
                        started_at_ms=_stage_started_at_ms(stage_audit, default_finished_at_ms=finished_at_ms),
                        finished_at_ms=_stage_finished_at_ms(stage_audit, default_finished_at_ms=finished_at_ms),
                        created_at_ms=finished_at_ms,
                        safety_net_used=stage_audit.safety_net_used,
                        safety_net_retries=stage_audit.safety_net_retries,
                        parse_mode=stage_audit.parse_mode,
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
                health_status = PulseFreshnessHealthService(repos.conn).health(
                    window=context.window,
                    scope=context.scope,
                    now_ms=finished_at_ms,
                    since_hours=4,
                )
                write_gate_decision = PulseWriteGate().evaluate(
                    final_decision=final_decision,
                    eval_result=eval_result,
                    gate=gate,
                    evidence_gate=evidence_gate,
                    claim_verification=claim_verification,
                    health_status=health_status,
                    source_quality=source_quality,
                )
                eval_result = _eval_result_with_write_gate(eval_result, write_gate_decision.to_json())
                repos.pulse_agent_eval.upsert_agent_eval_result(
                    **eval_result,
                    created_at_ms=finished_at_ms,
                    commit=False,
                )
                for stage_audit in (
                    _deterministic_stage_audit(
                        stage="deterministic_eval",
                        route=route,
                        input_json={"eval_case_id": stored_eval_case.get("eval_case_id")},
                        response_json=eval_result,
                        trace_metadata_json=audit.get("trace_metadata") or {},
                        started_at_ms=finished_at_ms,
                        finished_at_ms=finished_at_ms,
                    ),
                    _deterministic_stage_audit(
                        stage="write_gate",
                        route=route,
                        input_json={
                            "eval_result_id": eval_result.get("eval_result_id"),
                            "publish_status": health_status.get("publish_status"),
                        },
                        response_json=write_gate_decision.to_json(),
                        trace_metadata_json=audit.get("trace_metadata") or {},
                        started_at_ms=finished_at_ms,
                        finished_at_ms=finished_at_ms,
                    ),
                ):
                    repos.pulse_runs.insert_agent_run_step(
                        step_id=_stable_id(run_id, stage_audit.stage, str(stage_audit.attempt_index)),
                        run_id=run_id,
                        stage=stage_audit.stage,
                        route=stage_audit.route,
                        attempt_index=stage_audit.attempt_index,
                        provider=self.decision_client.provider,
                        model=_model_for_stage(stage_audit.stage, lane_models),
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
                        started_at_ms=stage_audit.started_at_ms,
                        finished_at_ms=stage_audit.finished_at_ms,
                        created_at_ms=finished_at_ms,
                        commit=False,
                    )
                    stage_audits = (*stage_audits, stage_audit)
                repos.pulse_runs.finish_agent_run(
                    run_id,
                    "done",
                    response_json=final_decision.model_dump(mode="json"),
                    output_hash=result_audit.get("output_hash") or _stable_hash(final_decision.model_dump(mode="json")),
                    usage_json=run_usage_json,
                    outcome=outcome,
                    decision_route=route,
                    decision_stage_count=len(stage_audits),
                    evidence_packet_id=evidence_packet.evidence_packet_id,
                    evidence_packet_hash=evidence_packet.evidence_packet_hash,
                    evidence_status=evidence_gate.evidence_status,
                    display_status=write_gate_decision.display_status,
                    finished_at_ms=finished_at_ms,
                    commit=False,
                )
                if write_gate_decision.write_allowed:
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
                        gate_json={
                            **gate.to_json(),
                            "source_quality": source_quality.to_json(),
                            "write_gate": write_gate_decision.to_json(),
                        },
                        **decision_fields,
                        gate_reasons_json=gate.gate_reasons,
                        risk_reasons_json=gate.risk_reasons,
                        evidence_event_ids_json=list(final_decision.evidence_event_ids or context.evidence_event_ids),
                        source_event_ids_json=context.source_event_ids,
                        last_edge_events_json=list(context.edge_events),
                        agent_run_id=run_id,
                        evidence_packet_hash=evidence_packet.evidence_packet_hash,
                        evidence_status=evidence_gate.evidence_status,
                        decision_status=write_gate_decision.decision_status,
                        display_status=write_gate_decision.display_status,
                        claim_verification_json=claim_verification.to_json(),
                        evidence_gate_json=completeness_json,
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
        except asyncio.CancelledError as exc:
            if not is_worker_hard_timeout_cancelled(exc):
                raise
            failed_at_ms = _now_ms()
            execution_started = _cancelled_execution_started(exc, run_started=run_started)
            with self._repository_session() as repos, _transaction(repos.conn):
                if run_started:
                    repos.pulse_runs.finish_agent_run(
                        run_id,
                        "failed",
                        error="worker_timeout_cancelled",
                        outcome="worker_timeout",
                        trace_metadata_json_patch={"failure_reason": "worker_timeout_cancelled"},
                        finished_at_ms=failed_at_ms,
                        commit=False,
                    )
                repos.pulse_jobs.mark_job_cancelled_by_worker_timeout(
                    job,
                    now_ms=failed_at_ms,
                    execution_started=execution_started,
                    commit=False,
                )
            raise
        except Exception as exc:
            backpressure_reason = _agent_no_start_backpressure_reason(exc)
            failed_at_ms = int(now_ms) if backpressure_reason else _now_ms()
            failure_reason = _normalized_failure_reason(exc)
            compact_error = _compact_error(exc)
            failed_audits: tuple[StageRunAudit, ...] = ()
            if isinstance(exc, PulseStageFailure):
                failed_audits = exc.audits
            with self._repository_session() as repos, _transaction(repos.conn):
                if backpressure_reason:
                    if audit is not None and run_started:
                        repos.pulse_runs.finish_agent_run(
                            run_id,
                            "skipped",
                            error=compact_error,
                            outcome=f"backpressure_{backpressure_reason}",
                            trace_metadata_json_patch={
                                "agent_backpressure": True,
                                "agent_error_class": backpressure_reason,
                            },
                            finished_at_ms=failed_at_ms,
                            commit=False,
                        )
                    cooldown_until_ms = failed_at_ms + _provider_cooldown_delay_ms(backpressure_reason)
                    repos.pulse_jobs.release_running_job_for_provider_cooldown(
                        job,
                        reason=f"provider_cooldown:{backpressure_reason}",
                        now_ms=failed_at_ms,
                        cooldown_until_ms=cooldown_until_ms,
                        commit=False,
                    )
                else:
                    for stage_audit in failed_audits:
                        repos.pulse_runs.insert_agent_run_step(
                            step_id=_stable_id(run_id, stage_audit.stage, str(stage_audit.attempt_index)),
                            run_id=run_id,
                            stage=stage_audit.stage,
                            route=stage_audit.route,
                            attempt_index=stage_audit.attempt_index,
                            provider=self.decision_client.provider,
                            model=_model_for_stage(stage_audit.stage, lane_models),
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
                            started_at_ms=_stage_started_at_ms(stage_audit, default_finished_at_ms=failed_at_ms),
                            finished_at_ms=_stage_finished_at_ms(stage_audit, default_finished_at_ms=failed_at_ms),
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
                            outcome=run_outcome_from_failure(failure_reason),
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
            if backpressure_reason:
                raise PulseAgentBackpressureReleased(backpressure_reason) from exc
            raise

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _runtime_contract_from_client(client: Any) -> dict[str, Any]:
    contract = client.runtime_contract
    if not isinstance(contract, PulseAgentRuntimeContract):
        raise RuntimeError("pulse_agent_runtime_contract_missing")
    if tuple(contract.stage_names) != ("signal_analyst", "bear_case", "risk_portfolio_judge"):
        raise RuntimeError("pulse_agent_runtime_contract_mismatch")
    kwargs = contract.manifest_kwargs()
    if not kwargs.get("failure_taxonomy_version"):
        raise RuntimeError("pulse_agent_failure_taxonomy_missing")
    return kwargs


def _pulse_lane_models(client: Any) -> dict[str, str]:
    lanes = (
        "pulse.pipeline",
        "pulse.signal_analyst",
        "pulse.bear_case",
        "pulse.risk_portfolio_judge",
    )
    models: dict[str, str] = {}
    for lane in lanes:
        model = str(client.model_for_lane(lane) or "").strip()
        if not model:
            raise RuntimeError(f"pulse_agent_lane_model_missing:{lane}")
        models[lane] = model
    return models


def _model_for_stage(stage: str, lane_models: dict[str, str]) -> str:
    lane = {
        "signal_analyst": "pulse.signal_analyst",
        "bear_case": "pulse.bear_case",
        "risk_portfolio_judge": "pulse.risk_portfolio_judge",
    }.get(str(stage), "pulse.pipeline")
    model = str(lane_models.get(lane) or "").strip()
    if not model:
        raise RuntimeError(f"pulse_agent_stage_model_missing:{stage}")
    return model


def _cost_guard_request_json(
    cost_guard: PulseCostGuardDecision,
    *,
    terminal_run: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = cost_guard.to_json()
    return {
        "decision": payload,
        "fingerprint": cost_guard.fingerprint.to_json(),
        "stage_plan": cost_guard.stage_plan.to_json(),
        "reused_run_id": str(terminal_run.get("run_id")) if terminal_run else None,
    }


def _eval_result_with_write_gate(eval_result: dict[str, Any], write_gate: dict[str, Any]) -> dict[str, Any]:
    details = dict(eval_result.get("details_json") or {})
    details["write_gate"] = write_gate
    return {**eval_result, "details_json": details}


def _deterministic_stage_audit(
    *,
    stage: str,
    route: DecisionRoute,
    input_json: dict[str, Any],
    response_json: dict[str, Any],
    trace_metadata_json: dict[str, Any],
    started_at_ms: int,
    finished_at_ms: int,
) -> StageRunAudit:
    return StageRunAudit(
        stage=cast(Any, stage),
        route=route,
        attempt_index=0,
        input_json=input_json,
        prompt_text=f"deterministic {stage}",
        response_json=response_json,
        trace_metadata_json=trace_metadata_json,
        usage_json={},
        latency_ms=max(0, int(finished_at_ms) - int(started_at_ms)),
        started_at_ms=int(started_at_ms),
        finished_at_ms=int(finished_at_ms),
        status="ok",
        error=None,
    )


def _committee_memos_from_stage_audits(
    stage_audits: tuple[StageRunAudit, ...],
) -> tuple[SignalAnalystMemo, BearCaseMemo]:
    signal_memo = SignalAnalystMemo(
        bull_claims=(),
        what_changed_zh="证据门未允许进入 LLM 信号分析，本次只保留确定性证据缺口。",
        allowed_evidence_ref_ids=(),
    )
    bear_memo = BearCaseMemo(
        risk_claims=(),
        confidence_ceiling=0.0,
        missing_fact_impacts=(),
        allowed_evidence_ref_ids=(),
    )
    for stage_audit in stage_audits:
        if stage_audit.stage == "signal_analyst" and stage_audit.response_json:
            signal_memo = SignalAnalystMemo.model_validate(stage_audit.response_json)
        elif stage_audit.stage == "bear_case" and stage_audit.response_json:
            bear_memo = BearCaseMemo.model_validate(stage_audit.response_json)
    return signal_memo, bear_memo


def _packet_gate_refs(packet: PulseEvidencePacket) -> list[str]:
    return [ref.ref_id for ref in packet.allowed_evidence_refs if ref.ref_type == "gate"]


def _stage_finished_at_ms(stage_audit: StageRunAudit, *, default_finished_at_ms: int) -> int:
    value = stage_audit.finished_at_ms
    if value is not None:
        return int(value)
    return int(default_finished_at_ms)


def _stage_started_at_ms(stage_audit: StageRunAudit, *, default_finished_at_ms: int) -> int:
    value = stage_audit.started_at_ms
    if value is not None:
        return int(value)
    finished_at_ms = _stage_finished_at_ms(stage_audit, default_finished_at_ms=default_finished_at_ms)
    return max(0, finished_at_ms - int(stage_audit.latency_ms or 0))


def _aggregate_stage_usage(stage_audits: tuple[StageRunAudit, ...]) -> dict[str, Any]:
    totals: dict[str, int | float] = {}
    for stage_audit in stage_audits:
        for key, value in stage_audit.usage_json.items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            totals[key] = totals.get(key, 0) + value
    return totals


def _compact_error(exc: Exception, *, limit: int = 500) -> str:
    text = " ".join(str(exc).split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _normalized_failure_reason(exc: Exception) -> str:
    stage_error_class = _stage_failure_error_class(exc)
    if stage_error_class == "timeout":
        return "timeout"
    if stage_error_class == "rate_limited":
        return "provider_rate_limited"
    if stage_error_class in {"transport_error", "provider_error"}:
        return "provider_unavailable"
    if stage_error_class in {"schema_invalid", "domain_validation_failed"}:
        return "invalid_schema"
    text = str(exc).lower()
    if "unknown evidence" in text or "unknown final evidence" in text or "unknown event ids" in text:
        return "invalid_unknown_evidence_ref"
    if "model_validate" in text or "validation" in text or "schema" in text:
        return "invalid_schema"
    if isinstance(exc, TimeoutError) or "timed out" in text:
        return "timeout"
    if "rate limit" in text or "429" in text:
        return "provider_rate_limited"
    if "provider unavailable" in text or "503" in text:
        return "provider_unavailable"
    return "unexpected_exception"


def _stage_failure_error_class(exc: Exception) -> str | None:
    if not isinstance(exc, PulseStageFailure):
        return None
    for audit in reversed(exc.audits):
        trace = audit.trace_metadata_json
        raw = trace.get("error_class") if isinstance(trace, dict) else None
        if raw:
            return str(raw).strip().lower()
        if audit.status == "timeout":
            return "timeout"
    return None


def _agent_no_start_backpressure_reason(exc: Exception) -> str | None:
    error_class = _agent_error_class(exc)
    if error_class not in _NO_START_BACKPRESSURE_CLASSES:
        return None
    execution_started = getattr(exc, "execution_started", None)
    if execution_started is None and isinstance(exc, PulseStageFailure):
        execution_started = getattr(exc, "agent_execution_started", None)
    if execution_started is None:
        audit = getattr(exc, "audit", None) or getattr(exc, "agent_audit", None)
        if isinstance(audit, dict):
            execution_started = audit.get("execution_started")
        else:
            execution_started = getattr(audit, "execution_started", None)
    if execution_started is not False:
        return None
    return str(error_class.value if isinstance(error_class, AgentExecutionErrorClass) else error_class)


def _provider_cooldown_delay_ms(reason: str) -> int:
    normalized = str(reason or "").strip().lower()
    if normalized in {"provider_error", "transport_error"}:
        return 300_000
    if normalized in {"circuit_open", "capacity_denied", "rate_limited"}:
        return 120_000
    return 120_000


def _cancelled_execution_started(exc: asyncio.CancelledError, *, run_started: bool) -> bool:
    execution_started = getattr(exc, "execution_started", None)
    if execution_started is None:
        audit = getattr(exc, "audit", None) or getattr(exc, "agent_audit", None)
        if isinstance(audit, dict):
            execution_started = audit.get("execution_started")
        else:
            execution_started = getattr(audit, "execution_started", None)
    if execution_started is None:
        return bool(run_started)
    return bool(execution_started)


def _agent_error_class(exc: Exception) -> AgentExecutionErrorClass | None:
    raw = getattr(exc, "error_class", None)
    if raw is None and isinstance(exc, PulseStageFailure):
        raw = getattr(exc, "agent_error_class", None)
    if raw is None:
        audit = getattr(exc, "audit", None) or getattr(exc, "agent_audit", None)
        raw = audit.get("error_class") if isinstance(audit, dict) else getattr(audit, "error_class", None)
    if isinstance(raw, AgentExecutionErrorClass):
        return raw
    try:
        return AgentExecutionErrorClass(str(raw))
    except (TypeError, ValueError):
        return None


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
    data_gap_refs: list[str] | None = None,
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
        data_gap_refs=tuple(data_gap_refs or []),
    )


def _preserve_gate_ceiling_decision(
    final_decision: FinalDecision,
    *,
    gate: PulseGateResult,
    route: DecisionRoute,
    evidence_packet: PulseEvidencePacket,
) -> FinalDecision:
    if (
        gate.pulse_status != "risk_rejected_high_info"
        or final_decision.recommendation != "abstain"
        or final_decision.abstain_reason != "cost_guard_research_only"
    ):
        return final_decision
    ref = _first_allowed_ref(evidence_packet)
    refs = (ref,) if ref else tuple()
    reason = (gate.risk_reasons or gate.hard_risks or ["risk_rejected_high_info"])[0]
    return FinalDecision(
        route=route,
        recommendation="ignore",
        confidence=0.0,
        abstain_reason=None,
        summary_zh="因子门控识别为高信息风险拒绝，本次不进入付费最终判断。",
        narrative_archetype="risk_rejected",
        narrative_thesis_zh="确定性因子门控显示风险条件优先；系统保留研究审计并将候选限制为风险拒绝状态。",
        bull_view=BullBearView(strength="absent"),
        bear_view=BullBearView(strength="moderate", thesis_zh=str(reason)),
        playbook=TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon="1h",
        ),
        invalidation_conditions=[],
        residual_risks=list(gate.risk_reasons or gate.hard_risks or [reason]),
        evidence_event_ids=[],
        supporting_evidence_refs=refs,
        risk_evidence_refs=refs,
        data_gap_refs=tuple(),
    )


def _first_allowed_ref(packet: PulseEvidencePacket) -> str | None:
    for ref in packet.allowed_evidence_refs:
        if ref.ref_id:
            return ref.ref_id
    return None


def _run_outcome(
    final_decision: FinalDecision,
    *,
    evidence_gate: EvidenceCompletenessGateResult,
    claim_verification_valid: bool,
    claim_verification: Any | None = None,
) -> str:
    if not claim_verification_valid:
        unknown_refs = tuple(getattr(claim_verification, "unknown_ref_ids", ()) or ())
        if unknown_refs:
            return "invalid_unknown_evidence_ref"
        return "invalid_unsupported_claim"
    if evidence_gate.hard_blocked:
        return run_outcome_from_failure(evidence_gate.blocked_reason or "insufficient_evidence")
    if final_decision.recommendation == "abstain":
        if final_decision.abstain_reason == "invalid_unknown_evidence_ref":
            return "invalid_unknown_evidence_ref"
        return "abstain_insufficient_evidence"
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
        post_clusters=context.post_clusters,
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
    artifact_version_hash = str(client.artifact_version_hash or "").strip()
    if not artifact_version_hash:
        raise RuntimeError("pulse_agent_artifact_hash_missing")
    return artifact_version_hash


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
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
