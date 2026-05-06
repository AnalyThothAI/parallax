from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..retrieval.account_alert_service import AccountAlertService
from ..retrieval.account_quality_service import AccountQualityService
from ..retrieval.asset_search_service import AssetSearchService
from ..retrieval.harness_service import HarnessService
from ..retrieval.token_flow_service import TokenFlowService
from ..retrieval.token_posts_service import (
    TokenPostsCursorError,
    TokenPostsIdentityError,
    TokenPostsRangeError,
    TokenPostsService,
    TokenPostsSortError,
)
from ..retrieval.token_signal_evaluation_service import TokenSignalEvaluationService
from ..retrieval.token_social_timeline_service import (
    TokenSocialTimelineCursorError,
    TokenSocialTimelineIdentityError,
    TokenSocialTimelineService,
)
from ..storage.account_quality_repository import AccountQualityRepository

WINDOWS = {"5m", "1h", "4h", "24h"}
SCOPES = {"all", "matched"}
ALERT_TYPES = {"account_token", "token"}
JOB_STATUSES = {"pending", "running", "failed", "dead", "done"}
DELIVERY_STATUSES = {"pending", "running", "failed", "dead", "delivered"}
HORIZONS = {"6h", "24h"}
SIGNAL_LAB_STAGES = {"extracted", "seeded", "frozen", "settled", "credited"}


class ApiUnauthorized(Exception):
    pass


class ApiBadRequest(Exception):
    def __init__(self, error: str, *, field: str | None = None):
        super().__init__(error)
        self.error = error
        self.field = field


def api_unauthorized_response(_: Request, __: ApiUnauthorized) -> JSONResponse:
    return _json({"ok": False, "error": "unauthorized"}, status_code=401)


