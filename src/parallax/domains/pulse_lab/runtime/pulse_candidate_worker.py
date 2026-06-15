from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from loguru import logger

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.pulse_lab.interfaces import (
    PULSE_GATE_VERSION,
    PULSE_VERSION,
)
from parallax.domains.pulse_lab.providers import PULSE_DECISION_LANE, PulseDecisionProvider
from parallax.domains.pulse_lab.services.pulse_admission_policy import (
    ESCALATION_EDGE_EVENTS,
    PulseAdmissionPolicy,
)
from parallax.domains.pulse_lab.services.pulse_candidate_gate import (
    PulseGateResult,
    PulseGateThresholds,
    gate_pulse_candidate_from_factor_snapshot,
)
from parallax.domains.pulse_lab.services.pulse_candidate_job_service import (
    PulseAgentBackpressureReleased,
    PulseCandidateJobService,
    _compact_error,
    _context_with_gate,
)
from parallax.domains.pulse_lab.services.pulse_edge_events import (
    build_pulse_edge_state,
    diff_pulse_edge_events,
)
from parallax.domains.pulse_lab.services.pulse_timeline_context import build_pulse_timeline_context
from parallax.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext
from parallax.domains.token_intel.interfaces import (
    TOKEN_RADAR_DEFAULT_VENUE,
    TOKEN_RADAR_PROJECTION_VERSION,
    require_token_factor_snapshot,
    safe_int,
)

PULSE_TRIGGER_METRICS_KEY = "pulse_trigger_metrics"
ADVISORY_LOCK_KEY = 2026051502
PULSE_SCOPE_WATCHED_ONLY = {
    "all": False,
    "matched": True,
}


