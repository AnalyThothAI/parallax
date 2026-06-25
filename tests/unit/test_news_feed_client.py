import httpx
import pytest

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


@pytest.mark.parametrize(
    ("kwargs", "error_code"),
    [
        pytest.param({"max_attempts": 0}, "feed_client_max_attempts_required", id="zero-attempts"),
        pytest.param({"max_attempts": True}, "feed_client_max_attempts_required", id="bool-attempts"),
        pytest.param({"max_attempts": "2"}, "feed_client_max_attempts_required", id="string-attempts"),
        pytest.param({"timeout_seconds": 0.0}, "feed_client_timeout_seconds_required", id="zero-timeout"),
        pytest.param({"timeout_seconds": True}, "feed_client_timeout_seconds_required", id="bool-timeout"),
        pytest.param({"timeout_seconds": "1"}, "feed_client_timeout_seconds_required", id="string-timeout"),
    ],
)
def test_feed_client_rejects_malformed_runtime_boundaries(kwargs: dict[str, object], error_code: str) -> None:
    with pytest.raises(ValueError, match=error_code):
        FeedClient(**kwargs)
