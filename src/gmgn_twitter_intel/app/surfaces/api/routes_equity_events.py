from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.exceptions import ApiBadRequest
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _limit
from gmgn_twitter_intel.domains.equity_event_intel.queries.equity_event_query import EquityEventQuery

router = APIRouter()


@router.get("/equity-events", response_model=api_schemas.ApiEnvelope[api_schemas.EquityEventsData])
def list_equity_events(
    request: Request,
    limit: Annotated[int, Query()] = 100,
    cursor: Annotated[str, Query()] = "",
    window: Annotated[str, Query()] = "",
    universe: Annotated[str, Query()] = "",
    ticker: Annotated[str, Query()] = "",
    event_type: Annotated[str, Query()] = "",
    priority: Annotated[str, Query()] = "",
    source_role: Annotated[str, Query()] = "",
    lifecycle_status: Annotated[str, Query()] = "",
    brief_status: Annotated[str, Query()] = "",
    q: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    validated_cursor = _public_cursor(cursor)
    with runtime.repositories() as repos:
        data = _equity_event_read_model(repos).list_events(
            limit=_limit(limit, maximum=200),
            cursor=validated_cursor,
            window=_public_window(window),
            universe=universe or None,
            ticker=ticker or None,
            event_type=event_type or None,
            priority=priority or None,
            source_role=source_role or None,
            lifecycle_status=lifecycle_status or None,
            brief_status=brief_status or None,
            q=q or None,
        )
    return _json({"ok": True, "data": data})


@router.get(
    "/equity-events/calendar",
    response_model=api_schemas.ApiEnvelope[api_schemas.EquityEventCalendarData],
)
def list_equity_event_calendar(
    request: Request,
    from_ms: Annotated[int | None, Query(alias="from")] = None,
    to_ms: Annotated[int | None, Query(alias="to")] = None,
    universe: Annotated[str, Query()] = "",
    ticker: Annotated[str, Query()] = "",
    status: Annotated[str, Query()] = "",
    session: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = _equity_event_read_model(repos).list_calendar(
            from_ms=from_ms,
            to_ms=to_ms,
            universe=universe or None,
            ticker=ticker or None,
            status=status or None,
            session=session or None,
        )
    return _json({"ok": True, "data": data})


@router.get(
    "/equity-events/sources/status",
    response_model=api_schemas.ApiEnvelope[api_schemas.EquityEventSourceStatusData],
)
def get_equity_event_source_status(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = {"sources": _equity_event_read_model(repos).source_status()}
    return _json({"ok": True, "data": data})


@router.get("/equity-events/summary", response_model=api_schemas.ApiEnvelope[api_schemas.EquityEventSummaryData])
def get_equity_event_summary(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = _equity_event_read_model(repos).summary()
    return _json({"ok": True, "data": data})


@router.get(
    "/equity-events/stories/{story_id}",
    response_model=api_schemas.ApiEnvelope[api_schemas.EquityEventObjectData],
)
def get_equity_event_story(request: Request, story_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        row = _equity_event_read_model(repos).get_story(story_id=story_id)
    if row is None:
        return JSONResponse({"ok": False, "error": "equity_event_story_not_found"}, status_code=404)
    return _json({"ok": True, "data": row})


@router.get(
    "/equity-events/companies/{ticker}/timeline",
    response_model=api_schemas.ApiEnvelope[api_schemas.EquityEventTimelineData],
)
def get_equity_event_company_timeline(
    request: Request,
    ticker: str,
    limit: Annotated[int, Query()] = 100,
    cursor: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    validated_cursor = _public_cursor(cursor)
    with runtime.repositories() as repos:
        data = _equity_event_read_model(repos).company_timeline(
            ticker=ticker,
            limit=_limit(limit, maximum=200),
            cursor=validated_cursor,
        )
    return _json({"ok": True, "data": data})


@router.get(
    "/equity-events/{event_id}",
    response_model=api_schemas.ApiEnvelope[api_schemas.EquityEventObjectData],
)
def get_equity_event(request: Request, event_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        row = _equity_event_read_model(repos).get_event(company_event_id=event_id)
    if row is None:
        return JSONResponse({"ok": False, "error": "equity_event_not_found"}, status_code=404)
    return _json({"ok": True, "data": row})


def _equity_event_read_model(repos: Any) -> EquityEventQuery:
    return EquityEventQuery(repository=repos.equity_events)


def _public_cursor(value: str) -> str | None:
    if not value:
        return None
    raw = value.strip()
    raw_time, separator, row_id = raw.partition(":")
    if not separator or not raw_time.isdigit() or not row_id.strip():
        raise ApiBadRequest("invalid_cursor", field="cursor")
    return raw


def _public_window(value: str) -> str | None:
    if not value:
        return None
    raw = value.strip().lower()
    if raw.endswith("ms"):
        amount = raw[:-2]
    elif raw.endswith(("m", "h", "d")):
        amount = raw[:-1]
    else:
        amount = raw
    if not amount.isdigit() or int(amount) <= 0:
        raise ApiBadRequest("invalid_window", field="window")
    return raw
