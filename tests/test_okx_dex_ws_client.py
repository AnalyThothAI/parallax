from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from typing import Any

import pytest

from gmgn_twitter_intel.integrations.okx import dex_ws_client
from gmgn_twitter_intel.integrations.okx.dex_ws_client import (
    OkxDexWebSocketMarketProvider,
    OkxDexWsClientError,
    _login_prehash,
    _login_signature,
    _okx_timestamp,
    _price_info_update_from_row,
    _rows_from_message,
)


def test_okx_dex_ws_login_uses_expected_signature_prehash():
    timestamp = "1704876947"

    assert _login_prehash(timestamp) == "1704876947GET/users/self/verify"
    expected = base64.b64encode(
        hmac.new(
            b"test-secret",
            b"1704876947GET/users/self/verify",
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    assert _login_signature(secret_key="test-secret", timestamp=timestamp) == expected


def test_okx_dex_ws_timestamp_is_unix_seconds():
    timestamp = _okx_timestamp()

    assert timestamp.isdigit()
    assert len(timestamp) == 10


def test_okx_dex_ws_price_info_normalizes_market_fields():
    update = _price_info_update_from_row(
        {
            "chainIndex": "501",
            "tokenContractAddress": "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
            "time": "1700086420000",
            "price": "0.111",
            "marketCap": "110900000",
            "liquidity": "4820000",
            "volume24H": "27400000",
            "holders": "57141",
        }
    )

    assert update is not None
    assert update.chain_id == "501"
    assert update.address == "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
    assert update.observed_at_ms == 1_700_086_420_000
    assert update.price_usd == 0.111
    assert update.market_cap_usd == 110_900_000
    assert update.liquidity_usd == 4_820_000
    assert update.volume_24h_usd == 27_400_000
    assert update.holders == 57_141


def test_okx_dex_ws_price_info_merges_subscription_arg_fields():
    rows = _rows_from_message(
        {
            "arg": {
                "channel": "price-info",
                "chainIndex": "501",
                "tokenContractAddress": "8jpRiwbUXLWH4yFQaF2TBDUkWDkfKWtBMX95sibTpump",
            },
            "data": [
                {
                    "time": "1778627069103",
                    "price": "0.00001733",
                    "marketCap": "17336.16",
                    "liquidity": "10416.54",
                    "holders": "224",
                }
            ],
        }
    )

    update = _price_info_update_from_row(rows[0])

    assert update is not None
    assert update.chain_id == "501"
    assert update.address == "8jpRiwbUXLWH4yFQaF2TBDUkWDkfKWtBMX95sibTpump"
    assert update.observed_at_ms == 1_778_627_069_103


def test_okx_dex_ws_unauthenticated_error_is_surfaceable():
    with pytest.raises(OkxDexWsClientError, match="60011"):
        _price_info_update_from_row({"event": "error", "code": "60011", "msg": "Please log in"})


def test_okx_dex_ws_exposes_connection_state_payload():
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test/ws",
        api_key="key",
        secret_key="secret",
        passphrase="pass",
        subscription_limit=10,
    )

    initial = provider.connection_state_payload()
    provider._set_connection_state("connecting")
    changed = provider.connection_state_payload()

    assert initial["state"] == "disconnected"
    assert changed["provider"] == "okx_dex_ws"
    assert changed["state"] == "connecting"
    assert isinstance(changed["last_state_change_at_ms"], int)


def test_okx_dex_ws_provider_subscribes_and_unsubscribes_without_reconnecting(monkeypatch):
    fake_ws = FakeWebSocket(messages=[_login_ok(), _price_message("1", "0xabc", price="1.23")])
    connect_calls: list[dict[str, Any]] = []

    def fake_connect(*args, **kwargs):
        return _FakeConnect(fake_ws, connect_calls, args=args, kwargs=kwargs)

    monkeypatch.setattr(dex_ws_client.websockets, "connect", fake_connect)
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test",
        api_key="key",
        secret_key="secret",
        passphrase="pass",
        subscription_limit=100,
    )

    async def scenario() -> None:
        await provider.ensure_connected()
        await provider.replace_subscriptions([{"chainIndex": "1", "tokenContractAddress": "0xabc"}])
        await provider.replace_subscriptions([{"chainIndex": "1", "tokenContractAddress": "0xdef"}])
        await provider.aclose()

    asyncio.run(scenario())

    assert len(connect_calls) == 1
    assert _sent_ops(fake_ws) == ["login", "subscribe", "unsubscribe", "subscribe"]
    sent_objects = [json.loads(payload) for payload in fake_ws.sent]
    # Subscriptions/unsubscriptions carry the right token contract addresses
    subscribe_ops = [obj for obj in sent_objects if obj.get("op") == "subscribe"]
    unsubscribe_ops = [obj for obj in sent_objects if obj.get("op") == "unsubscribe"]
    assert subscribe_ops[0]["args"][0]["tokenContractAddress"] == "0xabc"
    assert unsubscribe_ops[0]["args"][0]["tokenContractAddress"] == "0xabc"
    assert subscribe_ops[1]["args"][0]["tokenContractAddress"] == "0xdef"
    assert fake_ws.closed is True


