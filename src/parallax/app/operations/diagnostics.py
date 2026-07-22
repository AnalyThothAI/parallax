from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any

from parallax.app.operations.queue_health import fetch_queue_table_health
from parallax.app.operations.token_intel import token_radar_publication_status
from parallax.app.runtime.runtime_snapshot import RuntimeSnapshot
from parallax.app.runtime.worker_status import effective_worker_status
from parallax.domains.asset_market.providers import ProviderHealth
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from parallax.platform.db.postgres_client import postgres_liveness_check
from parallax.platform.paths.runtime_paths import config_path, workers_config_path

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
QUEUE_ALLOWED_STATUSES = {"pending", "running", "failed", "dead", "done", "delivered"}
NOTIFICATION_QUEUE_NAME = "notification_deliveries"
NOTIFICATION_QUEUE_TABLE = "notification_deliveries"
NOTIFICATION_QUEUE_WORKER = "notification_delivery"
AGENT_EXECUTION_RECENT_SIGNAL_MS = 5 * 60 * 1000
DIAGNOSTIC_STATUSES = frozenset({"blocked", "degraded", "disabled", "failed", "idle", "ok", "unavailable", "unknown"})
HEALTHY_CONNECTION_STATES = frozenset(
    {"authenticating", "connected", "connecting", "running", "streaming", "subscribed"}
)
BLOCKED_CONNECTION_STATES = frozenset({"circuit_open", "disconnected", "failed", "failed_terminal"})
AGENT_EXECUTION_POLICY_KEYS = (
    "lane",
    "model",
    "provider_family",
    "output_strategy",
    "schema_enforcement",
    "max_concurrency",
    "rpm_limit",
    "timeout_seconds",
)
AGENT_EXECUTION_COUNTER_KEYS = (
    "in_flight",
    "provider_running",
    "circuit_state",
    "circuit_open_until_ms",
    "capacity_denied_total",
    "circuit_open_total",
    "timeout_total",
    "last_denied_at_ms",
    "last_timeout_at_ms",
    "oldest_in_flight_age_ms",
)
AGENT_EXECUTION_FIELDS = frozenset({*AGENT_EXECUTION_POLICY_KEYS, *AGENT_EXECUTION_COUNTER_KEYS})


