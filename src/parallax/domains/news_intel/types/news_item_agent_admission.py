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
            exact_duplicate_candidates=_list_of_mappings(context.get("exact_duplicate_candidates")),
            story_candidates=_list_of_mappings(context.get("story_candidates")),
            material_delta=_optional_mapping(context.get("material_delta")) or {},
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


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None