def api_bad_request_response(_: Request, exc: ApiBadRequest) -> JSONResponse:
    payload = {"ok": False, "error": exc.error}
    if exc.field:
        payload["field"] = exc.field
    return _json(payload, status_code=400)


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
        with runtime.repositories() as repos:
            events = repos.evidence.recent_events(
                limit=_limit(limit),
                handles=_handle_set(handles),
                ca=ca or None,
                chain=chain or None,
                symbol=symbol or None,
                watched_only=parsed_scope == "matched",
            )
            items = [_payload_for_event(repos, event) for event in events]
        return _json(
            {
                "ok": True,
                "data": {
                    "scope": parsed_scope,
                    "events": events,
                    "items": items,
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
        with runtime.repositories() as repos:
            results = AssetSearchService(
                evidence=repos.evidence,
                assets=repos.assets,
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
                    "total_count": results.total_count,
                    "returned_count": results.returned_count,
                    "has_more": results.has_more,
                    "resolution": results.resolution,
                    "candidates": results.candidates,
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
        scope: Annotated[str, Query()] = "all",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_window = _window(window)
        parsed_scope = _scope(scope)
        with runtime.repositories() as repos:
            items = TokenFlowService(
                signals=repos.signals,
                tokens=repos.tokens,
                harness=repos.harness,
            ).token_flow(
                window=parsed_window,
                limit=_limit(limit),
                scope=parsed_scope,
            )
        return _json({"ok": True, "data": {"window": parsed_window, "scope": parsed_scope, "items": items}})

    @router.get("/token-posts")
    async def token_posts(
        request: Request,
        token_id: Annotated[str, Query()] = "",
        chain: Annotated[str, Query()] = "",
        address: Annotated[str, Query()] = "",
        window: Annotated[str, Query()] = "5m",
        post_range: Annotated[str, Query(alias="range")] = "current_window",
        sort: Annotated[str, Query()] = "recent",
        limit: Annotated[int, Query()] = 50,
        scope: Annotated[str, Query()] = "all",
        cursor: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        if not token_id and not (chain and address):
            return _json({"ok": False, "error": "missing_token_identity"}, status_code=400)
        parsed_window = _window(window)
        parsed_scope = _scope(scope)
        try:
            with runtime.repositories() as repos:
                data = TokenPostsService(signals=repos.signals).token_posts(
                    token_id=token_id or None,
                    chain=chain or None,
                    address=address or None,
                    window=parsed_window,
                    scope=parsed_scope,
                    post_range=_post_range(post_range),
                    sort=sort,
                    limit=_limit(limit, maximum=200),
                    cursor=cursor or None,
                )
        except TokenPostsIdentityError:
            return _json({"ok": False, "error": "invalid_token_identity"}, status_code=400)
        except TokenPostsRangeError:
            return _json({"ok": False, "error": "invalid_range", "field": "range"}, status_code=400)
        except TokenPostsSortError:
            return _json({"ok": False, "error": "invalid_sort", "field": "sort"}, status_code=400)
        except TokenPostsCursorError:
            return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
        return _json({"ok": True, "data": data})

    @router.get("/token-social-timeline")
    async def token_social_timeline(
        request: Request,
        token_id: Annotated[str, Query()] = "",
        chain: Annotated[str, Query()] = "",
        address: Annotated[str, Query()] = "",
        window: Annotated[str, Query()] = "1h",
        limit: Annotated[int, Query()] = 200,
        scope: Annotated[str, Query()] = "all",
        cursor: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        if "bucket" in request.query_params:
            raise ApiBadRequest("unsupported_query_param", field="bucket")
        if not token_id and not (chain and address):
            return _json({"ok": False, "error": "missing_token_identity"}, status_code=400)
        parsed_window = _window(window)
        parsed_scope = _scope(scope)
        try:
            with runtime.repositories() as repos:
                data = TokenSocialTimelineService(signals=repos.signals).timeline(
                    token_id=token_id or None,
                    chain=chain or None,
                    address=address or None,
                    window=parsed_window,
                    scope=parsed_scope,
                    limit=_limit(limit, maximum=500),
                    cursor=cursor or None,
                )
        except TokenSocialTimelineIdentityError:
            return _json({"ok": False, "error": "invalid_token_identity"}, status_code=400)
        except TokenSocialTimelineCursorError:
            return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
        return _json({"ok": True, "data": data})

    @router.get("/token-signal-snapshots")
    async def token_signal_snapshots(
        request: Request,
        window: Annotated[str, Query()] = "",
        scope: Annotated[str, Query()] = "",
        token_id: Annotated[str, Query()] = "",
        limit: Annotated[int, Query()] = 50,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            items = repos.token_signals.list_snapshots(
                window=_window(window) if window else None,
                scope=_scope(scope) if scope else None,
                token_id=token_id or None,
                limit=_limit(limit, maximum=500),
            )
        return _json(
            {
                "ok": True,
                "data": {
                    "items": items,
                },
            }
        )

    @router.get("/token-signal-outcomes")
    async def token_signal_outcomes(
        request: Request,
        horizon: Annotated[str, Query()] = "",
        status: Annotated[str, Query()] = "",
        limit: Annotated[int, Query()] = 50,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            items = repos.token_signals.list_outcomes(
                horizon=_horizon(horizon) if horizon else None,
                status=status or None,
                limit=_limit(limit, maximum=500),
            )
        return _json(
            {
                "ok": True,
                "data": {
                    "items": items,
                },
            }
        )

    @router.get("/token-signal-evaluations")
    async def token_signal_evaluations(
        request: Request,
        horizon: Annotated[str, Query()] = "",
        window: Annotated[str, Query()] = "",
        scope: Annotated[str, Query()] = "",
        refresh: Annotated[bool, Query()] = False,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_horizon = _horizon(horizon) if horizon else None
        parsed_window = _window(window) if window else None
        parsed_scope = _scope(scope) if scope else None
        if refresh and parsed_horizon and parsed_window and parsed_scope:
            with runtime.repositories() as repos:
                data = TokenSignalEvaluationService(repository=repos.token_signals).evaluate(
                    horizon=parsed_horizon,
                    window=parsed_window,
                    scope=parsed_scope,
                )
            return _json({"ok": True, "data": data})
        with runtime.repositories() as repos:
            items = repos.token_signals.list_evaluations(
                horizon=parsed_horizon,
                window=parsed_window,
                scope=parsed_scope,
            )
        return _json(
            {
                "ok": True,
                "data": {
                    "items": items,
                },
            }
        )

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
        with runtime.repositories() as repos:
            items = AccountAlertService(repos.signals).account_alerts(
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

    @router.get("/account-quality")
    async def account_quality(
        request: Request,
        handles: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = AccountQualityService(
                signals=repos.signals,
                repository=AccountQualityRepository(repos.conn),
            ).account_quality_for_handles(sorted(_handle_set(handles)))
        return _json({"ok": True, "data": data})

    @router.get("/notifications")
    async def notifications(
        request: Request,
        limit: Annotated[int, Query()] = 50,
        unread_only: Annotated[bool, Query()] = False,
        rule_id: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            rows = repos.notifications.list_notifications(
                limit=_limit(limit, maximum=500),
                subscriber_key="local",
                unread_only=bool(unread_only),
                rule_id=rule_id or None,
            )
            summary = repos.notifications.summary(subscriber_key="local")
        return _json(
            {
                "ok": True,
                "data": {
                    "items": [_notification_payload(row) for row in rows],
                    "summary": summary,
                },
            }
        )

    @router.get("/notification-summary")
    async def notification_summary(request: Request) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = repos.notifications.summary(subscriber_key="local")
        return _json({"ok": True, "data": data})

    @router.get("/notification-deliveries")
    async def notification_deliveries(
        request: Request,
        limit: Annotated[int, Query()] = 50,
        status: Annotated[str | None, Query()] = None,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            items = repos.notifications.list_deliveries(
                limit=_limit(limit, maximum=500),
                status=_delivery_status(status),
            )
        return _json(
            {
                "ok": True,
                "data": {
                    "items": items,
                },
            }
        )

    @router.post("/notifications/{notification_id}/read")
    async def mark_notification_read(request: Request, notification_id: str) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            updated = repos.notifications.mark_read(notification_id=notification_id, subscriber_key="local")
        return _json({"ok": True, "data": {"notification_id": notification_id, "updated": updated}})

    @router.post("/notifications/read-all")
    async def mark_all_notifications_read(request: Request) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            updated_count = repos.notifications.mark_all_read(subscriber_key="local")
        return _json({"ok": True, "data": {"updated_count": updated_count}})

    @router.get("/social-events")
    async def social_events(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        limit: Annotated[int, Query()] = 50,
        handles: Annotated[str, Query()] = "",
        event_types: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = HarnessService(repos.harness).social_events(
                window=_window(window),
                limit=_limit(limit, maximum=500),
                handles=_handle_set(handles),
                event_types=_csv_set(event_types),
            )
        return _json({"ok": True, "data": data})

    @router.get("/attention-seeds")
    async def attention_seeds(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        limit: Annotated[int, Query()] = 50,
        handles: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = HarnessService(repos.harness).attention_seeds(
                window=_window(window),
                limit=_limit(limit, maximum=500),
                handles=_handle_set(handles),
            )
        return _json({"ok": True, "data": data})

    @router.get("/harness-snapshots")
    async def harness_snapshots(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        horizon: Annotated[str, Query()] = "6h",
        limit: Annotated[int, Query()] = 50,
        asset: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = HarnessService(repos.harness).snapshots(
                window=_window(window),
                horizon=_horizon(horizon),
                limit=_limit(limit, maximum=500),
                asset=asset or None,
            )
        return _json({"ok": True, "data": data})

    @router.get("/harness-outcomes")
    async def harness_outcomes(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        horizon: Annotated[str, Query()] = "6h",
        limit: Annotated[int, Query()] = 50,
        asset: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = HarnessService(repos.harness).outcomes(
                window=_window(window),
                horizon=_horizon(horizon),
                limit=_limit(limit, maximum=500),
                asset=asset or None,
            )
        return _json({"ok": True, "data": data})

    @router.get("/harness-credits")
    async def harness_credits(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        horizon: Annotated[str, Query()] = "6h",
        limit: Annotated[int, Query()] = 80,
        asset: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = HarnessService(repos.harness).credits(
                window=_window(window),
                horizon=_horizon(horizon),
                limit=_limit(limit, maximum=500),
                asset=asset or None,
            )
        return _json({"ok": True, "data": data})

    @router.get("/signal-lab/chains")
    async def signal_lab_chains(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        horizon: Annotated[str, Query()] = "6h",
        scope: Annotated[str, Query()] = "matched",
        stage: Annotated[str, Query()] = "",
        asset: Annotated[str, Query()] = "",
        handle: Annotated[str, Query()] = "",
        q: Annotated[str, Query()] = "",
        limit: Annotated[int, Query()] = 50,
        cursor: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_scope = _scope(scope)
        with runtime.repositories() as repos:
            data = HarnessService(repos.harness).chains(
                window=_window(window),
                horizon=_horizon(horizon),
                scope=parsed_scope,
                stage=_signal_lab_stage(stage),
                asset=asset or None,
                handle=handle or None,
                q=q or None,
                handles=set(runtime.settings.handles) if parsed_scope == "matched" else None,
                limit=_limit(limit, maximum=500),
                cursor=cursor or None,
            )
        return _json({"ok": True, "data": data})

    @router.get("/harness-weights")
    async def harness_weights(
        request: Request,
        horizon: Annotated[str, Query()] = "",
        limit: Annotated[int, Query()] = 100,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = HarnessService(repos.harness).weights(
                horizon=_horizon(horizon) if horizon else None,
                limit=_limit(limit, maximum=500),
            )
        return _json({"ok": True, "data": data})

    @router.get("/harness-health")
    async def harness_health(request: Request) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            job_counts = repos.enrichment.job_counts()
            data = HarnessService(repos.harness).health(
                llm_configured=bool(runtime.settings.llm_configured),
                extractor_running=runtime.enrichment_task is not None and not runtime.enrichment_task.done(),
                pending_jobs=int(job_counts.get("pending", 0)),
                schema_success_rate=repos.enrichment.job_success_rate(),
            )
            data["dead_jobs"] = int(job_counts.get("dead", 0))
            data["failed_jobs"] = int(job_counts.get("failed", 0))
            data["harness_ops_running"] = runtime.harness_ops_task is not None and not runtime.harness_ops_task.done()
        return _json({"ok": True, "data": data})

    @router.get("/harness-score-buckets")
    async def harness_score_buckets(
        request: Request,
        horizon: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        with runtime.repositories() as repos:
            data = HarnessService(repos.harness).score_buckets(
                horizon=_horizon(horizon) if horizon else None,
            )
        return _json({"ok": True, "data": data})

    @router.get("/enrichment-jobs")
    async def enrichment_jobs(
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


def _payload_for_event(repos: Any, event: dict[str, Any]) -> dict[str, Any]:
    event_id = str(event["event_id"])
    return {
        "type": "event",
        "event": event,
        "entities": repos.entities.entities_for_event(event_id),
        "alerts": repos.signals.alerts_for_event(event_id),
        "token_attributions": repos.signals.token_attributions_for_event(event_id),
        "harness": repos.harness.harness_for_event(event_id),
    }


def _notification_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["payload"] = _json_loads(payload.pop("payload_json", "{}"), {})
    payload["channels"] = _json_loads(payload.pop("channels_json", "[]"), [])
    return payload


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


def _csv_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def _limit(value: int, *, maximum: int = 1000) -> int:
    return max(0, min(int(value), maximum))


def _scope(value: str) -> str:
    return value if value in SCOPES else "matched"


def _window(value: str) -> str:
    if value in WINDOWS:
        return value
    raise ApiBadRequest("invalid_window", field="window")


def _post_range(value: str) -> str:
    if value in {"current_window", "since_ignition", "all_history"}:
        return value
    raise ApiBadRequest("invalid_range", field="range")


def _horizon(value: str) -> str:
    return value if value in HORIZONS else "6h"


def _signal_lab_stage(value: str) -> str | None:
    return value if value in SIGNAL_LAB_STAGES else None


def _alert_type(value: str | None) -> str | None:
    return value if value in ALERT_TYPES else None


def _job_status(value: str | None) -> str | None:
    return value if value in JOB_STATUSES else None


def _delivery_status(value: str | None) -> str | None:
    return value if value in DELIVERY_STATUSES else None


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
