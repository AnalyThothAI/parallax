from __future__ import annotations

from parallax.domains.news_intel.services.text_normalization import (
    canonicalize_url,
    clean_news_text,
    content_hash,
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
    url = "HTTPS://Example.COM/Path/Story/?b=2&utm_source=x&A=1&utm_campaign=y#section"

    assert canonicalize_url(url) == "https://example.com/Path/Story?A=1&b=2"


def test_title_fingerprint_casefolds_punctuation_and_whitespace() -> None:
    assert title_fingerprint("  SOL-ETF: Filing... APPROVED?!  ") == "sol etf filing approved"


def test_content_hash_is_stable_over_html_tracking_urls_and_case_noise() -> None:
    first = content_hash(
        " SOL ETF approved! ",
        "<p>Issuer confirms launch. Subscribe for more.</p>",
        "https://Example.com/news/sol/?utm_source=x&b=2&a=1",
    )
    second = content_hash(
        "sol etf approved",
        "Issuer confirms launch.",
        "https://example.com/news/sol?a=1&b=2",
    )

    assert first == second


def test_content_hash_changes_when_body_text_changes() -> None:
    first = content_hash("SOL ETF approved", "Issuer confirms launch.", "https://example.com/news/sol", body_text="A")
    second = content_hash("SOL ETF approved", "Issuer confirms launch.", "https://example.com/news/sol", body_text="B")

    assert first != second
