from __future__ import annotations

import pytest

from parallax.domains.token_intel.services.atomic_mention import (
    KOL_TIER_TAGS,
    LOW_TIER_TAGS,
    MID_TIER_TAGS,
    mention_confidence_from_status,
    tweet_quality,
)


def test_tweet_quality_uses_material_event_author_facts() -> None:
    kol_score = tweet_quality(author_followers=20_000, author_tags=("kol",))
    public_score = tweet_quality(author_followers=20_000, author_tags=())

    assert kol_score == pytest.approx(0.86, abs=0.01)
    assert kol_score > public_score > 0.0


def test_tweet_quality_bounds_missing_and_max_followers() -> None:
    assert tweet_quality(author_followers=None, author_tags=("kol",)) == pytest.approx(0.0602, abs=0.001)
    assert tweet_quality(author_followers=100_000, author_tags=("kol",)) == pytest.approx(1.0)


def test_tweet_quality_handles_none_tags() -> None:
    score = tweet_quality(author_followers=10_000, author_tags=None)

    assert 0.0 < score < 0.5


def test_mention_confidence_maps_status_correctly() -> None:
    assert mention_confidence_from_status("EXACT") == 1.0
    assert mention_confidence_from_status("UNIQUE_BY_CONTEXT") == 0.85
    assert mention_confidence_from_status("AMBIGUOUS") == 0.0
    assert mention_confidence_from_status(None) == 0.0


def test_kol_mid_low_tier_constants_exhaust_known_tags() -> None:
    known = {
        "kol",
        "founder",
        "master",
        "exchange",
        "binance_square",
        "celebrity",
        "politics",
        "media",
        "companies",
        "trader",
        "other",
    }
    assert known == KOL_TIER_TAGS | MID_TIER_TAGS | LOW_TIER_TAGS
    assert set() == KOL_TIER_TAGS & MID_TIER_TAGS
    assert set() == MID_TIER_TAGS & LOW_TIER_TAGS
    assert set() == KOL_TIER_TAGS & LOW_TIER_TAGS
