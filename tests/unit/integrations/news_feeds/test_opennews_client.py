from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from gmgn_twitter_intel.integrations.news_feeds.opennews_client import OpenNewsFeedClient

NOW_MS = 1_779_000_000_000


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
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 1}},
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
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 2}},
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
        source={"fetch_policy_json": {"stream_timeout_seconds": 0.25, "max_messages": 1}},
    )

    assert result.entries[0]["published_at_ms"] == int(
        datetime.fromisoformat("2026-05-26T19:18:48.871+08:00").timestamp() * 1000
    )


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