def test_okx_dex_ws_provider_reconnects_after_recv_failure(monkeypatch):
    first_ws = FakeWebSocket(messages=[_login_ok(), RuntimeError("connection closed")])
    second_ws = FakeWebSocket(messages=[_login_ok()])
    websockets = [first_ws, second_ws]
    connect_calls: list[dict[str, Any]] = []

    def fake_connect(*args, **kwargs):
        return _FakeConnect(websockets[len(connect_calls)], connect_calls, args=args, kwargs=kwargs)

    monkeypatch.setattr(dex_ws_client.websockets, "connect", fake_connect)
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test",
        api_key="key",
        secret_key="secret",
        passphrase="pass",
        subscription_limit=100,
    )

    async def scenario() -> None:
        await provider.replace_subscriptions([{"chainIndex": "1", "tokenContractAddress": "0xabc"}])
        iterator = provider.iter_price_info().__aiter__()
        with pytest.raises(RuntimeError, match="connection closed"):
            await iterator.__anext__()
        await provider.ensure_connected()
        await provider.aclose()

    asyncio.run(scenario())

    assert len(connect_calls) == 2
    assert first_ws.closed is True
    assert second_ws.closed is True


def test_okx_dex_ws_provider_no_longer_exposes_legacy_stream_price_info_method():
    # Regression: hard cut removed the per-call reconnect API. This test is the only place
    # in the codebase that mentions the old name to make sure it cannot creep back.
    provider = OkxDexWebSocketMarketProvider(
        url="wss://example.test",
        api_key="k",
        secret_key="s",
        passphrase="p",
        subscription_limit=10,
    )

    assert not hasattr(provider, "stream_price_info")


def _login_ok() -> str:
    return json.dumps({"event": "login", "code": "0"})


def _price_message(chain_index: str, address: str, *, price: str) -> str:
    return json.dumps(
        {
            "arg": {
                "channel": "price-info",
                "chainIndex": chain_index,
                "tokenContractAddress": address,
            },
            "data": [
                {
                    "time": "1778627069103",
                    "price": price,
                }
            ],
        }
    )


def _sent_ops(fake_ws: FakeWebSocket) -> list[str]:
    ops: list[str] = []
    for payload in fake_ws.sent:
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        op = obj.get("op")
        if isinstance(op, str):
            ops.append(op)
    return ops


class FakeWebSocket:
    def __init__(self, *, messages: list[str | BaseException]) -> None:
        self._messages = list(messages)
        self.sent: list[str] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def recv(self) -> str:
        if not self._messages:
            # Block forever (simulates idle ws). Tests must not await recv past their
            # asserted message count.
            await asyncio.Event().wait()
            raise RuntimeError("unreachable")
        message = self._messages.pop(0)
        if isinstance(message, BaseException):
            raise message
        return message

    async def close(self) -> None:
        self.closed = True


class _FakeConnect:
    def __init__(
        self,
        fake_ws: FakeWebSocket,
        connect_calls: list[dict[str, Any]],
        *,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        self._fake_ws = fake_ws
        self._connect_calls = connect_calls
        self._args = args
        self._kwargs = kwargs

    def __await__(self):
        async def _connect() -> FakeWebSocket:
            self._connect_calls.append({"args": self._args, "kwargs": self._kwargs})
            return self._fake_ws

        return _connect().__await__()

    async def __aenter__(self) -> FakeWebSocket:
        self._connect_calls.append({"args": self._args, "kwargs": self._kwargs})
        return self._fake_ws

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        await self._fake_ws.close()
        return False
