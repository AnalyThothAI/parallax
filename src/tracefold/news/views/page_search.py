from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_news_page_search_text(row: Mapping[str, Any]) -> str:
    terms: list[str] = []

    def add(value: Any) -> None:
        if value is None:
            return
        text = " ".join(str(value).split())
        if text:
            terms.append(text)

    add(row.get("headline"))
    add(row.get("summary"))
    add(row.get("source_domain"))

    source = _optional_json_object(row, "source_json")
    for field in (
        "source_domain",
        "provider_type",
        "source_id",
        "source_name",
        "source_role",
        "trust_tier",
        "source_quality_status",
    ):
        add(source.get(field))
    for source_id in _optional_json_list(row, "source_ids_json"):
        add(source_id)
    for source_domain in _optional_json_list(row, "source_domains_json"):
        add(source_domain)

    for lane_value in _optional_json_list(row, "token_lanes_json"):
        lane = _required_json_mapping(lane_value, field_name="token_lanes_json")
        for field in ("symbol", "target_id", "resolution_status", "target_type", "display_name"):
            add(lane.get(field))

    for fact_value in _optional_json_list(row, "fact_lanes_json"):
        fact = _required_json_mapping(fact_value, field_name="fact_lanes_json")
        for field in ("event_type", "status", "claim", "realis"):
            add(fact.get(field))

    return " ".join(terms)


def _optional_json_object(row: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in row:
        return {}
    return _required_json_mapping(row[field_name], field_name=field_name)


def _required_json_mapping(value: Any, *, field_name: str) -> dict[str, Any]:
    value = _json_value(value)
    if not isinstance(value, Mapping):
        raise ValueError(f"news_page_search_{field_name}_required")
    return _compact_mapping(dict(value))


def _compact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if item is not None}


def _optional_json_list(row: Mapping[str, Any], field_name: str) -> list[Any]:
    if field_name not in row:
        return []
    value = _json_value(row[field_name])
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    raise ValueError(f"news_page_search_{field_name}_required")


def _json_value(value: Any) -> Any:
    return getattr(value, "obj", value)


__all__ = ["build_news_page_search_text"]
