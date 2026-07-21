from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger

from parallax.app.runtime.bootstrap import Runtime, bootstrap
from parallax.app.runtime.telemetry import PROMETHEUS_CONTENT_TYPE
from parallax.app.runtime.worker_status import workers_status_payload
from parallax.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from parallax.app.surfaces.api.http import create_api_router
from parallax.app.surfaces.api.schemas import ReadinessData
from parallax.app.surfaces.api.ws import PublicWebSocketHub
from parallax.platform.config.settings import Settings, load_settings
from parallax.platform.db.postgres_client import postgres_liveness_check

FRONTEND_CACHE_CONTROL = "no-cache, max-age=0, must-revalidate"


class FrontendStaticFiles(StaticFiles):
    """Serve rebuilt Vite assets without letting the local browser pin stale chunks."""

    def file_response(self, full_path: Any, stat_result: Any, scope: Any, status_code: int = 200) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers.setdefault("Cache-Control", FRONTEND_CACHE_CONTROL)
        return response


def create_app(
    settings: Settings | None = None,
    *,
    start_collector: bool = True,
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = bootstrap(
            resolved_settings,
            start_collector=start_collector,
            publisher_factory=lambda db: PublicWebSocketHub(
                token=resolved_settings.ws_token,
                repository_session=db.api_session,
                default_replay_limit=resolved_settings.replay_limit,
            ),
        )
        await runtime.scheduler.start()
        app.state.service = runtime
        logger.info(
            "Starting Parallax | "
            f"handles={','.join(resolved_settings.handles) or 'all'} "
            f"channels={','.join(resolved_settings.upstream_channels)} "
            "storage=postgresql"
        )
        try:
            yield
        finally:
            await runtime.aclose()

    app = FastAPI(title="Parallax", lifespan=lifespan)
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(_status_payload))

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz() -> str:
        return "ok\n"

    @app.get("/readyz", response_model=ReadinessData)
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
        await cast(PublicWebSocketHub, app.state.service.hub).handle(websocket)

    _mount_frontend(app, frontend_dist=frontend_dist)

    return app


def _mount_frontend(app: FastAPI, *, frontend_dist: str | Path | None) -> None:
    dist = _frontend_dist_dir(frontend_dist)
    if dist is None:
        return

    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", FrontendStaticFiles(directory=assets), name="frontend-assets")

    if (dist / "favicon.svg").exists():

        async def frontend_favicon() -> FileResponse:
            return FileResponse(
                dist / "favicon.svg",
                headers={"Cache-Control": FRONTEND_CACHE_CONTROL},
            )

        app.add_api_route("/favicon.svg", frontend_favicon, include_in_schema=False)

    async def frontend_index() -> FileResponse:
        return FileResponse(
            dist / "index.html",
            headers={"Cache-Control": FRONTEND_CACHE_CONTROL},
        )

    app.add_api_route("/", frontend_index, include_in_schema=False)
    app.add_api_route("/app", frontend_index, include_in_schema=False)
    app.add_api_route("/app/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/news", frontend_index, include_in_schema=False)
    app.add_api_route("/news/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/macro", frontend_index, include_in_schema=False)
    app.add_api_route("/macro/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/ops", frontend_index, include_in_schema=False)
    app.add_api_route("/ops/{path:path}", frontend_index, include_in_schema=False)
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
    candidates.extend(parent / "web" / "dist" for parent in module_path.parents)
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


def _readiness_payload(runtime: Runtime) -> tuple[dict[str, Any], int]:
    db_status = _db_status(runtime)
    composition = _core_composition_status(runtime)
    reasons: list[str] = []
    if not db_status.get("ok"):
        reasons.append("database_unhealthy")
    if not composition.get("ok"):
        reasons.append("core_composition_incomplete")
    payload = {
        "ok": not reasons,
        "reasons": reasons,
        "handles": list(runtime.settings.handles),
        "store": "postgresql",
        "db": db_status,
        "composition": composition,
    }
    return payload, 503 if reasons else 200


