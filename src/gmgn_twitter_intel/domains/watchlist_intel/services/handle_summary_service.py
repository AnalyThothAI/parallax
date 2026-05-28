from __future__ import annotations

import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from gmgn_twitter_intel.domains.watchlist_intel.providers import HandleTopicSummaryProvider
from gmgn_twitter_intel.domains.watchlist_intel.types import normalize_watchlist_handle


@dataclass(frozen=True, slots=True)
class HandleSummaryTriggerConfig:
    signal_threshold: int = 10
    time_threshold_ms: int = 30 * 60 * 1000
    min_interval_ms: int = 5 * 60 * 1000
    input_limit: int = 80
    window_days: int = 7
    max_attempts: int = 3


@dataclass(frozen=True, slots=True)
class HandleSummaryInputs:
    handle: str
    since_ms: int
    now_ms: int
    events: list[dict[str, Any]]
    signal_count: int
    run_id: str
    context: dict[str, Any]


class WatchlistHandleSummaryService:
    def __init__(
        self,
        *,
        repository: Any,
        provider: HandleTopicSummaryProvider | None,
        config: HandleSummaryTriggerConfig | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.config = config or HandleSummaryTriggerConfig()

    def enqueue_handle_summary_if_due(
        self,
        *,
        handle: str,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        normalized = normalize_watchlist_handle(handle)
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        signal_count = self.repository.count_signal_events_total(normalized)
        summary = self.repository.get_handle_summary(normalized)
        job = self.repository.pending_summary_job(normalized)
        if _active_job(job):
            return None
        due, reason = _due_reason(
            signal_count=signal_count,
            summary=summary,
            now_ms=resolved_now_ms,
            config=self.config,
        )
        if not due:
            return None
        return cast(
            dict[str, Any],
            self.repository.enqueue_handle_summary_job(
                handle=normalized,
                next_run_at_ms=resolved_now_ms,
                pending_signal_count=signal_count,
                trigger_reason=reason,
                max_attempts=self.config.max_attempts,
                commit=commit,
            ),
        )

    async def summarize_handle(self, job: dict[str, Any], *, now_ms: int | None = None) -> dict[str, Any]:
        inputs = self.summary_inputs(job, now_ms=now_ms)
        if not inputs.events:
            response = not_enough_input_response()
            model = "deterministic:not_enough_input"
        else:
            if self.provider is None:
                raise RuntimeError("watchlist_handle_summary_provider_not_configured")
            request_audit: dict[str, Any] | None = None
            try:
                request_audit = self.provider.request_audit(
                    handle=inputs.handle,
                    events=inputs.events,
                    run_id=inputs.run_id,
                    job=job,
                    context=inputs.context,
                )
                response = await self.provider.summarize_handle(
                    handle=inputs.handle,
                    events=inputs.events,
                    run_id=inputs.run_id,
                    job=job,
                    context=inputs.context,
                )
            except Exception as exc:
                self.record_failed_summary(
                    job=job,
                    inputs=inputs,
                    model=str(getattr(self.provider, "model", "") or ""),
                    request_audit=request_audit,
                    error=str(exc),
                    started_at_ms=inputs.now_ms,
                    failed_at_ms=_now_ms(),
                )
                raise
            model = str(getattr(self.provider, "model", "") or "")
        return self.complete_summary(
            job=job,
            inputs=inputs,
            response=response,
            model=model,
            started_at_ms=inputs.now_ms,
            finished_at_ms=_now_ms(),
        )

    def summary_inputs(self, job: dict[str, Any], *, now_ms: int | None = None) -> HandleSummaryInputs:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        handle = normalize_watchlist_handle(str(job.get("handle") or ""))
        since_ms = resolved_now_ms - max(1, int(self.config.window_days)) * 24 * 60 * 60 * 1000
        events = self.repository.signal_events_for_summary(
            handle=handle,
            since_ms=since_ms,
            limit=self.config.input_limit,
        )
        signal_count = self.repository.count_signal_events_total(handle)
        run_id = _run_id(handle=handle, attempt=int(job.get("attempt_count") or 0), now_ms=resolved_now_ms)
        context = {
            "handle": handle,
            "input_window_start_ms": since_ms,
            "input_window_end_ms": resolved_now_ms,
            "input_event_count": len(events),
            "signal_count_at_generation": signal_count,
        }
        return HandleSummaryInputs(
            handle=handle,
            since_ms=since_ms,
            now_ms=resolved_now_ms,
            events=events,
            signal_count=signal_count,
            run_id=run_id,
            context=context,
        )

    def complete_summary(
        self,
        *,
        job: dict[str, Any],
        inputs: HandleSummaryInputs,
        response: dict[str, Any],
        model: str,
        started_at_ms: int,
        finished_at_ms: int,
    ) -> dict[str, Any]:
        run_audit = _mapping(response.get("agent_run_audit"))
        usage = _mapping(run_audit.get("usage"))
        summary = self.repository.complete_handle_summary(
            job=job,
            handle=inputs.handle,
            summary={
                "handle": inputs.handle,
                "generated_at_ms": inputs.now_ms,
                "input_window_start_ms": inputs.since_ms,
                "input_window_end_ms": inputs.now_ms,
                "input_event_count": len(inputs.events),
                "signal_count_at_generation": inputs.signal_count,
                "model": model,
                "summary_zh": str(response.get("summary_zh") or ""),
                "topics": _topics(response.get("topics")),
                "raw_response": _mapping(response),
            },
            run={
                "run_id": inputs.run_id,
                "handle": inputs.handle,
                "status": "done",
                "model": model,
                "request_json": inputs.context,
                "response_json": _mapping(response),
                "input_event_count": len(inputs.events),
                "usage_json": usage,
                "error": None,
                "started_at_ms": started_at_ms,
                "finished_at_ms": finished_at_ms,
                "safety_net_used": bool(run_audit.get("safety_net_used", False)),
                "safety_net_retries": int(run_audit.get("safety_net_retries") or 0),
                "parse_mode": str(run_audit.get("parse_mode") or "strict"),
            },
        )
        if summary is None:
            raise RuntimeError("watchlist_summary_job_lease_lost")
        return cast(dict[str, Any], summary)

    def record_failed_summary(
        self,
        *,
        job: dict[str, Any],
        inputs: HandleSummaryInputs,
        model: str,
        request_audit: dict[str, Any] | None,
        error: str,
        started_at_ms: int,
        failed_at_ms: int,
    ) -> None:
        audit = _mapping(request_audit)
        self.repository.insert_summary_run(
            run_id=inputs.run_id,
            handle=inputs.handle,
            status="failed",
            model=model,
            request_json={"context": inputs.context, "agent_run_audit": audit} if audit else inputs.context,
            response_json=None,
            input_event_count=len(inputs.events),
            usage_json=_mapping(audit.get("usage")),
            error=error,
            started_at_ms=started_at_ms,
            finished_at_ms=failed_at_ms,
            safety_net_used=bool(audit.get("safety_net_used", False)),
            safety_net_retries=int(audit.get("safety_net_retries") or 0),
            parse_mode=str(audit.get("parse_mode") or "strict"),
            commit=False,
        )
        self.repository.mark_summary_job_failed(job, error, now_ms=failed_at_ms, commit=True)


class WatchlistHandleReadService:
    def __init__(self, *, repository: Any, config: HandleSummaryTriggerConfig | None = None):
        self.repository = repository
        self.config = config or HandleSummaryTriggerConfig()

    def summary(self, *, handle: str, configured_handles: tuple[str, ...], now_ms: int | None = None) -> dict[str, Any]:
        normalized = _configured_handle(handle, configured_handles)
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        summary = self.repository.get_handle_summary(normalized)
        job = self.repository.pending_summary_job(normalized)
        signal_count = self.repository.count_signal_events_total(normalized)
        pending_recompute = _pending_recompute(job)
        is_stale = False
        status = "not_ready"
        if summary:
            generated_at_ms = int(summary.get("generated_at_ms") or 0)
            is_stale = bool(generated_at_ms and generated_at_ms < resolved_now_ms - 2 * self.config.time_threshold_ms)
            status = "ready"
        return {
            "handle": normalized,
            "status": status,
            "generated_at_ms": summary.get("generated_at_ms") if summary else None,
            "staleness_ms": resolved_now_ms - int(summary.get("generated_at_ms") or 0) if summary else None,
            "is_stale": is_stale,
            "pending_recompute": pending_recompute,
            "signal_count": signal_count,
            "input_event_count": summary.get("input_event_count") if summary else 0,
            "signal_count_at_generation": summary.get("signal_count_at_generation") if summary else 0,
            "model": summary.get("model") if summary else None,
            "summary_zh": summary.get("summary_zh") if summary else "",
            "topics": summary.get("topics") if summary else [],
        }

    def handles_overview(
        self,
        *,
        configured_handles: Sequence[str],
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        window_days = max(1, int(self.config.window_days))
        rows = self.repository.handles_overview(
            handles=tuple(normalize_watchlist_handle(handle) for handle in configured_handles),
            since_ms=_window_since_ms(now_ms=resolved_now_ms, window_days=window_days),
        )
        return {
            "window": f"{window_days}d",
            "items": [_public_handle_row(row, now_ms=resolved_now_ms, config=self.config) for row in rows],
        }

    def overview(
        self,
        *,
        handle: str,
        configured_handles: Sequence[str],
        scope: str,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        normalized = _configured_handle(handle, tuple(configured_handles))
        resolved_now_ms = int(now_ms if now_ms is not None else _now_ms())
        window_days = max(1, int(self.config.window_days))
        overview = cast(
            dict[str, Any],
            self.repository.handle_overview(
                handle=normalized,
                scope=scope,
                since_ms=_window_since_ms(now_ms=resolved_now_ms, window_days=window_days),
            ),
        )
        query = dict(overview.get("query") or {})
        overview["query"] = {
            "handle": normalized,
            "scope": str(query.get("scope") or scope),
            "window": f"{window_days}d",
        }
        return overview

    def timeline(
        self,
        *,
        handle: str,
        configured_handles: tuple[str, ...],
        scope: str,
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        normalized = _configured_handle(handle, configured_handles)
        return cast(
            dict[str, Any],
            self.repository.timeline(handle=normalized, scope=scope, cursor=cursor, limit=limit),
        )


def _due_reason(
    *,
    signal_count: int,
    summary: dict[str, Any] | None,
    now_ms: int,
    config: HandleSummaryTriggerConfig,
) -> tuple[bool, str]:
    if signal_count <= 0:
        return False, ""
    if summary is None:
        return True, "cold_start"
    generated_at_ms = int(summary.get("generated_at_ms") or 0)
    generated_count = int(summary.get("signal_count_at_generation") or 0)
    if now_ms - generated_at_ms < config.min_interval_ms:
        return False, ""
    if signal_count - generated_count >= config.signal_threshold:
        return True, "signal_threshold"
    if signal_count > generated_count and now_ms - generated_at_ms >= config.time_threshold_ms:
        return True, "time_threshold"
    return False, ""


def _active_job(job: dict[str, Any] | None) -> bool:
    return bool(job and job.get("status") in {"pending", "running", "failed"})


def _pending_recompute(job: dict[str, Any] | None) -> bool:
    return bool(job and job.get("status") in {"pending", "running", "failed"})


def _configured_handle(handle: str, configured_handles: tuple[str, ...]) -> str:
    normalized = normalize_watchlist_handle(handle)
    configured = {normalize_watchlist_handle(item) for item in configured_handles}
    if normalized not in configured:
        raise LookupError("handle_not_found")
    return normalized


def _public_handle_row(
    row: dict[str, Any],
    *,
    now_ms: int,
    config: HandleSummaryTriggerConfig,
) -> dict[str, Any]:
    public = dict(row)
    generated_at_ms = public.pop("summary_generated_at_ms", None)
    public["summary_is_stale"] = _summary_is_stale(generated_at_ms, now_ms=now_ms, config=config)
    return public


def _summary_is_stale(
    generated_at_ms: Any,
    *,
    now_ms: int,
    config: HandleSummaryTriggerConfig,
) -> bool:
    if generated_at_ms is None:
        return False
    return int(generated_at_ms) < now_ms - 2 * config.time_threshold_ms


def _window_since_ms(*, now_ms: int, window_days: int) -> int:
    return now_ms - max(1, int(window_days)) * 24 * 60 * 60 * 1000


def _topics(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _run_id(*, handle: str, attempt: int, now_ms: int) -> str:
    digest = hashlib.sha256(f"{handle}:{attempt}:{now_ms}".encode()).hexdigest()[:24]
    return f"watchlist-summary-run-{digest}"


def not_enough_input_response() -> dict[str, Any]:
    return {
        "summary_zh": "近窗口内还没有足够的结构化信号，暂不生成账号主题判断。",
        "topics": [],
        "status": "not_enough_input",
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "HandleSummaryInputs",
    "HandleSummaryTriggerConfig",
    "WatchlistHandleReadService",
    "WatchlistHandleSummaryService",
    "not_enough_input_response",
]
