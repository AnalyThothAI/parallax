from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime
from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import _limit
from parallax.domains.news_intel.queries.news_page_query import NewsPageQuery
from parallax.platform.config.news_provider_types import RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES

router = APIRouter()

_NEWS_SIGNALS = frozenset({"bullish", "bearish", "neutral"})


@router.get("/news", response_model=api_schemas.ApiEnvelope[api_schemas.NewsData])
def list_news(
    request: Request,
    limit: Annotated[int, Query()] = 100,
    cursor: Annotated[str, Query()] = "",
    status: Annotated[str, Query()] = "",
    signal: Annotated[str, Query()] = "",
    q: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = _news_read_model(repos).list_news(
            limit=_limit(limit, maximum=200),
            cursor=cursor or None,
            status=status or None,
            signal=_signal(signal),
            q=q.strip() or None,
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


@router.get(
    "/news/facts/{fact_candidate_id}",
    response_model=api_schemas.ApiEnvelope[api_schemas.NewsFactDetailData],
)
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
        data = {
            "provider_capabilities": _provider_capabilities(
                sources,
                supported_types=RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES,
            ),
            "source_hygiene": _source_hygiene(
                sources,
                supported_types=RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES,
            ),
            "sources": sources,
        }
    return _json({"ok": True, "data": data})


def _news_read_model(repos: Any) -> NewsPageQuery:
    return NewsPageQuery(repository=repos.news)


def _signal(value: str) -> str | None:
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized in _NEWS_SIGNALS:
        return normalized
    raise ApiBadRequest("invalid_news_signal")


def _provider_capabilities(sources: list[dict[str, Any]], *, supported_types: tuple[str, ...]) -> dict[str, Any]:
    supported = set(supported_types)
    configured = sorted({_required_source_text(source, "provider_type") for source in sources})
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
        source_id = _required_source_text(source, "source_id")
        provider_type = _required_source_text(source, "provider_type")
        if provider_type not in supported:
            unsupported_sources.append({"source_id": source_id, "provider_type": provider_type})
            warnings.append({"source_id": source_id, "reason": "unsupported_provider_type"})
        coverage_tags = _required_source_text_list(source, "coverage_tags")
        if bool(source.get("enabled")) and not coverage_tags:
            sources_missing_coverage_tags.append(source_id)
            warnings.append({"source_id": source_id, "reason": "missing_coverage_tags"})
        health = _required_source_mapping(source, "provider_health")
        health_status = _required_source_text(health, "status", label="provider_health_status")
        if health_status in {"degraded", "poor", "failing"}:
            degraded_sources.append({"source_id": source_id, "status": health_status})
            warnings.append({"source_id": source_id, "reason": f"provider_health_{health_status}"})
    return {
        "sources_missing_coverage_tags": sources_missing_coverage_tags,
        "unsupported_sources": unsupported_sources,
        "degraded_sources": degraded_sources,
        "warnings": warnings,
    }


def _required_source_mapping(source: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = source.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"news_source_status_{field_name}_required")
    return value


def _required_source_text(source: dict[str, Any], field_name: str, *, label: str | None = None) -> str:
    value = source.get(field_name)
    if not isinstance(value, str) or not value.strip():
        error_label = label or field_name
        raise ValueError(f"news_source_status_{error_label}_required")
    return value.strip()


def _required_source_text_list(source: dict[str, Any], field_name: str) -> list[str]:
    value = source.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"news_source_status_{field_name}_required")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"news_source_status_{field_name}_required")
        text = item.strip()
        if text:
            result.append(text)
    return result
