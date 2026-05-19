from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.runtime.ops_diagnostics import (
    INVALID_QUEUE,
    INVALID_STATUS,
    ops_diagnostics_payload,
    ops_queue_payload,
)
from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _limit, _scope, _window

router = APIRouter()


@router.get(
    "/ops/diagnostics",
    response_model=api_schemas.ApiEnvelope[api_schemas.OpsDiagnosticsData],
)
def ops_diagnostics(
    request: Request,
    since_hours: Annotated[int, Query(ge=1, le=168)] = 4,
    window: Annotated[str, Query()] = "1h",
    scope: Annotated[str, Query()] = "all",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    data = ops_diagnostics_payload(
        runtime,
        now_ms=_now_ms(),
        since_hours=since_hours,
        window=_window(window),
        scope=_scope(scope),
    )
    return _json({"ok": True, "data": data})


@router.get(
    "/ops/queues/{queue_name}",
    response_model=api_schemas.ApiEnvelope[api_schemas.OpsQueueData],
)
def ops_queue(
    request: Request,
    queue_name: str,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query()] = 50,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    data = ops_queue_payload(
        runtime,
        queue_name=queue_name,
        status=status,
        limit=_limit(limit, maximum=200),
        now_ms=_now_ms(),
    )
    if data == INVALID_QUEUE:
        return _json({"ok": False, "error": "invalid_queue"}, status_code=400)
    if data == INVALID_STATUS:
        return _json({"ok": False, "error": "invalid_status", "field": "status"}, status_code=400)
    return _json({"ok": True, "data": data})
