from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms, _runtime
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.domains.narrative_intel.queries import NarrativeBacklogHealthQuery

router = APIRouter()


@router.get("/bootstrap", response_model=api_schemas.ApiEnvelope[api_schemas.BootstrapData])
def bootstrap(request: Request) -> JSONResponse:
    runtime = _runtime(request)
    return _json(
        {
            "ok": True,
            "data": {
                "ws_token": runtime.settings.ws_token,
                "handles": list(runtime.settings.handles),
                "replay_limit": runtime.settings.replay_limit,
            },
        }
    )


@router.get(
    "/status/narrative-health",
    response_model=api_schemas.ApiEnvelope[api_schemas.NarrativeBacklogHealthData],
)
def narrative_health(
    request: Request,
    since_hours: Annotated[int, Query(ge=1, le=168)] = 4,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        health = NarrativeBacklogHealthQuery(repos.conn).health(
            now_ms=_now_ms(),
            since_hours=since_hours,
        )
    return _json({"ok": True, "data": health})


def create_router(readiness_payload: Callable[[Any], tuple[dict[str, Any], int]]) -> APIRouter:
    status_router = APIRouter()
    status_router.include_router(router)

    @status_router.get("/status", response_model=api_schemas.ApiEnvelope[api_schemas.StatusData])
    def status(request: Request) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        payload, _status_code = readiness_payload(runtime)
        return _json({"ok": True, "data": payload})

    return status_router
