from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _service() -> Any:
    try:
        return import_module("parallax.domains.news_intel.types.news_url_identity")
    except ModuleNotFoundError as exc:
        pytest.fail(f"news_url_identity policy module is required: {exc}")


def test_tass_root_url_is_homepage_not_article_identity() -> None:
    service = _service()

    assert service.url_identity_kind("https://tass.ru/") == "homepage"
    policy = service.public_url_identity_policy("https://tass.ru/")
    assert policy.allowed is False
    assert policy.blocked_reason == "homepage"


def test_afp_root_url_is_homepage_not_article_identity() -> None:
    service = _service()

    assert service.url_identity_kind("https://www.afp.com") == "homepage"
    policy = service.public_url_identity_policy("https://www.afp.com")
    assert policy.allowed is False
    assert policy.blocked_reason == "homepage"


def test_nyt_live_url_is_live_page_not_article_identity() -> None:
    service = _service()
    canonical_url = "https://www.nytimes.com/live/2026/05/28/business/crypto-market-news"

    assert service.url_identity_kind(canonical_url) == "live_page"
    policy = service.public_url_identity_policy(canonical_url)
    assert policy.allowed is False
    assert policy.identity_kind == "live_page"
    assert policy.blocked_reason == "live_page"
    assert service.hard_public_url_identity_key(canonical_url) == ""


def test_opennews_fallback_url_is_unknown() -> None:
    service = _service()

    assert service.url_identity_kind("opennews://item/2367422") == "unknown"
    policy = service.public_url_identity_policy("opennews://item/2367422")
    assert policy.allowed is False
    assert policy.blocked_reason == "not_public_url"


def test_binance_announcement_article_url_has_public_identity() -> None:
    service = _service()
    canonical_url = "https://www.binance.com/en/support/announcement/binance-will-list-example-abc123"

    assert service.url_identity_kind(canonical_url) == "article"
    assert service.public_url_identity_policy(canonical_url).identity_key == f"canonical-url:{canonical_url}"


def test_public_url_policy_allows_single_segment_news_slug() -> None:
    service = _service()
    url = "https://financefeeds.com/bessent-urges-lawmakers-to-pass-crypto-clarity-act-this-summer"

    policy = service.public_url_identity_policy(url)

    assert policy.allowed is True
    assert policy.identity_key == f"canonical-url:{url}"
    assert policy.identity_kind == "unknown"
    assert policy.blocked_reason == ""


def test_public_url_policy_blocks_generic_source_urls() -> None:
    service = _service()

    assert service.public_url_identity_policy("https://www.afp.com").blocked_reason == "homepage"
    assert service.public_url_identity_policy("https://tass.ru/").blocked_reason == "homepage"
    assert service.public_url_identity_policy("https://tass.com/world").blocked_reason == "aggregator"
    assert service.public_url_identity_policy("https://www.afp.com/en/news").blocked_reason == "aggregator"
    assert service.public_url_identity_policy("https://www.coindesk.com/markets").blocked_reason == "aggregator"
    assert service.public_url_identity_policy("https://www.coindesk.com/live").blocked_reason == "live_page"
    assert service.public_url_identity_policy("https://news.6551.io/preview/abc").blocked_reason == "preview"
    assert service.public_url_identity_policy("https://example.com/rss.xml").blocked_reason == "feed_index"


def test_twitter_status_url_has_stable_hard_public_identity() -> None:
    service = _service()

    assert (
        service.hard_public_url_identity_key("https://twitter.com/CoinbaseMarkets/status/2057891761607889216")
        == "social-status:twitter:2057891761607889216"
    )
    assert (
        service.hard_public_url_identity_key("https://x.com/coinbasemarkets/status/2057891761607889216?s=20")
        == "social-status:twitter:2057891761607889216"
    )


def test_preview_and_generic_urls_do_not_get_hard_public_identity() -> None:
    service = _service()

    assert service.hard_public_url_identity_key("https://news.6551.io/preview/abc") == ""
    assert service.hard_public_url_identity_key("https://www.treeofalpha.com/preview_article?id=123") == ""
    assert service.hard_public_url_identity_key("https://www.binance.com/en/support/announcement") == ""
    assert service.hard_public_url_identity_key("https://tass.ru/") == ""
    assert service.hard_public_url_identity_key("https://example.com/news/index") == ""
    assert service.hard_public_url_identity_key("https://example.com/news/index.html") == ""
    assert service.hard_public_url_identity_key("https://example.com/news/rss") == ""
    assert service.hard_public_url_identity_key("https://example.com/en/news/rss") == ""


def test_article_url_gets_canonical_hard_public_identity() -> None:
    service = _service()
    canonical_url = "https://www.binance.com/en/support/announcement/binance-will-list-example-abc123"

    assert service.hard_public_url_identity_key(canonical_url) == f"canonical-url:{canonical_url}"


def test_single_segment_slug_gets_canonical_hard_public_identity() -> None:
    service = _service()
    canonical_url = "https://financefeeds.com/bessent-urges-lawmakers-to-pass-crypto-clarity-act-this-summer"

    assert service.url_identity_kind(canonical_url) == "unknown"
    assert service.hard_public_url_identity_key(canonical_url) == f"canonical-url:{canonical_url}"


def test_article_under_rss_named_section_gets_hard_public_identity() -> None:
    service = _service()
    canonical_url = "https://example.com/news/rss/story-123456"

    assert service.hard_public_url_identity_key(canonical_url) == f"canonical-url:{canonical_url}"


def test_article_ending_in_index_html_gets_hard_public_identity() -> None:
    service = _service()
    canonical_url = "https://example.com/news/story/index.html"

    assert service.hard_public_url_identity_key(canonical_url) == f"canonical-url:{canonical_url}"
