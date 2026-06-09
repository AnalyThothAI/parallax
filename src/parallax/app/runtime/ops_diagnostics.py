from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from parallax.app.runtime.job_queue import JOB_QUEUE_DESCRIPTORS, JobQueueDescriptor
from parallax.app.runtime.worker_status import effective_worker_status, workers_status_payload
from parallax.domains.pulse_lab.queries.pulse_freshness_health_queries import (
    fetch_pulse_health_candidates,
    fetch_pulse_health_clocks,
    fetch_pulse_health_jobs,
    fetch_pulse_health_runs,
)
from parallax.domains.token_intel.repositories.projection_repository import ProjectionRepository
from parallax.platform.db.postgres_client import postgres_health_check
from parallax.platform.db.postgres_migrations import latest_migration_version
from parallax.platform.paths.runtime_paths import workers_config_path

OPS_DIAGNOSTICS_SCHEMA_VERSION = "ops.diagnostics.v1"
OPS_QUEUE_SCHEMA_VERSION = "ops.queue.v1"
INVALID_QUEUE = {"error": "invalid_queue"}
INVALID_STATUS = {"error": "invalid_status"}

SECRET_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "cookie",
    "dsn",
    "passphrase",
    "password",
    "secret",
)
SECRET_TOKEN_KEYS = (
    "access_token",
    "api_token",
    "auth_token",
    "bearer_token",
    "refresh_token",
    "session_token",
    "ws_token",
)
TERMINAL_SUCCESS_STATUSES = {"done", "delivered"}
QUEUE_ALLOWED_STATUSES = {"pending", "running", "failed", "dead", "done", "delivered"}
AGENT_EXECUTION_RECENT_SIGNAL_MS = 5 * 60 * 1000
AGENT_EXECUTION_POLICY_KEYS = {
    "allowed_child_lanes",
    "global_max_concurrency",
    "max_concurrency",
    "priority",
    "priority_label",
    "rpm_limit",
    "timeout_seconds",
}
AGENT_EXECUTION_COUNTER_KEYS = {
    "capacity_denied_total",
    "circuit_open_total",
    "global_in_flight",
    "in_flight",
    "last_capacity_denied_at_ms",
    "last_circuit_open_at_ms",
    "last_denied_at_ms",
    "last_parent_reservation_denied_at_ms",
    "last_provider_latency_timeout_at_ms",
    "last_rate_limit_at_ms",
    "last_rpm_wait_at_ms",
    "last_timeout_at_ms",
    "oldest_in_flight_age_ms",
    "parent_reservation_denied_total",
    "provider_latency_timeout_total",
    "provider_running",
    "rate_limit_denied_total",
    "rpm_waiting_count",
    "timeout_total",
}


def ops_diagnostics_payload(
    runtime: Any,
    *,
    now_ms: int | None = None,
    since_hours: int = 4,
    window: str = "1h",
    scope: str = "all",
) -> dict[str, Any]:
    generated_at_ms = int(now_ms if now_ms is not None else _now_ms())
    since_ms = generated_at_ms - max(1, int(since_hours)) * 60 * 60 * 1000
    database = _section("database", lambda: _database_payload(runtime))
    collector = _section("collector", lambda: _collector_payload(runtime))
    providers = _providers_payload(runtime)
    worker_status = workers_status_payload(runtime)
    workers = _workers_payload(worker_status["workers"])
    worker_lanes = worker_status["worker_lanes"]
    queues = _queues_payload(runtime, now_ms=generated_at_ms)
    agent_execution = _agent_execution_payload(runtime, now_ms=generated_at_ms)
    domains = _domains_payload(
        runtime,
        now_ms=generated_at_ms,
        since_ms=since_ms,
        window=window,
        scope=scope,
    )
    payload = {
        "schema_version": OPS_DIAGNOSTICS_SCHEMA_VERSION,
        "generated_at_ms": generated_at_ms,
        "overall": _overall_payload(
            database=database,
            collector=collector,
            providers=providers,
            workers=workers,
            queues=queues,
            agent_execution=agent_execution,
            domains=domains,
        ),
        "config": _config_payload(runtime),
        "database": database,
        "collector": collector,
        "providers": providers,
        "workers": workers,
        "worker_lanes": worker_lanes,
        "queues": queues,
        "agent_execution": agent_execution,
        "domains": domains,
        "suggested_checks": _suggested_checks(queues=queues, domains=domains),
    }
    return redact_diagnostics(payload)


