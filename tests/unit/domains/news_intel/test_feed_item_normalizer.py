from __future__ import annotations

import time
from datetime import datetime

import pytest

from parallax.domains.news_intel.services.feed_item_normalizer import normalize_feed_entry


def test_normalize_feed_entry_uses_feed_identity_and_cleans_text() -> None:
    published = time.struct_time((2026, 5, 19, 2, 30, 0, 1, 139, 0))
    entry = {
        "id": "guid-123",
        "link": "HTTPS://CoinDesk.COM/markets/sol/?utm_source=rss&b=2&a=1",
        "title": "<b>SOL ETF</b> filing approved",
        "summary": "<p>Issuer confirms launch. Read more</p>",
        "content": [{"value": "<div>Full body https://example.com tracking</div>"}],
        "published_parsed": published,
        "language": "EN",
    }

    item = normalize_feed_entry("coindesk.com", entry, fetched_at_ms=1_779_000_000_000)

    assert item is not None
    assert item.source_item_key == "guid-123"
    assert item.canonical_url == "https://coindesk.com/markets/sol?a=1&b=2"
    assert item.title == "SOL ETF filing approved"
    assert item.summary == "Issuer confirms launch."
    assert item.body_text == "Full body tracking"
    assert item.language == "en"
    assert item.published_at_ms == 1_779_157_800_000
    assert item.raw_payload["source_domain"] == "coindesk.com"


def test_normalize_feed_entry_falls_back_to_updated_time_and_link_key() -> None:
    updated = time.struct_time((2026, 5, 19, 3, 0, 0, 1, 139, 0))
    entry = {
        "guid": "",
        "link": "https://example.com/a",
        "title": "Exchange listing",
        "updated_parsed": updated,
    }

    item = normalize_feed_entry("example.com", entry, fetched_at_ms=1_779_000_000_000)

    assert item is not None
    assert item.source_item_key == "https://example.com/a"
    assert item.published_at_ms == 1_779_159_600_000


def test_normalize_feed_entry_uses_provider_epoch_milliseconds_when_present() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "id": "opennews-1",
            "link": "https://example.com/opennews-1",
            "title": "BTC liquidation alert",
            "published_at_ms": 1_779_000_000_000,
        },
        fetched_at_ms=1_779_000_060_000,
    )

    assert item is not None
    assert item.published_at_ms == 1_779_000_000_000


def test_normalize_feed_entry_prefers_explicit_source_item_key_over_provider_id() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "id": "2367422",
            "source_item_key": "source-key-2367422",
            "link": "https://example.com/opennews-2367422",
            "title": "OpenNews token alert",
        },
        fetched_at_ms=1_779_000_060_000,
    )

    assert item is not None
    assert item.source_item_key == "source-key-2367422"


@pytest.mark.parametrize(
    "marker",
    (
        {"provider_article_id": "2367422"},
        {"provider_article_key": "opennews:2367422"},
        {"opennews_method": "websocket"},
    ),
)
def test_normalize_feed_entry_preserves_opennews_fallback_url_with_opennews_marker(
    marker: dict[str, str],
) -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            **marker,
            "link": "opennews://item/2367422",
            "title": "OpenNews fallback token alert",
        },
        fetched_at_ms=1_779_000_060_000,
    )

    assert item is not None
    assert item.canonical_url == "opennews://item/2367422"
    assert item.title == "OpenNews fallback token alert"


def test_normalize_feed_entry_rejects_generic_opennews_fallback_url_with_only_rss_id() -> None:
    item = normalize_feed_entry(
        "example.com",
        {
            "id": "rss-guid-2367422",
            "guid": "rss-guid-2367422",
            "link": "opennews://item/2367422",
            "title": "Generic RSS item should not use OpenNews fallback",
        },
        fetched_at_ms=1_779_000_060_000,
    )

    assert item is None


def test_normalize_feed_entry_rejects_opennews_fallback_url_when_provider_id_mismatches_path() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "provider_article_id": "2367422",
            "link": "opennews://item/2367423",
            "title": "OpenNews fallback mismatch",
        },
        fetched_at_ms=1_779_000_060_000,
    )

    assert item is None


