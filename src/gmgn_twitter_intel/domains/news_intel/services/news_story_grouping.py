from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_STORY_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class StoryAssignment:
    story_id: str | None
    relation: str
    match_reason: str
    match_score: float


def choose_story_assignment(*, item: dict[str, Any], candidates: list[dict[str, Any]]) -> StoryAssignment:
    item_canonical_url = _optional_text(item.get("canonical_url"))
    item_content_hash = _optional_text(item.get("content_hash"))

    for candidate in candidates:
        candidate_content_hash = _optional_text(candidate.get("content_hash"))
        if item_content_hash and item_content_hash == candidate_content_hash:
            return StoryAssignment(str(candidate["story_id"]), "same_story", "same_content_hash", 1.0)

        candidate_canonical_url = _optional_text(candidate.get("canonical_url"))
        if (
            item_canonical_url
            and item_canonical_url == candidate_canonical_url
            and _is_article_url_identity(item)
            and _is_article_url_identity(candidate)
        ):
            return StoryAssignment(str(candidate["story_id"]), "same_story", "same_canonical_url", 1.0)

    return StoryAssignment(None, "representative", "new_story", 0.0)


def story_key_for_item(item: dict[str, Any]) -> str:
    content_hash = _optional_text(item.get("content_hash"))
    if content_hash:
        return f"content-hash:{content_hash}"

    canonical_url = _optional_text(item.get("canonical_url"))
    if canonical_url and _is_article_url_identity(item):
        return f"article-url:{canonical_url}"

    canonical_item_key = _optional_text(item.get("canonical_item_key"))
    if canonical_item_key:
        return f"canonical-item:{canonical_item_key}"

    return f"news-item:{_optional_text(item.get('news_item_id')) or ''}"


def new_story_id(*, story_key: str) -> str:
    seed = f"news-story|{NEWS_STORY_POLICY_VERSION}|{_optional_text(story_key) or ''}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _is_article_url_identity(row: dict[str, Any]) -> bool:
    return _optional_text(row.get("url_identity_kind")) == "article"
