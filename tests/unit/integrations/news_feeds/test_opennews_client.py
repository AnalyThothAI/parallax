from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from gmgn_twitter_intel.integrations.news_feeds.opennews_client import (
    OpenNewsFeedClient,
    _fetch_mode,
    _source_fetch_policy,
)

NOW_MS = 1_779_000_000_000


def test_opennews_fetch_policy_only_reads_json_contract() -> None:
    assert _source_fetch_policy({"fetch_policy": {"fetch_mode": "rest"}}) == {}
    assert _source_fetch_policy({"fetch_policy_json": {"fetch_mode": "rest"}}) == {"fetch_mode": "rest"}


def test_opennews_fetch_mode_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="unsupported OpenNews fetch_mode: push"):
        _fetch_mode({"fetch_mode": "push"})


def test_opennews_client_subscribes_and_normalizes_websocket_updates() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.ai_update",
                "params": {
                    "id": "article-1",
                    "text": "Bitcoin ETF flows accelerate",
                    "newsType": "Bloomberg",
                    "engineType": "news",
                    "link": "https://example.com/story?utm_source=opennews",
                    "coins": [{"symbol": "BTC", "score": 88, "signal": "long", "grade": "A"}],
                    "aiRating": {
                        "score": 88,
                        "grade": "A",
                        "signal": "long",
                        "summary": "资金流入继续增强。",
                        "enSummary": "ETF inflows continue to strengthen.",
                    },
                    "ts": NOW_MS - 1_000,
                },
            },
        ]
    )
    client = OpenNewsFeedClient(
        token="test-token",
        wss_url="wss://ai.6551.io/open/news_wss",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=1,
        source={
            "source_id": "opennews-realtime",
            "fetch_policy_json": {
                "engineTypes": {"news": ["Bloomberg"]},
                "coins": ["BTC"],
                "hasCoin": True,
                "stream_timeout_seconds": 0.25,
                "max_messages": 1,
                "fetch_mode": "websocket",
            },
        },
    )

    assert result.status_code == 101
    assert result.entries == [
        {
            "id": "article-1",
            "guid": "article-1",
            "link": "https://example.com/story?utm_source=opennews",
            "title": "Bitcoin ETF flows accelerate",
            "summary": "资金流入继续增强。",
            "content": [{"value": "ETF inflows continue to strengthen."}],
            "language": "en",
            "published_at_ms": NOW_MS - 1_000,
            "source_domain": "Bloomberg",
            "opennews_method": "news.ai_update",
            "provider_article_id": "article-1",
            "provider_article_key": "opennews:article-1",
            "provider_signal": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "label_zh": "利好",
                "signal": "long",
                "score": 88,
                "grade": "A",
                "summary_zh": "资金流入继续增强。",
                "summary_en": "ETF inflows continue to strengthen.",
                "method": "opennews.aiRating",
            },
            "provider_token_impacts": [
                {"symbol": "BTC", "market_type": None, "score": 88, "signal": "long", "grade": "A"}
            ],
            "raw": {
                "id": "article-1",
                "text": "Bitcoin ETF flows accelerate",
                "newsType": "Bloomberg",
                "engineType": "news",
                "link": "https://example.com/story?utm_source=opennews",
                "coins": [{"symbol": "BTC", "score": 88, "signal": "long", "grade": "A"}],
                "aiRating": {
                    "score": 88,
                    "grade": "A",
                    "signal": "long",
                    "summary": "资金流入继续增强。",
                    "enSummary": "ETF inflows continue to strengthen.",
                },
                "ts": NOW_MS - 1_000,
            },
        }
    ]
    assert result.feed == {
        "provider": "opennews",
        "subscription": {"engineTypes": {"news": ["Bloomberg"]}, "coins": ["BTC"], "hasCoin": True},
        "received": 1,
    }
    assert websocket.sent_messages == [
        {
            "jsonrpc": "2.0",
            "id": "opennews_subscribe_1",
            "method": "news.subscribe",
            "params": {"engineTypes": {"news": ["Bloomberg"]}, "coins": ["BTC"], "hasCoin": True},
        },
        {"jsonrpc": "2.0", "id": "opennews_unsubscribe_2", "method": "news.unsubscribe"},
    ]
    assert websocket.closed is True
    assert websocket.connected_url == "wss://ai.6551.io/open/news_wss?token=test-token"
    assert websocket.connect_kwargs["open_timeout"] == 3.0