@dataclass(frozen=True)
class PulseTriggerThresholds:
    min_rank_score: int


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
        if settings is None:
            raise RuntimeError("pulse_candidate_settings_required")
        if db is None:
            raise RuntimeError("pulse_candidate_db_required")
        if decision_client is None:
            raise RuntimeError("pulse_candidate_decision_client_required")
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry, wake_waiter=wake_waiter)
        self.decision_client = decision_client
        self.gate_func = gate_func
        self.windows = tuple(str(window).strip().lower() for window in settings.windows)
        self.scopes = tuple(str(scope).strip().lower() for scope in settings.scopes)
        self.batch_size = max(1, int(settings.batch_size))
        self.max_agent_jobs_per_cycle = max(1, int(settings.max_agent_jobs_per_cycle))
        self.max_attempts = max(1, int(settings.max_attempts))
        self.max_enqueues_per_cycle = max(1, int(settings.max_enqueues_per_cycle))
        self.max_pending_jobs_global = max(1, int(settings.max_pending_jobs_global))
        self.max_pending_jobs_per_window_scope = max(1, int(settings.max_pending_jobs_per_window_scope))
        self.job_running_timeout_ms = max(1, int(settings.job_running_timeout_ms))
        self.stale_running_terminalization_batch_size = max(
            1,
            int(settings.stale_running_terminalization_batch_size),
        )
        self.trigger_lease_ms = max(1, int(settings.trigger_lease_ms))
        self.trigger_capacity_retry_ms = max(1, int(settings.trigger_capacity_retry_ms))
        self.trigger_error_retry_ms = max(1, int(settings.trigger_error_retry_ms))
        self.target_edge_budget_per_hour = max(1, int(settings.target_edge_budget_per_hour))
        self.candidate_edge_budget_per_hour = max(1, int(settings.candidate_edge_budget_per_hour))
        self.failure_circuit_per_hour = max(1, int(settings.failure_circuit_per_hour))
        self.timeline_debounce_seconds = max(0, int(settings.timeline_debounce_seconds))
        self.failure_circuit_reasons = _required_string_tuple(
            settings.failure_circuit_reasons,
            error="pulse_candidate_failure_circuit_reasons_required",
        )
        self.trigger_thresholds = trigger_thresholds or _trigger_thresholds_from_settings(settings)
        self.gate_thresholds = gate_thresholds or _gate_thresholds_from_settings(settings)
        self.job_service = PulseCandidateJobService(
            name=name,
            settings=settings,
            db=db,
            decision_client=decision_client,
            gate_func=gate_func,
            gate_thresholds=self.gate_thresholds,
        )

    async def on_close(self) -> None:
        try:
            aclose = self.decision_client.aclose
        except AttributeError as exc:
            raise RuntimeError("pulse_candidate_decision_client_aclose_required") from exc
        if not callable(aclose):
            raise RuntimeError("pulse_candidate_decision_client_aclose_required")
        await aclose()

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

    def scan_triggers_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        result: dict[str, Any] = {
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
            "asset_seen": 0,
            "asset_enqueued": 0,
            "asset_skipped": 0,
            "missing_current_rows": 0,
            "target_exits_suppressed": 0,
            "dirty_triggers_done": 0,
            "dirty_triggers_rescheduled": 0,
            "dirty_triggers_failed": 0,
            "source_seen": 0,
            "source_enqueued": 0,
            "source_skipped": 0,
            "asset_suppressed_cycle_budget": 0,
            "asset_suppressed_pending_global": 0,
            "asset_suppressed_pending_window_scope": 0,
        }
        with self._repository_session() as repos, repos.transaction():
            queue_depth = _queue_depth(repos, now_ms=resolved_now_ms)
            result["queue_depth"] = queue_depth
            claims = repos.pulse_trigger_dirty_targets.claim_due(
                now_ms=resolved_now_ms,
                limit=self.batch_size,
                lease_owner=self.name,
                lease_ms=self.trigger_lease_ms,
                commit=False,
            )
            result["claimed"] = len(claims)
            if not claims:
                result["reason"] = "no_due_pulse_triggers"
                return result
            enqueued_this_cycle = 0
            pending_jobs_global = _pending_agent_job_count(repos)
            pending_jobs_by_window_scope: dict[tuple[str, str], int] = {}
            for claim in claims:
                window = _clean(claim.get("window"))
                scope = _clean(claim.get("scope"))
                target_type = _clean(claim.get("target_type"))
                target_id = _clean(claim.get("target_id"))
                try:
                    with repos.transaction():
                        if not window or not scope or not target_type or not target_id:
                            result["asset_skipped"] += 1
                            result["dirty_triggers_done"] += _mark_trigger_done(repos, claim, now_ms=resolved_now_ms)
                            continue
                        window = _required_configured_claim_dimension(
                            window,
                            allowed=self.windows,
                            field="window",
                            error_prefix="pulse_trigger_dirty_target",
                        )
                        scope = _required_configured_claim_dimension(
                            scope,
                            allowed=self.scopes,
                            field="scope",
                            error_prefix="pulse_trigger_dirty_target",
                        )
                        scope_key = (window, scope)
                        if scope_key not in pending_jobs_by_window_scope:
                            pending_jobs_by_window_scope[scope_key] = _pending_agent_job_count_for_window_scope(
                                repos,
                                window=window,
                                scope=scope,
                            )
                        if enqueued_this_cycle >= self.max_enqueues_per_cycle:
                            result["asset_skipped"] += 1
                            result["asset_suppressed_cycle_budget"] += 1
                            result["dirty_triggers_rescheduled"] += _reschedule_trigger(
                                repos,
                                claim,
                                now_ms=resolved_now_ms,
                                retry_ms=self.trigger_capacity_retry_ms,
                            )
                            continue
                        if pending_jobs_global >= self.max_pending_jobs_global:
                            result["asset_skipped"] += 1
                            result["asset_suppressed_pending_global"] += 1
                            result["dirty_triggers_rescheduled"] += _reschedule_trigger(
                                repos,
                                claim,
                                now_ms=resolved_now_ms,
                                retry_ms=self.trigger_capacity_retry_ms,
                            )
                            continue
                        if pending_jobs_by_window_scope[scope_key] >= self.max_pending_jobs_per_window_scope:
                            result["asset_skipped"] += 1
                            result["asset_suppressed_pending_window_scope"] += 1
                            result["dirty_triggers_rescheduled"] += _reschedule_trigger(
                                repos,
                                claim,
                                now_ms=resolved_now_ms,
                                retry_ms=self.trigger_capacity_retry_ms,
                            )
                            continue
                        row = repos.token_radar.current_row_for_target(
                            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                            target_type=target_type,
                            target_id=target_id,
                            window=window,
                            scope=scope,
                            venue=TOKEN_RADAR_DEFAULT_VENUE,
                        )
                        if row is None:
                            result["asset_skipped"] += 1
                            result["missing_current_rows"] += 1
                            if _is_exit_trigger(claim):
                                result["target_exits_suppressed"] += _suppress_exited_trigger_target(
                                    repos,
                                    claim,
                                    now_ms=resolved_now_ms,
                                    target_edge_budget_per_hour=self.target_edge_budget_per_hour,
                                    candidate_edge_budget_per_hour=self.candidate_edge_budget_per_hour,
                                )
                            result["dirty_triggers_done"] += _mark_trigger_done(repos, claim, now_ms=resolved_now_ms)
                            continue
                        result["asset_seen"] += 1
                        result["targets_loaded"] += 1
                        context = self._asset_context(repos, row, window=window, scope=scope, now_ms=resolved_now_ms)
                        if context is None:
                            result["asset_skipped"] += 1
                            result["dirty_triggers_done"] += _mark_trigger_done(repos, claim, now_ms=resolved_now_ms)
                            continue
                        if self._enqueue_if_due(repos, context, now_ms=resolved_now_ms):
                            result["asset_enqueued"] += 1
                            result["rows_written"] += 1
                            enqueued_this_cycle += 1
                            pending_jobs_global += 1
                            pending_jobs_by_window_scope[scope_key] += 1
                        else:
                            result["asset_skipped"] += 1
                        result["dirty_triggers_done"] += _mark_trigger_done(repos, claim, now_ms=resolved_now_ms)
                except Exception as exc:
                    logger.warning(
                        "pulse trigger processing failed: target_type={} target_id={} window={} scope={} error={}",
                        target_type,
                        target_id,
                        window,
                        scope,
                        _compact_error(exc),
                    )
                    result["asset_skipped"] += 1
                    with repos.transaction():
                        result["dirty_triggers_failed"] += repos.pulse_trigger_dirty_targets.mark_error(
                            [claim],
                            error=str(exc),
                            now_ms=resolved_now_ms,
                            retry_ms=self.trigger_error_retry_ms,
                            commit=False,
                        )
        return result

    def process_due_jobs_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        return asyncio.run(self.process_due_jobs_once_async(now_ms=now_ms))

    async def process_due_jobs_once_async(self, *, now_ms: int | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "claimed": 0,
            "processed": 0,
            "failed": 0,
            "missing_context": 0,
            "terminalized_stale_running": 0,
        }
        for _ in range(min(self.batch_size, self.max_agent_jobs_per_cycle)):
            resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
            with self._repository_session() as repos:
                result["terminalized_stale_running"] += _terminalize_exhausted_stale_running_jobs(
                    repos.pulse_jobs,
                    now_ms=resolved_now_ms,
                    running_timeout_ms=self.job_running_timeout_ms,
                    limit=self.stale_running_terminalization_batch_size,
                )
            reservation = self.decision_client.try_reserve_execution(
                PULSE_DECISION_LANE,
                child_lanes=(PULSE_DECISION_LANE,),
                scope="parent",
            )
            if not reservation.acquired:
                _record_agent_backpressure(result, reservation)
                return result
            try:
                with self._repository_session() as repos:
                    job = repos.pulse_jobs.claim_due_job(now_ms=resolved_now_ms)
                if job is None:
                    break
                result["claimed"] += 1
                context = _context_from_job(job)
                if context is None:
                    with self._repository_session() as repos:
                        repos.pulse_jobs.mark_job_failed(
                            job,
                            "pulse_candidate_context_missing",
                            now_ms=resolved_now_ms,
                        )
                    result["missing_context"] += 1
                    result["failed"] += 1
                    continue
                try:
                    await self.job_service.run_job(
                        job,
                        context,
                        now_ms=resolved_now_ms,
                        parent_reservation=reservation,
                    )
                except PulseAgentBackpressureReleased as exc:
                    result["agent_backpressure"] = exc.reason
                    _increment_agent_backpressure_reason(result, exc.reason)
                    return result
                except Exception as exc:  # pragma: no cover - job service records failure before re-raising
                    logger.warning(
                        "pulse candidate job failed: job_id={} error={}",
                        job.get("job_id"),
                        _compact_error(exc),
                    )
                    result["failed"] += 1
                    continue
                result["processed"] += 1
            finally:
                await reservation.release()
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
        source_event_ids = _source_event_ids(row)
        early_gate = self.gate_func(
            factor_snapshot=factor_snapshot,
            thresholds=self.gate_thresholds,
        )
        if early_gate.max_recommendation == "ignore":
            _hide_existing_public_candidate_for_low_information(
                repos,
                row,
                window=window,
                scope=scope,
                target_type=target_type,
                target_id=target_id,
                source_event_ids=source_event_ids,
                gate=early_gate,
                trigger_thresholds=self.trigger_thresholds,
                gate_thresholds=self.gate_thresholds,
                target_edge_budget_per_hour=self.target_edge_budget_per_hour,
                candidate_edge_budget_per_hour=self.candidate_edge_budget_per_hour,
                now_ms=now_ms,
            )
            return None
        if not source_event_ids:
            return None
        target = _target_payload(row)
        rows = repos.token_targets.timeline_rows_for_event_ids(
            target_type=target_type,
            target_id=target_id,
            event_ids=source_event_ids,
            watched_only=_watched_only_for_scope(scope, error_prefix="pulse_trigger_dirty_target"),
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
            post_clusters=list(timeline_payload.get("post_clusters") or []),
            gate_result=None,
            edge_state=None,
            edge_events=(),
            source_event_ids=source_event_ids,
            evidence_event_ids=source_event_ids,
        )

    def _enqueue_if_due(self, repos: Any, context: PulseCandidateContext, *, now_ms: int) -> bool:
        existing_job = repos.pulse_jobs.job_for_candidate(context.candidate_id)
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
        existing_edge = repos.pulse_admission.edge_state_by_candidate(context.candidate_id) or {}
        previous_state = _mapping(existing_edge.get("last_processed_state_json"))
        edge_events = diff_pulse_edge_events(previous_state, edge_state)
        hour_bucket_ms = now_ms // 3_600_000 * 3_600_000
        recent_failure_count = _recent_target_failure_count(
            repos,
            target_type=context.target_type,
            target_id=context.target_id,
            since_ms=hour_bucket_ms,
            edge_events=edge_events,
            failure_circuit_reasons=self.failure_circuit_reasons,
        )
        decision = PulseAdmissionPolicy().classify(
            previous_state=previous_state,
            current_state=edge_state,
            existing_job=existing_job,
            edge_events=edge_events,
            pending_score_band=_clean(existing_edge.get("pending_score_band")),
            pending_score_band_count=safe_int(existing_edge.get("pending_score_band_count")),
            recent_failure_count=recent_failure_count,
            failure_circuit_per_hour=self.failure_circuit_per_hour,
            last_processed_at_ms=safe_int(existing_edge.get("last_processed_at_ms")) or None,
            now_ms=now_ms,
            timeline_debounce_seconds=self.timeline_debounce_seconds,
        )
        context = _context_with_gate(context, gate, edge_state=edge_state, edge_events=decision.edge_events)
        with repos.transaction():
            claim = repos.pulse_admission.claim_pulse_admission(
                candidate_id=context.candidate_id,
                target_type=context.target_type,
                target_id=context.target_id,
                hour_bucket_ms=hour_bucket_ms,
                now_ms=now_ms,
                target_limit=self.target_edge_budget_per_hour,
                candidate_limit=self.candidate_edge_budget_per_hour,
                edge_state=edge_state,
                edge_events=decision.edge_events,
                admission_action=decision.action,
                admission_reason=decision.reason,
                commit=False,
            )
            if not claim.accepted:
                return False
            job = repos.pulse_jobs.enqueue_job(
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
                commit=False,
            )
            repos.pulse_admission.mark_edge_job_enqueued(
                candidate_id=context.candidate_id,
                processed_state_json=edge_state,
                edge_events_json=list(decision.edge_events),
                job_id=str(job.get("job_id") or ""),
                processed_at_ms=now_ms,
                commit=False,
            )
            return True

    @contextmanager
    def _repository_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        ) as repos:
            yield repos


