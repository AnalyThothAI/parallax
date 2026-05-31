from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _worker_running
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import (
    _limit,
    _scope,
    _signal_pulse_public_status,
    _signal_pulse_visibility,
    _signal_pulse_window,
)
from parallax.domains.pulse_lab.read_models.signal_pulse_service import SignalPulseService
from parallax.domains.pulse_lab.services.pulse_horizon_policy import SIGNAL_PULSE_DEFAULT_WINDOW

router = APIRouter()


@router.get(
    "/signal-lab/pulse",
    response_model=api_schemas.ApiEnvelope[api_schemas.SignalPulseData],
)
def signal_lab_pulse(
    request: Request,
    window: Annotated[str, Query()] = SIGNAL_PULSE_DEFAULT_WINDOW,
    scope: Annotated[str, Query()] = "all",
    status: Annotated[str, Query()] = "",
    handle: Annotated[str, Query()] = "",
    q: Annotated[str, Query()] = "",
    visibility: Annotated[str, Query()] = "public",
    limit: Annotated[int, Query()] = 80,
    cursor: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_window = _signal_pulse_window(window)
    parsed_scope = _scope(scope)
    parsed_limit = _limit(limit, maximum=500)
    parsed_status = _signal_pulse_public_status(status)
    parsed_visibility = _signal_pulse_visibility(visibility)
    data = _signal_lab_pulse_data(
        runtime,
        window=parsed_window,
        scope=parsed_scope,
        status=parsed_status,
        handle=handle or None,
        q=q or None,
        visibility=parsed_visibility,
        limit=parsed_limit,
        cursor=cursor or None,
        agent_worker_running=_worker_running(runtime, "pulse_candidate"),
    )
    return _json({"ok": True, "data": data})


@router.get(
    "/signal-lab/pulse/{candidate_id}",
    response_model=api_schemas.ApiEnvelope[api_schemas.SignalPulseItem],
)
def signal_lab_pulse_by_id(
    request: Request,
    candidate_id: str,
    visibility: Annotated[str, Query()] = "public",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_visibility = _signal_pulse_visibility(visibility)
    normalized = (candidate_id or "").strip()
    if not normalized:
        return JSONResponse(
            {"ok": False, "error": "invalid_candidate_id", "field": "candidate_id"},
            status_code=400,
        )
    with runtime.repositories() as repos:
        data = SignalPulseService(
            pulse_read=repos.pulse_read,
            pulse_runs=repos.pulse_runs,
        ).candidate(
            candidate_id=normalized,
            visibility=parsed_visibility,
        )
    if data is None:
        return JSONResponse(
            {"ok": False, "error": "not_found", "field": "candidate_id"},
            status_code=404,
        )
    return _json({"ok": True, "data": data})


def _signal_lab_pulse_data(
    runtime: Any,
    *,
    window: str,
    scope: str,
    status: str | None,
    handle: str | None,
    q: str | None,
    visibility: str,
    limit: int,
    cursor: str | None,
    agent_worker_running: bool,
) -> dict[str, Any]:
    with runtime.repositories() as repos:
        return SignalPulseService(
            pulse_read=repos.pulse_read,
            pulse_runs=repos.pulse_runs,
        ).pulse(
            window=window,
            scope=scope,
            status=status,
            handle=handle,
            q=q,
            visibility=visibility,
            limit=limit,
            cursor=cursor,
            agent_worker_running=agent_worker_running,
        )
