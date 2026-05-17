from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _handle_set, _limit, _scope

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
