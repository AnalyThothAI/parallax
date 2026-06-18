from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

_AUTHORITATIVE_SOURCE_ROLES = frozenset(
    {
        "developer_signal",
        "official_exchange",
        "official_protocol",
        "official_project",
        "official_regulator",
        "regulator",
    }
)
_HIGH_TRUST_TIERS = frozenset({"high", "official"})
_MATERIAL_CONTENT_CLASSES = frozenset(
    {
        "ai_semiconductors",
        "energy_geopolitics",
        "exchange_listing",
        "macro_policy",
        "rates_fed",
        "regulatory_action",
        "security_incident",
    }
)
_MATERIAL_MARKET_SCOPES = frozenset(
    {
        "ai_semiconductors",
        "broad_risk",
        "commodity",
        "commodities",
        "crypto",
        "energy_geopolitics",
        "fx",
        "macro_rates",
        "private_company",
        "regulation",
        "us_equity",
    }
)


def news_item_agent_brief_priority(
    *,
    item: Mapping[str, Any],
    admission: Any | None = None,
) -> int:
    admission_payload = _admission_payload(item=item, admission=admission)
    status = _text(admission_payload.get("status") or item.get("agent_admission_status"))
    if status not in {"eligible", "eligible_refresh"}:
        return 100
    if status == "eligible_refresh":
        return 10

    basis = _object(admission_payload.get("basis"))
    priority = 55
    if _has_material_delta(
        admission_payload.get("material_delta") or basis.get("material_delta") or item.get("material_delta_json")
    ):
        priority = min(priority, 18)

    scopes = _market_scopes(item=item, basis=basis)
    material_scopes = {scope for scope in scopes if scope in _MATERIAL_MARKET_SCOPES}
    if len(material_scopes) >= 3:
        priority -= 14
    elif material_scopes:
        priority -= 7
    if _text(item.get("source_role")) in _AUTHORITATIVE_SOURCE_ROLES:
        priority -= 8
    if _text(item.get("trust_tier")) in _HIGH_TRUST_TIERS:
        priority -= 5
    if _text(item.get("content_class")) in _MATERIAL_CONTENT_CLASSES:
        priority -= 6
    return max(12, min(95, priority))


def _admission_payload(*, item: Mapping[str, Any], admission: Any | None) -> dict[str, Any]:
    if admission is not None:
        return {
            "status": _text(getattr(admission, "status", "")),
            "reason": _text(getattr(admission, "reason", "")),
            "basis": _object(getattr(admission, "basis", {})),
        }
    return _object(item.get("agent_admission_json"))


def _has_material_delta(value: Any) -> bool:
    payload = _object(value)
    if bool(payload.get("has_delta")):
        return True
    if _text(payload.get("status")) == "material":
        return True
    return bool(_list(payload.get("changed_fields")) or _list(payload.get("reasons")))


def _market_scopes(*, item: Mapping[str, Any], basis: Mapping[str, Any]) -> set[str]:
    scopes: set[str] = set()
    for value in (basis.get("market_scope"), item.get("market_scope_json"), item.get("market_scope")):
        scopes.update(_scope_names(value))
    return {scope for scope in scopes if scope and scope != "unknown"}


def _scope_names(value: Any) -> set[str]:
    payload = _object(value)
    if payload:
        names = set(_text_list(payload.get("scope") or payload.get("market_scope")))
        primary = _text(payload.get("primary") or payload.get("market_scope_primary"))
        if primary:
            names.add(primary)
        return names
    return set(_text_list(value))


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _text_list(value: Any) -> list[str]:
    return [_text(item) for item in _list(value) if _text(item)]


def _text(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


__all__ = [
    "news_item_agent_brief_priority",
]
