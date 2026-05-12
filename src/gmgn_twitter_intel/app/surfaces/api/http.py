from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.domains.account_quality.read_models.account_alert_service import AccountAlertService
from gmgn_twitter_intel.domains.account_quality.read_models.account_quality_service import AccountQualityService
from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from gmgn_twitter_intel.domains.closed_loop_harness.interfaces import HarnessService
from gmgn_twitter_intel.domains.pulse_lab.read_models.signal_pulse_service import SignalPulseService
from gmgn_twitter_intel.domains.token_intel.queries.search_events_query import SearchEventsQuery
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from gmgn_twitter_intel.domains.token_intel.read_models.search_inspect_service import SearchInspectService
from gmgn_twitter_intel.domains.token_intel.read_models.search_service import SearchCursorError, SearchService
from gmgn_twitter_intel.domains.token_intel.read_models.stocks_radar_service import StocksRadarService
from gmgn_twitter_intel.domains.token_intel.read_models.token_target_cursor import TokenTargetCursorError
from gmgn_twitter_intel.domains.token_intel.read_models.token_target_posts_service import (
    TokenTargetPostsCursorError,
    TokenTargetPostsRangeError,
    TokenTargetPostsService,
    TokenTargetPostsSortError,
)
from gmgn_twitter_intel.domains.token_intel.read_models.token_target_social_timeline_service import (
    TokenTargetSocialTimelineService,
)

