from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from parallax.app.runtime.queue_health import fetch_queue_table_health
from parallax.app.runtime.worker_manifest import worker_queue_health_tables
from parallax.domains.asset_market.repositories.discovery_repository import DISCOVERY_PROVIDER
from parallax.platform.db.queue_terminal import inspect_terminal_events, list_terminal_event_ids, resolve_terminal_event

QUEUE_RETRY_TRANSITIONS: Mapping[tuple[str, str], Callable[..., dict[str, Any]]]


def handle_queue_inspect(args: object, repos: object) -> tuple[int, dict[str, Any]]:
    try:
        limit = _positive_limit(args, default=50)
    except ValueError as exc:
        return 1, {"ok": False, "error": str(exc)}
    if str(getattr(args, "status", "") or "terminal") == "active":
        data = _inspect_active_queues(
            _conn(repos),
            worker_name=str(getattr(args, "worker", "") or "") or None,
            source_table=str(getattr(args, "source_table", "") or "") or None,
            limit=limit,
        )
        return 0, {"ok": True, "data": data}
    data = inspect_terminal_events(
        _conn(repos),
        worker_name=str(getattr(args, "worker", "") or "") or None,
        source_table=str(getattr(args, "source_table", "") or "") or None,
        status=str(getattr(args, "status", "") or "terminal"),
        reason_bucket=str(getattr(args, "reason_bucket", "") or "") or None,
        limit=limit,
    )
    return 0, {"ok": True, "data": data}


def handle_queue_resolve(args: object, repos: object, *, now_ms: int) -> tuple[int, dict[str, Any]]:
    reason = str(getattr(args, "reason", "") or "").strip()
    if not bool(getattr(args, "execute", False)) or not reason:
        return 1, {"ok": False, "error": "execute_and_reason_required"}
    try:
        data = resolve_terminal_event(
            _conn(repos),
            terminal_id=str(getattr(args, "terminal_id", "") or ""),
            action=str(getattr(args, "action", "") or ""),
            reason=reason,
            now_ms=int(now_ms),
            retry_transitions=_bound_retry_transitions(repos),
        )
    except ValueError as exc:
        return 1, {"ok": False, "error": str(exc)}
    return 0, {"ok": True, "data": data}


def handle_queue_resolve_bucket(args: object, repos: object, *, now_ms: int) -> tuple[int, dict[str, Any]]:
    reason = str(getattr(args, "reason", "") or "").strip()
    worker_name = str(getattr(args, "worker", "") or "").strip()
    source_table = str(getattr(args, "source_table", "") or "").strip()
    reason_bucket = str(getattr(args, "reason_bucket", "") or "").strip()
    action = str(getattr(args, "action", "") or "").strip()
    execute = bool(getattr(args, "execute", False))
    dry_run = bool(getattr(args, "dry_run", False))
    try:
        limit = _positive_limit(args, default=100)
    except ValueError as exc:
        return 1, {"ok": False, "error": str(exc)}
    if not reason:
        return 1, {"ok": False, "error": "reason_required"}
    if not worker_name or not source_table or not reason_bucket:
        return 1, {"ok": False, "error": "queue_resolve_bucket_filters_required"}
    terminal_ids = list_terminal_event_ids(
        _conn(repos),
        worker_name=worker_name,
        source_table=source_table,
        reason_bucket=reason_bucket,
        limit=limit,
    )
    data: dict[str, Any] = {
        "mode": "execute" if execute else "dry_run",
        "execute": execute,
        "dry_run": dry_run,
        "worker": worker_name,
        "source_table": source_table,
        "reason_bucket": reason_bucket,
        "action": action,
        "limit": limit,
        "matched_count": len(terminal_ids),
        "resolved_count": 0,
        "error_count": 0,
        "error_counts": {},
    }
    if not execute:
        return 0, {"ok": True, "data": data}

    retry_transitions = _bound_retry_transitions(repos)
    error_counts: dict[str, int] = {}
    for terminal_id in terminal_ids:
        try:
            resolve_terminal_event(
                _conn(repos),
                terminal_id=terminal_id,
                action=action,
                reason=reason,
                now_ms=int(now_ms),
                retry_transitions=retry_transitions,
            )
        except ValueError as exc:
            message = str(exc)
            error_counts[message] = error_counts.get(message, 0) + 1
            continue
        data["resolved_count"] = int(data["resolved_count"]) + 1
    data["error_counts"] = dict(sorted(error_counts.items()))
    data["error_count"] = sum(error_counts.values())
    if data["error_count"]:
        return 1, {"ok": False, "error": "queue_resolve_bucket_partial_failed", "data": data}
    return 0, {"ok": True, "data": data}


