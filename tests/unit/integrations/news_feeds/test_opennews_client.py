from __future__ import annotations

import inspect
from typing import Any

import pytest

from parallax.integrations.news_feeds.opennews_client import (
    OpenNewsFeedClient,
    _source_fetch_policy,
)

NOW_MS = 1_779_000_000_000


def test_opennews_fetch_policy_only_reads_json_contract() -> None:
    assert _source_fetch_policy({"fetch_policy": {"engineTypes": {"news": []}}}) == {}
    assert _source_fetch_policy({"fetch_policy_json": {"engineTypes": {"news": []}}}) == {"engineTypes": {"news": []}}


def test_opennews_client_constructor_is_rest_only() -> None:
    parameters = inspect.signature(OpenNewsFeedClient).parameters

    assert "token" in parameters
    assert "api_base_url" in parameters
    assert "wss_url" not in parameters
    assert "connect_timeout_seconds" not in parameters
    assert "connect" not in parameters


def test_opennews_client_rest_fetch_posts_to_news_search_and_reports_rest() -> None:
    rest_requests: list[dict[str, Any]] = []

    async def fake_post_json(url: str, *, token: str, body: dict[str, Any]) -> dict[str, Any]:
        rest_requests.append({"url": url, "token": token, "body": body})
        return {
            "data": [
                {
                    "id": 2378100,
                    "text": "Anthropic revenue runs ahead of OpenAI",
                    "newsType": "6551News",
                    "engineType": "news",
                    "link": "https://example.com/news/2378100",
                    "coins": [
                        {"symbol": "ANTHROPIC", "market_type": "cex", "score": 75, "signal": "long", "grade": "A"}
                    ],
                    "aiRating": {
                        "status": "done",
                        "score": 75,
                        "signal": "long",
                        "grade": "A",
                        "summary": "Ready summary",
                    },
                    "ts": NOW_MS - 1_000,
                }
            ]
        }

    client = OpenNewsFeedClient(token="test-token", api_base_url="https://ai.6551.io/", post_json=fake_post_json)

    result = client.fetch(
        "opennews://subscribe",
        limit=5,
        source={
            "source_id": "opennews-news",
            "fetch_policy_json": {
                "engineTypes": {"news": ["6551News"]},
                "hasCoin": True,
                "rest_limit": 5,
                "max_rest_pages": 1,
            },
        },
    )

    assert result.status_code == 200
    assert result.feed == {
        "provider": "opennews",
        "transport": "rest",
        "subscription": {"engineTypes": {"news": ["6551News"]}, "hasCoin": True},
        "rest_received": 1,
        "received": 1,
    }
    assert result.entries[0]["id"] == "2378100"
    assert result.entries[0]["provider_signal"]["status"] == "ready"
    assert result.entries[0]["provider_signal"]["score"] == 75
    assert rest_requests == [
        {
            "url": "https://ai.6551.io/open/news_search",
            "token": "test-token",
            "body": {"limit": 5, "page": 1, "engineTypes": {"news": ["6551News"]}, "hasCoin": True},
        }
    ]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("fetch_mode", "hybrid"),
        ("wss_url", "wss://example.test/open/news_wss"),
        ("stream_timeout_seconds", 10),
        ("streamTimeoutSeconds", 10),
        ("max_messages", 20),
        ("maxMessages", 20),
        ("connect_timeout_seconds", 3),
        ("connectTimeoutSeconds", 3),
    ],
)
def test_opennews_client_rejects_removed_websocket_policy_keys(key: str, value: object) -> None:
    client = OpenNewsFeedClient(token="test-token", post_json=_unused_post_json)

    with pytest.raises(ValueError, match=f"removed OpenNews websocket policy keys: {key}"):
        client.fetch("opennews://subscribe", source={"fetch_policy_json": {key: value}})


def test_opennews_client_requires_configured_token_without_echoing_value() -> None:
    client = OpenNewsFeedClient(token="")

    with pytest.raises(ValueError, match="OpenNews token is not configured"):
        client.fetch("opennews://subscribe")


