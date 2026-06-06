from __future__ import annotations

from parallax.domains.news_intel.services.news_story_similarity import decide_news_story_similarity


def test_same_opennews_article_id_is_exact_duplicate() -> None:
    evidence = decide_news_story_similarity(
        item={
            "news_item_id": "news-new",
            "provider_article_keys_json": ["opennews:123"],
            "published_at_ms": 2_000,
        },
        exact_duplicate_candidates=[
            {"news_item_id": "news-rep", "provider_article_keys": ["opennews:123"], "published_at_ms": 1_000}
        ],
        story_candidates=[],
    )

    assert evidence.exact_duplicate is True
    assert evidence.reason == "same_provider_article_id"
    assert evidence.representative_news_item_id == "news-rep"


def test_same_content_hash_is_exact_duplicate() -> None:
    evidence = decide_news_story_similarity(
        item={"news_item_id": "news-new", "content_hash": "sha256:same"},
        exact_duplicate_candidates=[{"news_item_id": "news-rep", "content_hash": "sha256:same"}],
        story_candidates=[],
    )

    assert evidence.exact_duplicate is True
    assert evidence.reason == "same_content_hash"


def test_homepage_url_alone_is_not_exact_duplicate() -> None:
    evidence = decide_news_story_similarity(
        item={"news_item_id": "news-new", "canonical_url": "https://example.com/", "url_identity_kind": "homepage"},
        exact_duplicate_candidates=[
            {"news_item_id": "news-rep", "canonical_url": "https://example.com/", "url_identity_kind": "homepage"}
        ],
        story_candidates=[],
    )

    assert evidence.exact_duplicate is False
    assert evidence.similar_story is False


def test_iran_hormuz_burst_with_distinct_article_ids_is_similar_story() -> None:
    evidence = decide_news_story_similarity(
        item={
            "news_item_id": "news-new",
            "story_key": "news-story:hormuz-shipping-risk:t1",
            "provider_article_keys_json": ["opennews:999"],
            "title": "Oil rises as Iran Hormuz shipping risk grows",
        },
        exact_duplicate_candidates=[
            {"news_item_id": "news-old", "provider_article_keys": ["opennews:998"], "title": "Oil rises"}
        ],
        story_candidates=[
            {
                "news_item_id": "news-rep",
                "story_key": "news-story:hormuz-shipping-risk:t1",
                "title": "Oil rises as Iran Hormuz shipping risk grows",
            }
        ],
    )

    assert evidence.exact_duplicate is False
    assert evidence.similar_story is True
    assert evidence.reason == "same_story_key"
    assert evidence.representative_news_item_id == "news-rep"
