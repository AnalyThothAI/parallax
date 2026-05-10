from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Any

from loguru import logger

from gmgn_twitter_intel.integrations.openai_agents.pulse_thesis_agent_client import PulseThesisClientProtocol
from gmgn_twitter_intel.pipeline.pulse_candidate_gate import PulseGateResult, PulseGateThresholds, gate_pulse_candidate
from gmgn_twitter_intel.pipeline.pulse_contract import (
    AGENT_NAME,
    BACKEND,
    PULSE_GATE_VERSION,
    PULSE_PLAYBOOK_VERSION,
    PULSE_THESIS_PROMPT_VERSION,
    PULSE_THESIS_SCHEMA_VERSION,
    PULSE_VERSION,
    WORKFLOW_NAME,
)
from gmgn_twitter_intel.pipeline.pulse_thesis import PulseThesisPayload
from gmgn_twitter_intel.pipeline.pulse_timeline_context import build_pulse_timeline_context
from gmgn_twitter_intel.pipeline.token_radar_contract import TOKEN_RADAR_PROJECTION_VERSION
from gmgn_twitter_intel.retrieval.scoring_common import safe_float, safe_int

SOURCE_TIMELINE_LOOKBACK_MS = 24 * 60 * 60 * 1000
SOURCE_EVENT_LOOKBACK_MS = 60 * 60 * 1000
DEFAULT_WINDOWS = ("1h",)
DEFAULT_SCOPES = ("all",)
SOURCE_WINDOW = "1h"
SOURCE_SCOPE = "matched"
PULSE_TRIGGER_METRICS_KEY = "pulse_trigger_metrics"

_PLAYBOOK_STATUSES = {"trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info"}
_COOLDOWN_MS = {
    "trade_candidate": 5 * 60 * 1000,
    "token_watch": 15 * 60 * 1000,
    "theme_watch": 60 * 60 * 1000,
    "risk_rejected_high_info": 30 * 60 * 1000,
    "blocked_low_information": 120 * 60 * 1000,
}
_STATUS_RANK = {
    "blocked_low_information": 0,
    "risk_rejected_high_info": 1,
    "theme_watch": 2,
    "token_watch": 3,
    "trade_candidate": 4,
}


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
    radar_score: dict[str, Any]
    market_context: dict[str, Any]
    timeline_context: dict[str, Any]
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
            "radar_score": self.radar_score,
            "market_context": self.market_context,
            "timeline_context": self.timeline_context,
            "source_event_ids": self.source_event_ids,
            "evidence_event_ids": self.evidence_event_ids,
            **self.timeline_context,
        }


@dataclass(frozen=True)
class PulseTriggerThresholds:
    asset_heat_min: int = 80
    asset_propagation_min: int = 70