def _is_asset_trigger(row: dict[str, Any], *, thresholds: PulseTriggerThresholds) -> bool:
    factor_snapshot = _factor_snapshot(row)
    if factor_snapshot is None:
        return False
    if not _clean(row.get("target_type")) or not _clean(row.get("target_id")):
        return False
    score = safe_int(_nested(factor_snapshot, "composite", "rank_score"))
    decision = str(_nested(factor_snapshot, "composite", "recommended_decision") or "")
    return decision in {"high_alert", "watch"} or score >= thresholds.min_rank_score


def _trigger_thresholds_from_settings(settings: Any) -> PulseTriggerThresholds:
    return PulseTriggerThresholds(min_rank_score=int(settings.trigger_thresholds.min_rank_score))


def _gate_thresholds_from_settings(settings: Any) -> PulseGateThresholds:
    return PulseGateThresholds(
        trade_candidate_min=int(settings.gate_thresholds.trade_candidate_min),
        token_watch_min=int(settings.gate_thresholds.token_watch_min),
        high_info_rejection_min=int(settings.gate_thresholds.high_info_rejection_min),
        high_conviction_min=int(settings.gate_thresholds.high_conviction_min),
    )


def _required_string_tuple(values: Any, *, error: str) -> tuple[str, ...]:
    result = tuple(str(value).strip() for value in values if str(value).strip())
    if not result:
        raise RuntimeError(error)
    return result


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
    post_clusters = context.get("post_clusters")
    if not isinstance(post_clusters, list):
        post_clusters = []
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
        post_clusters=[cluster for cluster in post_clusters if isinstance(cluster, dict)],
        gate_result=_mapping(context.get("gate_result")) or None,
        edge_state=_mapping(context.get("edge_state")) or None,
        edge_events=tuple(_stable_strings(context.get("edge_events"))),
        source_event_ids=_stable_strings(context.get("source_event_ids")),
        evidence_event_ids=_stable_strings(context.get("evidence_event_ids")),
    )


