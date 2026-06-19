from __future__ import annotations

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
    status = _text(admission_payload.get("status"))
    if status not in {"eligible", "eligible_refresh"}:
        return 100
    if status == "eligible_refresh":
        return 10

    basis = _optional_policy_mapping(admission_payload.get("basis"), "basis")
    priority = 55
    if _has_material_delta(basis.get("material_delta")):
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
            "basis": _optional_policy_mapping(getattr(admission, "basis", None), "basis"),
        }
    return _optional_policy_mapping(item.get("agent_admission_json"), "agent_admission_json")


def _has_material_delta(value: Any) -> bool:
    payload = _optional_policy_mapping(value, "material_delta")
    changed_fields = _optional_policy_list(payload.get("changed_fields"), "material_delta_changed_fields")
    reasons = _optional_policy_list(payload.get("reasons"), "material_delta_reasons")
    if bool(payload.get("has_delta")):
        return True
    if _text(payload.get("status")) == "material":
        return True
    return bool(changed_fields or reasons)


def _market_scopes(*, item: Mapping[str, Any], basis: Mapping[str, Any]) -> set[str]:
    scopes: set[str] = set()
    scopes.update(_scope_names(basis.get("market_scope"), field_name="admission_basis_market_scope"))
    scopes.update(_scope_names(item.get("market_scope_json"), field_name="market_scope_json"))
    return {scope for scope in scopes if scope and scope != "unknown"}


def _scope_names(value: Any, *, field_name: str) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        names: set[str] = set()
        if "scope" in value:
            names.update(_text_list(value.get("scope"), field_name=f"{field_name}_scope"))
        primary = _optional_policy_text(value.get("primary"), f"{field_name}_primary")
        if primary:
            names.add(primary)
        return names
    return set(_text_list(value, field_name=field_name))


def _optional_policy_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError(f"news_item_agent_policy_{field_name}_required")


def _optional_policy_list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    raise ValueError(f"news_item_agent_policy_{field_name}_required")


def _optional_policy_text(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _text(value)
    raise ValueError(f"news_item_agent_policy_{field_name}_required")


def _text_list(value: Any, *, field_name: str) -> list[str]:
    text_values: list[str] = []
    for item in _optional_policy_list(value, field_name):
        if not isinstance(item, str):
            raise ValueError(f"news_item_agent_policy_{field_name}_required")
        text = _text(item)
        if text:
            text_values.append(text)
    return text_values


def _text(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


__all__ = [
    "news_item_agent_brief_priority",
]
