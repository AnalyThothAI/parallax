from __future__ import annotations

import time
from datetime import datetime

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
