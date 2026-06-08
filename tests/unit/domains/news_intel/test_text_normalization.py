from __future__ import annotations

import hashlib

import pytest

from parallax.domains.news_intel.types.text_normalization import (
    canonicalize_url,
    clean_news_text,
    content_hash,
    qualified_content_hash,
    title_fingerprint,
)


def test_clean_news_text_strips_markup_urls_boilerplate_and_clamps_length() -> None:
    raw = """
    <article><h1>ETF Approved</h1>
    <p>Issuer <b>confirms</b> launch at https://example.com/story?utm_source=x.</p>
    <p>Read more: full article</p></article>
    """

    assert clean_news_text(raw, max_chars=28) == "ETF Approved Issuer confirms"


def test_canonicalize_url_lowercases_origin_removes_tracking_and_sorts_query() -> None:
    url = (
        "HTTPS://Example.COM/Path/Story/?b=2&utm_source=x&A=1&utm_campaign=y"
        "&fbclid=fb&gclid=gc&gbraid=gb&wbraid=wb&mc_cid=cid&mc_eid=eid"
        "&igshid=ig&ref=referrer&ref_src=src#section"
    )

    assert canonicalize_url(url) == "https://example.com/Path/Story?A=1&b=2"


@pytest.mark.parametrize(
    "url",
    (
        "https://example.com:bad/path",
        "https://[::1",
        "http://",
        "https:///path",
        "not a url",
        "www.example.com/story",
        "https://exa mple.com/news",
        "https://example.com/news story",
        "https://example.com/news\tstory",
        "https://example.com/news\nstory",
    ),
)
def test_canonicalize_url_returns_empty_for_malformed_urls(url: str) -> None:
    assert canonicalize_url(url) == ""


def test_canonicalize_url_preserves_valid_encoded_whitespace() -> None:
    assert canonicalize_url("https://example.com/news/a%20story?b=2") == "https://example.com/news/a%20story?b=2"


def test_canonicalize_url_strips_outer_whitespace_before_validation() -> None:
    assert canonicalize_url(" https://example.com/a ") == "https://example.com/a"


def test_title_fingerprint_casefolds_punctuation_and_whitespace() -> None:
    assert title_fingerprint("  SOL-ETF: Filing... APPROVED?!  ") == "sol etf filing approved"


def test_content_hash_uses_only_cleaned_content_fields() -> None:
    title = " SOL ETF approved! "
    summary = "<p>Issuer confirms launch. Subscribe for more.</p>"
    body_text = "<div>Market makers confirmed spot liquidity.</div>"
    expected_payload = "\x1f".join(
        (
            title_fingerprint(title),
            clean_news_text(summary),
            clean_news_text(body_text),
        )
    )

    assert (
        content_hash(title, summary, body_text=body_text)
        == hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()
    )


def test_content_hash_changes_when_body_text_changes() -> None:
    first = content_hash("SOL ETF approved", "Issuer confirms launch.", body_text="A")
    second = content_hash("SOL ETF approved", "Issuer confirms launch.", body_text="B")

    assert first != second


def test_qualified_content_hash_returns_content_hash_for_high_signal_content() -> None:
    title = "Bitcoin ETF flows accelerate after issuer amends registration statement"
    summary = (
        "Bitcoin exchange traded fund inflows accelerated after a major issuer filed an amended registration "
        "statement and market makers reported deeper spot liquidity across Coinbase Binance Kraken and CME "
        "venues during New York trading."
    )

    assert qualified_content_hash(title, summary, "") == content_hash(title, summary)


@pytest.mark.parametrize(
    ("title", "summary", "body_text"),
    (
        ("Market Update", "", ""),
        ("Breaking News", "Bitcoin Ethereum Solana liquidity exchange filing issuer market maker " * 4, ""),
        ("Latest News", "Fresh headlines links summaries feeds index latest homepage markets " * 4, ""),
        ("Live Updates", "Fresh headlines links summaries feeds index latest homepage markets " * 4, ""),
        ("News Feed", "Fresh headlines links summaries feeds index latest homepage markets " * 4, ""),
        ("Bitcoin ETF", "short summary", ""),
    ),
)
def test_qualified_content_hash_rejects_generic_or_low_signal_content(
    title: str,
    summary: str,
    body_text: str,
) -> None:
    assert qualified_content_hash(title, summary, body_text) == ""