def _bound_retry_transitions(repos: object) -> dict[tuple[str, str], Callable[..., dict[str, Any]]]:
    return {key: _bind_retry_transition(repos, transition) for key, transition in QUEUE_RETRY_TRANSITIONS.items()}


def _bind_retry_transition(
    repos: object,
    transition: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    def bound(event: dict[str, Any], *, now_ms: int, reason: str) -> dict[str, Any]:
        return transition(repos, event, now_ms=now_ms, reason=reason)

    return bound


def _conn(repos: object) -> object:
    try:
        return cast(Any, repos).signals.conn
    except AttributeError as exc:
        raise ValueError("signals_connection_required") from exc


def _inspect_active_queues(
    conn: object,
    *,
    worker_name: str | None,
    source_table: str | None,
    limit: int,
) -> dict[str, Any]:
    tables_by_worker = worker_queue_health_tables()
    if worker_name is not None:
        selected_tables = list(tables_by_worker.get(worker_name, ()))
    else:
        selected_tables = sorted({table for tables in tables_by_worker.values() for table in tables})
    if source_table is not None:
        selected_tables = [table for table in selected_tables if table == source_table]
    limit = max(1, min(500, int(limit)))
    selected_tables = selected_tables[:limit]
    now_ms = _now_ms()
    items = [
        {
            "source_table": table,
            "queue_health": fetch_queue_table_health(conn, table, now_ms=now_ms, worker_name=worker_name),
        }
        for table in selected_tables
    ]
    return {
        "status": "active",
        "worker": worker_name,
        "source_table": source_table,
        "limit": limit,
        "count": len(items),
        "items": items,
    }


def _positive_limit(args: object, *, default: int, maximum: int = 500) -> int:
    try:
        raw_value = getattr(args, "limit", default)
        raw_limit = int(default if raw_value is None else raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit_must_be_positive") from exc
    if raw_limit < 1:
        raise ValueError("limit_must_be_positive")
    return min(maximum, raw_limit)


def _retry_discovery_lookup_key(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        enqueue_lookup_keys = cast(Any, repos).discovery.enqueue_lookup_keys
    except AttributeError as exc:
        raise ValueError("discovery_repository_required") from exc
    if not callable(enqueue_lookup_keys):
        raise ValueError("discovery_repository_required")
    source_row = _source_row(event)
    lookup_key = _lookup_key(event, source_row)
    provider = str(source_row.get("provider") or DISCOVERY_PROVIDER)
    if provider != DISCOVERY_PROVIDER:
        raise ValueError(f"unsupported_discovery_provider:{provider}")
    latest_seen_ms = _optional_int(source_row.get("latest_seen_ms")) or int(now_ms)
    intent_count = max(1, _optional_int(source_row.get("intent_count")) or 1)
    requeued = enqueue_lookup_keys(
        [lookup_key],
        reason=f"terminal_retry:{reason}",
        now_ms=int(now_ms),
        due_at_ms=int(now_ms),
        latest_seen_ms=latest_seen_ms,
        intent_count=intent_count,
        commit=False,
    )
    if int(requeued or 0) <= 0:
        raise ValueError("discovery_lookup_retry_not_requeued")
    return {
        "provider": provider,
        "lookup_key": lookup_key,
        "requeued": int(requeued or 0),
        "due_at_ms": int(now_ms),
        "latest_seen_at_ms": latest_seen_ms,
        "intent_count": intent_count,
    }


def _retry_event_anchor_job(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        retry = cast(Any, repos).event_anchor_jobs.retry_terminal_job_from_snapshot
    except AttributeError as exc:
        raise ValueError("event_anchor_job_repository_required") from exc
    if not callable(retry):
        raise ValueError("event_anchor_job_repository_required")
    row = retry(_source_row(event), now_ms=int(now_ms), reason=reason)
    _require_requeued(row, "event_anchor_job_retry_not_requeued")
    return {"requeued": 1, "job": row}


def _retry_pulse_agent_job(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        retry = cast(Any, repos).pulse_jobs.retry_terminal_job_from_snapshot
    except AttributeError as exc:
        raise ValueError("pulse_jobs_repository_required") from exc
    if not callable(retry):
        raise ValueError("pulse_jobs_repository_required")
    row = retry(_source_row(event), now_ms=int(now_ms), reason=reason)
    _require_requeued(row, "pulse_agent_job_retry_not_requeued")
    return {"requeued": 1, "job": row}


def _retry_pulse_trigger_dirty_target(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        enqueue_targets = cast(Any, repos).pulse_trigger_dirty_targets.enqueue_targets
    except AttributeError as exc:
        raise ValueError("pulse_trigger_dirty_target_repository_required") from exc
    if not callable(enqueue_targets):
        raise ValueError("pulse_trigger_dirty_target_repository_required")
    source_row = _source_row(event)
    target = {**source_row, "due_at_ms": int(now_ms)}
    requeued = enqueue_targets(
        [target],
        reason=f"terminal_retry:{reason}",
        now_ms=int(now_ms),
        due_at_ms=int(now_ms),
        commit=False,
    )
    requeued_count = int((requeued or {}).get("targets") or 0)
    if requeued_count <= 0:
        raise ValueError("pulse_trigger_dirty_target_retry_not_requeued")
    return {"requeued": requeued_count, "due_at_ms": int(now_ms)}


def _retry_narrative_admission_dirty_target(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        enqueue_targets = cast(Any, repos).narrative_admission_dirty_targets.enqueue_targets
    except AttributeError as exc:
        raise ValueError("narrative_admission_dirty_target_repository_required") from exc
    if not callable(enqueue_targets):
        raise ValueError("narrative_admission_dirty_target_repository_required")
    source_row = _source_row(event)
    target = {**source_row, "due_at_ms": int(now_ms)}
    requeued = enqueue_targets(
        [target],
        reason=f"terminal_retry:{reason}",
        now_ms=int(now_ms),
        due_at_ms=int(now_ms),
        commit=False,
    )
    requeued_count = int((requeued or {}).get("targets") or 0)
    if requeued_count <= 0:
        raise ValueError("narrative_admission_dirty_target_retry_not_requeued")
    return {"requeued": requeued_count, "due_at_ms": int(now_ms)}


def _retry_market_tick_current_dirty_target(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        enqueue_targets = cast(Any, repos).market_tick_current_dirty_targets.enqueue_targets
    except AttributeError as exc:
        raise ValueError("market_tick_current_dirty_target_repository_required") from exc
    if not callable(enqueue_targets):
        raise ValueError("market_tick_current_dirty_target_repository_required")
    source_row = _source_row(event)
    requeued = enqueue_targets(
        [source_row],
        reason=f"terminal_retry:{reason}",
        now_ms=int(now_ms),
        commit=False,
    )
    requeued_count = int(requeued or 0)
    if requeued_count <= 0:
        raise ValueError("market_tick_current_dirty_target_retry_not_requeued")
    return {"requeued": requeued_count, "due_at_ms": int(now_ms)}


def _retry_token_image_source_target(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        enqueue_targets = cast(Any, repos).token_image_source_dirty_targets.enqueue_targets
    except AttributeError as exc:
        raise ValueError("token_image_source_dirty_target_repository_required") from exc
    if not callable(enqueue_targets):
        raise ValueError("token_image_source_dirty_target_repository_required")
    source_row = _source_row(event)
    target = {**source_row, "due_at_ms": int(now_ms)}
    requeued = enqueue_targets(
        [target],
        reason=f"terminal_retry:{reason}",
        now_ms=int(now_ms),
        due_at_ms=int(now_ms),
        commit=False,
    )
    requeued_count = int((requeued or {}).get("targets") or 0)
    if requeued_count <= 0:
        raise ValueError("token_image_source_retry_not_requeued")
    return {
        "requeued": requeued_count,
        "source_url": str(source_row.get("source_url") or ""),
        "target_type": str(source_row.get("target_type") or ""),
        "target_id": str(source_row.get("target_id") or ""),
        "due_at_ms": int(now_ms),
    }


def _retry_token_profile_current_dirty_target(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        enqueue_targets = cast(Any, repos).token_profile_current_dirty_targets.enqueue_targets
    except AttributeError as exc:
        raise ValueError("token_profile_current_dirty_target_repository_required") from exc
    if not callable(enqueue_targets):
        raise ValueError("token_profile_current_dirty_target_repository_required")
    source_row = _source_row(event)
    requeued = enqueue_targets(
        [{**source_row, "due_at_ms": int(now_ms)}],
        reason=f"terminal_retry:{reason}",
        now_ms=int(now_ms),
        due_at_ms=int(now_ms),
        commit=False,
    )
    requeued_count = int((requeued or {}).get("targets") or 0)
    if requeued_count <= 0:
        raise ValueError("token_profile_current_dirty_target_retry_not_requeued")
    return {"requeued": requeued_count, "due_at_ms": int(now_ms)}


def _retry_token_radar_dirty_target(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        enqueue_targets = cast(Any, repos).token_radar_dirty_targets.enqueue_targets
    except AttributeError as exc:
        raise ValueError("token_radar_dirty_target_repository_required") from exc
    if not callable(enqueue_targets):
        raise ValueError("token_radar_dirty_target_repository_required")
    source_row = _source_row(event)
    requeued = enqueue_targets(
        [source_row],
        reason=f"terminal_retry:{reason}",
        now_ms=int(now_ms),
        due_at_ms=int(now_ms),
        commit=False,
    )
    requeued_count = int(requeued or 0)
    if requeued_count <= 0:
        raise ValueError("token_radar_dirty_target_retry_not_requeued")
    return {"requeued": requeued_count, "due_at_ms": int(now_ms)}


def _retry_token_radar_source_dirty_event(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        enqueue_events = cast(Any, repos).token_radar_source_dirty_events.enqueue_events
    except AttributeError as exc:
        raise ValueError("token_radar_source_dirty_event_repository_required") from exc
    if not callable(enqueue_events):
        raise ValueError("token_radar_source_dirty_event_repository_required")
    source_row = _source_row(event)
    requeued = enqueue_events(
        [source_row],
        reason=f"terminal_retry:{reason}",
        now_ms=int(now_ms),
        due_at_ms=int(now_ms),
        commit=False,
    )
    requeued_count = int(requeued or 0)
    if requeued_count <= 0:
        raise ValueError("token_radar_source_dirty_event_retry_not_requeued")
    return {"requeued": requeued_count, "due_at_ms": int(now_ms)}


def _retry_macro_projection_dirty_target(
    repos: object,
    event: dict[str, Any],
    *,
    now_ms: int,
    reason: str,
) -> dict[str, Any]:
    try:
        repo = cast(Any, repos).macro_intel
    except AttributeError as exc:
        raise ValueError("macro_intel_repository_required") from exc
    source_row = _source_row(event)
    projection_name = str(source_row.get("projection_name") or "").strip()
    projection_version = str(source_row.get("projection_version") or "").strip()
    target_kind = str(source_row.get("target_kind") or "").strip()
    if not projection_name or not projection_version or not target_kind:
        raise ValueError("macro_projection_dirty_target_source_row_required")
    retry_reason = f"terminal_retry:{reason}"
    if target_kind == "current":
        try:
            enqueue_current = repo.enqueue_macro_projection_dirty_target
        except AttributeError as exc:
            raise ValueError("macro_intel_repository_required") from exc
        if not callable(enqueue_current):
            raise ValueError("macro_intel_repository_required")
        requeued = enqueue_current(
            projection_name=projection_name,
            projection_version=projection_version,
            now_ms=int(now_ms),
            due_at_ms=int(now_ms),
            reason=retry_reason,
            commit=False,
        )
    elif target_kind == "concept":
        try:
            enqueue_changes = repo.enqueue_macro_projection_dirty_targets_for_changes
        except AttributeError as exc:
            raise ValueError("macro_intel_repository_required") from exc
        if not callable(enqueue_changes):
            raise ValueError("macro_intel_repository_required")
        concept_key = str(source_row.get("concept_key") or source_row.get("target_id") or "").strip()
        observed_at = (
            source_row.get("max_observed_at")
            or source_row.get("source_watermark_date")
            or source_row.get("min_observed_at")
        )
        if not concept_key or observed_at is None:
            raise ValueError("macro_projection_dirty_target_concept_source_row_required")
        requeued = enqueue_changes(
            changed_observations=[{"concept_key": concept_key, "observed_at": observed_at}],
            projection_name=projection_name,
            projection_version=projection_version,
            now_ms=int(now_ms),
            due_at_ms=int(now_ms),
            reason=retry_reason,
            commit=False,
        )
    else:
        raise ValueError(f"unsupported_macro_projection_dirty_target_kind:{target_kind}")
    requeued_count = int(requeued or 0)
    if requeued_count <= 0:
        raise ValueError("macro_projection_dirty_target_retry_not_requeued")
    return {
        "requeued": requeued_count,
        "projection_name": projection_name,
        "projection_version": projection_version,
        "target_kind": target_kind,
        "due_at_ms": int(now_ms),
    }


def _source_row(event: dict[str, Any]) -> dict[str, Any]:
    source_row = event.get("source_row_json")
    if not isinstance(source_row, dict):
        raise ValueError("terminal_source_row_required")
    return source_row


def _lookup_key(event: dict[str, Any], source_row: dict[str, Any]) -> str:
    lookup_key = str(source_row.get("lookup_key") or "").strip()
    if lookup_key:
        return lookup_key
    target_key = str(event.get("target_key") or "")
    prefix = f"{DISCOVERY_PROVIDER}:"
    if target_key.startswith(prefix):
        lookup_key = target_key.removeprefix(prefix).strip()
    if not lookup_key:
        raise ValueError("terminal_lookup_key_required")
    return lookup_key


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _require_requeued(row: object, code: str) -> None:
    if not row:
        raise ValueError(code)


QUEUE_RETRY_TRANSITIONS = {
    ("resolution_refresh", "token_discovery_dirty_lookup_keys"): _retry_discovery_lookup_key,
    ("event_anchor_backfill", "event_anchor_backfill_jobs"): _retry_event_anchor_job,
    ("market_tick_current_projection", "market_tick_current_dirty_targets"): _retry_market_tick_current_dirty_target,
    ("narrative_admission", "narrative_admission_dirty_targets"): _retry_narrative_admission_dirty_target,
    ("pulse_candidate", "pulse_agent_jobs"): _retry_pulse_agent_job,
    ("pulse_candidate", "pulse_trigger_dirty_targets"): _retry_pulse_trigger_dirty_target,
    ("token_image_mirror", "token_image_source_dirty_targets"): _retry_token_image_source_target,
    ("token_profile_current", "token_profile_current_dirty_targets"): _retry_token_profile_current_dirty_target,
    ("token_radar_projection", "token_radar_dirty_targets"): _retry_token_radar_dirty_target,
    ("token_radar_projection", "token_radar_source_dirty_events"): _retry_token_radar_source_dirty_event,
    ("macro_view_projection", "macro_projection_dirty_targets"): _retry_macro_projection_dirty_target,
}


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)
