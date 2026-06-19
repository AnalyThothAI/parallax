from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from parallax.domains.news_intel._constants import NEWS_ITEM_AGENT_ADMISSION_VERSION

NewsItemAgentAdmissionStatus = Literal[
    "eligible",
    "eligible_refresh",
    "exact_duplicate",
    "similar_story_covered",
    "similar_story_burst",
    "materially_superseded",
    "source_suppressed",
    "operational_disabled",
    "needs_review",
]


@dataclass(frozen=True, slots=True)
class NewsItemAgentAdmissionContext:
    exact_duplicate_candidates: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    story_candidates: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    material_delta: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> NewsItemAgentAdmissionContext:
        return cls()

    @classmethod
    def from_repository_context(cls, context: Mapping[str, Any]) -> NewsItemAgentAdmissionContext:
        return cls(
            exact_duplicate_candidates=_optional_context_mapping_list(context, "exact_duplicate_candidates"),
            story_candidates=_optional_context_mapping_list(context, "story_candidates"),
            material_delta=_optional_context_mapping(context, "material_delta"),
        )


@dataclass(frozen=True, slots=True)
class NewsItemAgentAdmission:
    eligible: bool
    status: NewsItemAgentAdmissionStatus
    reason: str
    representative_news_item_id: str
    basis: dict[str, Any]
    version: str = NEWS_ITEM_AGENT_ADMISSION_VERSION


__all__ = [
    "NewsItemAgentAdmission",
    "NewsItemAgentAdmissionContext",
    "NewsItemAgentAdmissionStatus",
]


def _optional_context_mapping_list(context: Mapping[str, Any], field_name: str) -> list[Mapping[str, Any]]:
    if field_name not in context:
        return []
    value = context[field_name]
    if not isinstance(value, list):
        _raise_context_value_error(field_name)
    rows: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            _raise_context_value_error(field_name)
        rows.append(dict(item))
    return rows


def _optional_context_mapping(context: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    if field_name not in context:
        return {}
    value = context[field_name]
    if not isinstance(value, Mapping):
        _raise_context_value_error(field_name)
    return dict(value)


def _raise_context_value_error(field_name: str) -> None:
    raise ValueError(f"news_item_agent_admission_context_{field_name}_required")
