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
    has_token: Annotated[bool | None, Query()] = None,
    signal: Annotated[str, Query()] = "",
    min_score: Annotated[int | None, Query()] = None,
    q: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = _news_read_model(repos).list_news(
            limit=_limit(limit, maximum=200),
            cursor=cursor or None,
            status=status or None,
            has_token=has_token,
            signal=_signal(signal),
            min_score=min_score,
            q=q or None,
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
        sources = _news_read_model(repos).source_status()
        supported_types = _supported_news_provider_types(runtime)
        data = {
            "provider_capabilities": _provider_capabilities(sources, supported_types=supported_types),
            "source_hygiene": _source_hygiene(sources, supported_types=supported_types),
            "sources": sources,
        }
    return _json({"ok": True, "data": data})


def _news_read_model(repos: Any) -> NewsPageQuery:
    return NewsPageQuery(repository=repos.news)


def _signal(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized == "long":
        return "bullish"
    if normalized == "short":
        return "bearish"
    return normalized


def _provider_capabilities(sources: list[dict[str, Any]], *, supported_types: tuple[str, ...]) -> dict[str, Any]:
    supported = set(supported_types)
    configured = sorted({str(source.get("provider_type") or "") for source in sources if source.get("provider_type")})
    unsupported = [provider_type for provider_type in configured if provider_type not in supported]
    return {
        "supported_provider_types": list(supported_types),
        "configured_provider_types": configured,
        "unsupported_configured_provider_types": unsupported,
    }


def _source_hygiene(sources: list[dict[str, Any]], *, supported_types: tuple[str, ...]) -> dict[str, Any]:
    supported = set(supported_types)
    sources_missing_coverage_tags: list[str] = []
    unsupported_sources: list[dict[str, str]] = []
    degraded_sources: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for source in sources:
        source_id = str(source.get("source_id") or "")
        if not source_id:
            continue
        provider_type = str(source.get("provider_type") or "")
        if provider_type and provider_type not in supported:
            unsupported_sources.append({"source_id": source_id, "provider_type": provider_type})
            warnings.append({"source_id": source_id, "reason": "unsupported_provider_type"})
        if bool(source.get("enabled")) and not source.get("coverage_tags"):
            sources_missing_coverage_tags.append(source_id)
            warnings.append({"source_id": source_id, "reason": "missing_coverage_tags"})
        health = source.get("provider_health") if isinstance(source.get("provider_health"), dict) else {}
        health_status = str(health.get("status") or source.get("source_quality_status") or "")
        if health_status in {"degraded", "poor", "failing"}:
            degraded_sources.append({"source_id": source_id, "status": health_status})
            warnings.append({"source_id": source_id, "reason": f"provider_health_{health_status}"})
    return {
        "sources_missing_coverage_tags": sources_missing_coverage_tags,
        "unsupported_sources": unsupported_sources,
        "degraded_sources": degraded_sources,
        "warnings": warnings,
    }


def _supported_news_provider_types(runtime: Any) -> tuple[str, ...]:
    news_intel = getattr(getattr(runtime, "providers", None), "news_intel", None)
    feed_client = getattr(news_intel, "feed_client", None)
    supported = getattr(feed_client, "supported_provider_types", None)
    if callable(supported):
        return tuple(str(value) for value in supported())
    registry = getattr(feed_client, "_registry", None)
    registry_supported = getattr(registry, "supported_provider_types", None)
    if callable(registry_supported):
        return tuple(str(value) for value in registry_supported())
    return ()
