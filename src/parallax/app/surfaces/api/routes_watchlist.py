from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms
from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import _watchlist_timeline_scope
from parallax.domains.watchlist_intel.services.watchlist_read_service import (
    WatchlistHandleReadService,
    WatchlistReadWindowConfig,
)
from parallax.domains.watchlist_intel.types import WatchlistTimelineCursorError, normalize_watchlist_handle

router = APIRouter()


@router.get(
    "/watchlist/handles/overview",
    response_model=api_schemas.ApiEnvelope[api_schemas.WatchlistHandlesOverviewData],
)
def watchlist_handles_overview(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = WatchlistHandleReadService(
            repository=repos.watchlist_intel,
            config=_watchlist_read_config(runtime),
        ).handles_overview(
            configured_handles=tuple(runtime.settings.handles),
            now_ms=_now_ms(),
        )
    return _json({"ok": True, "data": data})


@router.get(
    "/watchlist/handle/{handle}/overview",
    response_model=api_schemas.ApiEnvelope[api_schemas.WatchlistHandleOverviewData],
)
def watchlist_handle_overview(
    request: Request,
    handle: str,
    scope: Annotated[str, Query()] = "signal",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    try:
        normalized_handle = normalize_watchlist_handle(handle)
    except ValueError:
        raise ApiBadRequest("invalid_handle", field="handle") from None
    parsed_scope = _watchlist_timeline_scope(scope)
    try:
        with runtime.repositories() as repos:
            data = WatchlistHandleReadService(
                repository=repos.watchlist_intel,
                config=_watchlist_read_config(runtime),
            ).overview(
                handle=normalized_handle,
                configured_handles=tuple(runtime.settings.handles),
                scope=parsed_scope,
                now_ms=_now_ms(),
            )
    except LookupError:
        return _json({"ok": False, "error": "handle_not_found", "field": "handle"}, status_code=404)
    return _json({"ok": True, "data": data})


@router.get(
    "/watchlist/handle/{handle}/timeline",
    response_model=api_schemas.ApiEnvelope[api_schemas.WatchlistHandleTimelineData],
)
def watchlist_handle_timeline(
    request: Request,
    handle: str,
    scope: Annotated[str, Query()] = "signal",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    try:
        normalized_handle = normalize_watchlist_handle(handle)
    except ValueError:
        raise ApiBadRequest("invalid_handle", field="handle") from None
    parsed_scope = _watchlist_timeline_scope(scope)
    try:
        with runtime.repositories() as repos:
            data = WatchlistHandleReadService(repository=repos.watchlist_intel).timeline(
                handle=normalized_handle,
                configured_handles=tuple(runtime.settings.handles),
                scope=parsed_scope,
                cursor=cursor or None,
                limit=limit,
            )
    except LookupError:
        return _json({"ok": False, "error": "handle_not_found", "field": "handle"}, status_code=404)
    except WatchlistTimelineCursorError:
        return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
    return _json({"ok": True, "data": data})


def _watchlist_read_config(_runtime: object) -> WatchlistReadWindowConfig:
    return WatchlistReadWindowConfig(
        window_days=3,
    )
