from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from tracefold.app.http import schemas as api_schemas
from tracefold.app.http.dependencies import _authenticated_runtime, _now_ms
from tracefold.app.http.responses import _validated_json
from tracefold.app.http.validators import _alert_type, _delivery_status, _handle_set, _limit, _window
from tracefold.notifications import AccountAlertService

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
            now_ms=_now_ms(),
            handles=_handle_set(handles),
            alert_type=parsed_alert_type,
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.AccountAlertsData],
        {
            "ok": True,
            "data": {
                "window": parsed_window,
                "alert_type": parsed_alert_type,
                "items": items,
            },
        },
    )


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
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.NotificationsData],
        {
            "ok": True,
            "data": data,
        },
    )


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
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.NotificationDeliveriesData],
        {
            "ok": True,
            "data": {
                "items": items,
            },
        },
    )


@router.post(
    "/notifications/{notification_id}/read",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationReadData],
)
def mark_notification_read(request: Request, notification_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos, repos.transaction():
        updated = repos.notifications.mark_read(notification_id=notification_id, subscriber_key="local")
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.NotificationReadData],
        {"ok": True, "data": {"notification_id": notification_id, "updated": updated}},
    )


@router.post(
    "/notifications/read-all",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationReadAllData],
)
def mark_all_notifications_read(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos, repos.transaction():
        updated_count = repos.notifications.mark_all_read(subscriber_key="local")
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.NotificationReadAllData],
        {"ok": True, "data": {"updated_count": updated_count}},
    )


@router.post(
    "/notifications/author/{author_handle}/read",
    response_model=api_schemas.ApiEnvelope[api_schemas.NotificationReadAllData],
)
def mark_author_notifications_read(request: Request, author_handle: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos, repos.transaction():
        updated_count = repos.notifications.mark_author_read(
            author_handle=author_handle,
            subscriber_key="local",
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.NotificationReadAllData],
        {"ok": True, "data": {"updated_count": updated_count}},
    )


def _notification_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    raw_payload = _notification_payload_json(_required_notification_field(payload, "payload_json"))
    payload["payload"] = raw_payload
    payload["channels"] = _notification_channels(_required_notification_field(payload, "channels_json"))
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


def _notification_payload_json(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError("notification_payload_json_mapping_required")


def _notification_channels(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(channel, str) or not channel for channel in value)
    ):
        raise ValueError("notification_channels_json_list_required")
    return list(value)


def _required_notification_field(payload: dict[str, Any], field_name: str) -> Any:
    if field_name not in payload:
        raise ValueError(f"notification_{field_name}_required")
    return payload.pop(field_name)
