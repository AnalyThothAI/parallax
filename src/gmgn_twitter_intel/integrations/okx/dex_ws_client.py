from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import websockets
from loguru import logger

from gmgn_twitter_intel.integrations.okx.dex_client import EVM_ADDRESS_RE


class OkxDexWsClientError(RuntimeError):
    pass


WS_CONNECTION_STATES = frozenset({"disconnected", "connecting", "authenticating", "subscribed", "streaming", "failed"})


@dataclass(frozen=True, slots=True)
class OkxDexPriceInfoUpdate:
    chain_id: str
    address: str
    observed_at_ms: int
    price_usd: float | None = None
    market_cap_usd: float | None = None
    liquidity_usd: float | None = None
    volume_24h_usd: float | None = None
    open_interest_usd: float | None = None
    holders: int | None = None
    raw: dict[str, Any] | None = None


class OkxDexWebSocketMarketProvider:
    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        secret_key: str,
        passphrase: str,
        subscription_limit: int,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.subscription_limit = max(1, int(subscription_limit))
        self.connection_state = "disconnected"
        self.last_state_change_at_ms = _now_ms()

    def connection_state_payload(self) -> dict[str, Any]:
        return {
            "provider": "okx_dex_ws",
            "state": self.connection_state,
            "last_state_change_at_ms": self.last_state_change_at_ms,
        }

    async def stream_price_info(
        self,
        targets: list[dict[str, str]],
    ) -> AsyncIterator[OkxDexPriceInfoUpdate]:
        args = [
            {
                "channel": "price-info",
                "chainIndex": str(target.get("chainIndex") or target.get("chain_id") or ""),
                "tokenContractAddress": _normalize_address(
                    target.get("tokenContractAddress") or target.get("address") or ""
                ),
            }
            for target in targets[: self.subscription_limit]
            if str(target.get("chainIndex") or target.get("chain_id") or "").strip()
            and str(target.get("tokenContractAddress") or target.get("address") or "").strip()
        ]
        if not args:
            return
        try:
            self._set_connection_state("connecting")
            async with websockets.connect(self.url, ping_interval=20, close_timeout=5) as websocket:
                self._set_connection_state("authenticating")
                await websocket.send(json.dumps(_login_payload(self.api_key, self.secret_key, self.passphrase)))
                await _wait_for_login(websocket)
                await websocket.send(json.dumps({"op": "subscribe", "args": args}))
                self._set_connection_state("subscribed")
                while True:
                    raw_message = await websocket.recv()
                    message = json.loads(str(raw_message))
                    if isinstance(message, dict) and message.get("event") == "error":
                        raise OkxDexWsClientError(_error_message(message))
                    for row in _rows_from_message(message):
                        update = _price_info_update_from_row(row)
                        if update is not None:
                            self._set_connection_state("streaming")
                            yield update
        except asyncio.CancelledError:
            self._set_connection_state("disconnected")
            raise
        except Exception:
            self._set_connection_state("failed")
            raise

    def _set_connection_state(self, state: str) -> None:
        if state not in WS_CONNECTION_STATES:
            raise ValueError(f"unsupported OKX DEX WS state: {state}")
        if state == self.connection_state:
            return
        self.connection_state = state
        self.last_state_change_at_ms = _now_ms()
        logger.info(
            "OKX DEX WS connection state changed | state={} last_state_change_at_ms={}",
            self.connection_state,
            self.last_state_change_at_ms,
        )


def _login_payload(api_key: str, secret_key: str, passphrase: str) -> dict[str, Any]:
    timestamp = _okx_timestamp()
    return {
        "op": "login",
        "args": [
            {
                "apiKey": api_key,
                "passphrase": passphrase,
                "timestamp": timestamp,
                "sign": _login_signature(secret_key=secret_key, timestamp=timestamp),
            }
        ],
    }


async def _wait_for_login(websocket: Any) -> None:
    while True:
        raw_message = await websocket.recv()
        message = json.loads(str(raw_message))
        if not isinstance(message, dict):
            continue
        if message.get("event") == "error":
            raise OkxDexWsClientError(_error_message(message))
        if message.get("event") == "login":
            code = str(message.get("code") or "")
            if code and code != "0":
                raise OkxDexWsClientError(_error_message(message))
            return


def _rows_from_message(message: Any) -> list[dict[str, Any]]:
    if not isinstance(message, dict):
        return []
    arg = message.get("arg")
    context = arg if isinstance(arg, dict) else {}
    data = message.get("data")
    if isinstance(data, list):
        return [_with_message_context(row, context) for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [_with_message_context(data, context)]
    return [message]


def _with_message_context(row: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not context:
        return row
    return {**context, **row}


def _price_info_update_from_row(row: dict[str, Any]) -> OkxDexPriceInfoUpdate | None:
    if row.get("event") == "error":
        raise OkxDexWsClientError(_error_message(row))
    chain_index = _text(row.get("chainIndex") or row.get("chain_index"))
    address = _text(row.get("tokenContractAddress") or row.get("tokenAddress") or row.get("address"))
    observed_at_ms = _int(row.get("time") or row.get("timestamp") or row.get("ts") or row.get("observedAtMs"))
    if not chain_index or not address or observed_at_ms is None:
        return None
    return OkxDexPriceInfoUpdate(
        chain_id=chain_index,
        address=_normalize_address(address),
        observed_at_ms=observed_at_ms,
        price_usd=_float(row.get("price") or row.get("priceUsd") or row.get("priceUSD")),
        market_cap_usd=_float(row.get("marketCap") or row.get("marketCapUsd") or row.get("marketCapUSD")),
        liquidity_usd=_float(row.get("liquidity") or row.get("liquidityUsd") or row.get("liquidityUSD")),
        volume_24h_usd=_float(row.get("volume24H") or row.get("volume24h") or row.get("volume24hUsd")),
        open_interest_usd=_float(row.get("openInterestUsd") or row.get("openInterestUSD")),
        holders=_int(row.get("holders") or row.get("holderCount")),
        raw=dict(row),
    )


def _login_prehash(timestamp: str) -> str:
    return f"{timestamp}GET/users/self/verify"


def _login_signature(*, secret_key: str, timestamp: str) -> str:
    digest = hmac.new(
        secret_key.encode("utf-8"),
        _login_prehash(timestamp).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _okx_timestamp() -> str:
    return str(int(time.time()))


def _now_ms() -> int:
    return int(time.time() * 1000)


def _error_message(row: dict[str, Any]) -> str:
    code = _text(row.get("code")) or "unknown"
    message = _text(row.get("msg") or row.get("message")) or "OKX DEX websocket error"
    return f"{code}: {message}"


def _normalize_address(address: Any) -> str:
    text = str(address or "").strip()
    return text.lower() if EVM_ADDRESS_RE.match(text) else text


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
