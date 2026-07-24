from __future__ import annotations

from dataclasses import dataclass
from typing import Any

NEWS_STORY_IDENTITY_VERSION = "news_story_identity_v2"


@dataclass(frozen=True, slots=True)
class NewsStoryIdentity:
    story_key: str
    confidence: str
    basis: dict[str, Any]
    version: str


__all__ = ["NEWS_STORY_IDENTITY_VERSION", "NewsStoryIdentity"]