def _asset_candidate_id(
    *,
    candidate_type: str,
    window: str,
    scope: str,
    target_type: str,
    target_id: str,
) -> str:
    return _stable_id(candidate_type, window, scope, target_type, target_id)


def _asset_trigger_signature(
    *,
    row: dict[str, Any],
    candidate_type: str,
    window: str,
    scope: str,
    trigger_thresholds: PulseTriggerThresholds,
    gate_thresholds: PulseGateThresholds | None = None,
) -> str:
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
        "trigger_thresholds": {"min_rank_score": trigger_thresholds.min_rank_score},
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


def _recent_target_failure_count(
    repos: Any,
    *,
    target_type: str | None,
    target_id: str | None,
    since_ms: int,
    edge_events: list[str] | tuple[str, ...],
    failure_circuit_reasons: tuple[str, ...],
) -> int:
    if set(edge_events) & ESCALATION_EDGE_EVENTS:
        return 0
    return safe_int(
        repos.pulse_admission.recent_target_failure_count(
            target_type=target_type,
            target_id=target_id,
            since_ms=since_ms,
            reasons=failure_circuit_reasons,
        )
    )


def _hide_existing_public_candidate_for_low_information(
    repos: Any,
    row: dict[str, Any],
    *,
    window: str,
    scope: str,
    target_type: str,
    target_id: str,
    source_event_ids: list[str],
    gate: PulseGateResult,
    trigger_thresholds: PulseTriggerThresholds,
    gate_thresholds: PulseGateThresholds,
    target_edge_budget_per_hour: int,
    candidate_edge_budget_per_hour: int,
    now_ms: int,
) -> dict[str, Any] | None:
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window=window,
        scope=scope,
        target_type=target_type,
        target_id=target_id,
    )
    trigger_signature = _asset_trigger_signature(
        row=row,
        candidate_type="token_target",
        window=window,
        scope=scope,
        trigger_thresholds=trigger_thresholds,
        gate_thresholds=gate_thresholds,
    )
    hidden_row = repos.pulse_candidates.hide_public_candidate_for_low_information(
        candidate_id=candidate_id,
        candidate_score=gate.candidate_score,
        trigger_signature=trigger_signature,
        factor_snapshot_json=_factor_snapshot(row) or {},
        gate_json=gate.to_json(),
        gate_reasons_json=gate.gate_reasons,
        risk_reasons_json=gate.risk_reasons,
        evidence_event_ids_json=source_event_ids,
        source_event_ids_json=source_event_ids,
        last_edge_events_json=["pulse_status_changed"],
        updated_at_ms=now_ms,
        commit=False,
    )
    if hidden_row is None:
        return None
    edge_state = build_pulse_edge_state(
        candidate_id=candidate_id,
        candidate_type="token_target",
        target_type=target_type,
        target_id=target_id,
        window=window,
        scope=scope,
        trigger_signature=trigger_signature,
        timeline_signature="low_information",
        factor_snapshot=_factor_snapshot(row) or {},
        gate=gate,
        pulse_version=PULSE_VERSION,
        gate_version=PULSE_GATE_VERSION,
    )
    repos.pulse_admission.claim_pulse_admission(
        candidate_id=candidate_id,
        target_type=target_type,
        target_id=target_id,
        hour_bucket_ms=int(now_ms) // 3_600_000 * 3_600_000,
        now_ms=now_ms,
        target_limit=target_edge_budget_per_hour,
        candidate_limit=candidate_edge_budget_per_hour,
        edge_state=edge_state,
        edge_events=("pulse_status_changed",),
        admission_action="suppress",
        admission_reason="blocked_low_information",
        commit=False,
    )
    return cast("dict[str, Any]", hidden_row)


