from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from ..collector.subscriptions import event_matches_handles, normalize_handles
from ..models import TwitterEvent
from ..pipeline.token_extractor import normalize_ca
from ..storage.tweet_repository import TweetRepository


@dataclass(eq=False)
class ClientSubscription:
    websocket: WebSocket
    handles: set[str] = field(default_factory=set)
    cas: set[tuple[str, str]] = field(default_factory=set)
    symbols: set[str] = field(default_factory=set)


class PublicWebSocketHub:
    def __init__(self, *, token: str, store: TweetRepository, default_replay_limit: int = 100):
        self.token = token
        self.store = store
        self.default_replay_limit = default_replay_limit
        self._clients: set[ClientSubscription] = set()

    async def publish(self, event: TwitterEvent) -> None:
        if not self._clients:
            return

        event_payload = event.to_dict()
        payload = _json_message({"type": "event", "event": event_payload})
        stale_clients = []
        for client in list(self._clients):
            if not self._event_matches_subscription(event, client):
                continue
            try:
                await client.websocket.send_text(payload)
            except WebSocketDisconnect:
                stale_clients.append(client)
            except RuntimeError:
                stale_clients.append(client)

        for client in stale_clients:
            self._clients.discard(client)

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        client = ClientSubscription(websocket=websocket)
        try:
            await self._authenticate(websocket)
            self._clients.add(client)
            await websocket.send_text(_json_message({"type": "ready"}))
            while True:
                raw_message = await websocket.receive_text()
                await self._handle_client_message(client, raw_message)
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(client)

    async def _authenticate(self, websocket: WebSocket) -> None:
        try:
            raw_message = await asyncio.wait_for(websocket.receive_text(), timeout=10)
            message = json.loads(raw_message)
        except (TimeoutError, json.JSONDecodeError) as exc:
            await _close_if_connected(websocket, code=1008, reason="authentication required")
            raise WebSocketDisconnect(code=1008) from exc

        if message.get("type") != "auth" or message.get("token") != self.token:
            await _close_if_connected(websocket, code=1008, reason="authentication failed")
            raise WebSocketDisconnect(code=1008)

    async def _handle_client_message(self, client: ClientSubscription, raw_message: str) -> None:
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            await client.websocket.send_text(_json_message({"type": "error", "code": "invalid_json"}))
            return

        if message.get("type") != "subscribe":
            await client.websocket.send_text(_json_message({"type": "error", "code": "unsupported_message"}))
            return

        client.handles = normalize_handles(message.get("handles") or [])
        try:
            client.cas = _normalize_cas(message.get("cas") or message.get("ca") or [])
        except ValueError:
            await client.websocket.send_text(_json_message({"type": "error", "code": "invalid_ca"}))
            return
        client.symbols = _normalize_symbols(message.get("symbols") or message.get("tokens") or [])
        for symbol in client.symbols:
            candidates = self.store.symbol_ca_candidates(symbol)
            if len(candidates) > 1:
                await client.websocket.send_text(
                    _json_message({"type": "error", "code": "ambiguous_symbol", "candidates": candidates})
                )
                return
        replay_limit = _replay_limit(message.get("replay"), self.default_replay_limit)
        replay_events = self._replay_events(client, replay_limit)
        for event in reversed(replay_events):
            await client.websocket.send_text(_json_message({"type": "event", "event": event}))

    def _replay_events(self, client: ClientSubscription, limit: int) -> list[dict[str, Any]]:
        collected: dict[str, dict[str, Any]] = {}
        if client.cas or client.symbols:
            for chain, ca in client.cas:
                for event in self.store.recent_events(limit=limit, ca=ca, chain=chain):
                    collected[event["event_id"]] = event
            for symbol in client.symbols:
                for event in self.store.recent_events(limit=limit, symbol=symbol):
                    collected[event["event_id"]] = event
            events = list(collected.values())
            events.sort(key=lambda item: item.get("received_at_ms") or 0, reverse=True)
            return events[:limit]
        return self.store.recent_events(limit=limit, handles=client.handles)

    def _event_matches_subscription(self, event: TwitterEvent, client: ClientSubscription) -> bool:
        has_token_filters = bool(client.cas or client.symbols)
        if client.handles and event_matches_handles(event, client.handles):
            return True
        if not has_token_filters:
            return event_matches_handles(event, client.handles)
        rows = self.store.client.query_where(
            "tweet_entities",
            where=f"event_id = '{_sql_literal(event.event_id)}'",
        )
        for row in rows:
            if row.get("entity_type") == "ca" and (row.get("chain"), row.get("normalized_value")) in client.cas:
                return True
            if row.get("entity_type") == "symbol" and str(row.get("normalized_value") or "").upper() in client.symbols:
                return True
        return False


def _json_message(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def _replay_limit(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, 1000))


def _normalize_cas(raw: Any) -> set[tuple[str, str]]:
    values = raw if isinstance(raw, list) else [raw]
    normalized: set[tuple[str, str]] = set()
    for item in values:
        if not item:
            continue
        if isinstance(item, dict):
            value = str(item.get("ca") or item.get("address") or "")
            chain = item.get("chain")
        else:
            value = str(item)
            chain = None
        normalized.add(normalize_ca(value, chain=str(chain) if chain else None))
    return normalized


def _normalize_symbols(raw: Any) -> set[str]:
    values = raw if isinstance(raw, list) else [raw]
    symbols: set[str] = set()
    for item in values:
        if not item:
            continue
        value = str(item.get("symbol") or "") if isinstance(item, dict) else str(item)
        value = value.strip().lstrip("$").upper()
        if value and not value.startswith("0X"):
            symbols.add(value)
    return symbols


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


async def _close_if_connected(websocket: WebSocket, *, code: int, reason: str) -> None:
    if websocket.client_state != WebSocketState.DISCONNECTED:
        await websocket.close(code=code, reason=reason)
