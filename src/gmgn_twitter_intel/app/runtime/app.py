from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger

from gmgn_twitter_intel.app.runtime.bootstrap import Runtime, bootstrap
from gmgn_twitter_intel.app.runtime.telemetry import PROMETHEUS_CONTENT_TYPE
from gmgn_twitter_intel.app.runtime.worker_status import workers_status_payload
from gmgn_twitter_intel.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from gmgn_twitter_intel.app.surfaces.api.http import create_api_router
from gmgn_twitter_intel.app.surfaces.api.schemas import StatusData
from gmgn_twitter_intel.platform.config.settings import Settings, load_settings
from gmgn_twitter_intel.platform.db.postgres_client import postgres_health_check
from gmgn_twitter_intel.platform.db.postgres_migrations import latest_migration_version


def create_app(
    settings: Settings | None = None,
    *,
    start_collector: bool = True,
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = bootstrap(resolved_settings, start_collector=start_collector)
        await runtime.scheduler.start()
        app.state.service = runtime
        logger.info(
            "Starting GMGN Twitter Intel | "
            f"handles={','.join(resolved_settings.handles) or 'all'} "
            f"channels={','.join(resolved_settings.upstream_channels)} "
            "storage=postgresql"
        )
        try:
            yield
        finally:
            await runtime.aclose()

    app = FastAPI(title="GMGN Twitter Intel", lifespan=lifespan)
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(_readiness_payload))

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        return "ok\n"

    @app.get("/readyz", response_model=StatusData)
    def readyz() -> JSONResponse:
        runtime = app.state.service
        payload, status_code = _readiness_payload(runtime)
        return JSONResponse(payload, status_code=status_code)

    @app.get("/metrics")
    def metrics() -> Response:
        runtime = app.state.service
        return Response(
            runtime.telemetry.render_prometheus_text(),
            media_type=PROMETHEUS_CONTENT_TYPE,
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await app.state.service.hub.handle(websocket)

    _mount_frontend(app, frontend_dist=frontend_dist)

    return app


def _mount_frontend(app: FastAPI, *, frontend_dist: str | Path | None) -> None:
    dist = _frontend_dist_dir(frontend_dist)
    if dist is None:
        return

    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    if (dist / "favicon.svg").exists():

        async def frontend_favicon() -> FileResponse:
            return FileResponse(dist / "favicon.svg")

        app.add_api_route("/favicon.svg", frontend_favicon, include_in_schema=False)

    async def frontend_index() -> FileResponse:
        return FileResponse(dist / "index.html")

    app.add_api_route("/", frontend_index, include_in_schema=False)
    app.add_api_route("/app", frontend_index, include_in_schema=False)
    app.add_api_route("/app/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/signal-lab", frontend_index, include_in_schema=False)
    app.add_api_route("/signal-lab/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/news", frontend_index, include_in_schema=False)
    app.add_api_route("/news/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/search", frontend_index, include_in_schema=False)
    app.add_api_route("/search/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/stocks", frontend_index, include_in_schema=False)
    app.add_api_route("/stocks/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/token", frontend_index, include_in_schema=False)
    app.add_api_route("/token/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/watchlist", frontend_index, include_in_schema=False)
    app.add_api_route("/watchlist/{path:path}", frontend_index, include_in_schema=False)


def _frontend_dist_dir(frontend_dist: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if frontend_dist is not None:
        candidates.append(Path(frontend_dist))
    module_path = Path(__file__).resolve()
    candidates.extend(
        [
            module_path.parents[2] / "web" / "dist",
            module_path.parents[4] / "web" / "dist",
        ]
    )
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


def _readiness_payload(runtime: Runtime, *, now_ms: int | None = None) -> tuple[dict[str, Any], int]:
    _ = now_ms if now_ms is not None else _now_ms()
    collector_status = runtime.collector.status.to_dict()
    db_status = _db_status(runtime)
    reasons = _unhealthy_reasons(runtime, db_status=db_status)
    stream_dex_market = _stream_dex_market(runtime)
    payload = {
        "ok": not reasons,
        "reasons": reasons,
        "snapshot_gate": collector_status.get("snapshot_gate_outcomes", {}),
        "handles": list(runtime.settings.handles),
        "store": "postgresql",
        "db": db_status,
        "provider_states": {
            "gmgn_direct_ws": _provider_state_payload(getattr(runtime.collector, "upstream_client", None)),
            "okx_dex_ws": _provider_state_payload(stream_dex_market),
        },
        "agent_execution": _agent_execution_status(runtime),
        "workers": workers_status_payload(runtime),
    }
    return payload, 503 if reasons else 200


def _workers_status_payload(runtime: Runtime) -> dict[str, dict[str, Any]]:
    return workers_status_payload(runtime)


def _stream_dex_market(runtime: Any) -> Any | None:
    providers = getattr(runtime, "providers", None)
    asset_market = getattr(providers, "asset_market", None)
    return getattr(asset_market, "stream_dex_market", None)


def _agent_execution_status(runtime: Any) -> dict[str, Any] | None:
    gateway = getattr(runtime, "agent_execution_gateway", None)
    if gateway is None:
        providers = getattr(runtime, "providers", None)
        gateway = getattr(providers, "agent_execution_gateway", None)
    snapshot = getattr(gateway, "status_snapshot", None)
    if not callable(snapshot):
        return None
    try:
        payload = snapshot()
    except Exception as exc:
        return {"status": "unavailable", "error": type(exc).__name__}
    return payload if isinstance(payload, dict) else {"status": "unavailable"}


def _unhealthy_reasons(runtime: Runtime, *, db_status: dict[str, object]) -> list[str]:
    reasons = list(runtime.scheduler.unhealthy_reasons())
    if not db_status.get("ok"):
        reasons.append("database_unhealthy")
    return reasons


def _db_status(runtime: Runtime) -> dict[str, object]:
    try:
        with runtime.db.api_pool.connection() as conn:
            return postgres_health_check(conn, expected_migration_version=latest_migration_version())
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}


def _provider_state_payload(provider: object | None) -> dict[str, object | None]:
    if provider is None:
        return {"state": "disconnected", "last_state_change_at_ms": None}
    payload = getattr(provider, "connection_state_payload", None)
    if payload is None:
        return {"state": "disconnected", "last_state_change_at_ms": None}
    try:
        value = payload()
    except Exception as exc:
        return {"state": "failed", "last_state_change_at_ms": None, "error": str(exc)}
    return value if isinstance(value, dict) else {"state": "failed", "last_state_change_at_ms": None}


def _enrichment_job_counts(runtime: Runtime) -> dict[str, int]:
    try:
        with runtime.repositories() as repos:
            return repos.enrichment.job_counts()
    except Exception:
        return {}


def _notification_summary(runtime: Runtime) -> dict[str, object]:
    try:
        with runtime.repositories() as repos:
            return repos.notifications.summary(subscriber_key="local")
    except Exception:
        return {}


def _now_ms() -> int:
    return int(time.time() * 1000)