def _pending_agent_job_count(repos: Any) -> int:
    return safe_int(repos.pulse_jobs.pending_agent_job_count())


def _pending_agent_job_count_for_window_scope(repos: Any, *, window: str, scope: str) -> int:
    return safe_int(repos.pulse_jobs.pending_agent_job_count_for_window_scope(window=window, scope=scope))


def _queue_depth(repos: Any, *, now_ms: int) -> int:
    return safe_int(repos.pulse_trigger_dirty_targets.queue_depth(now_ms=now_ms))


def _reschedule_trigger(repos: Any, claim: dict[str, Any], *, now_ms: int, retry_ms: int) -> int:
    return safe_int(
        repos.pulse_trigger_dirty_targets.reschedule(
            [claim],
            due_at_ms=int(now_ms) + int(retry_ms),
            now_ms=int(now_ms),
            commit=False,
        )
    )


def _is_exit_trigger(claim: dict[str, Any]) -> bool:
    return str(claim.get("dirty_reason") or "") == "token_radar_exited"


def _claim_payload_hash(claim: dict[str, Any]) -> str:
    try:
        value = claim["payload_hash"]
    except KeyError as exc:
        raise ValueError("pulse_trigger_dirty_claim_payload_hash_required") from exc
    if value is None:
        raise ValueError("pulse_trigger_dirty_claim_payload_hash_required")
    payload_hash = str(value).strip()
    if not payload_hash:
        raise ValueError("pulse_trigger_dirty_claim_payload_hash_required")
    return payload_hash