WINDOWS = {"5m", "1h", "4h", "24h"}
SCOPES = {"all", "matched"}
ALERT_TYPES = {"account_token", "token"}
JOB_STATUSES = {"pending", "running", "failed", "dead", "done"}
DELIVERY_STATUSES = {"pending", "running", "failed", "dead", "delivered"}
HORIZONS = {"6h", "24h"}
SIGNAL_PULSE_STATUSES = {"trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info"}


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

    @router.get("/search/inspect")
    async def search_inspect(
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
            data = SearchInspectService(
                search_query=SearchEventsQuery(repos.conn),
                token_radar=repos.token_radar,
                targets=repos.token_targets,
            ).inspect(
                q,
                window=parsed_window,
                scope=parsed_scope,
                limit=_limit(limit, maximum=200),
                now_ms=_now_ms(),
            )
        return _json({"ok": True, "data": data})

    @router.get("/token-radar")
    async def token_radar(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        limit: Annotated[int, Query()] = 20,
        scope: Annotated[str, Query()] = "all",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_window = _window(window)
        parsed_scope = _scope(scope)
        with runtime.repositories() as repos:
            data = AssetFlowService(
                token_radar=repos.token_radar,
                live_market_gateway=runtime.live_price_gateway,
            ).asset_flow(
                window=parsed_window,
                limit=_limit(limit),
                scope=parsed_scope,
                now_ms=_now_ms(),
            )
        return _json({"ok": True, "data": {"window": parsed_window, "scope": parsed_scope, **data}})

    @router.get("/stocks-radar")
    async def stocks_radar(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        limit: Annotated[int, Query()] = 20,
        scope: Annotated[str, Query()] = "all",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_window = _window(window)
        parsed_scope = _scope(scope)
        with runtime.repositories() as repos:
            data = await StocksRadarService(
                conn=repos.conn,
                quote_provider=getattr(runtime, "stock_quote_provider", None),
            ).stocks_radar(
                window=parsed_window,
                limit=_limit(limit),
                scope=parsed_scope,
                now_ms=_now_ms(),
            )
        return _json({"ok": True, "data": data})

    @router.get("/live-market")
    async def live_market(
        request: Request,
        target_type: Annotated[str, Query()] = "",
        target_id: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_target_type = _target_type(target_type)
        if not parsed_target_type or not target_id:
            raise ApiBadRequest("target_required", field="target_id")
        gateway = getattr(runtime, "live_price_gateway", None)
        if gateway is None:
            snapshot = {"target_type": parsed_target_type, "target_id": target_id, "status": "unsupported"}
        else:
            snapshot = gateway.snapshot(target_type=parsed_target_type, target_id=target_id, now_ms=_now_ms())
        return _json({"ok": True, "data": snapshot})

    @router.get("/target-posts")
    async def target_posts(
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
        except TokenTargetPostsRangeError:
            return _json({"ok": False, "error": "invalid_range", "field": "range"}, status_code=400)
        except TokenTargetPostsSortError:
            return _json({"ok": False, "error": "invalid_sort", "field": "sort"}, status_code=400)
        except TokenTargetPostsCursorError:
            return _json({"ok": False, "error": "invalid_cursor"}, status_code=400)
        return _json({"ok": True, "data": data})

    @router.get("/target-social-timeline")
    async def target_social_timeline(
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
                data = TokenTargetSocialTimelineService(targets=repos.token_targets).timeline(
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

    @router.get("/signal-lab/pulse")
    async def signal_lab_pulse(
        request: Request,
        window: Annotated[str, Query()] = "1h",
        scope: Annotated[str, Query()] = "all",
        status: Annotated[str, Query()] = "",
        handle: Annotated[str, Query()] = "",
        q: Annotated[str, Query()] = "",
        limit: Annotated[int, Query()] = 80,
        cursor: Annotated[str, Query()] = "",
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        parsed_window = _window(window)
        parsed_scope = _scope(scope)
        parsed_limit = _limit(limit, maximum=500)
        parsed_status = _signal_pulse_status(status)
        with runtime.repositories() as repos:
            data = SignalPulseService(pulse=repos.pulse, harness=repos.harness).pulse(
                window=parsed_window,
                scope=parsed_scope,
                status=parsed_status,
                handle=handle or None,
                q=q or None,
                limit=parsed_limit,
                cursor=cursor or None,
                agent_worker_running=_task_running(getattr(runtime, "pulse_candidate_task", None)),
            )
        return _json({"ok": True, "data": data})

    @router.get("/signal-lab/pulse/{candidate_id}")
    async def signal_lab_pulse_by_id(
        request: Request,
        candidate_id: str,
    ) -> JSONResponse:
        runtime = _authenticated_runtime(request)
        normalized = (candidate_id or "").strip()
        if not normalized:
            return JSONResponse(
                {"ok": False, "error": "invalid_candidate_id", "field": "candidate_id"},
                status_code=400,
            )
        with runtime.repositories() as repos:
            data = SignalPulseService(pulse=repos.pulse, harness=repos.harness).candidate(
                candidate_id=normalized,
            )
        if data is None:
            return JSONResponse(
                {"ok": False, "error": "not_found", "field": "candidate_id"},
                status_code=404,
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
        "token_intents": repos.token_intents.intents_for_event(event_id),
        "token_resolutions": repos.intent_resolutions.resolutions_for_event(event_id),
        "harness": repos.harness.harness_for_event(event_id),
    }


def _notification_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["payload"] = _json_loads(payload.pop("payload_json", "{}"), {})
    payload["channels"] = _json_loads(payload.pop("channels_json", "[]"), [])
    return payload


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


def _target_type(value: str) -> str | None:
    return value if value in {"Asset", "CexToken"} else None


def _horizon(value: str) -> str:
    return value if value in HORIZONS else "6h"


def _alert_type(value: str | None) -> str | None:
    return value if value in ALERT_TYPES else None


def _signal_pulse_status(value: str) -> str | None:
    if not value:
        return None
    if value in SIGNAL_PULSE_STATUSES:
        return value
    raise ApiBadRequest("invalid_status", field="status")


def _task_running(task: Any | None) -> bool:
    return task is not None and not task.done()


def _job_status(value: str | None) -> str | None:
    return value if value in JOB_STATUSES else None


def _delivery_status(value: str | None) -> str | None:
    return value if value in DELIVERY_STATUSES else None


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(payload), status_code=status_code)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