def _status_payload(runtime: Runtime) -> tuple[dict[str, Any], int]:
    collector_status = runtime.collector.status.to_dict()
    db_status = _db_status(runtime)
    worker_status = workers_status_payload(runtime)
    news_provider_contract = _news_provider_contract_payload(runtime)
    reasons = _unhealthy_reasons(
        runtime,
        db_status=db_status,
        news_provider_contract=news_provider_contract,
    )
    stream_dex_market = _stream_dex_market(runtime)
    payload = {
        "ok": not reasons,
        "reasons": reasons,
        "snapshot_gate": collector_status.get("snapshot_gate_outcomes", {}),
        "handles": list(runtime.settings.handles),
        "store": "postgresql",
        "db": db_status,
        "provider_states": {
            "gmgn_direct_ws": _provider_state_payload(runtime.collector.upstream_client),
            "okx_dex_ws": _provider_state_payload(stream_dex_market),
        },
        "agent_execution": _agent_execution_status(runtime),
        "news_provider_contract": news_provider_contract,
        "workers": worker_status["workers"],
        "worker_lanes": worker_status["worker_lanes"],
    }
    return payload, 503 if reasons else 200


def _stream_dex_market(runtime: Runtime) -> Any | None:
    return runtime.providers.asset_market.stream_dex_market


def _agent_execution_status(runtime: Runtime) -> dict[str, Any] | None:
    gateway = runtime.agent_execution_gateway
    if gateway is None:
        return None
    try:
        payload = gateway.status_snapshot()
    except AttributeError:
        return {"status": "unavailable", "error": "agent_execution_status_contract_missing"}
    except Exception as exc:
        return {"status": "unavailable", "error": type(exc).__name__}
    if not isinstance(payload, dict):
        return {"status": "unavailable", "error": "agent_execution_status_payload_not_dict"}
    return payload


def _unhealthy_reasons(
    runtime: Runtime,
    *,
    db_status: dict[str, object],
    news_provider_contract: dict[str, Any],
) -> list[str]:
    reasons = [reason for reason in runtime.scheduler.unhealthy_reasons() if ":stopped" not in str(reason)]
    if not db_status.get("ok"):
        reasons.append("database_unhealthy")
    news_contract_reason = str(news_provider_contract.get("reason") or "")
    if news_provider_contract.get("ok") is False and (
        news_contract_reason.startswith("news_provider_type_")
        or news_contract_reason == "news_provider_settings_contract_required"
    ):
        reasons.append("news_provider_contract_error")
    return reasons


def _news_provider_contract_payload(runtime: Runtime) -> dict[str, Any]:
    return dict(runtime.news_provider_contract)


def _db_status(runtime: Runtime) -> dict[str, object]:
    try:
        with runtime.db.api_pool.connection() as conn:
            liveness = postgres_liveness_check(conn)
        startup_schema = dict(runtime.startup_db_status)
        schema_ok = bool(startup_schema.get("ok"))
        return {
            **liveness,
            "ok": bool(liveness.get("ok")) and schema_ok,
            "schema": startup_schema,
        }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}


def _core_composition_status(runtime: Runtime) -> dict[str, object]:
    try:
        repository_factory = runtime.repositories
        settings = runtime.settings
        api_pool = runtime.db.api_pool
    except AttributeError as exc:
        return {"ok": False, "error": "runtime_core_contract_missing", "detail": str(exc)}
    if not callable(repository_factory):
        return {"ok": False, "error": "runtime_repository_factory_required"}
    if settings is None or api_pool is None:
        return {"ok": False, "error": "runtime_core_contract_missing"}
    return {"ok": True}


def _provider_state_payload(provider: Any | None) -> dict[str, object | None]:
    if provider is None:
        return {"state": "disconnected", "last_state_change_at_ms": None}
    try:
        value = provider.connection_state_payload()
    except AttributeError:
        return {
            "state": "failed",
            "last_state_change_at_ms": None,
            "error": "provider_connection_state_contract_missing",
        }
    except Exception as exc:
        return {"state": "failed", "last_state_change_at_ms": None, "error": str(exc)}
    if not isinstance(value, dict):
        return {
            "state": "failed",
            "last_state_change_at_ms": None,
            "error": "provider_connection_state_payload_not_dict",
        }
    return value