def _suppress_exited_trigger_target(
    repos: Any,
    claim: dict[str, Any],
    *,
    now_ms: int,
    target_edge_budget_per_hour: int,
    candidate_edge_budget_per_hour: int,
) -> int:
    target_type = _clean(claim.get("target_type"))
    target_id = _clean(claim.get("target_id"))
    window = _clean(claim.get("window"))
    scope = _clean(claim.get("scope"))
    if not target_type or not target_id or not window or not scope:
        return 0
    candidate_id = _asset_candidate_id(
        candidate_type="token_target",
        window=window,
        scope=scope,
        target_type=target_type,
        target_id=target_id,
    )
    edge_state = {
        "candidate_id": candidate_id,
        "candidate_type": "token_target",
        "target_type": target_type,
        "target_id": target_id,
        "window": window,
        "scope": scope,
        "pulse_version": PULSE_VERSION,
        "gate_version": PULSE_GATE_VERSION,
        "pulse_status": "not_active",
        "verdict": "not_active",
        "score_band": "exited",
        "trigger_signature": _claim_payload_hash(claim),
        "timeline_signature": "token_radar_exited",
        "exit_reason": "token_radar_exited",
    }
    repos.pulse_admission.claim_pulse_admission(
        candidate_id=candidate_id,
        target_type=target_type,
        target_id=target_id,
        hour_bucket_ms=int(now_ms) // 3_600_000 * 3_600_000,
        now_ms=int(now_ms),
        target_limit=target_edge_budget_per_hour,
        candidate_limit=candidate_edge_budget_per_hour,
        edge_state=edge_state,
        edge_events=("token_radar_exited",),
        admission_action="suppress",
        admission_reason="token_radar_exited",
        commit=False,
    )
    return 1


