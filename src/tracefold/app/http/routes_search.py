from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from tracefold.app.http import schemas as api_schemas
from tracefold.app.http.dependencies import _authenticated_runtime, _now_ms
from tracefold.app.http.exceptions import ApiBadRequest
from tracefold.app.http.responses import _validated_json
from tracefold.app.http.validators import _limit, _positive_limit, _post_range, _scope, _target_type, _window
from tracefold.market import (
    MarketCandlesService,
    SearchCursorError,
    SearchEventsQuery,
    SearchInspectService,
    SearchService,
    TokenCaseInvalidScope,
    TokenCaseService,
    TokenCaseTargetNotFound,
    TokenProfileReadModel,
    TokenTargetCursorError,
    TokenTargetPostsCursorError,
    TokenTargetPostsRangeError,
    TokenTargetPostsService,
    TokenTargetSocialTimelineService,
    normalize_token_case_scope,
)

router = APIRouter()


@router.get("/search", response_model=api_schemas.ApiEnvelope[api_schemas.SearchData])
def search(
    request: Request,
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query()] = 20,
    scope: Annotated[str, Query()] = "all",
    cursor: Annotated[str, Query()] = "",
    window: Annotated[str, Query()] = "24h",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    for removed in ("symbol", "ca", "chain", "handle"):
        if removed in request.query_params:
            raise ApiBadRequest("unsupported_query_param", field=removed)
    parsed_window = _window(window)
    try:
        with runtime.repositories() as repos:
            results = SearchService(search_query=SearchEventsQuery(repos.conn)).search(
                q,
                limit=_limit(limit, maximum=200),
                scope=_scope(scope),
                cursor=cursor or None,
                window=parsed_window,
                now_ms=_now_ms(),
            )
    except SearchCursorError:
        return _validated_json(
            api_schemas.ApiEnvelope[api_schemas.SearchData],
            {"ok": False, "error": "invalid_cursor"},
            status_code=400,
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.SearchData],
        {
            "ok": results.ok,
            "data": {
                "query": results.query,
                "page": results.page,
                "target_candidates": results.target_candidates,
                "items": results.items,
            },
            "error": results.error,
        },
    )


@router.get(
    "/search/inspect",
    response_model=api_schemas.ApiEnvelope[api_schemas.SearchInspectData],
)
def search_inspect(
    request: Request,
    q: Annotated[str, Query()] = "",
    window: Annotated[str, Query()] = "24h",
    scope: Annotated[str, Query()] = "all",
    limit: Annotated[int, Query()] = 200,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_window = _window(window)
    parsed_scope = _scope(scope)
    with runtime.repositories() as repos:
        profiles = TokenProfileReadModel(token_profiles=repos.token_profiles)
        data = SearchInspectService(
            search_query=SearchEventsQuery(repos.conn),
            targets=repos.token_targets,
            profiles=profiles,
            token_radar=repos.token_radar,
            market_candles=_market_candles_service(),
        ).inspect(
            q,
            window=parsed_window,
            scope=parsed_scope,
            limit=_limit(limit, maximum=200),
            now_ms=_now_ms(),
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.SearchInspectData],
        {"ok": True, "data": data},
    )


@router.get("/token-case", response_model=api_schemas.ApiEnvelope[api_schemas.TokenCaseData])
def token_case(
    request: Request,
    target_type: Annotated[str, Query()] = "",
    target_id: Annotated[str, Query()] = "",
    window: Annotated[str, Query()] = "1h",
    scope: Annotated[str, Query()] = "all",
    posts_limit: Annotated[int, Query()] = 24,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_target_type = _target_type(target_type)
    if not parsed_target_type:
        raise ApiBadRequest("invalid_target", field="target_type")
    if not target_id:
        raise ApiBadRequest("invalid_target", field="target_id")
    parsed_window = _window(window)
    try:
        normalize_token_case_scope(scope)
    except TokenCaseInvalidScope as exc:
        raise ApiBadRequest("invalid_scope", field="scope") from exc
    try:
        with runtime.repositories() as repos:
            data = TokenCaseService(
                targets=repos.token_targets,
                profiles=TokenProfileReadModel(token_profiles=repos.token_profiles),
                token_radar=repos.token_radar,
                market_candles=_market_candles_service(),
            ).dossier(
                target_type=parsed_target_type,
                target_id=target_id,
                window=parsed_window,
                scope=scope,
                posts_limit=_positive_limit(posts_limit, maximum=50, field="posts_limit"),
                now_ms=_now_ms(),
            )
    except TokenCaseTargetNotFound:
        return _validated_json(
            api_schemas.ApiEnvelope[api_schemas.TokenCaseData],
            {"ok": False, "error": "target_not_found"},
            status_code=404,
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.TokenCaseData],
        {"ok": True, "data": data},
    )


