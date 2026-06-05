from __future__ import annotations

import hashlib
from importlib import import_module
from typing import Any

import pytest

from parallax.domains.news_intel.services.text_normalization import qualified_content_hash

_HIGH_SIGNAL_TITLE = "Bitcoin ETF flows accelerate after issuer amends registration statement"
_HIGH_SIGNAL_SUMMARY = (
    "Bitcoin exchange traded fund inflows accelerated after a major issuer filed an amended registration statement "
    "and market makers reported deeper spot liquidity across Coinbase Binance Kraken and CME venues during New "
    "York trading."
)


def _service() -> Any:
    try:
        return import_module("parallax.domains.news_intel.services.news_canonical_identity")
    except ModuleNotFoundError as exc:
        pytest.fail(f"news_canonical_identity service is required: {exc}")


def test_public_canonical_url_wins_over_opennews_id_and_content_hash() -> None:
    service = _service()
    canonical_url = "https://www.binance.com/en/support/announcement/binance-will-list-example-abc123"

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="2367422",
        canonical_url=canonical_url,
        content_hash="hash-abc",
        title_fingerprint="binance will list example",
        title="Binance will list example",
        summary=_HIGH_SIGNAL_SUMMARY,
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == f"canonical-url:{canonical_url}"
    assert identity.news_item_id == service.stable_news_item_id(f"canonical-url:{canonical_url}")
    assert identity.dedup_key_kind == "canonical_url"
    assert identity.dedup_key_confidence == "strong"
    assert identity.match_type == "same_canonical_url"
    assert identity.match_confidence == "strong"
    assert identity.evidence["provider_article_key"] == "opennews:2367422"
    assert identity.evidence["content_hash"] == "hash-abc"


def test_homepage_url_uses_weak_fallback_when_content_is_unqualified() -> None:
    service = _service()
    canonical_url = "https://tass.ru/"
    published_at_ms = 1_714_004_321_000
    published_hour_ms = published_at_ms - (published_at_ms % 3_600_000)

    identity = service.canonical_identity_for_observation(
        provider_type="rss",
        source_id="tass-rss",
        provider_article_id="",
        canonical_url=canonical_url,
        content_hash="hash-same-content",
        title_fingerprint="market update",
        title="Market Update",
        summary="",
        body_text="",
        published_at_ms=published_at_ms,
    )

    assert identity.canonical_item_key == f"weak-title-source-window:tass-rss:{published_hour_ms}:market update"
    assert identity.url_identity_kind == "homepage"
    assert identity.dedup_key_kind == "weak_title_time_source"
    assert identity.dedup_key_confidence == "weak"
    assert identity.match_type == "weak_title_time_source"


def test_live_url_uses_public_url_identity_even_when_content_is_unqualified() -> None:
    service = _service()
    canonical_url = "https://www.nytimes.com/live/2026/05/28/business/crypto-market-news"
    published_at_ms = 1_714_004_321_000
    published_hour_ms = published_at_ms - (published_at_ms % 3_600_000)

    identity = service.canonical_identity_for_observation(
        provider_type="rss",
        source_id="nyt-live-rss",
        provider_article_id="",
        canonical_url=canonical_url,
        content_hash="hash-live-page",
        title_fingerprint="live updates",
        title="Live Updates",
        summary="Fresh headlines links summaries feeds index latest homepage markets " * 4,
        body_text="",
        published_at_ms=published_at_ms,
    )

    assert identity.url_identity_kind == "live_page"
    assert identity.canonical_item_key == f"weak-title-source-window:nyt-live-rss:{published_hour_ms}:live updates"
    assert identity.dedup_key_kind == "weak_title_time_source"
    assert identity.dedup_key_confidence == "weak"
    assert identity.match_type == "weak_title_time_source"


