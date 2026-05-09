"""Per-mention atomic signal helpers (pure functions, no I/O)."""

from __future__ import annotations

import math
from collections.abc import Iterable

KOL_TIER_TAGS: frozenset[str] = frozenset({"kol", "founder", "master"})
MID_TIER_TAGS: frozenset[str] = frozenset({
    "exchange", "binance_square", "celebrity", "politics", "media", "companies"
})
LOW_TIER_TAGS: frozenset[str] = frozenset({"trader", "other"})

_KOL_WEIGHT = 1.0
_MID_WEIGHT = 0.85
_LOW_WEIGHT = 0.7
_NO_TAG_WEIGHT = 0.5

_FOLLOWERS_NORMALIZER = math.log1p(100_000.0)
_AGE_SATURATION_MS = 180 * 24 * 60 * 60_000

_RESOLUTION_CONFIDENCE = {
    "EXACT": 1.0,
    "UNIQUE_BY_CONTEXT": 0.85,
}


def tweet_quality(
    *,
    gmgn_platform_followers: int | None,
    ws_author_followers: int | None,
    user_tags: Iterable[str],
    first_seen_age_ms: int,
) -> float:
    followers = _select_followers(gmgn_platform_followers, ws_author_followers)
    follower_component = math.log1p(max(0, followers)) / _FOLLOWERS_NORMALIZER
    tag_component = _tag_weight(user_tags)
    age_component = min(1.0, max(0, first_seen_age_ms) / _AGE_SATURATION_MS)
    return max(0.0, min(1.0, follower_component * tag_component * age_component))


def mention_confidence_from_status(status: str | None) -> float:
    if status is None:
        return 0.0
    return _RESOLUTION_CONFIDENCE.get(status, 0.0)


def _select_followers(gmgn: int | None, ws: int | None) -> int:
    if gmgn is not None and gmgn > 0:
        return int(gmgn)
    if ws is not None and ws > 0:
        return int(ws)
    return 0


def _tag_weight(tags: Iterable[str]) -> float:
    normalized = {tag.lower() for tag in tags if tag}
    if not normalized:
        return _NO_TAG_WEIGHT
    if normalized & KOL_TIER_TAGS:
        return _KOL_WEIGHT
    if normalized & MID_TIER_TAGS:
        return _MID_WEIGHT
    if normalized & LOW_TIER_TAGS:
        return _LOW_WEIGHT
    return _NO_TAG_WEIGHT
