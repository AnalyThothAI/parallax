from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime, _worker_running
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _limit, _scope, _signal_pulse_public_status, _window
from gmgn_twitter_intel.domains.pulse_lab.read_models.signal_pulse_service import SignalPulseService

router = APIRouter()


@router.get(
    "/signal-lab/pulse",
    response_model=api_schemas.ApiEnvelope[api_schemas.SignalPulseData],
)
def signal_lab_pulse(
    request: Request,
    window: Annotated[str, Query()] = "5m",
    scope: Annotated[str, Query()] = "all",
    status: Annotated[str, Query()] = "",
    handle: Annotated[str, Query()] = "",
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query()] = 80,
    cursor: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_window = _window(window)
    parsed_scope = _scope(scope)
    parsed_limit = _limit(limit, maximum=500)
    parsed_status = _signal_pulse_public_status(status)
    data = _signal_lab_pulse_data(
        runtime,
        window=parsed_window,
        scope=parsed_scope,
        status=parsed_status,
        handle=handle or None,
        q=q or None,
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
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
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
            limit=limit,
            cursor=cursor,
            agent_worker_running=agent_worker_running,
        )