def test_opennews_client_rest_scan_uses_cursor_overlap_and_returns_next_cursor() -> None:
    rest_requests: list[dict[str, Any]] = []
    pages = {
        1: [{"id": 2378101, "text": "Newer alert", "link": "https://example.com/news/newer", "ts": NOW_MS - 10_000}],
        2: [
            {
                "id": 2378102,
                "text": "Overlap alert",
                "link": "https://example.com/news/overlap",
                "ts": NOW_MS - 500_000,
            }
        ],
        3: [
            {
                "id": 2378103,
                "text": "Old alert",
                "link": "https://example.com/news/old",
                "ts": NOW_MS - 700_000,
            }
        ],
    }

    async def fake_post_json(url: str, *, token: str, body: dict[str, Any]) -> dict[str, Any]:
        rest_requests.append({"url": url, "token": token, "body": body})
        return {"data": pages.get(int(body["page"]), [])}

    client = OpenNewsFeedClient(
        token="test-token",
        post_json=fake_post_json,
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        cursor={"high_watermark_ms": NOW_MS - 60_000, "overlap_ms": 600_000},
        limit=20,
        source={
            "fetch_policy_json": {
                "engineTypes": {"news": ["6551News"]},
                "rest_limit": 2,
                "max_rest_pages": 5,
            }
        },
    )

    assert [request["body"]["page"] for request in rest_requests] == [1, 2, 3]
    assert {entry["id"] for entry in result.entries} == {"2378101", "2378102", "2378103"}
    assert result.next_cursor == {
        "high_watermark_ms": NOW_MS - 10_000,
        "overlap_ms": 600_000,
        "pages_scanned": 3,
        "rest_received": 3,
        "oldest_seen_ms": NOW_MS - 700_000,
        "stop_reason": "oldest_before_overlap",
    }


def test_opennews_client_rest_fetch_sends_since_ms_and_filters_older_entries() -> None:
    rest_requests: list[dict[str, Any]] = []
    since_ms = NOW_MS - 60_000

    async def fake_post_json(url: str, *, token: str, body: dict[str, Any]) -> dict[str, Any]:
        rest_requests.append({"url": url, "token": token, "body": body})
        return {
            "data": [
                {
                    "id": 2378201,
                    "text": "Fresh alert",
                    "link": "https://example.com/news/fresh",
                    "ts": since_ms + 1,
                },
                {
                    "id": 2378202,
                    "text": "Old alert",
                    "link": "https://example.com/news/old",
                    "ts": since_ms - 1,
                },
            ]
        }

    client = OpenNewsFeedClient(token="test-token", post_json=fake_post_json, now_ms=lambda: NOW_MS)

    result = client.fetch(
        "opennews://subscribe",
        since_ms=since_ms,
        source={"fetch_policy_json": {"engineTypes": {"news": ["6551News"]}, "max_rest_pages": 1}},
    )

    assert rest_requests[0]["body"]["publishedAfterMs"] == since_ms
    assert [entry["id"] for entry in result.entries] == ["2378201"]


def test_opennews_client_rest_scan_merges_article_fragments_and_counts_visible_entries() -> None:
    async def fake_post_json(_url: str, *, token: str, body: dict[str, Any]) -> dict[str, Any]:
        assert token == "test-token"
        assert body["page"] == 1
        return {
            "data": [
                {
                    "id": 2378101,
                    "text": "Bitcoin ETF flows accelerate",
                    "newsType": "6551News",
                    "engineType": "news",
                    "link": "https://example.com/news/2378101",
                    "ts": NOW_MS - 10_000,
                },
                {
                    "id": 2378101,
                    "newsType": "6551News",
                    "engineType": "news",
                    "aiRating": {
                        "status": "done",
                        "score": 81,
                        "signal": "long",
                        "grade": "A",
                        "summary": "Ready summary",
                    },
                    "ts": NOW_MS - 9_000,
                },
                {
                    "id": 2378102,
                    "newsType": "6551News",
                    "engineType": "news",
                    "link": "https://example.com/news/2378102",
                    "ts": NOW_MS - 8_000,
                },
            ]
        }

    client = OpenNewsFeedClient(token="test-token", post_json=fake_post_json, now_ms=lambda: NOW_MS)

    result = client.fetch(
        "opennews://subscribe",
        source={"fetch_policy_json": {"engineTypes": {"news": ["6551News"]}, "max_rest_pages": 1}},
    )

    assert [entry["id"] for entry in result.entries] == ["2378101"]
    assert result.entries[0]["title"] == "Bitcoin ETF flows accelerate"
    assert result.entries[0]["summary"] == "Ready summary"
    assert result.entries[0]["provider_signal"]["status"] == "ready"
    assert result.entries[0]["provider_signal"]["score"] == 81
    assert result.feed["rest_received"] == 3
    assert result.feed["received"] == 1


async def _unused_post_json(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise AssertionError("removed OpenNews websocket policy keys must be rejected before REST fetch")