def test_opennews_client_requires_configured_token_without_echoing_value() -> None:
    client = OpenNewsFeedClient(token="")

    with pytest.raises(ValueError, match="OpenNews token is not configured"):
        client.fetch("opennews://subscribe")


def test_opennews_client_uses_fetch_clock_when_push_has_no_timestamp() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.update",
                "params": {
                    "id": "article-1",
                    "text": "Solana listing rumor accelerates",
                    "newsType": "CoinDesk",
                    "engineType": "news",
                    "link": "https://example.com/sol",
                },
            },
        ]
    )
    client = OpenNewsFeedClient(
        token="test-token",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=1,
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 1, "fetch_mode": "websocket"}},
    )

    assert result.entries[0]["published_at_ms"] == NOW_MS


def test_opennews_client_merges_ai_update_patch_by_article_id() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.update",
                "params": {
                    "id": "article-1",
                    "text": "Bitcoin ETF flows accelerate",
                    "newsType": "Bloomberg",
                    "engineType": "news",
                    "link": "https://example.com/story",
                    "ts": NOW_MS - 2_000,
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "news.ai_update",
                "params": {
                    "id": "article-1",
                    "coins": [{"symbol": "BTC", "score": 91, "signal": "long", "grade": "A"}],
                    "aiRating": {
                        "score": 91,
                        "grade": "A",
                        "signal": "long",
                        "summary": "ETF 资金流继续增强。",
                    },
                    "ts": NOW_MS - 1_000,
                },
            },
        ]
    )
    client = OpenNewsFeedClient(
        token="test-token",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=2,
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 2, "fetch_mode": "websocket"}},
    )

    assert len(result.entries) == 1
    assert result.entries[0]["id"] == "article-1"
    assert result.entries[0]["link"] == "https://example.com/story"
    assert result.entries[0]["title"] == "Bitcoin ETF flows accelerate"
    assert result.entries[0]["summary"] == "ETF 资金流继续增强。"
    assert result.entries[0]["provider_signal"]["status"] == "ready"
    assert result.entries[0]["provider_signal"]["score"] == 91
    assert result.entries[0]["provider_token_impacts"] == [
        {"symbol": "BTC", "market_type": None, "score": 91, "signal": "long", "grade": "A"}
    ]
    assert result.entries[0]["raw"]["link"] == "https://example.com/story"
    assert result.entries[0]["raw"]["aiRating"]["score"] == 91


def test_opennews_client_parses_iso_timestamp_from_live_push_shape() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.update",
                "params": {
                    "id": "2367468",
                    "text": "Token alert",
                    "newsType": "6551News",
                    "engineType": "news",
                    "link": "https://example.com/news",
                    "coins": [{"market_type": "cex", "symbol": "EX"}],
                    "ts": "2026-05-26T19:18:48.871+08:00",
                },
            },
        ]
    )
    client = OpenNewsFeedClient(
        token="test-token",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=1,
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 1, "fetch_mode": "websocket"}},
    )

    assert result.entries[0]["published_at_ms"] == int(
        datetime.fromisoformat("2026-05-26T19:18:48.871+08:00").timestamp() * 1000
    )


