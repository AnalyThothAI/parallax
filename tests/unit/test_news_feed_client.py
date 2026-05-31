import httpx

from parallax.integrations.news_feeds.feed_client import FeedClient


def test_feed_client_retries_transient_transport_error_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary connect failure", request=request)
        return httpx.Response(
            200,
            content=b"""<?xml version="1.0"?><rss><channel><item><title>Fed holds rates</title><link>https://example.com/a</link></item></channel></rss>""",
        )

    client = FeedClient(
        timeout_seconds=1,
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    try:
        result = client.fetch("https://example.com/rss.xml")
    finally:
        client.close()

    assert attempts == 2
    assert result.status_code == 200
    assert result.entries[0]["title"] == "Fed holds rates"


def test_feed_client_retries_transient_server_error_once() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, content=b"try later")
        return httpx.Response(
            200,
            content=b"""<?xml version="1.0"?><rss><channel><item><title>BTC ETF inflow</title><link>https://example.com/b</link></item></channel></rss>""",
        )

    client = FeedClient(
        timeout_seconds=1,
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    try:
        result = client.fetch("https://example.com/rss.xml")
    finally:
        client.close()

    assert attempts == 2
    assert result.status_code == 200
    assert result.entries[0]["title"] == "BTC ETF inflow"
