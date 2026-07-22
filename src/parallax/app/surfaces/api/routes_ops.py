from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.operations.diagnostics import (
    INVALID_QUEUE,
    INVALID_STATUS,
    ops_diagnostics_payload,
    ops_queue_payload,
)
from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms
from parallax.app.surfaces.api.responses import _validated_json
from parallax.app.surfaces.api.validators import _limit

router = APIRouter()


@router.get(
    "/ops/diagnostics",
    response_model=api_schemas.ApiEnvelope[api_schemas.OpsDiagnosticsData],
)
def ops_diagnostics(
    request: Request,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    data = ops_diagnostics_payload(
        runtime,
        now_ms=_now_ms(),
    )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.OpsDiagnosticsData],
        {"ok": True, "data": data},
    )


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
        return _validated_json(
            api_schemas.ApiEnvelope[api_schemas.OpsQueueData],
            {"ok": False, "error": "invalid_queue"},
            status_code=400,
        )
    if data == INVALID_STATUS:
        return _validated_json(
            api_schemas.ApiEnvelope[api_schemas.OpsQueueData],
            {"ok": False, "error": "invalid_status", "field": "status"},
            status_code=400,
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.OpsQueueData],
        {"ok": True, "data": data},
    )
