from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _limit
from gmgn_twitter_intel.domains.news_intel.queries.news_page_query import NewsPageQuery

router = APIRouter()


@router.get("/news", response_model=api_schemas.ApiEnvelope[api_schemas.NewsData])
def list_news(
    request: Request,
    limit: Annotated[int, Query()] = 100,
    cursor: Annotated[str, Query()] = "",
    status: Annotated[str, Query()] = "",
    direction: Annotated[str, Query()] = "",
    lane: Annotated[str, Query()] = "",
    source: Annotated[str, Query()] = "",
    target: Annotated[str, Query()] = "",
    provider_type: Annotated[str, Query()] = "",
    source_role: Annotated[str, Query()] = "",
    trust_tier: Annotated[str, Query()] = "",
    coverage_tag: Annotated[str, Query()] = "",
    content_class: Annotated[str, Query()] = "",
    content_tag: Annotated[str, Query()] = "",
    decision_class: Annotated[str, Query()] = "",
    q: Annotated[str, Query()] = "",
    include_unprojected: Annotated[bool, Query()] = False,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = _news_read_model(repos).list_news(
            limit=_limit(limit, maximum=200),
            cursor=cursor or None,
            status=status or None,
            direction=direction or None,
            lane=lane or None,
            source=source or None,
            target=target or None,
            provider_type=provider_type or None,
            source_role=source_role or None,
            trust_tier=trust_tier or None,
            coverage_tag=coverage_tag or None,
            content_class=content_class or None,
            content_tag=content_tag or None,
            decision_class=decision_class or None,
            q=q or None,
            include_unprojected=include_unprojected,
        )
    return _json({"ok": True, "data": data})


@router.get("/news/items/{news_item_id}", response_model=api_schemas.ApiEnvelope[api_schemas.NewsObjectData])
def get_news_item(request: Request, news_item_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        row = _news_read_model(repos).get_item(news_item_id=news_item_id)
    if row is None:
        return JSONResponse({"ok": False, "error": "news_item_not_found"}, status_code=404)
    return _json({"ok": True, "data": row})


@router.get("/news/stories/{story_id}", response_model=api_schemas.ApiEnvelope[api_schemas.NewsObjectData])
def get_news_story(request: Request, story_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        row = _news_read_model(repos).get_story(story_id=story_id)
    if row is None:
        return JSONResponse({"ok": False, "error": "news_story_not_found"}, status_code=404)
    return _json({"ok": True, "data": row})


@router.get("/news/facts/{fact_candidate_id}", response_model=api_schemas.ApiEnvelope[api_schemas.NewsObjectData])
def get_news_fact(request: Request, fact_candidate_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        row = _news_read_model(repos).get_fact(fact_candidate_id=fact_candidate_id)
    if row is None:
        return JSONResponse({"ok": False, "error": "news_fact_not_found"}, status_code=404)
    return _json({"ok": True, "data": row})


@router.get("/news/sources/status", response_model=api_schemas.ApiEnvelope[api_schemas.NewsSourceStatusData])
def get_news_source_status(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = {"sources": _news_read_model(repos).source_status()}
    return _json({"ok": True, "data": data})


def _news_read_model(repos: Any) -> NewsPageQuery:
    return NewsPageQuery(repository=repos.news)
