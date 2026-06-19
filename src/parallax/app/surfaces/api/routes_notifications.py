from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import _alert_type, _delivery_status, _handle_set, _limit, _window
from parallax.domains.account_quality.read_models.account_alert_service import AccountAlertService
from parallax.domains.account_quality.read_models.account_quality_service import AccountQualityService

router = APIRouter()

_NEWS_HIGH_SIGNAL_TEXT_PAYLOAD_FIELDS = (
    "news_item_id",
    "representative_news_item_id",
    "story_key",
    "agent_admission_status",
    "agent_admission_reason",
    "decision_class",
    "direction",
    "semantic_signature",
    "display_title",
    "external_push_signature",
    "external_push_suppression_reason",
    "canonical_url",
    "source_domain",
)


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
        data = AccountQualityService.from_conn(repos.conn).account_quality_for_handles(sorted(_handle_set(handles)))
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
    rule_id = str(payload.get("rule_id") or "")
    raw_payload = _notification_payload_json(rule_id, payload.pop("payload_json", None))
    payload["payload"] = _public_notification_payload(rule_id, raw_payload)
    payload["channels"] = _json_loads(payload.pop("channels_json", "[]"), [])
    return payload


def _public_notification_payload(rule_id: str, raw_payload: Any) -> dict[str, Any]:
    if rule_id != "news_high_signal":
        return _json_object(raw_payload)
    payload = _required_news_mapping(raw_payload, "payload")
    public: dict[str, Any] = {}
    for key in _NEWS_HIGH_SIGNAL_TEXT_PAYLOAD_FIELDS:
        text = _optional_news_payload_text(payload, key)
        if text is not None:
            public[key] = text
    if "story" in payload:
        public["story"] = _public_news_story_payload(payload["story"])
    if "market_scope" in payload:
        public["market_scope"] = _public_news_market_scope_payload(payload["market_scope"])
    if "agent_admission" in payload:
        public["agent_admission"] = _public_news_agent_admission_payload(payload["agent_admission"])
    external_push_eligible = _optional_news_payload_bool(payload, "external_push_eligible")
    if external_push_eligible is not None:
        public["external_push_eligible"] = external_push_eligible
    duplicate_count = _optional_news_payload_nonnegative_int(payload, "duplicate_count")
    if duplicate_count is not None:
        public["duplicate_count"] = duplicate_count
    if "agent_brief" in payload:
        public["agent_brief"] = _public_news_agent_brief(payload["agent_brief"])
    if "affected_entities" in payload:
        public["affected_entities"] = _public_news_affected_entities(payload["affected_entities"])
    if "token_impacts" in payload:
        public["token_impacts"] = _public_news_token_impacts(payload["token_impacts"])
    return public


def _public_news_agent_brief(value: Any) -> dict[str, Any]:
    payload = _required_news_mapping(value, "agent_brief")
    public: dict[str, Any] = {"status": _required_news_agent_brief_text(payload, "status")}
    for key in ("direction", "decision_class", "title_zh", "summary_zh", "market_read_zh"):
        text = _optional_news_agent_brief_text(payload, key)
        if text is not None:
            public[key] = text
    if "affected_entities" in payload and payload.get("affected_entities") is not None:
        public["affected_entities"] = _public_news_affected_entities(payload["affected_entities"])
    return public


def _public_news_story_payload(value: Any) -> dict[str, Any]:
    payload = _required_news_mapping(value, "story")
    public = {
        "story_key": _required_news_payload_text(payload, "story", "story_key"),
        "member_count": _required_news_payload_positive_int(payload, "story", "member_count"),
    }
    representative_news_item_id = _optional_news_payload_section_text(payload, "story", "representative_news_item_id")
    if representative_news_item_id is not None:
        public["representative_news_item_id"] = representative_news_item_id
    for field_name in ("member_news_item_ids", "source_domains", "source_ids", "provider_article_keys"):
        values = _optional_news_payload_string_list(payload, "story", field_name)
        if values is not None:
            public[field_name] = values
    return public


def _public_news_market_scope_payload(value: Any) -> dict[str, Any]:
    payload = _required_news_mapping(value, "market_scope")
    return {
        "scope": _required_news_payload_string_list(payload, "market_scope", "scope"),
        "primary": _required_news_payload_text(payload, "market_scope", "primary"),
        "status": _required_news_payload_text(payload, "market_scope", "status"),
        "reason": _required_news_payload_text(payload, "market_scope", "reason"),
        "basis": _required_news_payload_mapping(payload, "market_scope", "basis"),
        "version": _required_news_payload_text(payload, "market_scope", "version"),
    }