def test_single_segment_slug_uses_public_url_identity() -> None:
    service = _service()
    canonical_url = "https://financefeeds.com/bessent-urges-lawmakers-to-pass-crypto-clarity-act-this-summer"

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="2511056",
        canonical_url=canonical_url,
        content_hash="hash-financefeeds",
        title_fingerprint="bessent urges lawmakers to pass crypto clarity act this summer",
        title="Bessent Urges Lawmakers to Pass Crypto Clarity Act This Summer",
        summary="",
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.url_identity_kind == "unknown"
    assert identity.canonical_item_key == f"canonical-url:{canonical_url}"
    assert identity.dedup_key_kind == "canonical_url"
    assert identity.dedup_key_confidence == "strong"
    assert identity.match_type == "same_canonical_url"


@pytest.mark.parametrize(
    ("canonical_url", "expected_url_kind"),
    (
        ("https://tass.ru/", "homepage"),
        ("https://www.coindesk.com/markets", "aggregator"),
        ("https://www.binance.com/en/support/announcement", "article"),
        ("https://example.com/feed", "unknown"),
        ("https://example.com/rss", "unknown"),
        ("https://example.com/rss.xml", "unknown"),
        ("https://example.com/en/news/rss", "article"),
        ("https://example.com/news/index", "article"),
        ("https://example.com/news/index.html", "article"),
        ("https://example.com/news/preview/story-123456", "article"),
        ("https://example.com/atom", "unknown"),
        ("https://example.com/atom.xml", "unknown"),
    ),
)
def test_generic_feed_or_index_urls_do_not_promote_high_signal_content_identity(
    canonical_url: str,
    expected_url_kind: str,
) -> None:
    service = _service()
    published_at_ms = 1_714_004_321_000
    published_hour_ms = published_at_ms - (published_at_ms % 3_600_000)

    identity = service.canonical_identity_for_observation(
        provider_type="rss",
        source_id="rss-marketwatch",
        provider_article_id="",
        canonical_url=canonical_url,
        content_hash="stored-content-hash",
        title_fingerprint="bitcoin etf flows accelerate after issuer amends registration statement",
        title=_HIGH_SIGNAL_TITLE,
        summary=_HIGH_SIGNAL_SUMMARY,
        body_text="",
        published_at_ms=published_at_ms,
    )

    assert identity.url_identity_kind == expected_url_kind
    assert identity.canonical_item_key == (
        "weak-title-source-window:"
        f"rss-marketwatch:{published_hour_ms}:bitcoin etf flows accelerate after issuer amends registration statement"
    )
    assert identity.dedup_key_kind == "weak_title_time_source"
    assert identity.match_type == "weak_title_time_source"
    assert not identity.canonical_item_key.startswith("content-hash:")


@pytest.mark.parametrize(
    ("provider_type", "canonical_url"),
    (
        ("opennews", "opennews://item/123"),
        ("rss", "rss://feed/item"),
    ),
)
def test_non_http_provider_urls_do_not_promote_high_signal_content_identity(
    provider_type: str,
    canonical_url: str,
) -> None:
    service = _service()
    published_at_ms = 1_714_004_321_000
    published_hour_ms = published_at_ms - (published_at_ms % 3_600_000)
    source_id = f"{provider_type}-source"

    identity = service.canonical_identity_for_observation(
        provider_type=provider_type,
        source_id=source_id,
        provider_article_id="",
        canonical_url=canonical_url,
        content_hash="stored-content-hash",
        title_fingerprint="bitcoin etf flows accelerate after issuer amends registration statement",
        title=_HIGH_SIGNAL_TITLE,
        summary=_HIGH_SIGNAL_SUMMARY,
        body_text="",
        published_at_ms=published_at_ms,
    )

    assert identity.url_identity_kind == "unknown"
    assert identity.canonical_item_key == (
        "weak-title-source-window:"
        f"{source_id}:{published_hour_ms}:bitcoin etf flows accelerate after issuer amends registration statement"
    )
    assert identity.dedup_key_kind == "weak_title_time_source"
    assert identity.match_type == "weak_title_time_source"
    assert not identity.canonical_item_key.startswith("content-hash:")


