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

    source = _json_object(row.get("source_json") or row.get("source"))
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
    for source_id in _json_list(row.get("source_ids_json") or row.get("source_ids")):
        add(source_id)
    for source_domain in _json_list(row.get("source_domains_json") or row.get("source_domains")):
        add(source_domain)

    for lane_value in _json_list(row.get("token_lanes_json") or row.get("token_lanes")):
        lane = _json_object(lane_value)
        for field in ("symbol", "target_id", "resolution_status", "target_type", "display_name"):
            add(lane.get(field))

    for fact_value in _json_list(row.get("fact_lanes_json") or row.get("fact_lanes")):
        fact = _json_object(fact_value)
        for field in ("event_type", "status", "claim", "realis"):
            add(fact.get(field))

    return " ".join(terms)


def _json_object(value: Any) -> dict[str, Any]:
    value = getattr(value, "obj", value)
    if value is None or not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items() if item is not None}


def _json_list(value: Any) -> list[Any]:
    value = getattr(value, "obj", value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return list(value)
    return []


__all__ = ["build_news_page_search_text"]