def test_opennews_client_keeps_live_push_without_external_link() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.update",
                "params": {
                    "id": "2367468",
                    "text": "OpenNews token alert",
                    "newsType": "6551News",
                    "engineType": "news",
                    "coins": [
                        {"market_type": "cex", "symbol": "BTC"},
                        {"market_type": "dex", "symbol": "SOL"},
                    ],
                    "ts": "2026-05-26T19:18:48.871+08:00",
                },
            },
        ]
    )
    client = OpenNewsFeedClient(
        token="test-token",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=1,
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 1, "fetch_mode": "websocket"}},
    )

    assert len(result.entries) == 1
    assert result.entries[0]["link"] == "opennews://item/2367468"
    assert result.entries[0]["title"] == "OpenNews token alert"
    assert result.entries[0]["provider_signal"]["status"] == "partial"
    assert result.entries[0]["provider_token_impacts"] == [
        {"symbol": "BTC", "market_type": "cex", "score": None, "signal": None, "grade": None},
        {"symbol": "SOL", "market_type": "dex", "score": None, "signal": None, "grade": None},
    ]


def test_opennews_client_keeps_source_item_key_as_observation_key_only() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.update",
                "params": {
                    "sourceItemKey": "transient-source-key",
                    "text": "OpenNews source-key-only alert",
                    "newsType": "6551News",
                    "engineType": "news",
                    "ts": NOW_MS - 1_000,
                },
            },
        ]
    )
    client = OpenNewsFeedClient(
        token="test-token",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=1,
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 1, "fetch_mode": "websocket"}},
    )

    entry = result.entries[0]
    assert "id" not in entry
    assert entry["guid"] == "transient-source-key"
    assert entry["link"] == "opennews://item/transient-source-key"
    assert "provider_article_id" not in entry
    assert "provider_article_key" not in entry
    assert entry["raw"] == {
        "sourceItemKey": "transient-source-key",
        "text": "OpenNews source-key-only alert",
        "newsType": "6551News",
        "engineType": "news",
        "ts": NOW_MS - 1_000,
    }


def test_opennews_client_preserves_source_item_key_when_official_id_exists() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.update",
                "params": {
                    "id": "2367422",
                    "sourceItemKey": "transient-source-key",
                    "text": "OpenNews alert with official id",
                    "newsType": "6551News",
                    "engineType": "news",
                    "link": "https://example.com/news/2367422",
                    "ts": NOW_MS - 1_000,
                },
            },
        ]
    )
    client = OpenNewsFeedClient(
        token="test-token",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=1,
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 1, "fetch_mode": "websocket"}},
    )

    entry = result.entries[0]
    assert entry["id"] == "2367422"
    assert entry["guid"] == "transient-source-key"
    assert entry["source_item_key"] == "transient-source-key"
    assert entry["provider_article_id"] == "2367422"
    assert entry["provider_article_key"] == "opennews:2367422"


def test_opennews_client_later_partial_patch_does_not_degrade_ready_payload() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.ai_update",
                "params": {
                    "id": "2367422",
                    "text": "Ready headline",
                    "newsType": "6551News",
                    "engineType": "news",
                    "link": "https://example.com/news/2367422",
                    "coins": [{"symbol": "BTC", "score": 90, "signal": "long", "grade": "A"}],
                    "aiRating": {
                        "status": "done",
                        "score": 90,
                        "signal": "long",
                        "summary": "Ready summary",
                        "enSummary": "Ready body",
                    },
                    "ts": NOW_MS - 2_000,
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "news.update",
                "params": {
                    "id": "2367422",
                    "sourceItemKey": "source-key-2367422",
                    "text": "Partial headline",
                    "newsType": "6551News",
                    "engineType": "news",
                    "link": "https://example.com/live",
                    "coins": [{"symbol": "BTC"}],
                    "ts": NOW_MS - 1_000,
                },
            },
        ]
    )
    client = OpenNewsFeedClient(
        token="test-token",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=2,
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 2, "fetch_mode": "websocket"}},
    )

    entry = result.entries[0]
    assert entry["source_item_key"] == "source-key-2367422"
    assert entry["link"] == "https://example.com/news/2367422"
    assert entry["title"] == "Ready headline"
    assert entry["summary"] == "Ready summary"
    assert entry["content"] == [{"value": "Ready body"}]
    assert entry["provider_signal"]["status"] == "ready"
    assert entry["provider_token_impacts"] == [
        {"symbol": "BTC", "market_type": None, "score": 90, "signal": "long", "grade": "A"}
    ]
    assert entry["raw"]["text"] == "Ready headline"
    assert entry["raw"]["aiRating"]["status"] == "done"


