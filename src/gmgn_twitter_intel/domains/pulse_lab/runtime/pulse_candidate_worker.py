from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any, cast

from loguru import logger

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
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
from gmgn_twitter_intel.domains.pulse_lab.providers import PulseDecisionProvider
from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness import (
    PULSE_AGENT_STRATEGY,
    build_pulse_harness_manifest,
    pulse_harness_hash,
)
from gmgn_twitter_intel.domains.pulse_lab.services.agent_harness_eval import (
    build_pulse_deterministic_eval_case,
    grade_pulse_deterministic_eval_case,
)
from gmgn_twitter_intel.domains.pulse_lab.services.agent_routing import compute_completeness, route_decision_context
from gmgn_twitter_intel.domains.pulse_lab.services.decision_mapping import candidate_fields_from_decision
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import (
    PulseGateResult,
    PulseGateThresholds,
    gate_pulse_candidate_from_factor_snapshot,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_edge_events import (
    build_pulse_edge_state,
    diff_pulse_edge_events,
    pulse_edge_signature,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_timeline_context import build_pulse_timeline_context
from gmgn_twitter_intel.domains.pulse_lab.types.agent_decision import FinalDecision, PulseStageFailure, StageRunAudit
from gmgn_twitter_intel.domains.token_intel.interfaces import (
    TOKEN_RADAR_PROJECTION_VERSION,
    require_token_factor_snapshot,
    safe_int,
)

SOURCE_TIMELINE_LOOKBACK_MS = 24 * 60 * 60 * 1000
DEFAULT_WINDOWS = ("1h",)
DEFAULT_SCOPES = ("all",)
PULSE_TRIGGER_METRICS_KEY = "pulse_trigger_metrics"
PULSE_EDGE_BUDGET_PER_HOUR = 3
ADVISORY_LOCK_KEY = 2026051502

_PLAYBOOK_STATUSES = {"trade_candidate", "token_watch", "risk_rejected_high_info"}


@dataclass(frozen=True)
class PulseCandidateContext:
    candidate_id: str
    candidate_type: str
    subject_key: str
    window: str
    scope: str
    trigger_signature: str
    timeline_signature: str
    priority: int
    target_type: str | None
    target_id: str | None
    symbol: str | None
    factor_snapshot: dict[str, Any]
    selected_posts: list[dict[str, Any]]
    gate_result: dict[str, Any] | None
    edge_state: dict[str, Any] | None
    edge_events: tuple[str, ...]
    source_event_ids: list[str]
    evidence_event_ids: list[str]

    def agent_context(self) -> dict[str, Any]:
        return {
            "pulse_version": PULSE_VERSION,
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type,
            "subject_key": self.subject_key,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "symbol": self.symbol,
            "window": self.window,
            "scope": self.scope,
            "trigger_signature": self.trigger_signature,
            "timeline_signature": self.timeline_signature,
            "factor_snapshot": self.factor_snapshot,
            "gate_result": self.gate_result or {},
            "edge_state": self.edge_state or {},
            "edge_events": list(self.edge_events),
            "selected_posts": self.selected_posts,
            "source_event_ids": self.source_event_ids,
            "evidence_event_ids": self.evidence_event_ids,
        }


@dataclass(frozen=True)
class PulseTriggerThresholds:
    min_rank_score: int = 45


class PulseCandidateWorker(WorkerBase):
    SINGLE_WRITER_KEY = ADVISORY_LOCK_KEY

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        decision_client: PulseDecisionProvider,
        gate_func: Callable[..., PulseGateResult] = gate_pulse_candidate_from_factor_snapshot,
        trigger_thresholds: PulseTriggerThresholds | None = None,
        gate_thresholds: PulseGateThresholds | None = None,
        wake_waiter: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry, wake_waiter=wake_waiter)
        self.decision_client = decision_client
        self.gate_func = gate_func
        self.windows = tuple(getattr(settings, "windows", DEFAULT_WINDOWS) or DEFAULT_WINDOWS)
        self.scopes = tuple(getattr(settings, "scopes", DEFAULT_SCOPES) or DEFAULT_SCOPES)
        self.batch_size = max(1, int(getattr(settings, "batch_size", 10) or 10))
        self.max_attempts = max(1, int(getattr(settings, "max_attempts", 3) or 3))
        self.trigger_thresholds = trigger_thresholds or _trigger_thresholds_from_settings(settings)
        self.gate_thresholds = gate_thresholds or _gate_thresholds_from_settings(settings)

    async def on_close(self) -> None:
        close = getattr(self.decision_client, "aclose", None)
        if close is not None:
            await close()
            return
        close_sync = getattr(self.decision_client, "close", None)
        if close_sync is not None:
            close_sync()

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        result = await self.run_once_async(now_ms=now_ms)
        scan = result["scan"]
        process = result["process"]
        return WorkerResult(
            processed=int(process.get("processed") or 0) + int(scan.get("asset_enqueued") or 0),
            failed=int(process.get("failed") or 0),
            skipped=int(scan.get("asset_skipped") or 0) + int(process.get("missing_context") or 0),
            notes=result,
        )

    async def run_once_async(self, *, now_ms: int | None = None) -> dict[str, Any]:
        started_at_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_error = None
        scan = await asyncio.to_thread(self.scan_triggers_once, now_ms=started_at_ms)
        process_now_ms = started_at_ms if now_ms is not None else None
        process = await self.process_due_jobs_once_async(now_ms=process_now_ms)
        result = {"scan": scan, "process": process}
        return result

    def scan_triggers_once(self, *, now_ms: int | None = None) -> dict[str, int]:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        result = {
            "asset_seen": 0,
            "asset_enqueued": 0,
            "asset_skipped": 0,
            "source_seen": 0,
            "source_enqueued": 0,
            "source_skipped": 0,
        }
        with self._repository_session() as repos:
            for window in self.windows:
                for scope in self.scopes:
                    rows = repos.token_radar.latest_rows(
                        window=window,
                        scope=scope,
                        limit=self.batch_size,
                        projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                    )
                    for row in rows:
                        result["asset_seen"] += 1
                        context = self._asset_context(repos, row, window=window, scope=scope, now_ms=resolved_now_ms)
                        if context is None:
                            result["asset_skipped"] += 1
                            continue
                        if self._enqueue_if_due(repos, context, now_ms=resolved_now_ms):
                            result["asset_enqueued"] += 1
                        else:
                            result["asset_skipped"] += 1
        return result

    def process_due_jobs_once(self, *, now_ms: int | None = None) -> dict[str, int]:
        return asyncio.run(self.process_due_jobs_once_async(now_ms=now_ms))

    async def process_due_jobs_once_async(self, *, now_ms: int | None = None) -> dict[str, int]:
        result = {"claimed": 0, "processed": 0, "failed": 0, "missing_context": 0}
        for _ in range(self.batch_size):
            resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
            with self._repository_session() as repos:
                job = repos.pulse.claim_due_job(now_ms=resolved_now_ms)
            if job is None:
                break
            result["claimed"] += 1
            context = _context_from_job(job)
            if context is None:
                with self._repository_session() as repos:
                    repos.pulse.mark_job_failed(
                        job,
                        "pulse_candidate_context_missing",
                        now_ms=resolved_now_ms,
                    )
                result["missing_context"] += 1
                result["failed"] += 1
                continue
            try:
                await self._run_job(job, context, now_ms=resolved_now_ms)
            except Exception as exc:  # pragma: no cover - _run_job records failure before re-raising
                logger.warning(
                    "pulse candidate job failed: job_id={} error={}",
                    job.get("job_id"),
                    _compact_error(exc),
                )
                result["failed"] += 1
                continue
            result["processed"] += 1
        return result

    def _asset_context(
        self,
        repos: Any,
        row: dict[str, Any],
        *,
        window: str,
        scope: str,
        now_ms: int,
    ) -> PulseCandidateContext | None:
        if not _is_asset_trigger(row, thresholds=self.trigger_thresholds):
            return None
        factor_snapshot = _factor_snapshot(row)
        if factor_snapshot is None:
            return None
        target_type = _clean(row.get("target_type"))
        target_id = _clean(row.get("target_id"))
        if not target_type or not target_id:
            return None
        target = _target_payload(row)
        rows = repos.token_targets.timeline_rows(
            target_type=target_type,
            target_id=target_id,
            since_ms=now_ms - SOURCE_TIMELINE_LOOKBACK_MS,
            watched_only=False,
            limit=200,
        )
        timeline_payload = build_pulse_timeline_context(
            target=target,
            rows=rows,
            window=window,
            scope=scope,
            now_ms=now_ms,
        )
        trigger_signature = _asset_trigger_signature(
            row=row,
            candidate_type="token_target",
            window=window,
            scope=scope,
            trigger_thresholds=self.trigger_thresholds,
            gate_thresholds=self.gate_thresholds,
        )
        candidate_id = _asset_candidate_id(
            candidate_type="token_target",
            window=window,
            scope=scope,
            target_type=target_type,
            target_id=target_id,
        )
        return PulseCandidateContext(
            candidate_id=candidate_id,
            candidate_type="token_target",
            subject_key=_subject_key(target, row),
            window=window,
            scope=scope,
            trigger_signature=trigger_signature,
            timeline_signature=_timeline_signature(timeline_payload),
            priority=_priority(row),
            target_type=target_type,
            target_id=target_id,
            symbol=_clean(target.get("symbol") or row.get("symbol")),
            factor_snapshot=factor_snapshot,
            selected_posts=list(timeline_payload.get("selected_posts") or []),
            gate_result=None,
            edge_state=None,
            edge_events=(),
            source_event_ids=_source_event_ids(row),
            evidence_event_ids=_source_event_ids(row),
        )

    def _enqueue_if_due(self, repos: Any, context: PulseCandidateContext, *, now_ms: int) -> bool:
        existing_job = _call_optional(repos.pulse, "job_for_candidate", context.candidate_id)
        if _active_job_blocks_reenqueue(existing_job):
            return False

        gate = self.gate_func(
            factor_snapshot=context.factor_snapshot,
            thresholds=self.gate_thresholds,
        )
        edge_state = build_pulse_edge_state(
            candidate_id=context.candidate_id,
            candidate_type=context.candidate_type,
            target_type=context.target_type,
            target_id=context.target_id,
            window=context.window,
            scope=context.scope,
            trigger_signature=context.trigger_signature,
            timeline_signature=context.timeline_signature,
            factor_snapshot=context.factor_snapshot,
            gate=gate,
            pulse_version=PULSE_VERSION,
            gate_version=PULSE_GATE_VERSION,
        )
        observed = repos.pulse.record_edge_observation(
            candidate_id=context.candidate_id,
            current_state_json=edge_state,
            edge_signature=pulse_edge_signature(edge_state),
            observed_at_ms=now_ms,
        )
        edge_events = diff_pulse_edge_events(_mapping(observed.get("last_processed_state_json")), edge_state)
        if not edge_events:
            return False
        hour_bucket_ms = now_ms // 3_600_000 * 3_600_000
        if not repos.pulse.claim_edge_budget(
            candidate_id=context.candidate_id,
            hour_bucket_ms=hour_bucket_ms,
            now_ms=now_ms,
            max_enqueues=PULSE_EDGE_BUDGET_PER_HOUR,
        ):
            repos.pulse.mark_edge_budget_rejected(
                candidate_id=context.candidate_id,
                edge_events_json=edge_events,
                rejected_at_ms=now_ms,
            )
            return False
        context = _context_with_gate(context, gate, edge_state=edge_state, edge_events=edge_events)
        job = repos.pulse.enqueue_job(
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
            context_json=context.agent_context(),
            max_attempts=self.max_attempts,
            next_run_at_ms=now_ms,
            now_ms=now_ms,
        )
        repos.pulse.mark_edge_job_enqueued(
            candidate_id=context.candidate_id,
            processed_state_json=edge_state,
            edge_events_json=edge_events,
            job_id=str(job.get("job_id") or ""),
            processed_at_ms=now_ms,
        )
        return True

    async def _run_job(self, job: dict[str, Any], context: PulseCandidateContext, *, now_ms: int) -> None:
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
        harness = build_pulse_harness_manifest(
            provider=provider,
            model=model,
            artifact_version_hash=artifact_version_hash,
            timeout_seconds=float(getattr(self.decision_client, "timeout_seconds", 30.0) or 30.0),
        )
        harness_hash = pulse_harness_hash(harness)
        audit: dict[str, Any] | None = None
        try:
            audit = self.decision_client.request_audit(
                context=agent_context,
                run_id=run_id,
                job=job,
                route=route,
                completeness=completeness_json,
                harness=harness,
            )
            with self._repository_session() as repos, _transaction(repos.conn):
                repos.pulse.upsert_agent_harness_version(
                    harness_version=str(harness["harness_version"]),
                    harness_hash=harness_hash,
                    strategy=PULSE_AGENT_STRATEGY,
                    provider=provider,
                    model=model,
                    prompt_version=PULSE_DECISION_PROMPT_VERSION,
                    schema_version=PULSE_DECISION_SCHEMA_VERSION,
                    manifest_json=harness,
                    created_at_ms=now_ms,
                    commit=False,
                )
                repos.pulse.insert_agent_run(
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
                    harness_version=str(harness["harness_version"]),
                    harness_hash=harness_hash,
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
                            harness=harness,
                        ),
                        timeout=timeout_seconds,
                    )
                except TimeoutError as exc:
                    raise TimeoutError(f"Agents SDK request timed out after {timeout_seconds:g}s") from exc
                final_decision = result.final_decision
                stage_audits = result.stage_audits
                result_audit = result.agent_run_audit or audit
            finished_at_ms = _now_ms()
            decision_fields = candidate_fields_from_decision(final_decision, stage_count=len(stage_audits))
            decision_fields.pop("score_band", None)
            outcome = _run_outcome(final_decision, completeness_blocked=completeness.hard_blocked)
            with self._repository_session() as repos, _transaction(repos.conn):
                for stage_audit in stage_audits:
                    repos.pulse.insert_agent_run_step(
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
                        commit=False,
                    )
                repos.pulse.finish_agent_run(
                    run_id,
                    "done",
                    response_json=final_decision.model_dump(mode="json"),
                    output_hash=result_audit.get("output_hash") or _stable_hash(final_decision.model_dump(mode="json")),
                    usage_json=result_audit.get("usage") or _aggregate_stage_usage(stage_audits),
                    outcome=outcome,
                    decision_route=route,
                    decision_stage_count=len(stage_audits),
                    finished_at_ms=finished_at_ms,
                    commit=False,
                )
                eval_case = build_pulse_deterministic_eval_case(
                    run_id=run_id,
                    harness_hash=harness_hash,
                    context=agent_context,
                    route=route,
                    completeness=completeness_json,
                    final_decision=final_decision,
                    stage_audits=tuple(stage_audits),
                )
                stored_eval_case = repos.pulse.insert_agent_eval_case(
                    **eval_case,
                    status="active",
                    created_at_ms=finished_at_ms,
                    commit=False,
                )
                eval_result = grade_pulse_deterministic_eval_case(stored_eval_case)
                repos.pulse.upsert_agent_eval_result(
                    **eval_result,
                    created_at_ms=finished_at_ms,
                    commit=False,
                )
                repos.pulse.upsert_candidate(
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
                    narrative_type=_narrative_type_from_context(context),
                    candidate_score=gate.candidate_score,
                    score_band=gate.score_band,
                    trigger_signature=context.trigger_signature,
                    timeline_signature=context.timeline_signature,
                    factor_snapshot_json=context.factor_snapshot,
                    gate_json=gate.to_json(),
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
                if gate.pulse_status in _PLAYBOOK_STATUSES:
                    repos.pulse.upsert_playbook_snapshot(
                        **_playbook_snapshot_payload(
                            context=context,
                            gate=gate,
                            final_decision=final_decision,
                            now_ms=now_ms,
                        ),
                        commit=False,
                    )
                repos.pulse.mark_edge_run_finished(
                    candidate_id=context.candidate_id,
                    agent_run_id=run_id,
                    finished_at_ms=finished_at_ms,
                    commit=False,
                )
                repos.pulse.mark_job_succeeded(str(job["job_id"]), now_ms=finished_at_ms, commit=False)
        except Exception as exc:
            failed_at_ms = _now_ms()
            failed_audits: tuple[StageRunAudit, ...] = ()
            if isinstance(exc, PulseStageFailure):
                failed_audits = exc.audits
            with self._repository_session() as repos, _transaction(repos.conn):
                for stage_audit in failed_audits:
                    repos.pulse.insert_agent_run_step(
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
                        commit=False,
                    )
                if audit is not None:
                    repos.pulse.finish_agent_run(
                        run_id,
                        "failed",
                        error=str(exc)[:1000],
                        outcome="failed",
                        finished_at_ms=failed_at_ms,
                        commit=False,
                    )
                repos.pulse.mark_job_failed(job, str(exc), now_ms=failed_at_ms, commit=False)
            raise

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _is_asset_trigger(row: dict[str, Any], *, thresholds: PulseTriggerThresholds | None = None) -> bool:
    factor_snapshot = _factor_snapshot(row)
    if factor_snapshot is None:
        return False
    if not _clean(row.get("target_type")) or not _clean(row.get("target_id")):
        return False
    resolved_thresholds = thresholds or PulseTriggerThresholds()
    score = safe_int(_nested(factor_snapshot, "composite", "rank_score"))
    decision = str(_nested(factor_snapshot, "composite", "recommended_decision") or "")
    watched_mentions = safe_int(_nested(factor_snapshot, "families", "social_heat", "facts", "watched_mentions"))
    return decision in {"high_alert", "watch"} or score >= resolved_thresholds.min_rank_score or watched_mentions > 0


def _trigger_thresholds_from_settings(settings: Any) -> PulseTriggerThresholds:
    config = getattr(settings, "trigger_thresholds", None)
    return PulseTriggerThresholds(min_rank_score=int(getattr(config, "min_rank_score", 45) or 45))


def _gate_thresholds_from_settings(settings: Any) -> PulseGateThresholds:
    config = getattr(settings, "gate_thresholds", None)
    return PulseGateThresholds(
        trade_candidate_min=int(getattr(config, "trade_candidate_min", 72) or 72),
        token_watch_min=int(getattr(config, "token_watch_min", 45) or 45),
        high_info_rejection_min=int(getattr(config, "high_info_rejection_min", 30) or 30),
        high_conviction_min=int(getattr(config, "high_conviction_min", 78) or 78),
    )


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


def _context_from_job(job: dict[str, Any]) -> PulseCandidateContext | None:
    context = _mapping(job.get("context_json"))
    if not context:
        return None
    candidate_id = _clean(context.get("candidate_id"))
    candidate_type = _clean(context.get("candidate_type"))
    subject_key = _clean(context.get("subject_key"))
    window = _clean(context.get("window"))
    scope = _clean(context.get("scope"))
    trigger_signature = _clean(context.get("trigger_signature"))
    timeline_signature = _clean(context.get("timeline_signature"))
    if (
        candidate_id is None
        or candidate_type is None
        or subject_key is None
        or window is None
        or scope is None
        or trigger_signature is None
        or timeline_signature is None
    ):
        return None
    factor_snapshot = _mapping(context.get("factor_snapshot"))
    if not factor_snapshot:
        return None
    selected_posts = context.get("selected_posts")
    if not isinstance(selected_posts, list):
        selected_posts = []
    return PulseCandidateContext(
        candidate_id=candidate_id,
        candidate_type=candidate_type,
        subject_key=subject_key,
        window=window,
        scope=scope,
        trigger_signature=trigger_signature,
        timeline_signature=timeline_signature,
        priority=safe_int(job.get("priority")),
        target_type=_clean(context.get("target_type")),
        target_id=_clean(context.get("target_id")),
        symbol=_clean(context.get("symbol")),
        factor_snapshot=factor_snapshot,
        selected_posts=[post for post in selected_posts if isinstance(post, dict)],
        gate_result=_mapping(context.get("gate_result")) or None,
        edge_state=_mapping(context.get("edge_state")) or None,
        edge_events=tuple(_stable_strings(context.get("edge_events"))),
        source_event_ids=_stable_strings(context.get("source_event_ids")),
        evidence_event_ids=_stable_strings(context.get("evidence_event_ids")),
    )


def _compact_error(exc: Exception, *, limit: int = 500) -> str:
    text = " ".join(str(exc).split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _asset_candidate_id(
    *,
    candidate_type: str,
    window: str,
    scope: str,
    target_type: str,
    target_id: str,
) -> str:
    return _stable_id(PULSE_VERSION, candidate_type, window, scope, target_type, target_id)


def _asset_trigger_signature(
    *,
    row: dict[str, Any],
    candidate_type: str,
    window: str,
    scope: str,
    trigger_thresholds: PulseTriggerThresholds | None = None,
    gate_thresholds: PulseGateThresholds | None = None,
) -> str:
    resolved_trigger_thresholds = trigger_thresholds or PulseTriggerThresholds()
    factor_snapshot = _factor_snapshot(row) or {}
    metrics = _asset_trigger_metrics(row)
    payload = {
        "pulse_version": PULSE_VERSION,
        "candidate_type": candidate_type,
        "target_type": _clean(row.get("target_type")),
        "target_id": _clean(row.get("target_id")),
        "window": window,
        "scope": scope,
        "rank_score_bucket": _score_bucket(metrics["rank_score"]),
        "recommended_decision": _nested(factor_snapshot, "composite", "recommended_decision"),
        "blocked_reasons": _stable_strings(_nested(factor_snapshot, "gates", "blocked_reasons")),
        "watched_confirmation": metrics["watched_confirmation"],
        "trigger_thresholds": {"min_rank_score": resolved_trigger_thresholds.min_rank_score},
    }
    return _stable_hash(payload)


def _timeline_signature(timeline_context: dict[str, Any]) -> str:
    signature = str(timeline_context.get("timeline_signature") or "")
    if signature.startswith("sha256:"):
        return signature
    if signature:
        return f"sha256:{signature}"
    return _stable_hash(timeline_context)


def _asset_trigger_metrics(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = _factor_snapshot(row) or {}
    blocked_reasons = _stable_strings(_nested(factor_snapshot, "gates", "blocked_reasons"))
    rank_score = safe_int(_nested(factor_snapshot, "composite", "rank_score"))
    attention_facts = _mapping(_nested(factor_snapshot, "families", "social_heat", "facts"))
    diffusion_facts = _mapping(_nested(factor_snapshot, "families", "social_propagation", "facts"))
    return {
        "rank_score": rank_score,
        "recommended_decision": _clean(_nested(factor_snapshot, "composite", "recommended_decision")),
        "watched_confirmation": safe_int(attention_facts.get("watched_mentions")) > 0,
        "independent_author_count": max(
            safe_int(attention_facts.get("unique_authors")),
            safe_int(diffusion_facts.get("independent_authors")),
        ),
        "blocked_reasons": blocked_reasons,
        "hard_risks": blocked_reasons,
        "trade_candidate_eligible": bool(_nested(factor_snapshot, "gates", "eligible_for_high_alert"))
        and not blocked_reasons
        and rank_score >= 72,
    }


def _active_job_blocks_reenqueue(existing_job: dict[str, Any] | None) -> bool:
    if not existing_job:
        return False
    status = _clean(existing_job.get("status"))
    if status in {"pending", "running"}:
        return True
    if status == "failed":
        attempt_count = safe_int(existing_job.get("attempt_count"))
        max_attempts = safe_int(existing_job.get("max_attempts")) or 3
        return attempt_count < max_attempts
    return False


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
        invalidation_conditions=[],
        residual_risks=residual_risks or [reason],
        evidence_event_ids=[],
    )


def _run_outcome(final_decision: FinalDecision, *, completeness_blocked: bool) -> str:
    if final_decision.recommendation == "abstain":
        if completeness_blocked:
            return "abstain_insufficient_data"
        if final_decision.abstain_reason == "critic_veto":
            return "abstain_critic_veto"
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


def _target_payload(row: dict[str, Any]) -> dict[str, Any]:
    target = _mapping(row.get("target_json")) or _mapping(row.get("asset_json"))
    return {
        **_jsonable(target),
        "target_type": _clean(row.get("target_type")),
        "target_id": _clean(row.get("target_id")),
    }


def _subject_key(target: dict[str, Any], row: dict[str, Any]) -> str:
    symbol = _clean(target.get("symbol") or row.get("symbol"))
    if symbol:
        return symbol.lstrip("$").upper()
    return f"{row.get('target_type')}:{row.get('target_id')}"


def _priority(row: dict[str, Any]) -> int:
    factor_snapshot = _factor_snapshot(row) or {}
    decision_priority = {"high_alert": 30, "watch": 20}.get(
        _clean(_nested(factor_snapshot, "composite", "recommended_decision")) or "",
        0,
    )
    return decision_priority + safe_int(_nested(factor_snapshot, "composite", "rank_score"))


def _source_event_ids(row: dict[str, Any]) -> list[str]:
    values = row.get("source_event_ids_json")
    if not isinstance(values, list):
        values = [row.get("event_id")]
    return _stable_strings(values)


def _score_bucket(score: int | float | None) -> str:
    value = max(0, min(100, safe_int(score)))
    lower = (value // 10) * 10
    if lower >= 100:
        return "100"
    return f"{lower}-{lower + 9}"


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


def _factor_snapshot(row: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = row.get("factor_snapshot_json")
    try:
        valid_snapshot = require_token_factor_snapshot(snapshot, field_name="factor_snapshot_json")
    except ValueError:
        return None
    return _mapping(_jsonable(valid_snapshot))


def _social_phase_from_snapshot(factor_snapshot: dict[str, Any]) -> str:
    semantic_facts = _mapping(_nested(factor_snapshot, "families", "semantic_catalyst", "facts"))
    timing_facts = _mapping(_nested(factor_snapshot, "families", "timing_risk", "facts"))
    return (
        _clean(semantic_facts.get("phase"))
        or _clean(semantic_facts.get("dominant_phase"))
        or _clean(timing_facts.get("phase"))
        or "unknown"
    )


def _narrative_type_from_context(context: PulseCandidateContext) -> str:
    return "direct_token"


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


def _call_optional(target: Any, method: str, *args: Any) -> Any:
    func = getattr(target, method, None)
    if func is None:
        return None
    return func(*args)


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    if hasattr(conn, "transaction"):
        return cast(AbstractContextManager[Any], conn.transaction())
    return nullcontext()


def _artifact_hash(client: Any) -> str:
    return str(getattr(client, "artifact_version_hash", "") or f"artifact:{getattr(client, 'model', '')}")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stable_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values if isinstance(values, list | tuple | set) else []:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


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