@router.get("/target-posts", response_model=api_schemas.ApiEnvelope[api_schemas.TargetPostsData])
def target_posts(
    request: Request,
    target_type: Annotated[str, Query()] = "",
    target_id: Annotated[str, Query()] = "",
    window: Annotated[str, Query()] = "5m",
    post_range: Annotated[str, Query(alias="range")] = "current_window",
    limit: Annotated[int, Query()] = 50,
    scope: Annotated[str, Query()] = "all",
    cursor: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    if "sort" in request.query_params:
        raise ApiBadRequest("unsupported_query_param", field="sort")
    parsed_target_type = _target_type(target_type)
    if not parsed_target_type or not target_id:
        raise ApiBadRequest("target_required", field="target_id")
    parsed_window = _window(window)
    parsed_scope = _scope(scope)
    try:
        with runtime.repositories() as repos:
            data = TokenTargetPostsService(targets=repos.token_targets).target_posts(
                target_type=parsed_target_type,
                target_id=target_id,
                window=parsed_window,
                scope=parsed_scope,
                post_range=_post_range(post_range),
                limit=_limit(limit, maximum=200),
                cursor=cursor or None,
            )
    except TokenTargetPostsRangeError:
        return _validated_json(
            api_schemas.ApiEnvelope[api_schemas.TargetPostsData],
            {"ok": False, "error": "invalid_range", "field": "range"},
            status_code=400,
        )
    except TokenTargetPostsCursorError:
        return _validated_json(
            api_schemas.ApiEnvelope[api_schemas.TargetPostsData],
            {"ok": False, "error": "invalid_cursor"},
            status_code=400,
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.TargetPostsData],
        {"ok": True, "data": data},
    )


@router.get(
    "/target-social-timeline",
    response_model=api_schemas.ApiEnvelope[api_schemas.TargetSocialTimelineData],
)
def target_social_timeline(
    request: Request,
    target_type: Annotated[str, Query()] = "",
    target_id: Annotated[str, Query()] = "",
    window: Annotated[str, Query()] = "1h",
    scope: Annotated[str, Query()] = "all",
    limit: Annotated[int, Query()] = 200,
    cursor: Annotated[str, Query()] = "",
) -> JSONResponse:
    if "bucket" in request.query_params:
        raise ApiBadRequest("unsupported_query_param", field="bucket")
    parsed_target_type = _target_type(target_type)
    if not parsed_target_type or not target_id:
        raise ApiBadRequest("target_required", field="target_id")
    runtime = _authenticated_runtime(request)
    parsed_window = _window(window)
    parsed_scope = _scope(scope)
    try:
        with runtime.repositories() as repos:
            data = TokenTargetSocialTimelineService(
                targets=repos.token_targets,
                market_candles=_market_candles_service(),
            ).timeline(
                target_type=parsed_target_type,
                target_id=target_id,
                window=parsed_window,
                scope=parsed_scope,
                limit=_limit(limit),
                cursor=cursor or None,
            )
    except TokenTargetCursorError:
        return _validated_json(
            api_schemas.ApiEnvelope[api_schemas.TargetSocialTimelineData],
            {"ok": False, "error": "invalid_cursor"},
            status_code=400,
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.TargetSocialTimelineData],
        {"ok": True, "data": data},
    )


def _market_candles_service() -> MarketCandlesService:
    return MarketCandlesService()