def test_opennews_client_hybrid_fetch_merges_ai_rating_for_partial_push() -> None:
    websocket = FakeWebSocket(
        recv_messages=[
            {"jsonrpc": "2.0", "id": "opennews_subscribe_1", "result": {"success": True}},
            {
                "jsonrpc": "2.0",
                "method": "news.update",
                "params": {
                    "id": "2378100",
                    "text": "Anthropic revenue runs ahead of OpenAI",
                    "newsType": "6551News",
                    "engineType": "news",
                    "coins": [
                        {"symbol": "ANTHROPIC", "market_type": "cex"},
                        {"symbol": "OPENAI", "market_type": "cex"},
                    ],
                    "ts": "2026-05-27T09:04:25.319+08:00",
                },
            },
        ]
    )
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
                    "coins": [
                        {"symbol": "ANTHROPIC", "market_type": "cex", "score": 75, "signal": "long", "grade": "A"},
                        {"symbol": "OPENAI", "market_type": "cex", "score": 65, "signal": "short", "grade": "B+"},
                    ],
                    "aiRating": {"status": "done", "score": 75, "signal": "long", "grade": "A"},
                    "ts": "2026-05-27T09:04:25.319+08:00",
                }
            ]
        }

    client = OpenNewsFeedClient(
        token="test-token",
        connect=lambda url, **kwargs: FakeConnect(url=url, websocket=websocket, kwargs=kwargs),
        post_json=fake_post_json,
        now_ms=lambda: NOW_MS,
    )

    result = client.fetch(
        "opennews://subscribe",
        limit=5,
        source={
            "fetch_policy_json": {
                "engineTypes": {"news": ["6551News"]},
                "hasCoin": True,
                "stream_timeout_seconds": 0.25,
                "max_messages": 1,
                "rest_limit": 5,
                "max_rest_pages": 1,
            }
        },
    )

    assert len(result.entries) == 1
    assert result.entries[0]["id"] == "2378100"
    assert result.entries[0]["provider_signal"]["status"] == "ready"
    assert result.entries[0]["provider_signal"]["score"] == 75
    assert result.entries[0]["provider_signal"]["direction"] == "bullish"
    assert result.entries[0]["provider_token_impacts"] == [
        {"symbol": "ANTHROPIC", "market_type": "cex", "score": 75, "signal": "long", "grade": "A"},
        {"symbol": "OPENAI", "market_type": "cex", "score": 65, "signal": "short", "grade": "B+"},
    ]
    assert result.feed["websocket_received"] == 1
    assert result.feed["rest_received"] == 1
    assert rest_requests == [
        {
            "url": "https://ai.6551.io/open/news_search",
            "token": "test-token",
            "body": {"limit": 5, "page": 1, "engineTypes": {"news": ["6551News"]}, "hasCoin": True},
        }
    ]


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
                "fetch_mode": "rest",
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


class FakeWebSocket:
    def __init__(self, *, recv_messages: list[dict[str, Any]]) -> None:
        self._recv_messages = list(recv_messages)
        self.sent_messages: list[dict[str, Any]] = []
        self.closed = False
        self.connected_url = ""
        self.connect_kwargs: dict[str, Any] = {}

    async def send(self, payload: str) -> None:
        self.sent_messages.append(json.loads(payload))

    async def recv(self) -> str:
        if not self._recv_messages:
            raise TimeoutError("no more messages")
        return json.dumps(self._recv_messages.pop(0))

    async def close(self) -> None:
        self.closed = True


class FakeConnect:
    def __init__(self, *, url: str, websocket: FakeWebSocket, kwargs: dict[str, Any]) -> None:
        self.url = url
        self.websocket = websocket
        self.kwargs = kwargs

    async def __aenter__(self) -> FakeWebSocket:
        self.websocket.connected_url = self.url
        self.websocket.connect_kwargs = dict(self.kwargs)
        return self.websocket

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.websocket.close()
