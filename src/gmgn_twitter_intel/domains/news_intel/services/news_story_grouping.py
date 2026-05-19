from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_STORY_POLICY_VERSION

_FUZZY_TITLE_THRESHOLD = 0.72
_FUZZY_TIME_WINDOW_MS = 6 * 60 * 60 * 1000
_TOKEN_RE = re.compile(r"[a-z0-9]+")


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
        candidate_canonical_url = _optional_text(candidate.get("canonical_url"))
        if item_canonical_url and item_canonical_url == candidate_canonical_url:
            return StoryAssignment(str(candidate["story_id"]), "same_story", "same_canonical_url", 1.0)

        candidate_content_hash = _optional_text(candidate.get("content_hash"))
        if item_content_hash and item_content_hash == candidate_content_hash:
            return StoryAssignment(str(candidate["story_id"]), "same_story", "same_content_hash", 1.0)

    best: StoryAssignment | None = None
    for candidate in candidates:
        score = _lexical_score(_title_text(item), _title_text(candidate))
        if score < _FUZZY_TITLE_THRESHOLD:
            continue
        if not _has_token_overlap(item, candidate):
            continue
        if not _is_time_close(item, candidate):
            continue

        assignment = StoryAssignment(
            str(candidate["story_id"]),
            "same_story",
            "title_token_time_overlap",
            score,
        )
        if best is None or assignment.match_score > best.match_score:
            best = assignment

    if best is not None:
        return best
    return StoryAssignment(None, "representative", "new_story", 0.0)


def new_story_id(*, news_item_id: str) -> str:
    seed = f"news-story|{NEWS_STORY_POLICY_VERSION}|{news_item_id}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _title_text(row: dict[str, Any]) -> str:
    return str(row.get("title_fingerprint") or row.get("representative_title") or row.get("title") or "")


def _lexical_score(left: str, right: str) -> float:
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / float(min(len(left_tokens), len(right_tokens)))


def _title_tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.casefold()))


def _has_token_overlap(item: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return bool(_token_targets(item) & _token_targets(candidate))


def _token_targets(row: dict[str, Any]) -> set[str]:
    return {_optional_text(value) for value in row.get("token_targets") or [] if _optional_text(value)}


def _is_time_close(item: dict[str, Any], candidate: dict[str, Any]) -> bool:
    item_time = _optional_int(item.get("published_at_ms") or item.get("fetched_at_ms"))
    candidate_time = _optional_int(candidate.get("latest_seen_at_ms") or candidate.get("published_at_ms"))
    if item_time is None or candidate_time is None:
        return False
    return abs(item_time - candidate_time) <= _FUZZY_TIME_WINDOW_MS


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
