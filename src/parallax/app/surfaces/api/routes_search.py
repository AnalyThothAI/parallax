from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms
from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import _limit, _positive_limit, _post_range, _scope, _target_type, _window
from parallax.domains.asset_market.read_models.market_candles_service import MarketCandlesService
from parallax.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from parallax.domains.narrative_intel.read_models.narrative_read_model import NarrativeReadModel
from parallax.domains.token_intel.queries.search_events_query import SearchEventsQuery
from parallax.domains.token_intel.read_models.search_inspect_service import SearchInspectService
from parallax.domains.token_intel.read_models.search_service import SearchCursorError, SearchService
from parallax.domains.token_intel.read_models.token_case_service import (
    TokenCaseInvalidScope,
    TokenCaseService,
    TokenCaseTargetNotFound,
    normalize_token_case_scope,
)
from parallax.domains.token_intel.read_models.token_target_cursor import TokenTargetCursorError
from parallax.domains.token_intel.read_models.token_target_posts_service import (
    TokenTargetPostsCursorError,
    TokenTargetPostsRangeError,
    TokenTargetPostsService,
    TokenTargetPostsSortError,
)
from parallax.domains.token_intel.read_models.token_target_social_timeline_service import (
    TokenTargetSocialTimelineService,
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
        return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
    return _json(
        {
            "ok": results.ok,
            "data": {
                "query": results.query,
                "page": results.page,
                "target_candidates": results.target_candidates,
                "items": results.items,
            },
            "error": results.error,
        }
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
            token_radar=repos.token_radar,
            targets=repos.token_targets,
            profiles=profiles,
            market_candles=_market_candles_service(),
            cex_detail_snapshots=repos.cex_detail_snapshots,
        ).inspect(
            q,
            window=parsed_window,
            scope=parsed_scope,
            limit=_limit(limit, maximum=200),
            now_ms=_now_ms(),
        )
        if isinstance(data.get("token_result"), dict):
            data["token_result"].pop("agent_brief", None)
            data["token_result"] = _narrative_read_model(repos).hydrate_token_case(
                data["token_result"],
                window=parsed_window,
                scope=parsed_scope,
                now_ms=_now_ms(),
            )
    return _json({"ok": True, "data": data})


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
                market_candles=_market_candles_service(),
                cex_detail_snapshots=repos.cex_detail_snapshots,
            ).dossier(
                target_type=parsed_target_type,
                target_id=target_id,
                window=parsed_window,
                scope=scope,
                posts_limit=_positive_limit(posts_limit, maximum=50, field="posts_limit"),
                now_ms=_now_ms(),
            )
            data.pop("agent_brief", None)
            _, response_scope = normalize_token_case_scope(scope)
            data = _narrative_read_model(repos).hydrate_token_case(
                data,
                window=parsed_window,
                scope=response_scope,
                now_ms=_now_ms(),
            )
    except TokenCaseTargetNotFound:
        return _json({"ok": False, "error": "target_not_found"}, status_code=404)
    return _json({"ok": True, "data": data})


@router.get("/target-posts", response_model=api_schemas.ApiEnvelope[api_schemas.TargetPostsData])
def target_posts(
    request: Request,
    target_type: Annotated[str, Query()] = "",
    target_id: Annotated[str, Query()] = "",
    window: Annotated[str, Query()] = "5m",
    post_range: Annotated[str, Query(alias="range")] = "current_window",
    sort: Annotated[str, Query()] = "recent",
    limit: Annotated[int, Query()] = 50,
    scope: Annotated[str, Query()] = "all",
    cursor: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
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
                sort=sort,
                limit=_limit(limit, maximum=200),
                cursor=cursor or None,
            )
            data = _narrative_read_model(repos).hydrate_target_posts(
                data,
                window=parsed_window,
                scope=parsed_scope,
                now_ms=_now_ms(),
            )
    except TokenTargetPostsRangeError:
        return _json({"ok": False, "error": "invalid_range", "field": "range"}, status_code=400)
    except TokenTargetPostsSortError:
        return _json({"ok": False, "error": "invalid_sort", "field": "sort"}, status_code=400)
    except TokenTargetPostsCursorError:
        return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
    return _json({"ok": True, "data": data})


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
        return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
    return _json({"ok": True, "data": data})


def _market_candles_service() -> MarketCandlesService:
    return MarketCandlesService()


def _narrative_read_model(repos: Any) -> Any:
    return NarrativeReadModel(repository=repos.narratives)
