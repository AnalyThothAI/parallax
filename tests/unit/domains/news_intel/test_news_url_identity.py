from __future__ import annotations

from importlib import import_module
from typing import Any

import pytest


def _service() -> Any:
    try:
        return import_module("parallax.domains.news_intel.services.news_url_identity")
    except ModuleNotFoundError as exc:
        pytest.fail(f"news_url_identity service is required: {exc}")


def test_tass_root_url_is_homepage_not_article_identity() -> None:
    service = _service()

    assert service.url_identity_kind("https://tass.ru/") == "homepage"
    assert service.is_article_identity("https://tass.ru/") is False


def test_afp_root_url_is_homepage_not_article_identity() -> None:
    service = _service()

    assert service.url_identity_kind("https://www.afp.com") == "homepage"
    assert service.is_article_identity("https://www.afp.com") is False


def test_nyt_live_url_is_live_page_not_article_identity() -> None:
    service = _service()
    canonical_url = "https://www.nytimes.com/live/2026/05/28/business/crypto-market-news"

    assert service.url_identity_kind(canonical_url) == "live_page"
    assert service.is_article_identity(canonical_url) is False


def test_opennews_fallback_url_is_unknown() -> None:
    service = _service()

    assert service.url_identity_kind("opennews://item/2367422") == "unknown"
    assert service.is_article_identity("opennews://item/2367422") is False


def test_binance_announcement_url_is_article_identity() -> None:
    service = _service()
    canonical_url = "https://www.binance.com/en/support/announcement/binance-will-list-example-abc123"

    assert service.url_identity_kind(canonical_url) == "article"
    assert service.is_article_identity(canonical_url) is True


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


def test_article_under_rss_named_section_gets_hard_public_identity() -> None:
    service = _service()
    canonical_url = "https://example.com/news/rss/story-123456"

    assert service.hard_public_url_identity_key(canonical_url) == f"canonical-url:{canonical_url}"


def test_article_ending_in_index_html_gets_hard_public_identity() -> None:
    service = _service()
    canonical_url = "https://example.com/news/story/index.html"

    assert service.hard_public_url_identity_key(canonical_url) == f"canonical-url:{canonical_url}"