def _public_news_agent_admission_payload(value: Any) -> dict[str, Any]:
    payload = _required_news_mapping(value, "agent_admission")
    public: dict[str, Any] = {
        "status": _required_news_payload_text(payload, "agent_admission", "status"),
        "reason": _required_news_payload_text(payload, "agent_admission", "reason"),
        "representative_news_item_id": _required_news_payload_text(
            payload,
            "agent_admission",
            "representative_news_item_id",
        ),
    }
    basis = _optional_news_payload_mapping(payload, "agent_admission", "basis")
    if basis is not None:
        public["basis"] = basis
    version = _optional_news_payload_section_text(payload, "agent_admission", "version")
    if version is not None:
        public["version"] = version
    eligible = _optional_news_payload_section_bool(payload, "agent_admission", "eligible")
    if eligible is not None:
        public["eligible"] = eligible
    return public


def _public_news_affected_entities(value: Any) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for item in _required_news_list(value, "affected_entities"):
        entity = _public_news_affected_entity(item)
        if entity:
            entities.append(entity)
    return entities


def _public_news_affected_entity(value: Any) -> dict[str, Any]:
    entity = _required_news_mapping(value, "affected_entities")
    payload: dict[str, Any] = {}
    for key in (
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
    ):
        text = _optional_news_affected_entity_text(entity, key)
        if text is not None:
            payload[key] = text
    evidence_refs = _optional_news_affected_entity_string_list(entity, "evidence_refs")
    if evidence_refs is not None:
        payload["evidence_refs"] = evidence_refs
    return payload


def _public_news_token_impacts(value: Any) -> list[dict[str, Any]]:
    impacts: list[dict[str, Any]] = []
    for item in _required_news_list(value, "token_impacts"):
        impact = _required_news_mapping(item, "token_impacts")
        public: dict[str, Any] = {}
        for key in ("symbol", "market_type"):
            text = _optional_news_token_impact_text(impact, key)
            if text is not None:
                public[key] = text
        if public:
            impacts.append(public)
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


def _notification_payload_json(rule_id: str, value: Any) -> Any:
    if rule_id != "news_high_signal":
        return _json_loads(value, {})
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError("news_high_signal_payload_json_required")


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _required_news_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError(f"news_high_signal_{field_name}_required")


def _required_news_list(value: Any, field_name: str) -> list[Any]:
    if isinstance(value, list):
        return value
    raise ValueError(f"news_high_signal_{field_name}_required")


def _optional_news_payload_text(payload: Mapping[str, Any], field_name: str) -> str | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value.strip()


def _optional_news_payload_bool(payload: Mapping[str, Any], field_name: str) -> bool | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value


def _optional_news_payload_nonnegative_int(payload: Mapping[str, Any], field_name: str) -> int | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"news_high_signal_{field_name}_required")
    return value


def _required_news_payload_text(payload: Mapping[str, Any], section: str, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value.strip()


def _optional_news_payload_section_text(
    payload: Mapping[str, Any],
    section: str,
    field_name: str,
) -> str | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    return _required_news_payload_text(payload, section, field_name)


def _required_news_payload_string_list(payload: Mapping[str, Any], section: str, field_name: str) -> list[str]:
    values = payload.get(field_name)
    if not isinstance(values, list):
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    strings: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"news_high_signal_{section}_{field_name}_required")
        strings.append(value.strip())
    if not strings:
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return strings


def _optional_news_payload_string_list(
    payload: Mapping[str, Any],
    section: str,
    field_name: str,
) -> list[str] | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    return _required_news_payload_string_list(payload, section, field_name)


def _required_news_payload_mapping(payload: Mapping[str, Any], section: str, field_name: str) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return dict(value)


def _optional_news_payload_mapping(
    payload: Mapping[str, Any],
    section: str,
    field_name: str,
) -> dict[str, Any] | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    return _required_news_payload_mapping(payload, section, field_name)


def _required_news_payload_positive_int(payload: Mapping[str, Any], section: str, field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value


def _optional_news_payload_section_bool(
    payload: Mapping[str, Any],
    section: str,
    field_name: str,
) -> bool | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"news_high_signal_{section}_{field_name}_required")
    return value


def _optional_news_agent_brief_text(payload: Mapping[str, Any], field_name: str) -> str | None:
    if field_name not in payload or payload.get(field_name) is None:
        return None
    return _required_news_agent_brief_text(payload, field_name)


def _required_news_agent_brief_text(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_agent_brief_{field_name}_required")
    return value.strip()


def _optional_news_affected_entity_text(entity: Mapping[str, Any], field_name: str) -> str | None:
    if field_name not in entity or entity.get(field_name) is None:
        return None
    value = entity.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_affected_entities_{field_name}_required")
    return value.strip()


def _optional_news_affected_entity_string_list(entity: Mapping[str, Any], field_name: str) -> list[str] | None:
    if field_name not in entity or entity.get(field_name) is None:
        return None
    values = entity.get(field_name)
    if not isinstance(values, list):
        raise ValueError(f"news_high_signal_affected_entities_{field_name}_required")
    refs: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"news_high_signal_affected_entities_{field_name}_required")
        refs.append(value.strip())
    return refs


def _optional_news_token_impact_text(impact: Mapping[str, Any], field_name: str) -> str | None:
    if field_name not in impact or impact.get(field_name) is None:
        return None
    value = impact.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"news_high_signal_token_impacts_{field_name}_required")
    return value.strip()
