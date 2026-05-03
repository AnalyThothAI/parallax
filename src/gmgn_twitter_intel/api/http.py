from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..retrieval.account_alert_service import AccountAlertService
from ..retrieval.narrative_service import NarrativeService
from ..retrieval.search_service import SearchService
from ..retrieval.token_flow_service import TokenFlowService

WINDOWS = {"1m", "5m", "1h", "24h"}
SCOPES = {"all", "matched"}
ALERT_TYPES = {"account_token", "token"}
JOB_STATUSES = {"pending", "running", "failed", "dead", "done"}


class ApiUnauthorized(Exception):
    pass


def api_unauthorized_response(_: Request, __: ApiUnauthorized) -> JSONResponse:
    return _json({"ok": False, "error": "unauthorized"}, status_code=401)


def create_api_router(readiness_payload: Callable[[Any], tuple[dict[str, Any], int]]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["api"])

    @router.get("/bootstrap")
    async def bootstrap(request: Request) -> JSONResponse:
        runtime = _runtime(request)
        return _json(
            {
                "ok": True,
                "data": {
                    "ws_token": runtime.settings.ws_token,
                    "handles": list(runtime.settings.handles),
                    "replay_limit": runtime.settings.replay_limit,
                },
            }
        )

    @router.get("/status")
    async def status(request: Request) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        payload, status_code = readiness_payload(runtime)
        return _json({"ok": payload.get("ok", status_code < 500), "data": payload}, status_code=status_code)

    @router.get("/recent")
    async def recent(
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
        events = runtime.read_evidence.recent_events(
            limit=_limit(limit),
            handles=_handle_set(handles),
            ca=ca or None,
            chain=chain or None,
            symbol=symbol or None,
            watched_only=parsed_scope == "matched",
        )
        return _json(
            {
                "ok": True,
                "data": {
                    "scope": parsed_scope,
                    "events": events,
                    "items": [_payload_for_event(runtime, event) for event in events],
                },
            }
        )

    @router.get("/search")
    async def search(
        request: Request,
        q: Annotated[str, Query()] = "",
        limit: Annotated[int, Query()] = 20,
        symbol: Annotated[str, Query()] = "",
        ca: Annotated[str, Query()] = "",
        chain: Annotated[str, Query()] = "",
        handle: Annotated[str, Query()] = "",
        scope: Annotated[str, Query()] = "all",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        query = _search_query(q=q, symbol=symbol, ca=ca, chain=chain, handle=handle)
        results = SearchService(
            evidence=runtime.read_evidence,
            entities=runtime.read_entities,
            signals=runtime.read_signals,
        ).search(
            query,
            limit=_limit(limit),
            scope=_scope(scope),
        )
        return _json(
            {
                "ok": results.ok,
                "data": {
                    "query": results.query,
                    "result_count": len(results.items),
                    "items": results.items,
                },
                "error": results.error,
            }
        )

    @router.get("/token-flow")
    async def token_flow(
        request: Request,
        window: Annotated[str, Query()] = "5m",
        limit: Annotated[int, Query()] = 20,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_window = _window(window)
        items = TokenFlowService(signals=runtime.read_signals, tokens=runtime.read_tokens).token_flow(
            window=parsed_window,
            limit=_limit(limit),
        )
        return _json({"ok": True, "data": {"window": parsed_window, "items": items}})

    @router.get("/account-alerts")
    async def account_alerts(
        request: Request,
        window: Annotated[str, Query()] = "24h",
        limit: Annotated[int, Query()] = 50,
        handles: Annotated[str, Query()] = "",
        alert_type: Annotated[str | None, Query()] = None,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_window = _window(window)
        parsed_alert_type = _alert_type(alert_type)
        items = AccountAlertService(runtime.read_signals).account_alerts(
            window=parsed_window,
            limit=_limit(limit, maximum=500),
            handles=_handle_set(handles),
            alert_type=parsed_alert_type,
        )
        return _json(
            {
                "ok": True,
                "data": {
                    "window": parsed_window,
                    "alert_type": parsed_alert_type,
                    "items": items,
                },
            }
        )

    @router.get("/narrative-flow")
    async def narrative_flow(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        limit: Annotated[int, Query()] = 20,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_window = _window(window)
        items = NarrativeService(runtime.read_enrichment).narrative_flow(window=parsed_window, limit=_limit(limit))
        return _json({"ok": True, "data": {"window": parsed_window, "items": items}})

    @router.get("/account-narratives")
    async def account_narratives(
        request: Request,
        window: Annotated[str, Query()] = "24h",
        limit: Annotated[int, Query()] = 50,
        handles: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_window = _window(window)
        items = NarrativeService(runtime.read_enrichment).account_narratives(
            window=parsed_window,
            limit=_limit(limit, maximum=500),
            handles=_handle_set(handles),
        )
        return _json({"ok": True, "data": {"window": parsed_window, "items": items}})

    @router.get("/enrichment-jobs")
    async def enrichment_jobs(
        request: Request,
        limit: Annotated[int, Query()] = 50,
        status: Annotated[str | None, Query()] = None,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_status = _job_status(status)
        return _json(
            {
                "ok": True,
                "data": {
                    "items": runtime.read_enrichment.list_jobs(limit=_limit(limit, maximum=500), status=parsed_status),
                    "counts": runtime.read_enrichment.job_counts(),
                },
            }
        )

    return router


def _runtime(request: Request) -> Any:
    return request.app.state.service


def _authenticated_runtime(request: Request) -> Any:
    runtime = _runtime(request)
    if not runtime.settings.ws_token or _request_token(request) != runtime.settings.ws_token:
        raise ApiUnauthorized()
    return runtime


def _request_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    token = request.query_params.get("token")
    return token.strip() if token else None


def _payload_for_event(runtime: Any, event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event["event_id"])
    return {
        "type": "event",
        "event": event,
        "entities": runtime.read_entities.entities_for_event(event_id),
        "alerts": runtime.read_signals.alerts_for_event(event_id),
        "enrichment": runtime.read_enrichment.enrichment_for_event(event_id),
    }


def _search_query(*, q: str, symbol: str, ca: str, chain: str, handle: str) -> str:
    if ca:
        return f"{chain}:{ca}" if chain else ca
    if symbol:
        return f"${symbol.strip().lstrip('$')}"
    if handle:
        return f"@{handle.strip().lstrip('@')}"
    return q


def _handle_set(raw: str) -> set[str]:
    return {item.strip().lstrip("@").lower() for item in raw.split(",") if item.strip()}


def _limit(value: int, *, maximum: int = 1000) -> int:
    return max(0, min(int(value), maximum))


def _scope(value: str) -> str:
    return value if value in SCOPES else "matched"


def _window(value: str) -> str:
    return value if value in WINDOWS else "5m"


def _alert_type(value: str | None) -> str | None:
    return value if value in ALERT_TYPES else None


def _job_status(value: str | None) -> str | None:
    return value if value in JOB_STATUSES else None


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code)
