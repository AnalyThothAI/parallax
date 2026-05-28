from __future__ import annotations

import hashlib
from importlib import import_module
from typing import Any

import pytest


def _service() -> Any:
    try:
        return import_module("gmgn_twitter_intel.domains.news_intel.services.news_canonical_identity")
    except ModuleNotFoundError as exc:
        pytest.fail(f"news_canonical_identity service is required: {exc}")


def test_content_hash_wins_over_opennews_id_and_url() -> None:
    service = _service()

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="2367422",
        canonical_url="https://www.binance.com/en/support/announcement/binance-will-list-example-abc123",
        content_hash="hash-abc",
        title_fingerprint="binance will list example",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == "content-hash:hash-abc"
    assert identity.news_item_id == service.stable_news_item_id("content-hash:hash-abc")
    assert identity.dedup_key_kind == "content_hash"
    assert identity.dedup_key_confidence == "strong"
    assert identity.match_type == "same_content_hash"
    assert identity.match_confidence == "strong"
    assert identity.evidence["provider_article_key"] == "opennews:2367422"


def test_container_url_does_not_win_over_content_hash() -> None:
    service = _service()

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="",
        canonical_url="https://tass.ru/",
        content_hash="hash-same-content",
        title_fingerprint="market update",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == "content-hash:hash-same-content"
    assert identity.url_identity_kind == "homepage"
    assert identity.dedup_key_kind == "content_hash"
    assert identity.dedup_key_confidence == "strong"
    assert identity.match_type == "same_content_hash"


def test_article_url_wins_when_provider_id_and_content_hash_missing() -> None:
    service = _service()
    canonical_url = "https://www.binance.com/en/support/announcement/binance-will-list-example-abc123"

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="",
        canonical_url=canonical_url,
        content_hash="",
        title_fingerprint="binance will list example",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == f"article-url:{canonical_url}"
    assert identity.url_identity_kind == "article"
    assert identity.dedup_key_kind == "article_url"
    assert identity.dedup_key_confidence == "strong"
    assert identity.match_type == "same_article_url"


def test_stable_news_item_id_is_order_independent() -> None:
    service = _service()
    kwargs = {
        "provider_type": "opennews",
        "source_id": "opennews-news",
        "provider_article_id": "",
        "canonical_url": "https://www.binance.com/en/support/announcement/binance-will-list-example-abc123",
        "content_hash": "hash-abc",
        "title_fingerprint": "binance will list example",
        "published_at_ms": 1_714_004_321_000,
    }

    first = service.canonical_identity_for_observation(**kwargs)
    second = service.canonical_identity_for_observation(**dict(reversed(tuple(kwargs.items()))))
    expected = "news-item-" + hashlib.sha256(first.canonical_item_key.encode("utf-8")).hexdigest()[:32]

    assert first.news_item_id == second.news_item_id == expected


def test_weak_fallback_includes_source_and_published_hour() -> None:
    service = _service()
    published_at_ms = 1_714_004_321_000
    published_hour_ms = published_at_ms - (published_at_ms % 3_600_000)

    identity = service.canonical_identity_for_observation(
        provider_type="rss",
        source_id="rss-cointelegraph",
        provider_article_id="",
        canonical_url="",
        content_hash="",
        title_fingerprint="bitcoin etf flow update",
        published_at_ms=published_at_ms,
    )

    assert identity.canonical_item_key == (
        f"weak-title-source-window:rss-cointelegraph:{published_hour_ms}:bitcoin etf flow update"
    )
    assert identity.dedup_key_kind == "weak_title_time_source"
    assert identity.dedup_key_confidence == "weak"
    assert identity.match_type == "weak_title_time_source"
    assert identity.match_confidence == "weak"
    assert identity.evidence["source_id"] == "rss-cointelegraph"
    assert identity.evidence["published_hour_ms"] == published_hour_ms
