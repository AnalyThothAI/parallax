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