def test_normalize_feed_entry_rejects_opennews_fallback_url_when_provider_key_mismatches_path() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "provider_article_key": "opennews:2367422",
            "link": "opennews://item/2367423",
            "title": "OpenNews fallback key mismatch",
        },
        fetched_at_ms=1_779_000_060_000,
    )

    assert item is None


def test_normalize_feed_entry_rejects_opennews_fallback_url_with_whitespace_item_id() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "provider_article_id": "2367422",
            "link": "opennews://item/2367 422",
            "title": "OpenNews fallback whitespace path",
        },
        fetched_at_ms=1_779_000_060_000,
    )

    assert item is None


def test_opennews_homepage_link_uses_provider_fallback_url() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "provider_article_id": "2514613",
            "provider_article_key": "opennews:2514613",
            "opennews_method": "news.rest",
            "link": "https://tass.ru/",
            "title": "TASS: FOUR TU-214 AIRCRAFT ARE PLANNED TO BE DELIVERED IN 2026",
            "published_at_ms": 1_780_542_000_000,
        },
        fetched_at_ms=1_780_542_000_000,
    )

    assert item is not None
    assert item.canonical_url == "opennews://item/2514613"
    assert item.raw_payload["link"] == "https://tass.ru/"


def test_opennews_article_link_keeps_public_url() -> None:
    url = "https://financefeeds.com/bessent-urges-lawmakers-to-pass-crypto-clarity-act-this-summer"
    item = normalize_feed_entry(
        "6551.io",
        {
            "provider_article_id": "2511056",
            "provider_article_key": "opennews:2511056",
            "opennews_method": "news.rest",
            "link": url,
            "title": "Bessent Urges Lawmakers to Pass Crypto Clarity Act This Summer",
        },
        fetched_at_ms=1_780_542_000_000,
    )

    assert item is not None
    assert item.canonical_url == url


def test_opennews_blocked_public_link_can_fallback_from_provider_key_without_raw_opennews_url() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "provider_article_key": "opennews:2514614",
            "opennews_method": "news.rest",
            "link": "https://www.coindesk.com/markets",
            "title": "COINDESK: Market board refresh",
        },
        fetched_at_ms=1_780_542_000_000,
    )

    assert item is not None
    assert item.canonical_url == "opennews://item/2514614"


def test_blocked_public_link_with_provider_article_id_only_does_not_create_opennews_fallback() -> None:
    item = normalize_feed_entry(
        "example.com",
        {
            "provider_article_id": "rss-local-1",
            "link": "https://www.coindesk.com/markets",
            "title": "Generic feed market index item",
        },
        fetched_at_ms=1_780_542_000_000,
    )

    assert item is None


def test_normalize_feed_entry_uses_provider_iso_timestamp_when_present() -> None:
    item = normalize_feed_entry(
        "6551.io",
        {
            "id": "opennews-1",
            "link": "https://example.com/opennews-1",
            "title": "OpenNews token alert",
            "ts": "2026-05-26T19:18:48.871+08:00",
        },
        fetched_at_ms=1_779_000_060_000,
    )

    assert item is not None
    assert item.published_at_ms == int(datetime.fromisoformat("2026-05-26T19:18:48.871+08:00").timestamp() * 1000)


def test_normalize_feed_entry_rejects_entries_without_title_or_url() -> None:
    assert normalize_feed_entry("example.com", {"title": "No URL"}, fetched_at_ms=1) is None
    assert normalize_feed_entry("example.com", {"link": "https://example.com/a"}, fetched_at_ms=1) is None


def test_normalize_feed_entry_rejects_invalid_url_without_raising() -> None:
    item = normalize_feed_entry(
        "example.com",
        {
            "link": "www.example.com/story",
            "title": "Malformed URL should not fail the run",
        },
        fetched_at_ms=1,
    )

    assert item is None


def test_normalize_feed_entry_rejects_whitespace_malformed_url_without_raising() -> None:
    item = normalize_feed_entry(
        "example.com",
        {
            "link": "https://exa mple.com/news",
            "title": "Whitespace malformed URL should not fail the run",
        },
        fetched_at_ms=1,
    )

    assert item is None
