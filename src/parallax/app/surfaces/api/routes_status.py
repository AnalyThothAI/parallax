from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _runtime
from parallax.app.surfaces.api.responses import _json

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


def create_router(readiness_payload: Callable[[Any], tuple[dict[str, Any], int]]) -> APIRouter:
    status_router = APIRouter()
    status_router.include_router(router)

    @status_router.get("/status", response_model=api_schemas.ApiEnvelope[api_schemas.StatusData])
    def status(request: Request) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        payload, _status_code = readiness_payload(runtime)
        return _json({"ok": True, "data": payload})

    return status_router