def test_malformed_url_does_not_raise_or_promote_high_signal_content_identity() -> None:
    service = _service()
    published_at_ms = 1_714_004_321_000
    published_hour_ms = published_at_ms - (published_at_ms % 3_600_000)

    identity = service.canonical_identity_for_observation(
        provider_type="rss",
        source_id="rss-malformed",
        provider_article_id="",
        canonical_url="https://[::1",
        content_hash="stored-content-hash",
        title_fingerprint="bitcoin etf flows accelerate after issuer amends registration statement",
        title=_HIGH_SIGNAL_TITLE,
        summary=_HIGH_SIGNAL_SUMMARY,
        body_text="",
        published_at_ms=published_at_ms,
    )

    assert identity.url_identity_kind == "unknown"
    assert identity.canonical_item_key == (
        "weak-title-source-window:"
        f"rss-malformed:{published_hour_ms}:bitcoin etf flows accelerate after issuer amends registration statement"
    )
    assert identity.dedup_key_kind == "weak_title_time_source"
    assert identity.match_type == "weak_title_time_source"


def test_opennews_provider_id_wins_over_qualified_content_hash() -> None:
    service = _service()
    content_identity_hash = qualified_content_hash(_HIGH_SIGNAL_TITLE, _HIGH_SIGNAL_SUMMARY, "")

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="2367422",
        canonical_url="https://www.binance.com/en/support/announcement",
        content_hash=content_identity_hash,
        title_fingerprint="binance announcement",
        title=_HIGH_SIGNAL_TITLE,
        summary=_HIGH_SIGNAL_SUMMARY,
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == "provider:opennews:2367422"
    assert identity.dedup_key_kind == "provider_article_id"
    assert identity.match_type == "same_provider_article_id"


def test_opennews_fallback_url_with_provider_id_uses_provider_identity_over_content_hash() -> None:
    service = _service()
    content_identity_hash = qualified_content_hash(_HIGH_SIGNAL_TITLE, _HIGH_SIGNAL_SUMMARY, "")

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="123",
        canonical_url="opennews://item/123",
        content_hash=content_identity_hash,
        title_fingerprint="bitcoin etf flows accelerate after issuer amends registration statement",
        title=_HIGH_SIGNAL_TITLE,
        summary=_HIGH_SIGNAL_SUMMARY,
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == "provider:opennews:123"
    assert identity.url_identity_kind == "unknown"
    assert identity.dedup_key_kind == "provider_article_id"
    assert identity.match_type == "same_provider_article_id"
    assert identity.evidence["qualified_content_hash"] == content_identity_hash


def test_twitter_status_url_uses_social_status_identity() -> None:
    service = _service()

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="2367422",
        canonical_url="https://twitter.com/CoinbaseMarkets/status/2057891761607889216",
        content_hash="hash-abc",
        title_fingerprint="coinbase update",
        title=_HIGH_SIGNAL_TITLE,
        summary=_HIGH_SIGNAL_SUMMARY,
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == "social-status:twitter:2057891761607889216"
    assert identity.dedup_key_kind == "canonical_url"
    assert identity.match_type == "same_canonical_url"


def test_article_url_uses_the_global_canonical_url_key() -> None:
    service = _service()
    canonical_url = "https://www.binance.com/en/support/announcement/binance-will-list-example-abc123"

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="",
        canonical_url=canonical_url,
        content_hash="",
        title_fingerprint="binance will list example",
        title="Binance will list example",
        summary="",
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == f"canonical-url:{canonical_url}"
    assert identity.url_identity_kind == "article"
    assert identity.dedup_key_kind == "canonical_url"
    assert identity.dedup_key_confidence == "strong"
    assert identity.match_type == "same_canonical_url"


