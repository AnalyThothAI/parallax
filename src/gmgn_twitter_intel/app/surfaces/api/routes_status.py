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
    worker_settings = getattr(getattr(runtime, "settings", None), "workers", None)
    with runtime.repositories() as repos:
        health = NarrativeBacklogHealthQuery(
            repos.conn,
            **_narrative_health_worker_kwargs(worker_settings),
        ).health(
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
        payload, status_code = readiness_payload(runtime)
        return _json({"ok": payload.get("ok", status_code < 500), "data": payload}, status_code=status_code)

    return status_router


def _narrative_health_worker_kwargs(workers: object) -> dict[str, Any]:
    mention = getattr(workers, "mention_semantics", None)
    digest = getattr(workers, "token_discussion_digest", None)
    return {
        "realtime_windows": tuple(getattr(digest, "windows", ("1h",)) or ("1h",)),
        "semantics_rows_per_cycle": min(
            _positive_int(getattr(mention, "batch_size", 10), default=10),
            _positive_int(getattr(mention, "provider_batch_size", 10), default=10),
        ),
        "semantics_interval_seconds": _nonnegative_int(getattr(mention, "interval_seconds", 60), default=60),
        "digest_calls_per_cycle": max(
            1,
            _nonnegative_int(getattr(digest, "max_llm_calls_per_cycle", 3), default=3),
        ),
        "digest_interval_seconds": _nonnegative_int(getattr(digest, "interval_seconds", 120), default=120),
    }


def _positive_int(value: object, *, default: int) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default


def _nonnegative_int(value: object, *, default: int) -> int:
    try:
        return max(0, int(value if value is not None else default))
    except (TypeError, ValueError):
        return default
