from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import _alert_type, _delivery_status, _handle_set, _limit, _window
from parallax.domains.account_quality.read_models.account_alert_service import AccountAlertService
from parallax.domains.account_quality.read_models.account_quality_service import AccountQualityService
from parallax.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository

router = APIRouter()

_NEWS_HIGH_SIGNAL_PAYLOAD_KEYS = frozenset(
    {
        "news_item_id",
        "representative_news_item_id",
        "story_key",
        "story",
        "market_scope",
        "agent_admission_status",
        "agent_admission_reason",
        "agent_admission",
        "decision_class",
        "direction",
        "affected_entities",
        "semantic_signature",
        "display_title",
        "external_push_signature",
        "external_push_eligible",
        "external_push_suppression_reason",
        "agent_brief",
        "canonical_url",
        "source_domain",
        "duplicate_count",
        "token_impacts",
    }
)
_NEWS_AGENT_BRIEF_KEYS = frozenset(
    {
        "status",
        "direction",
        "decision_class",
        "title_zh",
        "summary_zh",
        "market_read_zh",
        "affected_entities",
    }
)
_NEWS_AFFECTED_ENTITY_KEYS = frozenset(
    {
        "label",
        "symbol",
        "name",
        "entity_type",
        "market_domain",
        "resolution_status",
        "target_type",
        "target_id",
        "impact_direction",
        "reason_zh",
        "evidence_refs",
    }
)
_NEWS_TOKEN_IMPACT_KEYS = frozenset({"symbol", "market_type"})


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
    raw_payload = _json_loads(payload.pop("payload_json", "{}"), {})
    payload["payload"] = _public_notification_payload(str(payload.get("rule_id") or ""), raw_payload)
    payload["channels"] = _json_loads(payload.pop("channels_json", "[]"), [])
    return payload


def _public_notification_payload(rule_id: str, raw_payload: Any) -> dict[str, Any]:
    payload = _json_object(raw_payload)
    if rule_id != "news_high_signal":
        return payload
    public = {key: payload[key] for key in _NEWS_HIGH_SIGNAL_PAYLOAD_KEYS if key in payload}
    if "agent_brief" in public:
        public["agent_brief"] = _public_news_agent_brief(public["agent_brief"])
    if "affected_entities" in public:
        public["affected_entities"] = _public_news_affected_entities(public["affected_entities"])
    if "token_impacts" in public:
        public["token_impacts"] = _public_news_token_impacts(public["token_impacts"])
    return public


def _public_news_agent_brief(value: Any) -> dict[str, Any]:
    payload = {
        key: item
        for key, item in _json_object(value).items()
        if key in _NEWS_AGENT_BRIEF_KEYS and item is not None
    }
    if "affected_entities" in payload:
        payload["affected_entities"] = _public_news_affected_entities(payload["affected_entities"])
    return payload


def _public_news_affected_entities(value: Any) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for item in _json_list(value):
        entity = {
            key: entity_value
            for key, entity_value in _json_object(item).items()
            if key in _NEWS_AFFECTED_ENTITY_KEYS and entity_value is not None
        }
        if entity:
            entities.append(entity)
    return entities


def _public_news_token_impacts(value: Any) -> list[dict[str, Any]]:
    impacts: list[dict[str, Any]] = []
    for item in _json_list(value):
        impact = {
            key: impact_value
            for key, impact_value in _json_object(item).items()
            if key in _NEWS_TOKEN_IMPACT_KEYS and impact_value is not None
        }
        if impact:
            impacts.append(impact)
    return impacts


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


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return []
