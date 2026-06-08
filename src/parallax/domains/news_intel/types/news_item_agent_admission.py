from __future__ import annotations

from collections.abc import Mapping
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
    "score_below_threshold",
    "source_suppressed",
    "operational_disabled",
    "needs_review",
]


@dataclass(frozen=True, slots=True)
class NewsItemAgentAdmissionContext:
    exact_duplicate: Mapping[str, Any] = field(default_factory=dict)
    similar_story: Mapping[str, Any] = field(default_factory=dict)
    material_delta: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> NewsItemAgentAdmissionContext:
        return cls()


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
