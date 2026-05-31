from __future__ import annotations

from parallax.domains.news_intel.services.news_content_classification import (
    classify_news_item_content,
)


def test_classifies_sec_tokenized_stock_delay_as_regulation() -> None:
    result = classify_news_item_content(
        headline="SEC Delays Tokenized Stocks Innovation Exemption Amid Concerns",
        summary="The SEC delayed a tokenized stocks exemption framework.",
        source_domain="decrypt.co",
        fact_event_types=["regulatory"],
    )

    assert result.content_class == "regulation"
    assert "tokenized_stocks" in result.content_tags


def test_classifies_empty_yahoo_price_target_as_analyst_rating_low_context() -> None:
    result = classify_news_item_content(
        headline="Morgan Stanley resets PANW stock price target on demand trends",
        summary="",
        source_domain="finance.yahoo.com",
        fact_event_types=[],
    )

    assert result.content_class == "analyst_rating"
    assert "low_context" in result.content_tags


def test_security_hack_priority_beats_crypto_market_terms() -> None:
    result = classify_news_item_content(
        headline="Bitcoin bridge hacked as market rallies",
        summary="Exploit drains protocol funds.",
        source_domain="example.com",
        fact_event_types=["security_incident"],
    )

    assert result.content_class == "security_hack"
    assert "security_incident" in result.content_tags