def test_article_ending_in_index_html_uses_the_global_canonical_url_key() -> None:
    service = _service()
    canonical_url = "https://example.com/news/story/index.html"

    identity = service.canonical_identity_for_observation(
        provider_type="rss",
        source_id="rss-example",
        provider_article_id="",
        canonical_url=canonical_url,
        content_hash="",
        title_fingerprint="example story",
        title="Example story",
        summary="",
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == f"canonical-url:{canonical_url}"
    assert identity.url_identity_kind == "article"
    assert identity.dedup_key_kind == "canonical_url"
    assert identity.match_type == "same_canonical_url"


def test_opennews_provider_id_wins_without_public_url_or_content_hash() -> None:
    service = _service()

    identity = service.canonical_identity_for_observation(
        provider_type="opennews",
        source_id="opennews-news",
        provider_article_id="2367422",
        canonical_url="opennews://item/2367422",
        content_hash="",
        title_fingerprint="binance will list example",
        title="Binance will list example",
        summary="",
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == "provider:opennews:2367422"
    assert identity.dedup_key_kind == "provider_article_id"
    assert identity.dedup_key_confidence == "strong"
    assert identity.match_type == "same_provider_article_id"


def test_stable_news_item_id_is_order_independent() -> None:
    service = _service()
    kwargs = {
        "provider_type": "opennews",
        "source_id": "opennews-news",
        "provider_article_id": "",
        "canonical_url": "https://www.binance.com/en/support/announcement/binance-will-list-example-abc123",
        "content_hash": "hash-abc",
        "title_fingerprint": "binance will list example",
        "title": "Binance will list example",
        "summary": _HIGH_SIGNAL_SUMMARY,
        "body_text": "",
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
        title="Bitcoin ETF flow update",
        summary="",
        body_text="",
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


def test_rss_provider_article_id_is_not_global_identity() -> None:
    service = _service()
    published_at_ms = 1_714_004_321_000
    published_hour_ms = published_at_ms - (published_at_ms % 3_600_000)

    identity = service.canonical_identity_for_observation(
        provider_type="rss",
        source_id="rss-cointelegraph",
        provider_article_id="guid-123",
        canonical_url="rss://cointelegraph/guid-123",
        content_hash="stored-content-hash",
        title_fingerprint="market update",
        title="Market Update",
        summary="",
        body_text="",
        published_at_ms=published_at_ms,
    )

    assert frozenset({"opennews"}) == service.PROVIDER_GLOBAL_ARTICLE_ID_TYPES
    assert service.provider_global_article_key(provider_type="rss", provider_article_id="guid-123") == ""
    assert identity.canonical_item_key == (
        f"weak-title-source-window:rss-cointelegraph:{published_hour_ms}:market update"
    )
    assert identity.dedup_key_kind == "weak_title_time_source"
    assert identity.evidence["provider_article_id"] == "guid-123"
    assert identity.evidence["provider_article_key"] is None


def test_qualified_content_hash_becomes_content_identity_without_hard_url_or_global_provider_id() -> None:
    service = _service()
    content_identity_hash = qualified_content_hash(_HIGH_SIGNAL_TITLE, _HIGH_SIGNAL_SUMMARY, "")

    identity = service.canonical_identity_for_observation(
        provider_type="rss",
        source_id="rss-marketwatch",
        provider_article_id="guid-123",
        canonical_url="",
        content_hash="stored-content-hash",
        title_fingerprint="bitcoin etf flows accelerate after issuer amends registration statement",
        title=_HIGH_SIGNAL_TITLE,
        summary=_HIGH_SIGNAL_SUMMARY,
        body_text="",
        published_at_ms=1_714_004_321_000,
    )

    assert identity.canonical_item_key == f"content-hash:{content_identity_hash}"
    assert identity.dedup_key_kind == "content_hash"
    assert identity.dedup_key_confidence == "strong"
    assert identity.match_type == "same_content_hash"
    assert identity.evidence["content_hash"] == "stored-content-hash"
    assert identity.evidence["qualified_content_hash"] == content_identity_hash
    assert identity.evidence["material_title_fingerprint"] == (
        "bitcoin etf flows accelerate after issuer amends registration statement"
    )