class PulseCandidateWorker:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        thesis_client: PulseThesisClientProtocol,
        gate_func: Callable[..., PulseGateResult] = gate_pulse_candidate,
        windows: tuple[str, ...] = DEFAULT_WINDOWS,
        scopes: tuple[str, ...] = DEFAULT_SCOPES,
        poll_interval: float = 60.0,
        batch_size: int = 10,
        max_attempts: int = 3,
        trigger_thresholds: PulseTriggerThresholds | None = None,
        gate_thresholds: PulseGateThresholds | None = None,
    ) -> None:
        self.repository_session = repository_session
        self.thesis_client = thesis_client
        self.gate_func = gate_func
        self.windows = tuple(windows)
        self.scopes = tuple(scopes)
        self.poll_interval = max(1.0, float(poll_interval))
        self.batch_size = max(1, int(batch_size))
        self.max_attempts = max(1, int(max_attempts))
        self.trigger_thresholds = trigger_thresholds or PulseTriggerThresholds()
        self.gate_thresholds = gate_thresholds or PulseGateThresholds()
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            try:
                await self.run_once_async()
            except Exception as exc:  # pragma: no cover - watchdog path
                self.last_error = str(exc)
                logger.exception(f"pulse candidate worker failed: {exc}")
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped = True

    async def aclose(self) -> None:
        close = getattr(self.thesis_client, "aclose", None)
        if close is not None:
            await close()
            return
        close_sync = getattr(self.thesis_client, "close", None)
        if close_sync is not None:
            close_sync()

    async def run_once_async(self, *, now_ms: int | None = None) -> dict[str, Any]:
        started_at_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_started_at_ms = started_at_ms
        self.last_error = None
        scan = await asyncio.to_thread(self.scan_triggers_once, now_ms=started_at_ms)
        process_now_ms = started_at_ms if now_ms is not None else None
        process = await self.process_due_jobs_once_async(now_ms=process_now_ms)
        result = {"scan": scan, "process": process}
        self.last_run_at_ms = _now_ms()
        self.last_result = result
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
        with self.repository_session() as repos:
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
            for event in repos.harness.list_social_events(
                window_ms=SOURCE_EVENT_LOOKBACK_MS,
                limit=self.batch_size,
                now_ms=resolved_now_ms,
                handles=None,
                event_types=None,
            ):
                result["source_seen"] += 1
                context = self._source_context(event, now_ms=resolved_now_ms)
                if context is None:
                    result["source_skipped"] += 1
                    continue
                if self._enqueue_if_due(repos, context, now_ms=resolved_now_ms):
                    result["source_enqueued"] += 1
                else:
                    result["source_skipped"] += 1
        return result

    def process_due_jobs_once(self, *, now_ms: int | None = None) -> dict[str, int]:
        return asyncio.run(self.process_due_jobs_once_async(now_ms=now_ms))

    async def process_due_jobs_once_async(self, *, now_ms: int | None = None) -> dict[str, int]:
        result = {"claimed": 0, "processed": 0, "failed": 0, "missing_context": 0}
        for _ in range(self.batch_size):
            resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
            with self.repository_session() as repos:
                job = repos.pulse.claim_due_job(now_ms=resolved_now_ms)
            if job is None:
                break
            result["claimed"] += 1
            context = _context_from_job(job)
            if context is None:
                with self.repository_session() as repos:
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
                logger.exception(f"pulse candidate job failed: job_id={job.get('job_id')} error={exc}")
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
        radar_score = _radar_score(row)
        market_context = _market_context(row)
        timeline_context = build_pulse_timeline_context(
            target=target,
            rows=rows,
            window=window,
            scope=scope,
            now_ms=now_ms,
            radar_score=radar_score,
            market_overlay=market_context,
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
        metrics = _asset_trigger_metrics(row, timeline_context=timeline_context, gate_thresholds=self.gate_thresholds)
        radar_score[PULSE_TRIGGER_METRICS_KEY] = metrics
        return PulseCandidateContext(
            candidate_id=candidate_id,
            candidate_type="token_target",
            subject_key=_subject_key(target, row),
            window=window,
            scope=scope,
            trigger_signature=trigger_signature,
            timeline_signature=_timeline_signature(timeline_context),
            priority=_priority(row),
            target_type=target_type,
            target_id=target_id,
            symbol=_clean(target.get("symbol") or row.get("symbol")),
            radar_score=radar_score,
            market_context=market_context,
            timeline_context=timeline_context,
            source_event_ids=_source_event_ids(row),
            evidence_event_ids=_source_event_ids(row),
        )

    def _source_context(self, event: dict[str, Any], *, now_ms: int) -> PulseCandidateContext | None:
        if not _source_event_is_signal(event):
            return None
        source_event_id = _clean(event.get("event_id"))
        if not source_event_id:
            return None
        trigger_signature = _source_trigger_signature(event)
        timeline_signature = _source_timeline_signature(event)
        candidate_id = _source_candidate_id(
            window=SOURCE_WINDOW,
            scope=SOURCE_SCOPE,
            source_event_id=source_event_id,
        )
        metrics = _source_trigger_metrics(event)
        timeline_context = {
            "source_event": _jsonable(event),
            "source_event_ids": [source_event_id],
            "timeline_signature": timeline_signature,
            "windows": {},
            "selected_posts": [
                {
                    "event_id": source_event_id,
                    "author_handle": _clean(event.get("author_handle")),
                    "text": _source_summary_text(event),
                    "role": "source_seed",
                    "received_at_ms": safe_int(event.get("received_at_ms")),
                }
            ],
        }
        radar_score = {PULSE_TRIGGER_METRICS_KEY: metrics}
        return PulseCandidateContext(
            candidate_id=candidate_id,
            candidate_type="source_seed",
            subject_key=f"source:{source_event_id}",
            window=SOURCE_WINDOW,
            scope=SOURCE_SCOPE,
            trigger_signature=trigger_signature,
            timeline_signature=timeline_signature,
            priority=50,
            target_type=None,
            target_id=None,
            symbol=None,
            radar_score=radar_score,
            market_context={},
            timeline_context=timeline_context,
            source_event_ids=[source_event_id],
            evidence_event_ids=[source_event_id],
        )

    def _enqueue_if_due(self, repos: Any, context: PulseCandidateContext, *, now_ms: int) -> bool:
        existing_job = _call_optional(repos.pulse, "job_for_candidate", context.candidate_id)
        existing_candidate = _call_optional(repos.pulse, "candidate_by_id", context.candidate_id)
        if _active_job_blocks_reenqueue(existing_job):
            return False
        if _same_signature(existing_job, context) or _same_signature(existing_candidate, context):
            return False
        if _cooldown_active(existing_candidate, context, now_ms=now_ms):
            return False
        repos.pulse.enqueue_job(
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
        agent_context = context.agent_context()
        audit: dict[str, Any] | None = None
        try:
            audit = self.thesis_client.request_audit(context=agent_context, run_id=run_id, job=job)
            with self.repository_session() as repos, _transaction(repos.conn):
                repos.pulse.insert_agent_run(
                    run_id=run_id,
                    job_id=str(job["job_id"]),
                    candidate_id=context.candidate_id,
                    provider=getattr(self.thesis_client, "provider", "openai"),
                    model=getattr(self.thesis_client, "model", ""),
                    backend=str(audit.get("backend") or BACKEND),
                    sdk_trace_id=audit.get("sdk_trace_id"),
                    workflow_name=str(audit.get("workflow_name") or WORKFLOW_NAME),
                    agent_name=str(audit.get("agent_name") or AGENT_NAME),
                    artifact_version_hash=str(audit.get("artifact_version_hash") or _artifact_hash(self.thesis_client)),
                    prompt_version=str(audit.get("prompt_version") or PULSE_THESIS_PROMPT_VERSION),
                    schema_version=str(audit.get("schema_version") or PULSE_THESIS_SCHEMA_VERSION),
                    input_hash=str(audit.get("input_hash") or _stable_hash(agent_context)),
                    trace_metadata_json=audit.get("trace_metadata") or {},
                    usage_json=audit.get("usage") or {},
                    status="running",
                    request_json={"context_hash": _stable_hash(agent_context)},
                    started_at_ms=now_ms,
                    commit=False,
                )
            timeout_seconds = max(0.1, float(getattr(self.thesis_client, "timeout_seconds", 30.0) or 30.0))
            try:
                result = await asyncio.wait_for(
                    self.thesis_client.write_thesis(context=agent_context, run_id=run_id, job=job),
                    timeout=timeout_seconds,
                )
            except TimeoutError as exc:
                raise TimeoutError(f"Agents SDK request timed out after {timeout_seconds:g}s") from exc
            thesis = result.payload
            result_audit = result.agent_run_audit or audit or {}
            gate = self.gate_func(
                thesis=thesis,
                radar_score=context.radar_score,
                market_context=context.market_context,
                timeline_context=context.timeline_context,
                historical_credit=None,
                thresholds=self.gate_thresholds,
            )
            finished_at_ms = _now_ms()
            with self.repository_session() as repos, _transaction(repos.conn):
                repos.pulse.finish_agent_run(
                    run_id,
                    "done",
                    response_json=_payload_dict(thesis),
                    output_hash=result_audit.get("output_hash"),
                    usage_json=result_audit.get("usage") or {},
                    finished_at_ms=finished_at_ms,
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
                    social_phase=str(getattr(thesis, "social_phase", "unknown") or "unknown"),
                    narrative_type=str(getattr(thesis, "narrative_type", "unknown") or "unknown"),
                    candidate_score=gate.candidate_score,
                    score_band=gate.score_band,
                    trigger_signature=context.trigger_signature,
                    timeline_signature=context.timeline_signature,
                    thesis_json=_payload_dict(thesis),
                    radar_score_json=context.radar_score,
                    market_context_json=context.market_context,
                    gate_reasons_json=gate.gate_reasons,
                    risk_reasons_json=gate.risk_reasons,
                    evidence_event_ids_json=list(getattr(thesis, "evidence_event_ids", context.evidence_event_ids)),
                    source_event_ids_json=list(getattr(thesis, "source_event_ids", context.source_event_ids)),
                    agent_run_id=run_id,
                    pulse_version=PULSE_VERSION,
                    gate_version=PULSE_GATE_VERSION,
                    prompt_version=PULSE_THESIS_PROMPT_VERSION,
                    schema_version=PULSE_THESIS_SCHEMA_VERSION,
                    updated_at_ms=finished_at_ms,
                    commit=False,
                )
                if gate.pulse_status in _PLAYBOOK_STATUSES:
                    repos.pulse.upsert_playbook_snapshot(
                        **_playbook_snapshot_payload(
                            context=context,
                            gate=gate,
                            thesis=thesis,
                            now_ms=now_ms,
                        ),
                        commit=False,
                    )
                repos.pulse.mark_job_succeeded(str(job["job_id"]), now_ms=finished_at_ms, commit=False)
        except Exception as exc:
            failed_at_ms = _now_ms()
            with self.repository_session() as repos, _transaction(repos.conn):
                if audit is not None:
                    repos.pulse.finish_agent_run(
                        run_id,
                        "failed",
                        error=str(exc)[:1000],
                        finished_at_ms=failed_at_ms,
                        commit=False,
                    )
                repos.pulse.mark_job_failed(job, str(exc), now_ms=failed_at_ms, commit=False)
            raise


def _is_asset_trigger(row: dict[str, Any], *, thresholds: PulseTriggerThresholds | None = None) -> bool:
    if not _clean(row.get("target_type")) or not _clean(row.get("target_id")):
        return False
    resolved_thresholds = thresholds or PulseTriggerThresholds()
    decision = _decision(row)
    attention = _mapping(row.get("attention_json"))
    return (
        decision in {"driver", "watch"}
        or _component_score(row, "heat") >= resolved_thresholds.asset_heat_min
        or _component_score(row, "propagation") >= resolved_thresholds.asset_propagation_min
        or safe_int(attention.get("watched_mentions")) > 0
    )


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
    if not all((candidate_id, candidate_type, subject_key, window, scope, trigger_signature, timeline_signature)):
        return None
    timeline_context = _mapping(context.get("timeline_context"))
    if not timeline_context:
        timeline_context = {
            key: value
            for key, value in context.items()
            if key
            in {
                "target",
                "windows",
                "stage_segments",
                "post_clusters",
                "selected_posts",
                "market_overlay",
                "source_event",
                "timeline_signature",
            }
        }
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
        radar_score=_mapping(context.get("radar_score")),
        market_context=_mapping(context.get("market_context")),
        timeline_context=timeline_context,
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
    return _stable_id(PULSE_VERSION, candidate_type, window, scope, target_type, target_id)


def _source_candidate_id(*, window: str, scope: str, source_event_id: str) -> str:
    return _stable_id(PULSE_VERSION, "source_seed", window, scope, source_event_id)


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
    resolved_gate_thresholds = gate_thresholds or PulseGateThresholds()
    metrics = _asset_trigger_metrics(row, timeline_context={}, gate_thresholds=resolved_gate_thresholds)
    payload = {
        "pulse_version": PULSE_VERSION,
        "candidate_type": candidate_type,
        "target_type": _clean(row.get("target_type")),
        "target_id": _clean(row.get("target_id")),
        "window": window,
        "scope": scope,
        "heat_bucket": metrics["heat_bucket"],
        "propagation_bucket": metrics["propagation_bucket"],
        "opportunity_decision": _decision(row),
        "social_phase": metrics["social_phase"],
        "watched_confirmation": metrics["watched_confirmation"],
        "chase_risk": metrics["chase_risk"],
        "trigger_thresholds": {
            "asset_heat_min": resolved_trigger_thresholds.asset_heat_min,
            "asset_propagation_min": resolved_trigger_thresholds.asset_propagation_min,
        },
        "gate_thresholds": _gate_threshold_payload(resolved_gate_thresholds),
    }
    return _stable_hash(payload)


def _source_trigger_signature(event: dict[str, Any]) -> str:
    payload = {
        "pulse_version": PULSE_VERSION,
        "candidate_type": "source_seed",
        "source_event_id": _clean(event.get("event_id")),
        "subject_key": _source_subject_key(event),
        "event_type": _clean(event.get("event_type")),
        "direction_hint": _clean(event.get("direction_hint")),
        "impact_bucket": _ratio_bucket(_source_number(event, "impact_score")),
        "novelty_bucket": _ratio_bucket(_source_number(event, "novelty_score")),
    }
    return _stable_hash(payload)


def _source_timeline_signature(event: dict[str, Any]) -> str:
    payload = {
        "source_event_id": _clean(event.get("event_id")),
        "extraction_id": _clean(event.get("extraction_id")),
        "author_handle": _clean(event.get("author_handle")),
        "received_at_bucket": _time_bucket_ms(safe_int(event.get("received_at_ms")), 5 * 60 * 1000),
        "subject": _source_subject_key(event),
        "event_type": _clean(event.get("event_type")),
        "summary": _source_summary_text(event),
    }
    return _stable_hash(payload)


def _timeline_signature(timeline_context: dict[str, Any]) -> str:
    signature = str(timeline_context.get("timeline_signature") or "")
    if signature.startswith("sha256:"):
        return signature
    if signature:
        return f"sha256:{signature}"
    return _stable_hash(timeline_context)


def _asset_trigger_metrics(
    row: dict[str, Any],
    *,
    timeline_context: dict[str, Any],
    gate_thresholds: PulseGateThresholds | None = None,
) -> dict[str, Any]:
    attention = _mapping(row.get("attention_json"))
    market = _market_context(row)
    resolved_gate_thresholds = gate_thresholds or PulseGateThresholds()
    return {
        "decision": _decision(row),
        "heat_bucket": _score_bucket(_component_score(row, "heat")),
        "propagation_bucket": _score_bucket(_component_score(row, "propagation")),
        "social_phase": _social_phase(row, timeline_context),
        "watched_confirmation": safe_int(attention.get("watched_mentions")) > 0,
        "chase_risk": _chase_risk(row),
        "independent_author_count": safe_int(attention.get("unique_authors")),
        "market_status": _clean(market.get("market_status")),
        "hard_risks": _hard_risks(_radar_score(row), market, timeline_context),
        "trade_candidate_eligible": _trade_candidate_eligible(row, market, thresholds=resolved_gate_thresholds),
    }


def _source_trigger_metrics(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_event_id": _clean(event.get("event_id")),
        "event_type": _clean(event.get("event_type")),
        "subject_key": _source_subject_key(event),
        "impact_bucket": _ratio_bucket(_source_number(event, "impact_score")),
        "novelty_bucket": _ratio_bucket(_source_number(event, "novelty_score")),
    }


def _cooldown_active(
    existing_candidate: dict[str, Any] | None,
    context: PulseCandidateContext,
    *,
    now_ms: int,
) -> bool:
    if not existing_candidate:
        return False
    previous_metrics = _previous_trigger_metrics(existing_candidate)
    current_metrics = _mapping(context.radar_score.get(PULSE_TRIGGER_METRICS_KEY))
    if _cooldown_bypass(existing_candidate, previous_metrics, current_metrics):
        return False
    cooldown_ms = _cooldown_ms(existing_candidate, current_metrics)
    updated_at_ms = safe_int(existing_candidate.get("updated_at_ms"))
    return bool(updated_at_ms and now_ms < updated_at_ms + cooldown_ms)


def _cooldown_bypass(
    existing_candidate: dict[str, Any],
    previous: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    previous_status = _clean(existing_candidate.get("pulse_status") or existing_candidate.get("verdict"))
    current_status = _inferred_status(current)
    if _STATUS_RANK.get(current_status, 0) > _STATUS_RANK.get(previous_status, 0):
        return True
    if current.get("trade_candidate_eligible") and previous_status != "trade_candidate":
        return True
    if not previous.get("watched_confirmation") and current.get("watched_confirmation"):
        return True
    if safe_int(current.get("independent_author_count")) >= safe_int(previous.get("independent_author_count")) + 5:
        return True
    if not previous.get("chase_risk") and current.get("chase_risk"):
        return True
    return bool(set(current.get("hard_risks") or []) - set(previous.get("hard_risks") or []))


def _cooldown_ms(existing_candidate: dict[str, Any], current_metrics: dict[str, Any]) -> int:
    status = _clean(existing_candidate.get("pulse_status") or existing_candidate.get("verdict"))
    if current_metrics.get("trade_candidate_eligible"):
        return _COOLDOWN_MS["trade_candidate"]
    return _COOLDOWN_MS.get(status, _COOLDOWN_MS["token_watch"])


def _previous_trigger_metrics(existing_candidate: dict[str, Any]) -> dict[str, Any]:
    radar = _mapping(existing_candidate.get("radar_score_json"))
    return _mapping(radar.get(PULSE_TRIGGER_METRICS_KEY))


def _same_signature(row: dict[str, Any] | None, context: PulseCandidateContext) -> bool:
    if not row:
        return False
    return (
        row.get("trigger_signature") == context.trigger_signature
        and row.get("timeline_signature") == context.timeline_signature
    )


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
    thesis: PulseThesisPayload,
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
            "candidate_score": gate.candidate_score,
            "score_band": gate.score_band,
            "summary_zh": thesis.summary_zh,
            "why_now_zh": thesis.why_now_zh,
        },
        "confirmation": {"triggers_zh": list(thesis.confirmation_triggers_zh)},
        "invalidation": {"triggers_zh": list(thesis.invalidation_triggers_zh)},
        "risk": {
            "top_risks": list(thesis.top_risks),
            "risk_reasons": gate.risk_reasons,
            "hard_risks": gate.hard_risks,
        },
        "entry_market": context.market_context,
        "playbook_version": PULSE_PLAYBOOK_VERSION,
        "outcome_status": "pending",
        "created_at_ms": now_ms,
    }


def _playbook_side(status: str) -> str:
    if status == "trade_candidate":
        return "LONG_BIAS"
    if status == "risk_rejected_high_info":
        return "RISK_OFF"
    if status == "blocked_low_information":
        return "FLAT"
    return "OBSERVE_ONLY"


def _radar_score(row: dict[str, Any]) -> dict[str, Any]:
    score = dict(_mapping(row.get("score_json")))
    score["decision"] = _decision(row)
    score["attention"] = _mapping(row.get("attention_json"))
    score["market"] = _market_context(row)
    score["price"] = _mapping(row.get("price_json"))
    score["data_health"] = _mapping(row.get("data_health_json"))
    return _jsonable(score)


def _market_context(row: dict[str, Any]) -> dict[str, Any]:
    market = _mapping(row.get("market_json")) or _mapping(row.get("price_json"))
    return _jsonable(market)


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
    decision_priority = {"driver": 30, "watch": 20}.get(_decision(row), 0)
    return decision_priority + _component_score(row, "heat")


def _source_event_ids(row: dict[str, Any]) -> list[str]:
    values = row.get("source_event_ids_json")
    if not isinstance(values, list):
        values = [row.get("event_id")]
    return _stable_strings(values)


def _source_event_is_signal(event: dict[str, Any]) -> bool:
    if bool(event.get("is_signal_event")):
        return True
    extraction = _mapping(event.get("extraction_json"))
    return bool(extraction.get("is_signal_event"))


def _source_subject_key(event: dict[str, Any]) -> str:
    return _clean(event.get("subject_key") or event.get("subject") or event.get("event_type")) or "source"


def _source_number(event: dict[str, Any], key: str) -> float:
    for alias in _source_number_aliases(key):
        if event.get(alias) is not None:
            return safe_float(event.get(alias))
    extraction = _mapping(event.get("extraction_json"))
    for alias in _source_number_aliases(key):
        if extraction.get(alias) is not None:
            return safe_float(extraction.get(alias))
    return 0.0


def _source_number_aliases(key: str) -> tuple[str, ...]:
    if key == "impact_score":
        return ("impact_score", "impact_hint")
    if key == "novelty_score":
        return ("novelty_score", "semantic_novelty_hint")
    return (key,)


def _source_summary_text(event: dict[str, Any]) -> str | None:
    extraction = _mapping(event.get("extraction_json"))
    return _clean(
        event.get("summary_zh")
        or extraction.get("summary_zh")
        or event.get("summary")
        or extraction.get("summary")
        or event.get("text")
        or extraction.get("text")
    )


def _component_score(row: dict[str, Any], key: str) -> int:
    score = _mapping(row.get("score_json"))
    value = score.get(key)
    if isinstance(value, dict):
        return safe_int(value.get("score"))
    return safe_int(value)


def _decision(row: dict[str, Any]) -> str:
    score = _mapping(row.get("score_json"))
    opportunity = _mapping(score.get("opportunity"))
    return _clean(opportunity.get("decision") or row.get("decision")) or ""


def _social_phase(row: dict[str, Any], timeline_context: dict[str, Any]) -> str:
    windows = _mapping(timeline_context.get("windows"))
    active = _mapping(windows.get("1h") or windows.get("5m"))
    if active.get("phase"):
        return str(active["phase"])
    propagation = _mapping(_mapping(row.get("score_json")).get("propagation"))
    return _clean(propagation.get("phase") or row.get("phase")) or "unknown"


def _chase_risk(row: dict[str, Any]) -> bool:
    score = _mapping(row.get("score_json"))
    timing = _mapping(score.get("timing"))
    price = _mapping(row.get("price_json"))
    return bool(timing.get("chase_risk") or row.get("chase_risk") or price.get("chase_risk"))


def _hard_risks(*sources: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for source in sources:
        for value in (source, *_mapping_values(source)):
            if not isinstance(value, dict):
                continue
            for key in ("hard_risks", "risks", "risk_flags"):
                items = value.get(key)
                if isinstance(items, list):
                    risks.extend(str(item) for item in items if item)
    return _stable_strings(risks)


def _trade_candidate_eligible(
    row: dict[str, Any],
    market: dict[str, Any],
    *,
    thresholds: PulseGateThresholds,
) -> bool:
    return (
        _decision(row) == "driver"
        and _component_score(row, "heat") >= thresholds.trade_heat_min
        and _component_score(row, "quality") >= thresholds.trade_quality_min
        and _component_score(row, "propagation") >= thresholds.trade_propagation_min
        and _component_score(row, "tradeability") >= thresholds.tradeability_min
        and _component_score(row, "timing") >= thresholds.timing_min
        and market.get("market_status") == "fresh"
        and not _chase_risk(row)
    )


def _gate_threshold_payload(thresholds: PulseGateThresholds) -> dict[str, Any]:
    return {
        "trade_heat_min": thresholds.trade_heat_min,
        "trade_quality_min": thresholds.trade_quality_min,
        "trade_propagation_min": thresholds.trade_propagation_min,
        "tradeability_min": thresholds.tradeability_min,
        "timing_min": thresholds.timing_min,
        "confidence_min": thresholds.confidence_min,
        "token_watch_signal_min": thresholds.token_watch_signal_min,
        "high_conviction_min": thresholds.high_conviction_min,
    }


def _inferred_status(metrics: dict[str, Any]) -> str:
    if metrics.get("trade_candidate_eligible"):
        return "trade_candidate"
    if metrics.get("source_event_id"):
        return "theme_watch"
    return "token_watch"


def _latest_source_event_id(row: dict[str, Any]) -> str | None:
    values = _source_event_ids(row)
    return values[-1] if values else _clean(row.get("event_id"))


def _latest_seen_ms(row: dict[str, Any]) -> int:
    attention = _mapping(row.get("attention_json"))
    return safe_int(attention.get("latest_seen_ms") or row.get("source_max_received_at_ms") or row.get("created_at_ms"))


def _score_bucket(score: int | float | None) -> str:
    value = max(0, min(100, safe_int(score)))
    lower = (value // 10) * 10
    if lower >= 100:
        return "100"
    return f"{lower}-{lower + 9}"


def _ratio_bucket(value: float) -> str:
    if value < 0.25:
        return "low"
    if value < 0.5:
        return "medium"
    if value < 0.75:
        return "high"
    return "very_high"


def _time_bucket_ms(value: int, bucket_ms: int) -> int:
    if not value:
        return 0
    return int(value) // int(bucket_ms) * int(bucket_ms)


def _payload_dict(payload: PulseThesisPayload | dict[str, Any]) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload)


def _call_optional(target: Any, method: str, *args: Any) -> Any:
    func = getattr(target, method, None)
    if func is None:
        return None
    return func(*args)


def _transaction(conn: Any):
    if hasattr(conn, "transaction"):
        return conn.transaction()
    return nullcontext()


def _artifact_hash(client: Any) -> str:
    return str(getattr(client, "artifact_version_hash", "") or f"artifact:{getattr(client, 'model', '')}")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _mapping_values(value: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in value.values() if isinstance(item, dict)]


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