def _mark_trigger_done(repos: Any, claim: dict[str, Any], *, now_ms: int) -> int:
    done = safe_int(
        repos.pulse_trigger_dirty_targets.mark_done(
            [claim],
            now_ms=int(now_ms),
            commit=False,
        )
    )
    if done != 1:
        raise RuntimeError("pulse_trigger_dirty_target_stale_completion")
    return done


def _target_payload(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = _factor_snapshot(row) or {}
    target = _mapping(factor_snapshot.get("subject"))
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
        return []
    return _stable_strings(values)


def _score_bucket(score: int | float | None) -> str:
    value = max(0, min(100, safe_int(score)))
    lower = (value // 10) * 10
    if lower >= 100:
        return "100"
    return f"{lower}-{lower + 9}"


def _factor_snapshot(row: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = row.get("factor_snapshot_json")
    try:
        valid_snapshot = require_token_factor_snapshot(snapshot, field_name="factor_snapshot_json")
    except ValueError:
        return None
    return _mapping(_jsonable(valid_snapshot))


def _nested(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _terminalize_exhausted_stale_running_jobs(
    pulse_jobs: Any,
    *,
    now_ms: int,
    running_timeout_ms: int,
    limit: int,
) -> int:
    return int(
        pulse_jobs.terminalize_exhausted_stale_running_jobs(
            now_ms=int(now_ms),
            stale_after_ms=int(running_timeout_ms),
            limit=max(1, int(limit)),
        )
        or 0
    )


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
    if isinstance(value, Decimal):
        return float(value)
    return value


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_configured_claim_dimension(
    value: str,
    *,
    allowed: tuple[str, ...],
    field: str,
    error_prefix: str,
) -> str:
    if value not in allowed:
        allowed_values = ",".join(allowed)
        raise ValueError(f"{error_prefix}_invalid_{field}:{value}:allowed={allowed_values}")
    return value


def _watched_only_for_scope(scope: str, *, error_prefix: str) -> bool:
    try:
        return PULSE_SCOPE_WATCHED_ONLY[scope]
    except KeyError as exc:
        raise ValueError(f"{error_prefix}_invalid_scope:{scope}") from exc


def _stable_id(*parts: str) -> str:
    return "pulse-" + hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:40]


def _prefixed_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:" + hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:40]


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _record_agent_backpressure(result: dict[str, Any], reservation: Any) -> None:
    reason = getattr(reservation, "reason", None)
    resolved_reason = str(getattr(reason, "value", reason) or "capacity_denied")
    result["agent_backpressure"] = resolved_reason
    _increment_agent_backpressure_reason(result, resolved_reason)


def _increment_agent_backpressure_reason(result: dict[str, Any], reason: str) -> None:
    resolved_reason = str(reason or "capacity_denied")
    key = f"agent_backpressure_{resolved_reason}"
    result[key] = int(result.get(key) or 0) + 1
