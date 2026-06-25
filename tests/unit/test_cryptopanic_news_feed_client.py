from __future__ import annotations

from pathlib import Path

import pytest

from parallax.integrations.news_feeds.cryptopanic_client import CryptopanicFeedClient


def test_cryptopanic_feed_client_maps_normalized_posts_to_news_feed_entries(tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakeTransport:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def fetch_posts_page(self, **kwargs):
            captured["query"] = kwargs
            return {
                "next": "web://posts?page=1&posts_cnt=50",
                "previous": None,
                "results": [
                    {
                        "id": 32675220,
                        "slug": "Mastercard-Acquires-BVNK",
                        "title": "Mastercard Acquires BVNK",
                        "description": "Crypto payments deal explained.",
                        "published_at": "2026-05-21T02:32:05Z",
                        "created_at": "2026-05-21T02:32:05Z",
                        "kind": "link",
                        "source": {"title": "coincu", "region": "en", "domain": "coincu.com"},
                        "original_url": "https://coincu.com/mastercard-acquires-bvnk/",
                        "url": "https://cryptopanic.com/news/32675220/Mastercard-Acquires-BVNK",
                        "currencies": [{"code": "BTC", "title": "Bitcoin", "slug": "bitcoin"}],
                        "votes": {"positive": 2, "negative": 0, "important": 1},
                        "panic_score": 74,
                    },
                    {
                        "id": 31925239,
                        "slug": "sponsored",
                        "title": "Sponsored",
                        "published_at": "2026-05-21T02:31:05Z",
                        "kind": "sponsored",
                    },
                ],
            }

    client = CryptopanicFeedClient(transport_factory=FakeTransport)

    result = client.fetch(
        "cryptopanic://posts?regions=en&currencies=btc,eth&filter=bullish&kind=news&max_items=25"
        f"&profile_dir={tmp_path / 'profile'}&timeout=12.5&evidence_dir={tmp_path / 'evidence'}"
    )

    assert result.status_code == 200
    assert result.etag == "web://posts?page=1&posts_cnt=50"
    assert len(result.entries) == 1
    assert result.entries[0]["id"] == "cryptopanic:32675220"
    assert result.entries[0]["link"] == "https://coincu.com/mastercard-acquires-bvnk/"
    assert result.entries[0]["title"] == "Mastercard Acquires BVNK"
    assert result.entries[0]["source"]["domain"] == "coincu.com"
    assert result.entries[0]["currencies_codes"] == ["BTC"]
    assert result.entries[0]["panic_score"] == 74
    assert captured["profile_dir"] == Path(tmp_path / "profile")
    assert captured["headless"] is True
    assert captured["timeout"] == 12.5
    assert captured["evidence_dir"] == Path(tmp_path / "evidence")
    assert captured["query"] == {
        "currencies": ["BTC", "ETH"],
        "filter": "bullish",
        "kind": "news",
        "regions": ["en"],
    }


def test_cryptopanic_feed_client_returns_not_modified_when_next_page_matches_cache(tmp_path) -> None:
    class FakeTransport:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def fetch_posts_page(self, **kwargs):
            return {"next": "web://posts?page=1&posts_cnt=50", "previous": None, "results": []}

    client = CryptopanicFeedClient(transport_factory=FakeTransport)

    result = client.fetch(
        f"cryptopanic://posts?profile_dir={tmp_path / 'profile'}",
        etag="web://posts?page=1&posts_cnt=50",
    )

    assert result.status_code == 304
    assert result.not_modified is True
    assert result.entries == []


@pytest.mark.parametrize(
    "max_items",
    [
        pytest.param("0", id="zero"),
        pytest.param("-1", id="negative"),
        pytest.param("bad", id="bad-text"),
    ],
)
def test_cryptopanic_feed_client_rejects_malformed_max_items_before_transport(
    tmp_path,
    max_items: str,
) -> None:
    class FailTransport:
        def __init__(self, **_kwargs):
            raise AssertionError("CryptoPanic transport must not open before max_items validation")

    client = CryptopanicFeedClient(transport_factory=FailTransport)

    with pytest.raises(ValueError, match="CryptoPanic feed URL invalid max_items"):
        client.fetch(f"cryptopanic://posts?profile_dir={tmp_path / 'profile'}&max_items={max_items}")
