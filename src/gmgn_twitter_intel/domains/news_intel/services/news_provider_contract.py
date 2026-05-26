from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


class NewsProviderContractError(ValueError):
    def __init__(
        self,
        reason: str,
        *,
        provider_types: Iterable[str],
        configured_provider_types: Iterable[str],
        supported_provider_types: Iterable[str],
        schema_provider_types: Iterable[str],
    ) -> None:
        self.reason = str(reason)
        self.provider_types = _normalized_unique(provider_types)
        self.configured_provider_types = _normalized_unique(configured_provider_types)
        self.supported_provider_types = _normalized_unique(supported_provider_types)
        self.schema_provider_types = _normalized_unique(schema_provider_types)
        super().__init__(self.reason)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "reason": self.reason,
            "provider_types": list(self.provider_types),
            "configured_provider_types": list(self.configured_provider_types),
            "supported_provider_types": list(self.supported_provider_types),
            "schema_provider_types": list(self.schema_provider_types),
        }


def validate_news_provider_contract(
    *,
    configured_sources: Iterable[Any],
    supported_provider_types: Iterable[str],
    schema_provider_types: Iterable[str],
) -> dict[str, Any]:
    configured = _configured_provider_types(configured_sources)
    supported = _normalized_unique(supported_provider_types)
    schema = _normalized_unique(schema_provider_types)

    missing_from_registry = tuple(provider_type for provider_type in configured if provider_type not in supported)
    if missing_from_registry:
        raise NewsProviderContractError(
            "news_provider_type_missing_from_registry",
            provider_types=missing_from_registry,
            configured_provider_types=configured,
            supported_provider_types=supported,
            schema_provider_types=schema,
        )

    missing_from_schema = tuple(provider_type for provider_type in configured if provider_type not in schema)
    if missing_from_schema:
        raise NewsProviderContractError(
            "news_provider_type_missing_from_db_constraint",
            provider_types=missing_from_schema,
            configured_provider_types=configured,
            supported_provider_types=supported,
            schema_provider_types=schema,
        )

    return {
        "ok": True,
        "configured_provider_types": list(configured),
        "supported_provider_types": list(supported),
        "schema_provider_types": list(schema),
    }


def _configured_provider_types(configured_sources: Iterable[Any]) -> tuple[str, ...]:
    values: list[str] = []
    for source in configured_sources:
        value = source.get("provider_type") if isinstance(source, Mapping) else getattr(source, "provider_type", None)
        provider_type = str(value or "").strip()
        if provider_type:
            values.append(provider_type)
    return tuple(sorted(dict.fromkeys(values)))


def _normalized_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(str(value or "").strip() for value in values if str(value or "").strip())))


__all__ = ["NewsProviderContractError", "validate_news_provider_contract"]
