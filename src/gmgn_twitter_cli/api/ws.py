from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from ..collector.subscriptions import event_matches_handles, normalize_handles
from ..models import TwitterEvent
from ..store.sqlite import EventStore


@dataclass(eq=False)
class ClientSubscription:
    websocket: WebSocket
    handles: set[str] = field(default_factory=set)


class PublicWebSocketHub:
    def __init__(self, *, token: str, store: EventStore, default_replay_limit: int = 100):
        self.token = token
        self.store = store
        self.default_replay_limit = default_replay_limit
        self._clients: set[ClientSubscription] = set()

    async def publish(self, event: TwitterEvent) -> None:
        if not self._clients:
            return

        payload = _json_message({"type": "event", "event": event.to_dict()})
        stale_clients = []
        for client in list(self._clients):
            if not event_matches_handles(event, client.handles):
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
        replay_limit = _replay_limit(message.get("replay"), self.default_replay_limit)
        replay_events = self.store.recent_events(limit=replay_limit, handles=client.handles)
        for event in reversed(replay_events):
            await client.websocket.send_text(_json_message({"type": "event", "event": event}))


def _json_message(message: dict[str, Any]) -> str:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def _replay_limit(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, 1000))


async def _close_if_connected(websocket: WebSocket, *, code: int, reason: str) -> None:
    if websocket.client_state != WebSocketState.DISCONNECTED:
        await websocket.close(code=code, reason=reason)
