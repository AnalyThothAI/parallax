from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _handle_set, _limit, _scope
from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository

router = APIRouter()


@router.get("/recent", response_model=api_schemas.ApiEnvelope[api_schemas.RecentData])
def recent(
    request: Request,
    limit: Annotated[int, Query()] = 20,
    handles: Annotated[str, Query()] = "",
    ca: Annotated[str, Query()] = "",
    chain: Annotated[str, Query()] = "",
    symbol: Annotated[str, Query()] = "",
    scope: Annotated[str, Query()] = "matched",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_scope = _scope(scope)
    data = _recent_data(
        runtime,
        limit=_limit(limit),
        handles=_handle_set(handles),
        ca=ca or None,
        chain=chain or None,
        symbol=symbol or None,
        scope=parsed_scope,
    )
    return _json(
        {
            "ok": True,
            "data": {
                "scope": parsed_scope,
                **data,
            },
        }
    )


@router.get(
    "/events/by-ids",
    response_model=api_schemas.ApiEnvelope[api_schemas.SourceEventsByIdsData],
)
def events_by_ids(
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
        events_payload = [_source_event_detail(records[event_id], watched) for event_id in raw if event_id in records]
        not_found = [event_id for event_id in raw if event_id not in records]
    return _json({"ok": True, "data": {"events": events_payload, "not_found": not_found}})


def _payload_for_event(
    repos: Any,
    event: dict[str, Any],
    *,
    token_resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    event_id = str(event["event_id"])
    return {
        "type": "event",
        "event": event,
        "entities": repos.entities.entities_for_event(event_id),
        "alerts": repos.signals.alerts_for_event(event_id),
        "token_intents": repos.token_intents.intents_for_event(event_id),
        "token_resolutions": (
            token_resolutions if token_resolutions is not None else repos.event_tokens.for_event(event_id)
        ),
    }


def _payloads_for_events(repos: Any, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_ids = tuple(str(event["event_id"]) for event in events)
    entities_by_event = repos.entities.entities_for_events(event_ids)
    alerts_by_event = repos.signals.alerts_for_events(event_ids)
    intents_by_event = repos.token_intents.intents_for_events(event_ids)
    token_resolutions_by_event = repos.event_tokens.for_events(event_ids)
    return [
        {
            "type": "event",
            "event": event,
            "entities": entities_by_event.get(str(event["event_id"]), []),
            "alerts": alerts_by_event.get(str(event["event_id"]), []),
            "token_intents": intents_by_event.get(str(event["event_id"]), []),
            "token_resolutions": token_resolutions_by_event.get(str(event["event_id"]), []),
        }
        for event in events
    ]


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


def _source_event_detail(event: dict[str, Any], watched: set[str]) -> dict[str, Any]:
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


def _recent_data(
    runtime: Any,
    *,
    limit: int,
    handles: set[str],
    ca: str | None,
    chain: str | None,
    symbol: str | None,
    scope: str,
) -> dict[str, Any]:
    with runtime.repositories() as repos:
        events = repos.evidence.recent_events(
            limit=limit,
            handles=handles,
            ca=ca,
            chain=chain,
            symbol=symbol,
            watched_only=scope == "matched",
        )
        return {
            "events": events,
            "items": _payloads_for_events(repos, events),
        }
