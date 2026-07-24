from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from tracefold.app.http import schemas as api_schemas
from tracefold.app.http.dependencies import _authenticated_runtime, _now_ms
from tracefold.app.http.exceptions import ApiBadRequest
from tracefold.app.http.responses import _json, _validated_json
from tracefold.market import (
    WatchlistReadConfig,
    WatchlistReadService,
    WatchlistTimelineCursorError,
    normalize_watchlist_handle,
)

router = APIRouter()


@router.get(
    "/watchlist/handles/overview",
    response_model=api_schemas.ApiEnvelope[api_schemas.WatchlistHandlesOverviewData],
)
def watchlist_handles_overview(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = WatchlistReadService(
            query=repos.watchlist,
            config=_watchlist_read_config(runtime),
        ).handles_overview(
            configured_handles=tuple(runtime.settings.handles),
            now_ms=_now_ms(),
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.WatchlistHandlesOverviewData],
        {"ok": True, "data": data},
    )


@router.get(
    "/watchlist/handle/{handle}/overview",
    response_model=api_schemas.ApiEnvelope[api_schemas.WatchlistHandleOverviewData],
)
def watchlist_handle_overview(
    request: Request,
    handle: str,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    try:
        normalized_handle = normalize_watchlist_handle(handle)
    except ValueError:
        raise ApiBadRequest("invalid_handle", field="handle") from None
    try:
        with runtime.repositories() as repos:
            data = WatchlistReadService(
                query=repos.watchlist,
                config=_watchlist_read_config(runtime),
            ).overview(
                handle=normalized_handle,
                configured_handles=tuple(runtime.settings.handles),
                now_ms=_now_ms(),
            )
    except LookupError:
        return _json({"ok": False, "error": "handle_not_found", "field": "handle"}, status_code=404)
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.WatchlistHandleOverviewData],
        {"ok": True, "data": data},
    )


@router.get(
    "/watchlist/handle/{handle}/timeline",
    response_model=api_schemas.ApiEnvelope[api_schemas.WatchlistHandleTimelineData],
)
def watchlist_handle_timeline(
    request: Request,
    handle: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    try:
        normalized_handle = normalize_watchlist_handle(handle)
    except ValueError:
        raise ApiBadRequest("invalid_handle", field="handle") from None
    try:
        with runtime.repositories() as repos:
            data = WatchlistReadService(
                query=repos.watchlist,
                config=_watchlist_read_config(runtime),
            ).timeline(
                handle=normalized_handle,
                configured_handles=tuple(runtime.settings.handles),
                cursor=cursor or None,
                limit=limit,
            )
    except LookupError:
        return _json({"ok": False, "error": "handle_not_found", "field": "handle"}, status_code=404)
    except WatchlistTimelineCursorError:
        return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.WatchlistHandleTimelineData],
        {"ok": True, "data": data},
    )


def _watchlist_read_config(_runtime: object) -> WatchlistReadConfig:
    return WatchlistReadConfig(
        window_days=3,
        overview_source_limit=500,
        overview_cluster_limit=500,
    )
