from __future__ import annotations

import pytest

from gmgn_twitter_intel.pipeline.atomic_mention import (
    KOL_TIER_TAGS,
    LOW_TIER_TAGS,
    MID_TIER_TAGS,
    mention_confidence_from_status,
    tweet_quality,
)


def test_tweet_quality_uses_gmgn_followers_when_present():
    score = tweet_quality(
        gmgn_platform_followers=20000,
        ws_author_followers=99999,
        user_tags=("kol",),
        first_seen_age_ms=365 * 24 * 60 * 60_000,
    )
    assert 0.5 < score <= 1.0


def test_tweet_quality_falls_back_to_ws_followers_when_gmgn_missing():
    score_with_gmgn = tweet_quality(
        gmgn_platform_followers=10000,
        ws_author_followers=10000,
        user_tags=("kol",),
        first_seen_age_ms=365 * 24 * 60 * 60_000,
    )
    score_with_ws_only = tweet_quality(
        gmgn_platform_followers=None,
        ws_author_followers=10000,
        user_tags=("kol",),
        first_seen_age_ms=365 * 24 * 60 * 60_000,
    )
    assert abs(score_with_gmgn - score_with_ws_only) < 1e-9


def test_tweet_quality_minimum_when_all_inputs_missing():
    score = tweet_quality(
        gmgn_platform_followers=None,
        ws_author_followers=None,
        user_tags=(),
        first_seen_age_ms=0,
    )
    assert 0.0 <= score < 0.05


def test_tweet_quality_kol_tier_outweighs_other_tier():
    kol_score = tweet_quality(
        gmgn_platform_followers=5000,
        ws_author_followers=None,
        user_tags=("kol",),
        first_seen_age_ms=365 * 86_400_000,
    )
    other_score = tweet_quality(
        gmgn_platform_followers=5000,
        ws_author_followers=None,
        user_tags=("other",),
        first_seen_age_ms=365 * 86_400_000,
    )
    assert kol_score > other_score


def test_tweet_quality_age_score_saturates_at_180_days():
    young = tweet_quality(
        gmgn_platform_followers=5000,
        ws_author_followers=None,
        user_tags=("kol",),
        first_seen_age_ms=30 * 86_400_000,
    )
    mature = tweet_quality(
        gmgn_platform_followers=5000,
        ws_author_followers=None,
        user_tags=("kol",),
        first_seen_age_ms=180 * 86_400_000,
    )
    very_old = tweet_quality(
        gmgn_platform_followers=5000,
        ws_author_followers=None,
        user_tags=("kol",),
        first_seen_age_ms=5 * 365 * 86_400_000,
    )
    assert young < mature
    assert mature == very_old


def test_mention_confidence_maps_status_correctly():
    assert mention_confidence_from_status("EXACT") == 1.0
    assert mention_confidence_from_status("UNIQUE_BY_CONTEXT") == 0.85
    assert mention_confidence_from_status("AMBIGUOUS") == 0.0
    assert mention_confidence_from_status(None) == 0.0
    assert mention_confidence_from_status("UNKNOWN_STATUS") == 0.0


def test_kol_mid_low_tier_constants_exhaust_known_tags():
    known = {
        "kol", "founder", "master", "exchange", "binance_square",
        "celebrity", "politics", "media", "companies", "trader", "other",
    }
    assert known == KOL_TIER_TAGS | MID_TIER_TAGS | LOW_TIER_TAGS
    assert set() == KOL_TIER_TAGS & MID_TIER_TAGS
    assert set() == MID_TIER_TAGS & LOW_TIER_TAGS
    assert set() == KOL_TIER_TAGS & LOW_TIER_TAGS


def test_tweet_quality_max_input_yields_exactly_one():
    score = tweet_quality(
        gmgn_platform_followers=100_000,
        ws_author_followers=None,
        user_tags=("kol",),
        first_seen_age_ms=180 * 86_400_000,
    )
    assert score == pytest.approx(1.0)


def test_tweet_quality_returns_floor_signal_when_followers_missing():
    score = tweet_quality(
        gmgn_platform_followers=None,
        ws_author_followers=None,
        user_tags=("kol",),
        first_seen_age_ms=180 * 86_400_000,
    )
    # log1p(1) / log1p(100000) ≈ 0.0602; tag=1.0; age=1.0
    assert score == pytest.approx(0.0602, abs=0.001)


def test_tweet_quality_handles_none_user_tags():
    score = tweet_quality(
        gmgn_platform_followers=10000,
        ws_author_followers=None,
        user_tags=None,
        first_seen_age_ms=180 * 86_400_000,
    )
    # tag_weight = _NO_TAG_WEIGHT = 0.5
    assert 0.0 < score < 0.5
