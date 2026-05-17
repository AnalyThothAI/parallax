from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _csv_set, _handle_set, _job_status, _limit, _window
from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository

router = APIRouter()


@router.get("/social-events", response_model=api_schemas.ApiEnvelope[api_schemas.LooseData])
def social_events(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query()] = 50,
    handles: Annotated[str, Query()] = "",
    event_types: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = repos.social_event_extractions.recent(
            window=_window(window),
            limit=_limit(limit, maximum=500),
            handles=_handle_set(handles),
            event_types=_csv_set(event_types),
        )
    return _json({"ok": True, "data": data})


@router.get(
    "/social-events/by-ids",
    response_model=api_schemas.ApiEnvelope[api_schemas.SocialEventsByIdsData],
)
def social_events_by_ids(
    request: Request,
    ids: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    raw = [token.strip() for token in (ids or "").split(",") if token.strip()]
    if not raw:
        return JSONResponse(
            {"ok": False, "error": "ids_required", "field": "ids"},
            status_code=400,
        )
    if len(raw) > 200:
        return JSONResponse(
            {"ok": False, "error": "too_many_ids", "field": "ids", "limit": 200},
            status_code=400,
        )
    with runtime.repositories() as repos:
        records = repos.evidence.events_by_ids(raw)
        handles = sorted(
            {
                str(event.get("author_handle") or "").lstrip("@").lower()
                for event in records.values()
                if event.get("author_handle")
            }
        )
        watched = _watched_handle_set(repos, handles)
        events_payload = [_social_event_detail(records[event_id], watched) for event_id in raw if event_id in records]
        not_found = [event_id for event_id in raw if event_id not in records]
    return _json({"ok": True, "data": {"events": events_payload, "not_found": not_found}})


@router.get(
    "/enrichment-jobs",
    response_model=api_schemas.ApiEnvelope[api_schemas.EnrichmentJobsData],
)
def enrichment_jobs(
    request: Request,
    limit: Annotated[int, Query()] = 50,
    status: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_status = _job_status(status)
    with runtime.repositories() as repos:
        items = repos.enrichment.list_jobs(limit=_limit(limit, maximum=500), status=parsed_status)
        counts = repos.enrichment.job_counts()
    return _json(
        {
            "ok": True,
            "data": {
                "items": items,
                "counts": counts,
            },
        }
    )


def _watched_handle_set(repos: Any, handles: list[str]) -> set[str]:
    if not handles:
        return set()
    try:
        profiles = AccountQualityRepository(repos.conn).profiles_by_handles(handles)
    except Exception:
        return set()
    return {
        handle for handle, profile in profiles.items() if (profile or {}).get("watched_status") in {"active", "watched"}
    }


def _social_event_detail(event: dict[str, Any], watched: set[str]) -> dict[str, Any]:
    author = _dict(event.get("author"))
    source = _dict(event.get("source"))
    handle = str(event.get("author_handle") or author.get("handle") or "").lstrip("@").lower() or None
    followers = event.get("author_followers", author.get("followers"))
    return {
        "event_id": str(event["event_id"]),
        "timestamp_ms": int(event.get("timestamp_ms") or event.get("received_at_ms") or 0),
        "source_provider": event.get("source_provider") or source.get("provider") or "",
        "channel": event.get("channel") or source.get("channel") or "",
        "action": event.get("action") or "",
        "author_handle": handle,
        "author_name": event.get("author_name") or author.get("name"),
        "author_followers": int(followers) if followers is not None else None,
        "author_watched": bool(handle and handle in watched),
        "text_clean": event.get("text_clean") or event.get("text") or _dict(event.get("content")).get("text"),
        "canonical_url": event.get("canonical_url"),
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