def ops_queue_payload(
    runtime: Any,
    *,
    queue_name: str,
    status: str | None,
    limit: int,
    now_ms: int | None = None,
) -> dict[str, Any]:
    descriptor = JOB_QUEUE_DESCRIPTORS.get(str(queue_name or "").strip())
    if descriptor is None:
        return INVALID_QUEUE
    normalized_status = str(status or "").strip() or None
    if normalized_status is not None and normalized_status not in QUEUE_ALLOWED_STATUSES:
        return INVALID_STATUS
    generated_at_ms = int(now_ms if now_ms is not None else _now_ms())
    with runtime.db.api_pool.connection() as conn:
        summary = _queue_summary(conn, descriptor, now_ms=generated_at_ms)
        items = _queue_items(
            conn,
            descriptor,
            limit=max(0, min(int(limit), 200)),
            status=normalized_status,
        )
    return redact_diagnostics(
        {
            "schema_version": OPS_QUEUE_SCHEMA_VERSION,
            "queue_name": descriptor.name,
            "status_filter": normalized_status,
            "counts_by_status": summary["counts_by_status"],
            "summary": summary,
            "items": items,
        }
    )


def redact_diagnostics(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if _is_secret_key(text_key):
                redacted[text_key] = "<redacted>"
            else:
                redacted[text_key] = redact_diagnostics(item)
        return redacted
    if isinstance(value, list):
        return [redact_diagnostics(item) for item in value]
    if isinstance(value, tuple):
        return [redact_diagnostics(item) for item in value]
    return value


def _section(name: str, factory: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        payload = dict(factory())
    except Exception as exc:
        return {
            "status": "unknown",
            "section": name,
            "error_type": type(exc).__name__,
            "reason": _preview_error(exc),
        }
    payload.setdefault("status", "ok")
    return payload


def _database_payload(runtime: Any) -> dict[str, Any]:
    with runtime.db.api_pool.connection() as conn:
        payload = postgres_health_check(conn, expected_migration_version=latest_migration_version())
    status = "ok" if payload.get("ok") else "blocked"
    return {"status": status, **payload}


def _collector_payload(runtime: Any) -> dict[str, Any]:
    collector = getattr(runtime, "collector", None)
    status_object = getattr(collector, "status", None)
    to_dict = getattr(status_object, "to_dict", None)
    details = to_dict() if callable(to_dict) else {}
    provider = getattr(collector, "upstream_client", None)
    connection = _provider_connection_payload(provider)
    state = str(connection.get("state") or "")
    status = "ok" if state in {"connected", "running"} or not provider else "degraded"
    return {
        "status": status,
        "connection": connection,
        "details": details if isinstance(details, dict) else {},
    }


def _providers_payload(runtime: Any) -> list[dict[str, Any]]:
    providers = []
    providers.extend(_asset_market_provider_health(runtime))
    providers.extend(_connection_providers(runtime))
    return sorted(providers, key=lambda item: (str(item.get("domain")), str(item.get("provider"))))


def _asset_market_provider_health(runtime: Any) -> list[dict[str, Any]]:
    asset_market = getattr(getattr(runtime, "providers", None), "asset_market", None)
    health_items = getattr(asset_market, "provider_health", ()) or ()
    providers: list[dict[str, Any]] = []
    for item in health_items:
        payload = _object_payload(item)
        capabilities = payload.get("capabilities") or []
        providers.append(
            {
                "provider": str(payload.get("provider") or "unknown"),
                "domain": "asset_market",
                "configured": bool(payload.get("configured")),
                "capabilities": sorted(str(capability) for capability in capabilities),
                "state": "configured" if payload.get("configured") else "disabled",
                "last_state_change_at_ms": None,
                "last_error_type": _error_type(payload.get("last_error")),
                "status": _provider_status(
                    configured=bool(payload.get("configured")),
                    state=None,
                    error=payload.get("last_error"),
                ),
                "reason": _provider_reason(configured=bool(payload.get("configured")), error=payload.get("last_error")),
            }
        )
    return providers


def _connection_providers(runtime: Any) -> list[dict[str, Any]]:
    collector = getattr(runtime, "collector", None)
    asset_market = getattr(getattr(runtime, "providers", None), "asset_market", None)
    return [
        _connection_provider_payload(
            provider_name="gmgn_direct_ws",
            domain="ingestion",
            provider=getattr(collector, "upstream_client", None),
            configured=getattr(collector, "upstream_client", None) is not None,
        ),
        _connection_provider_payload(
            provider_name="okx_dex_ws",
            domain="asset_market",
            provider=getattr(asset_market, "stream_dex_market", None),
            configured=getattr(asset_market, "stream_dex_market", None) is not None,
        ),
    ]


def _connection_provider_payload(
    *,
    provider_name: str,
    domain: str,
    provider: Any | None,
    configured: bool,
) -> dict[str, Any]:
    connection = _provider_connection_payload(provider)
    state = str(connection.get("state") or "disabled")
    error = connection.get("error")
    return {
        "provider": provider_name,
        "domain": domain,
        "configured": bool(configured),
        "capabilities": ["stream"],
        "state": state,
        "last_state_change_at_ms": connection.get("last_state_change_at_ms"),
        "last_error_type": _error_type(error),
        "status": _provider_status(configured=configured, state=state, error=error),
        "reason": _provider_reason(configured=configured, state=state, error=error),
    }


def _provider_connection_payload(provider: Any | None) -> dict[str, Any]:
    if provider is None:
        return {"state": "disabled", "last_state_change_at_ms": None}
    payload = getattr(provider, "connection_state_payload", None)
    if not callable(payload):
        return {"state": "configured", "last_state_change_at_ms": None}
    try:
        value = payload()
    except Exception as exc:
        return {"state": "failed", "last_state_change_at_ms": None, "error": _preview_error(exc)}
    return value if isinstance(value, dict) else {"state": "failed", "last_state_change_at_ms": None}


def _provider_status(*, configured: bool, state: str | None = None, error: Any = None) -> str:
    if not configured:
        return "disabled"
    if state in {"failed", "disconnected"}:
        return "blocked"
    if error:
        return "degraded"
    return "ok"


def _provider_reason(*, configured: bool, state: str | None = None, error: Any = None) -> str:
    if not configured:
        return "not_configured"
    if state in {"failed", "disconnected"}:
        return f"connection_{state}"
    if error:
        return "provider_error_visible"
    return "ready"


def _workers_payload(workers: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for name, status in sorted(workers.items()):
        last_error = status.get("last_error")
        enabled = bool(status.get("enabled"))
        running = bool(status.get("running"))
        effective_status = effective_worker_status(status)
        payloads.append(
            {
                "name": name,
                "group": _worker_group(name),
                "enabled": enabled,
                "running": running,
                "effective_status": effective_status,
                "unavailable_reason": status.get("unavailable_reason"),
                "last_started_at_ms": status.get("last_started_at_ms"),
                "last_finished_at_ms": status.get("last_finished_at_ms"),
                "last_result": status.get("last_result"),
                "last_error_type": _error_type(last_error),
                "iteration_duration_p99_ms": status.get("iteration_duration_p99_ms"),
                "pool_wait_ms_p99": status.get("pool_wait_ms_p99"),
                "queue_depth": status.get("queue_depth"),
                "details": status.get("details") or {},
                "status": effective_status,
                "reason": _worker_reason(
                    effective_status=effective_status,
                    unavailable_reason=status.get("unavailable_reason"),
                    last_error=last_error,
                ),
            }
        )
    return payloads


def _worker_reason(*, effective_status: str, unavailable_reason: Any, last_error: Any) -> str:
    if effective_status == "disabled":
        return "disabled"
    if effective_status == "intentionally_not_started":
        return "intentionally_not_started"
    if effective_status == "unavailable":
        return str(unavailable_reason or "unavailable")
    if effective_status == "failed":
        return "last_error_visible" if last_error else "worker_failed"
    if effective_status == "degraded":
        return "worker_degraded"
    if effective_status == "stopped":
        return "not_currently_running"
    return "running"


def _worker_group(name: str) -> str:
    if name in {"collector"}:
        return "ingestion"
    if name.startswith(("token_", "resolution", "asset_", "market_", "anchor_")):
        return "asset_market"
    if name.startswith(("pulse", "signal")):
        return "pulse"
    if name.startswith(("narrative", "mention", "token_discussion")):
        return "narrative"
    if name.startswith("news"):
        return "news"
    if name.startswith(("watchlist", "handle")):
        return "watchlist"
    if name.startswith("notification"):
        return "notifications"
    return "runtime"


def _queues_payload(runtime: Any, *, now_ms: int) -> list[dict[str, Any]]:
    db = getattr(runtime, "db", None)
    api_pool = getattr(db, "api_pool", None)
    connection = getattr(api_pool, "connection", None)
    if not callable(connection):
        return []
    with connection() as conn:
        return [_queue_summary(conn, descriptor, now_ms=now_ms) for descriptor in JOB_QUEUE_DESCRIPTORS.values()]


def _queue_summary(conn: Any, descriptor: JobQueueDescriptor, *, now_ms: int) -> dict[str, Any]:
    counts = _queue_counts(conn, descriptor)
    clocks = _queue_clocks(conn, descriptor, now_ms=now_ms)
    dead_count = int(counts.get("dead", 0))
    failed_count = int(counts.get("failed", 0))
    running_count = int(clocks.get("running_count", 0))
    due_count = int(clocks.get("due_count", 0))
    status = _queue_status(counts=counts, due_count=due_count, running_count=running_count)
    return {
        "queue_name": descriptor.name,
        "table": descriptor.table,
        "worker_name": _queue_worker_name(descriptor.name),
        "counts_by_status": counts,
        "due_count": due_count,
        "running_count": running_count,
        "dead_count": dead_count,
        "failed_count": failed_count,
        "oldest_due_age_ms": _age_ms(now_ms, clocks.get("oldest_due_at_ms")),
        "oldest_running_age_ms": _age_ms(now_ms, clocks.get("oldest_running_at_ms")),
        "status": status,
        "reason": _queue_reason(status=status, dead_count=dead_count, failed_count=failed_count, due_count=due_count),
    }


def _queue_counts(conn: Any, descriptor: JobQueueDescriptor) -> dict[str, int]:
    rows = conn.execute(f"SELECT status, COUNT(*) AS count FROM {descriptor.table} GROUP BY status").fetchall()
    counts: dict[str, int] = {}
    for row in rows:
        item = dict(row)
        counts[str(item.get("status"))] = int(item.get("count") or 0)
    return counts


def _queue_clocks(conn: Any, descriptor: JobQueueDescriptor, *, now_ms: int) -> dict[str, Any]:
    row = conn.execute(
        f"""
        SELECT
          COUNT(*) FILTER (
            WHERE status = 'pending' AND {descriptor.next_run_column} <= %s
          ) AS due_count,
          COUNT(*) FILTER (WHERE status = 'running') AS running_count,
          COUNT(*) FILTER (WHERE status = 'dead') AS dead_count,
          MIN({descriptor.next_run_column}) FILTER (
            WHERE status = 'pending' AND {descriptor.next_run_column} <= %s
          ) AS oldest_due_at_ms,
          MIN(updated_at_ms) FILTER (WHERE status = 'running') AS oldest_running_at_ms
        FROM {descriptor.table}
        """,
        (int(now_ms), int(now_ms)),
    ).fetchone()
    return dict(row) if row else {}


def _queue_items(
    conn: Any,
    descriptor: JobQueueDescriptor,
    *,
    limit: int,
    status: str | None,
) -> list[dict[str, Any]]:
    where = "WHERE status = %s" if status else ""
    params: tuple[Any, ...] = (status, limit) if status else (limit,)
    rows = conn.execute(
        f"""
        SELECT *
        FROM {descriptor.table}
        {where}
        ORDER BY updated_at_ms DESC
        LIMIT %s
        """,
        params,
    ).fetchall()
    return [_sanitized_job_row(dict(row), descriptor=descriptor) for row in rows]


def _sanitized_job_row(row: dict[str, Any], *, descriptor: JobQueueDescriptor) -> dict[str, Any]:
    return {
        "id": row.get(descriptor.id_column),
        "status": row.get("status"),
        "attempt_count": row.get("attempt_count"),
        "max_attempts": row.get("max_attempts"),
        "created_at_ms": row.get("created_at_ms"),
        "updated_at_ms": row.get("updated_at_ms"),
        "next_run_at_ms": row.get(descriptor.next_run_column),
        "last_attempt_at_ms": row.get(descriptor.last_attempt_at_column) if descriptor.last_attempt_at_column else None,
        "delivered_at_ms": row.get(descriptor.delivered_at_column) if descriptor.delivered_at_column else None,
        "last_error_type": _error_type(row.get("last_error")),
        "last_error_preview": _preview_text(row.get("last_error")),
        "source": _job_source(row),
    }


def _job_source(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "event_id",
        "candidate_id",
        "target_type",
        "target_id",
        "window",
        "scope",
        "handle",
        "rule_id",
        "notification_id",
        "channel",
    )
    return {key: row.get(key) for key in keys if row.get(key) is not None}


def _queue_status(*, counts: dict[str, int], due_count: int, running_count: int) -> str:
    if int(counts.get("dead", 0)) > 0:
        return "blocked"
    if int(counts.get("failed", 0)) > 0:
        return "degraded"
    if due_count > 0 or running_count > 0 or int(counts.get("pending", 0)) > 0:
        return "ok"
    if counts and any(status not in TERMINAL_SUCCESS_STATUSES for status in counts):
        return "ok"
    return "idle"


def _queue_reason(*, status: str, dead_count: int, failed_count: int, due_count: int) -> str:
    if dead_count > 0:
        return "dead_jobs_present"
    if failed_count > 0:
        return "retryable_failures_present"
    if due_count > 0:
        return "due_work_present"
    if status == "idle":
        return "no_active_work"
    return "fresh_work"


def _queue_worker_name(queue_name: str) -> str:
    return {
        "notification_deliveries": "notification_delivery",
        "pulse_agent_jobs": "pulse_candidate",
    }.get(queue_name, queue_name)


def _domains_payload(
    runtime: Any,
    *,
    now_ms: int,
    since_ms: int,
    window: str,
    scope: str,
) -> dict[str, Any]:
    return {
        "token_radar": _section("token_radar", lambda: _token_radar_domain(runtime)),
        "asset_market": _section("asset_market", lambda: _asset_market_domain(runtime)),
        "pulse": _section(
            "pulse",
            lambda: _pulse_domain(runtime, now_ms=now_ms, since_ms=since_ms, window=window, scope=scope),
        ),
        "news": _section("news", lambda: _news_domain(runtime)),
        "watchlist": _section("watchlist", lambda: _watchlist_domain(runtime)),
        "notifications": _section("notifications", lambda: _notifications_domain(runtime)),
    }


def _token_radar_domain(runtime: Any) -> dict[str, Any]:
    with runtime.repositories() as repos:
        summary = ProjectionRepository(repos.conn).status_summary()
    known = summary.get("known_projections") or []
    status = "ok" if known else "idle"
    return {"status": status, "projection": summary}


def _asset_market_domain(runtime: Any) -> dict[str, Any]:
    providers = _asset_market_provider_health(runtime)
    blocked = [provider for provider in providers if provider.get("status") == "blocked"]
    configured = [provider for provider in providers if provider.get("configured")]
    status = "blocked" if blocked else ("ok" if configured else "disabled")
    return {
        "status": status,
        "configured_provider_count": len(configured),
        "provider_count": len(providers),
    }


def _pulse_domain(runtime: Any, *, now_ms: int, since_ms: int, window: str, scope: str) -> dict[str, Any]:
    with runtime.db.api_pool.connection() as conn:
        payload = {}
        payload.update(fetch_pulse_health_clocks(conn, window=window, scope=scope))
        payload.update(fetch_pulse_health_jobs(conn, window=window, scope=scope, now_ms=now_ms, since_ms=since_ms))
        payload.update(fetch_pulse_health_runs(conn, window=window, scope=scope, since_ms=since_ms))
        payload.update(fetch_pulse_health_candidates(conn, window=window, scope=scope, since_ms=since_ms))
    status = "blocked" if int(payload.get("dead_jobs") or 0) > 0 else "ok"
    return {"status": status, **payload}


def _news_domain(runtime: Any) -> dict[str, Any]:
    with runtime.repositories() as repos:
        sources = repos.news.list_source_status()
    failing = [source for source in sources if str(source.get("status") or "").lower() not in {"ok", "ready", "active"}]
    status = "degraded" if failing else ("ok" if sources else "idle")
    return {"status": status, "sources": sources, "source_count": len(sources)}


def _watchlist_domain(runtime: Any) -> dict[str, Any]:
    configured_handles = tuple(getattr(getattr(runtime, "settings", None), "handles", ()) or ())
    return {"status": "ok" if configured_handles else "idle", "configured_handle_count": len(configured_handles)}


def _notifications_domain(runtime: Any) -> dict[str, Any]:
    with runtime.repositories() as repos:
        summary = repos.notifications.summary(subscriber_key="local")
    return {"status": "ok", "summary": summary}


def _agent_execution_payload(runtime: Any, *, now_ms: int) -> dict[str, Any]:
    gateway = getattr(runtime, "agent_execution_gateway", None)
    if gateway is None:
        providers = getattr(runtime, "providers", None)
        gateway = getattr(providers, "agent_execution_gateway", None)
    snapshot = getattr(gateway, "status_snapshot", None)
    if not callable(snapshot):
        return {"status": "disabled", "policy": {}, "counters": {}, "lanes": {}}
    try:
        raw_snapshot = snapshot()
    except Exception:
        return {"status": "unknown", "status_reason": "unavailable", "policy": {}, "counters": {}, "lanes": {}}
    if not isinstance(raw_snapshot, Mapping):
        return {"status": "unknown", "status_reason": "unavailable", "policy": {}, "counters": {}, "lanes": {}}

    policy = _agent_policy_fields(raw_snapshot)
    counters = _agent_counter_fields(raw_snapshot)
    lanes: dict[str, dict[str, Any]] = {}
    statuses: list[str] = []
    raw_lanes = raw_snapshot.get("lanes")
    if isinstance(raw_lanes, Mapping):
        for lane_name, lane_snapshot in sorted(raw_lanes.items(), key=lambda item: str(item[0])):
            if not isinstance(lane_snapshot, Mapping):
                continue
            lane_policy = _agent_policy_fields(lane_snapshot)
            nested_policy = lane_snapshot.get("policy")
            if isinstance(nested_policy, Mapping):
                lane_policy.update(_agent_policy_fields(nested_policy))
            lane_counters = _agent_counter_fields(lane_snapshot)
            lane_status = _agent_lane_status(
                lane_snapshot,
                policy=lane_policy,
                counters=lane_counters,
                now_ms=now_ms,
            )
            statuses.append(lane_status)
            lanes[str(lane_name)] = {
                "status": lane_status,
                "policy": lane_policy,
                "counters": lane_counters,
            }

    status = "blocked" if "blocked" in statuses else "degraded" if "degraded" in statuses else "ok"
    return {
        "status": status,
        "policy": policy,
        "counters": counters,
        "lanes": lanes,
    }


def _agent_policy_fields(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: snapshot.get(key) for key in AGENT_EXECUTION_POLICY_KEYS if key in snapshot}


def _agent_counter_fields(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: snapshot.get(key) for key in AGENT_EXECUTION_COUNTER_KEYS if key in snapshot}


def _agent_lane_status(
    snapshot: Mapping[str, Any],
    *,
    policy: Mapping[str, Any],
    counters: Mapping[str, Any],
    now_ms: int,
) -> str:
    circuit_open = str(snapshot.get("circuit_state") or "").lower() == "open"
    if circuit_open and _agent_priority_label(policy) == "high":
        return "blocked"
    if circuit_open:
        return "degraded"
    if _positive_counter(counters.get("rpm_waiting_count")):
        return "degraded"
    timeout_seconds = _float_or_none(policy.get("timeout_seconds"))
    oldest_in_flight_age_ms = _float_or_none(counters.get("oldest_in_flight_age_ms"))
    if (
        timeout_seconds is not None
        and oldest_in_flight_age_ms is not None
        and oldest_in_flight_age_ms >= timeout_seconds * 1000
        and _positive_counter(counters.get("provider_running"))
    ):
        return "degraded"
    recent_fields = (
        "last_capacity_denied_at_ms",
        "last_parent_reservation_denied_at_ms",
        "last_denied_at_ms",
        "last_provider_latency_timeout_at_ms",
        "last_rate_limit_at_ms",
        "last_rpm_wait_at_ms",
        "last_timeout_at_ms",
    )
    if any(_is_recent_ms(counters.get(field), now_ms=now_ms) for field in recent_fields):
        return "degraded"
    return "ok"


def _agent_priority_label(policy: Mapping[str, Any]) -> str:
    return str(policy.get("priority_label") or policy.get("priority") or "").strip().lower()


def _positive_counter(value: Any) -> bool:
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_recent_ms(value: Any, *, now_ms: int) -> bool:
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return False
    return 0 <= int(now_ms) - timestamp_ms <= AGENT_EXECUTION_RECENT_SIGNAL_MS


def _overall_payload(
    *,
    database: dict[str, Any],
    collector: dict[str, Any],
    providers: list[dict[str, Any]],
    workers: list[dict[str, Any]],
    queues: list[dict[str, Any]],
    agent_execution: dict[str, Any],
    domains: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    statuses = [
        str(database.get("status")),
        str(collector.get("status")),
        *(str(item.get("status")) for item in providers),
        *(str(item.get("status")) for item in workers),
        *(str(item.get("status")) for item in queues),
        str(agent_execution.get("status")),
        *(str(item.get("status")) for item in domains.values()),
    ]
    counts = dict(Counter(statuses))
    reasons: list[str] = []
    for source in (providers, workers, queues, list(domains.values())):
        reasons.extend(
            str(item.get("reason") or item.get("error_type") or item.get("status"))
            for item in source
            if item.get("status") in {"blocked", "degraded", "failed", "unavailable", "unknown"}
        )
    if agent_execution.get("status") in {"blocked", "degraded", "unknown"}:
        reasons.append(f"agent_execution_{agent_execution.get('status')}")
    if database.get("status") != "ok":
        reasons.append(str(database.get("reason") or "database_not_ready"))
    status = (
        "blocked"
        if counts.get("blocked") or counts.get("unavailable") or counts.get("failed")
        else "degraded"
        if counts.get("degraded") or counts.get("unknown")
        else "ok"
    )
    return {
        "status": status,
        "severity": "critical" if status == "blocked" else "warning" if status == "degraded" else "info",
        "reasons": reasons[:12],
        "section_status_counts": counts,
    }


def _config_payload(runtime: Any) -> dict[str, Any]:
    settings = getattr(runtime, "settings", None)
    app_home = Path(str(getattr(settings, "app_home", ""))).expanduser()
    return {
        "app_home": str(app_home) if str(app_home) else None,
        "config_path": str(app_home / "config.yaml") if str(app_home) else None,
        "workers_config_path": str(workers_config_path(app_home)) if str(app_home) else None,
        "handles_count": len(tuple(getattr(settings, "handles", ()) or ())),
        "upstream_channels": list(getattr(settings, "upstream_channels", ()) or ()),
        "gmgn_configured": bool(getattr(settings, "gmgn_configured", False)),
        "okx_dex_configured": bool(getattr(settings, "okx_dex_configured", False)),
        "llm_configured": bool(getattr(settings, "llm_configured", False)),
        "news_enabled": bool(getattr(settings, "news_intel_enabled", False)),
        "notifications_enabled": bool(getattr(settings, "notification_rules", None) is not None),
    }


def _suggested_checks(*, queues: list[dict[str, Any]], domains: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if any(queue.get("status") == "blocked" for queue in queues):
        checks.append(
            {
                "id": "inspect_worker_status",
                "label": "inspect worker queues",
                "reason": "blocked queue detected",
                "cli_equivalent": "uv run parallax ops worker-status",
                "safe_to_run": True,
                "requires_confirmation": False,
            }
        )
    if (domains.get("news") or {}).get("status") in {"degraded", "unknown"}:
        checks.append(
            {
                "id": "inspect_news_sources",
                "label": "inspect news sources",
                "reason": "news source health is not ready",
                "cli_equivalent": "GET /api/news/sources/status",
                "safe_to_run": True,
                "requires_confirmation": False,
            }
        )
    return checks


def _object_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {key: item for key, item in vars(value).items() if not key.startswith("_") and not callable(item)}


def _error_type(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, BaseException):
        return type(value).__name__
    text = str(value)
    return text.split(":", 1)[0][:80] if text else None


def _preview_error(exc: BaseException) -> str:
    return _preview_text(f"{type(exc).__name__}: {exc}") or type(exc).__name__


def _preview_text(value: Any, *, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:limit]


def _age_ms(now_ms: int, timestamp_ms: Any) -> int | None:
    if timestamp_ms is None:
        return None
    try:
        return max(0, int(now_ms) - int(timestamp_ms))
    except (TypeError, ValueError):
        return None


def _is_secret_key(key: str) -> bool:
    normalized = key.lower()
    if normalized == "token":
        return True
    if normalized.endswith(("_token", "-token")):
        return True
    return any(fragment in normalized for fragment in SECRET_KEY_FRAGMENTS) or any(
        token_key in normalized for token_key in SECRET_TOKEN_KEYS
    )


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = [
    "INVALID_QUEUE",
    "INVALID_STATUS",
    "ops_diagnostics_payload",
    "ops_queue_payload",
    "redact_diagnostics",
]
