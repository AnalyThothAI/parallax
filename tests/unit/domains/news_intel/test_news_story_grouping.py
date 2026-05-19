from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_STORY_POLICY_VERSION
from gmgn_twitter_intel.domains.news_intel.services.news_story_grouping import (
    choose_story_assignment,
    new_story_id,
)


def test_story_grouping_accepts_same_canonical_url() -> None:
    assignment = choose_story_assignment(
        item={
            "news_item_id": "n2",
            "canonical_url": "https://example.test/a",
            "content_hash": "h2",
            "title_fingerprint": "bitcoin etf inflow update",
            "published_at_ms": 1000,
            "token_targets": ["CexToken:BTC"],
        },
        candidates=[
            {
                "story_id": "s1",
                "canonical_url": "https://example.test/a",
                "content_hash": "h1",
                "representative_title": "Bitcoin ETF inflow",
                "latest_seen_at_ms": 900,
                "token_targets": ["CexToken:BTC"],
            }
        ],
    )

    assert assignment.story_id == "s1"
    assert assignment.relation == "same_story"
    assert assignment.match_reason == "same_canonical_url"
    assert assignment.match_score == 1.0


def test_story_grouping_accepts_same_content_hash() -> None:
    assignment = choose_story_assignment(
        item={
            "news_item_id": "n2",
            "canonical_url": "https://mirror.test/a",
            "content_hash": "same-body",
            "title_fingerprint": "bitcoin etf inflow update",
            "published_at_ms": 1000,
            "token_targets": ["CexToken:BTC"],
        },
        candidates=[
            {
                "story_id": "s1",
                "canonical_url": "https://example.test/a",
                "content_hash": "same-body",
                "representative_title": "Different syndication title",
                "latest_seen_at_ms": 900,
                "token_targets": [],
            }
        ],
    )

    assert assignment.story_id == "s1"
    assert assignment.match_reason == "same_content_hash"


def test_story_grouping_rejects_title_only_similarity_without_token_overlap() -> None:
    assignment = choose_story_assignment(
        item={
            "news_item_id": "n2",
            "canonical_url": "https://example.test/b",
            "content_hash": "h2",
            "title_fingerprint": "coinbase lists new token",
            "published_at_ms": 1000,
            "token_targets": ["symbol:NEWX"],
        },
        candidates=[
            {
                "story_id": "s1",
                "canonical_url": "https://example.test/a",
                "content_hash": "h1",
                "representative_title": "Coinbase lists old token",
                "latest_seen_at_ms": 900,
                "token_targets": ["symbol:OLDX"],
            }
        ],
    )

    assert assignment.story_id is None
    assert assignment.relation == "representative"
    assert assignment.match_reason == "new_story"


def test_story_grouping_rejects_fuzzy_match_outside_time_window() -> None:
    seven_hours_ms = 7 * 60 * 60 * 1000
    assignment = choose_story_assignment(
        item={
            "news_item_id": "n2",
            "canonical_url": "https://example.test/b",
            "content_hash": "h2",
            "title_fingerprint": "bitcoin etf inflow update",
            "published_at_ms": seven_hours_ms,
            "token_targets": ["CexToken:BTC"],
        },
        candidates=[
            {
                "story_id": "s1",
                "canonical_url": "https://example.test/a",
                "content_hash": "h1",
                "representative_title": "Bitcoin ETF inflow update",
                "latest_seen_at_ms": 0,
                "token_targets": ["CexToken:BTC"],
            }
        ],
    )

    assert assignment.story_id is None
    assert assignment.match_reason == "new_story"


def test_story_grouping_accepts_fuzzy_match_with_token_overlap_and_time_proximity() -> None:
    assignment = choose_story_assignment(
        item={
            "news_item_id": "n2",
            "canonical_url": "https://example.test/b",
            "content_hash": "h2",
            "title_fingerprint": "bitcoin etf inflow update",
            "published_at_ms": 1_000,
            "token_targets": ["CexToken:BTC"],
        },
        candidates=[
            {
                "story_id": "s1",
                "canonical_url": "https://example.test/a",
                "content_hash": "h1",
                "representative_title": "Bitcoin ETF inflow update",
                "latest_seen_at_ms": 900,
                "token_targets": ["CexToken:BTC"],
            }
        ],
    )

    assert assignment.story_id == "s1"
    assert assignment.match_reason == "title_token_time_overlap"
    assert assignment.match_score >= 0.72


def test_new_story_id_is_policy_scoped_and_stable() -> None:
    assert new_story_id(news_item_id="n1") == new_story_id(news_item_id="n1")
    assert new_story_id(news_item_id="n1") != new_story_id(news_item_id="n2")
    assert NEWS_STORY_POLICY_VERSION in "news_story_grouping_v1"