def ops_diagnostics_payload(
    runtime: Any,
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    generated_at_ms = int(now_ms if now_ms is not None else _now_ms())
    snapshot = runtime.current_snapshot()
    database = _section("database", lambda: _database_payload(runtime, snapshot))
    collector = _section("collector", lambda: _collector_payload(snapshot))
    providers = _providers_payload(runtime, snapshot)
    workers = _workers_payload(snapshot.workers)
    queues = _queues_payload(runtime, now_ms=generated_at_ms)
    agent_execution = _agent_execution_payload(snapshot.agent_execution, now_ms=generated_at_ms)
    domains = _domains_payload(runtime)
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
    normalized_queue_name = str(queue_name or "").strip()
    if normalized_queue_name != NOTIFICATION_QUEUE_NAME:
        return INVALID_QUEUE
    normalized_status = str(status or "").strip() or None
    if normalized_status is not None and normalized_status not in QUEUE_ALLOWED_STATUSES:
        return INVALID_STATUS
    generated_at_ms = int(now_ms if now_ms is not None else _now_ms())
    with runtime.db.api_pool.connection() as conn:
        summary = _queue_summary(conn, now_ms=generated_at_ms)
        items = _queue_items(
            conn,
            limit=max(0, min(int(limit), 200)),
            status=normalized_status,
        )
    return redact_diagnostics(
        {
            "schema_version": OPS_QUEUE_SCHEMA_VERSION,
            "queue_name": NOTIFICATION_QUEUE_NAME,
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
        status = payload.get("status")
        if not isinstance(status, str) or status not in DIAGNOSTIC_STATUSES:
            raise ValueError(f"diagnostic_section_status_invalid:{name}")
    except Exception as exc:
        return {
            "status": "unknown",
            "section": name,
            "error_type": type(exc).__name__,
            "reason": _preview_error(exc),
        }
    return payload


def _database_payload(runtime: Any, snapshot: RuntimeSnapshot) -> dict[str, Any]:
    with runtime.db.api_pool.connection() as conn:
        liveness = postgres_liveness_check(conn)
    startup_schema = dict(snapshot.startup_db_status)
    ok = bool(liveness.get("ok")) and bool(startup_schema.get("ok"))
    return {**liveness, "ok": ok, "status": "ok" if ok else "blocked", "schema": startup_schema}


def _collector_payload(snapshot: RuntimeSnapshot) -> dict[str, Any]:
    details = dict(snapshot.collector)
    connection = dict(snapshot.provider_states["gmgn_direct_ws"])
    state = _required_connection_state(connection)
    status = "ok" if state in HEALTHY_CONNECTION_STATES or state == "disabled" else "degraded"
    return {
        "status": status,
        "connection": connection,
        "details": details,
    }


def _providers_payload(runtime: Any, snapshot: RuntimeSnapshot) -> list[dict[str, Any]]:
    providers = []
    providers.extend(_asset_market_provider_health(runtime))
    providers.extend(_connection_providers(snapshot))
    return sorted(providers, key=lambda item: (str(item.get("domain")), str(item.get("provider"))))


def _asset_market_provider_health(runtime: Any) -> list[dict[str, Any]]:
    health_items = runtime.providers.asset_market.provider_health
    providers: list[dict[str, Any]] = []
    for item in health_items:
        payload = _provider_health_payload(item)
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


def _connection_providers(snapshot: RuntimeSnapshot) -> list[dict[str, Any]]:
    return [
        _connection_provider_payload(
            provider_name="gmgn_direct_ws",
            domain="ingestion",
            connection=snapshot.provider_states["gmgn_direct_ws"],
        ),
        _connection_provider_payload(
            provider_name="okx_dex_ws",
            domain="asset_market",
            connection=snapshot.provider_states["okx_dex_ws"],
        ),
    ]


def _connection_provider_payload(
    *,
    provider_name: str,
    domain: str,
    connection: Mapping[str, Any],
) -> dict[str, Any]:
    state = _required_connection_state(connection)
    configured = state != "disabled"
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


def _provider_status(*, configured: bool, state: str | None = None, error: Any = None) -> str:
    if not configured:
        return "disabled"
    if state is None:
        return "degraded" if error else "ok"
    if state in BLOCKED_CONNECTION_STATES:
        return "blocked"
    if state == "degraded_recoverable":
        return "degraded"
    if error or state not in HEALTHY_CONNECTION_STATES:
        return "degraded"
    return "ok"


def _provider_reason(*, configured: bool, state: str | None = None, error: Any = None) -> str:
    if not configured:
        return "not_configured"
    if state is None:
        return "provider_error_visible" if error else "ready"
    if state in BLOCKED_CONNECTION_STATES:
        return f"connection_{state}"
    if state == "degraded_recoverable":
        return "connection_degraded_recoverable"
    if error or state not in HEALTHY_CONNECTION_STATES:
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
    if name.startswith("news"):
        return "news"
    if name.startswith(("watchlist", "handle")):
        return "watchlist"
    if name.startswith("notification"):
        return "notifications"
    return "runtime"


def _queues_payload(runtime: Any, *, now_ms: int) -> list[dict[str, Any]]:
    with runtime.db.api_pool.connection() as conn:
        return [_queue_summary(conn, now_ms=now_ms)]


def _queue_summary(conn: Any, *, now_ms: int) -> dict[str, Any]:
    health = fetch_queue_table_health(
        conn,
        NOTIFICATION_QUEUE_TABLE,
        now_ms=now_ms,
        worker_name=NOTIFICATION_QUEUE_WORKER,
    )
    if not health.get("available"):
        raise RuntimeError(str(health.get("error_code") or "notification_queue_health_unavailable"))
    counts = dict(health["counts_by_status"])
    dead_count = int(counts.get("dead", 0))
    return {
        "queue_name": NOTIFICATION_QUEUE_NAME,
        "table": NOTIFICATION_QUEUE_TABLE,
        "worker_name": NOTIFICATION_QUEUE_WORKER,
        "counts_by_status": counts,
        "due_count": int(health["due_count"]),
        "running_count": int(health["running_count"]),
        "dead_count": dead_count,
        "failed_count": int(health["failed_count"]),
        "oldest_due_age_ms": health["oldest_due_age_ms"],
        "oldest_running_age_ms": health["oldest_running_age_ms"],
        "status": str(health["status"]),
        "reason": str(health["reason"]),
    }


def _queue_items(
    conn: Any,
    *,
    limit: int,
    status: str | None,
) -> list[dict[str, Any]]:
    where = "WHERE status = %s" if status else ""
    params: tuple[Any, ...] = (status, limit) if status else (limit,)
    rows = conn.execute(
        f"""
        SELECT *
        FROM {NOTIFICATION_QUEUE_TABLE}
        {where}
        ORDER BY updated_at_ms DESC
        LIMIT %s
        """,
        params,
    ).fetchall()
    return [_sanitized_job_row(dict(row)) for row in rows]


def _sanitized_job_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("delivery_id"),
        "status": row.get("status"),
        "attempt_count": row.get("attempt_count"),
        "max_attempts": row.get("max_attempts"),
        "created_at_ms": row.get("created_at_ms"),
        "updated_at_ms": row.get("updated_at_ms"),
        "next_run_at_ms": row.get("next_run_at_ms"),
        "last_attempt_at_ms": row.get("last_attempt_at_ms"),
        "delivered_at_ms": row.get("delivered_at_ms"),
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


def _domains_payload(runtime: Any) -> dict[str, Any]:
    return {
        "token_radar": _section("token_radar", lambda: _token_radar_domain(runtime)),
        "asset_market": _section("asset_market", lambda: _asset_market_domain(runtime)),
        "news": _section("news", lambda: _news_domain(runtime)),
        "watchlist": _section("watchlist", lambda: _watchlist_domain(runtime)),
        "notifications": _section("notifications", lambda: _notifications_domain(runtime)),
    }


def _token_radar_domain(runtime: Any) -> dict[str, Any]:
    with runtime.repositories() as repos:
        publication = token_radar_publication_status(
            repos.conn,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
        )
    status = {
        "ready": "ok",
        "missing": "idle",
        "degraded": "degraded",
        "failed": "blocked",
    }[str(publication["status"])]
    return {"status": status, "publication": publication}


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


def _news_domain(runtime: Any) -> dict[str, Any]:
    with runtime.repositories() as repos:
        sources = repos.news_sources.list_source_status()
    failing = [source for source in sources if str(source.get("status") or "").lower() not in {"ok", "ready", "active"}]
    status = "degraded" if failing else ("ok" if sources else "idle")
    return {"status": status, "sources": sources, "source_count": len(sources)}


def _watchlist_domain(runtime: Any) -> dict[str, Any]:
    configured_handles = tuple(runtime.settings.handles or ())
    return {"status": "ok" if configured_handles else "idle", "configured_handle_count": len(configured_handles)}


def _notifications_domain(runtime: Any) -> dict[str, Any]:
    with runtime.repositories() as repos:
        summary = repos.notifications.summary(subscriber_key="local")
    status = "ok" if runtime.settings.notifications.enabled else "disabled"
    return {"status": status, "summary": summary}


def _agent_execution_payload(raw_snapshot: Mapping[str, Any] | None, *, now_ms: int) -> dict[str, Any]:
    if raw_snapshot is None:
        return {"status": "disabled", "policy": None, "counters": None}
    if not isinstance(raw_snapshot, Mapping):
        return {
            "status": "unavailable",
            "status_reason": "unavailable",
            "error": "agent_execution_status_payload_not_mapping",
            "policy": None,
            "counters": None,
        }
    if raw_snapshot.get("status") == "unavailable":
        return {
            "status": "unavailable",
            "status_reason": "unavailable",
            "error": raw_snapshot.get("error"),
            "policy": None,
            "counters": None,
        }
    actual_fields = frozenset(raw_snapshot)
    if actual_fields != AGENT_EXECUTION_FIELDS:
        return _invalid_agent_execution_payload(
            "agent_execution_status_fields_mismatch:"
            f"missing={sorted(AGENT_EXECUTION_FIELDS - actual_fields)}:"
            f"unknown={sorted(actual_fields - AGENT_EXECUTION_FIELDS)}"
        )

    policy = _agent_policy_fields(raw_snapshot)
    counters = _agent_counter_fields(raw_snapshot)
    return {
        "status": _agent_execution_status(policy=policy, counters=counters, now_ms=now_ms),
        "policy": policy,
        "counters": counters,
    }


def _agent_policy_fields(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: snapshot[key] for key in AGENT_EXECUTION_POLICY_KEYS}


def _agent_counter_fields(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {key: snapshot[key] for key in AGENT_EXECUTION_COUNTER_KEYS}


def _agent_execution_status(
    *,
    policy: Mapping[str, Any],
    counters: Mapping[str, Any],
    now_ms: int,
) -> str:
    if str(counters.get("circuit_state") or "").lower() == "open":
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
    recent_fields = ("last_denied_at_ms", "last_timeout_at_ms")
    if any(_is_recent_ms(counters.get(field), now_ms=now_ms) for field in recent_fields):
        return "degraded"
    return "ok"


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
    settings = runtime.settings
    app_home = settings.app_home.expanduser()
    return {
        "app_home": str(app_home),
        "config_path": str(config_path(app_home)),
        "workers_config_path": str(workers_config_path(app_home)),
        "handles_count": len(tuple(settings.handles or ())),
        "upstream_channels": list(settings.upstream.channels),
        "gmgn_configured": bool(settings.gmgn_configured),
        "okx_dex_configured": bool(settings.okx_dex_configured),
        "llm_configured": bool(settings.llm_configured),
        "news_enabled": bool(settings.news_intel.enabled),
        "notifications_enabled": bool(settings.notifications.enabled),
    }


def _required_connection_state(connection: Mapping[str, Any]) -> str:
    state = connection.get("state")
    if not isinstance(state, str) or state not in (
        HEALTHY_CONNECTION_STATES | BLOCKED_CONNECTION_STATES | {"degraded_recoverable", "disabled"}
    ):
        raise ValueError("provider_connection_state_invalid")
    return state


def _invalid_agent_execution_payload(error: str) -> dict[str, Any]:
    return {
        "status": "unknown",
        "status_reason": "invalid_contract",
        "error": error,
        "policy": None,
        "counters": None,
    }


def _suggested_checks(*, queues: list[dict[str, Any]], domains: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if any(queue.get("status") == "blocked" for queue in queues):
        checks.append(
            {
                "id": "inspect_worker_status",
                "label": "inspect worker queues",
                "reason": "blocked queue detected",
                "cli_equivalent": "GET /api/ops/diagnostics",
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


def _provider_health_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, ProviderHealth):
        return asdict(value)
    if isinstance(value, Mapping):
        payload = dict(value)
        missing = sorted({"provider", "capabilities", "configured"} - set(payload))
        if missing:
            raise TypeError(f"asset_market_provider_health_item_missing_fields: {missing}")
        return payload
    raise TypeError(f"asset_market_provider_health_item_contract_required: {type(value).__name__}")


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
