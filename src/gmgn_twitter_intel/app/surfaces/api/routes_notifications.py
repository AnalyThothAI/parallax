from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _alert_type, _delivery_status, _handle_set, _limit, _window
from gmgn_twitter_intel.domains.account_quality.read_models.account_alert_service import AccountAlertService
from gmgn_twitter_intel.domains.account_quality.read_models.account_quality_service import AccountQualityService
from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository

router = APIRouter()


@router.get(
    "/account-alerts",
    response_model=api_schemas.ApiEnvelope[api_schemas.AccountAlertsData],
)
def account_alerts(
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


@router.get(
    "/account-quality",
    response_model=api_schemas.ApiEnvelope[api_schemas.AccountQualityData],
)
def account_quality(
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


@router.get(
    "/notifications",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationsData],
)
def notifications(
    request: Request,
    limit: Annotated[int, Query()] = 50,
    unread_only: Annotated[bool, Query()] = False,
    rule_id: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    data = _notifications_data(
        runtime,
        limit=_limit(limit, maximum=500),
        unread_only=bool(unread_only),
        rule_id=rule_id or None,
        subscriber_key="local",
    )
    return _json(
        {
            "ok": True,
            "data": data,
        }
    )


@router.get(
    "/notification-summary",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationSummary],
)
def notification_summary(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    data = _notification_summary_data(runtime, subscriber_key="local")
    return _json({"ok": True, "data": data})


@router.get(
    "/notification-deliveries",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationDeliveriesData],
)
def notification_deliveries(
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


@router.post(
    "/notifications/{notification_id}/read",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationReadData],
)
def mark_notification_read(request: Request, notification_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        updated = repos.notifications.mark_read(notification_id=notification_id, subscriber_key="local")
    return _json({"ok": True, "data": {"notification_id": notification_id, "updated": updated}})


@router.post(
    "/notifications/read-all",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationReadAllData],
)
def mark_all_notifications_read(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        updated_count = repos.notifications.mark_all_read(subscriber_key="local")
    return _json({"ok": True, "data": {"updated_count": updated_count}})


@router.post(
    "/notifications/author/{author_handle}/read",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationReadAllData],
)
def mark_author_notifications_read(request: Request, author_handle: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        updated_count = repos.notifications.mark_author_read(
            author_handle=author_handle,
            subscriber_key="local",
        )
    return _json({"ok": True, "data": {"updated_count": updated_count}})


def _notification_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["payload"] = _json_loads(payload.pop("payload_json", "{}"), {})
    payload["channels"] = _json_loads(payload.pop("channels_json", "[]"), [])
    return payload


def _notifications_data(
    runtime: Any,
    *,
    limit: int,
    unread_only: bool,
    rule_id: str | None,
    subscriber_key: str,
) -> dict[str, Any]:
    with runtime.repositories() as repos:
        rows = repos.notifications.list_notifications(
            limit=limit,
            subscriber_key=subscriber_key,
            unread_only=unread_only,
            rule_id=rule_id,
        )
        summary = repos.notifications.summary(subscriber_key=subscriber_key)
    return {
        "items": [_notification_payload(row) for row in rows],
        "summary": summary,
    }


def _notification_summary_data(runtime: Any, *, subscriber_key: str) -> dict[str, Any]:
    with runtime.repositories() as repos:
        return repos.notifications.summary(subscriber_key=subscriber_key)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
