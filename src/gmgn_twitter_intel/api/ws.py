from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from ..collector.subscriptions import normalize_handles
from ..pipeline.entity_extractor import normalize_ca


@dataclass(eq=False)
class ClientSubscription:
    websocket: WebSocket
    handles: set[str] = field(default_factory=set)
    cas: set[tuple[str, str]] = field(default_factory=set)
    symbols: set[str] = field(default_factory=set)


class PublicWebSocketHub:
    def __init__(
        self,
        *,
        token: str,
        evidence,
        entities,
        signals,
        enrichment,
        default_replay_limit: int = 100,
    ):
        self.token = token
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.enrichment = enrichment
        self.default_replay_limit = default_replay_limit
        self._clients: set[ClientSubscription] = set()

    async def publish(self, payload: dict[str, Any]) -> None:
        if not self._clients:
            return

        message = _json_message(payload)
        stale_clients = []
        for client in list(self._clients):
            if not self._payload_matches_subscription(payload, client):
                continue
            try:
                await client.websocket.send_text(message)
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
        replay_limit = _replay_limit(message.get("replay"), self.default_replay_limit)
        replay_events = self._replay_events(client, replay_limit)
        for payload in reversed(replay_events):
            await client.websocket.send_text(_json_message(payload))

    def _replay_events(self, client: ClientSubscription, limit: int) -> list[dict[str, Any]]:
        collected: dict[str, dict[str, Any]] = {}
        if client.cas or client.symbols:
            for chain, ca in client.cas:
                for event in self.evidence.recent_events(limit=limit, ca=ca, chain=chain):
                    collected[event["event_id"]] = self._payload_for_event(event)
            for symbol in client.symbols:
                for event in self.evidence.recent_events(limit=limit, symbol=symbol):
                    collected[event["event_id"]] = self._payload_for_event(event)
            payloads = list(collected.values())
            payloads.sort(key=lambda item: item["event"].get("received_at_ms") or 0, reverse=True)
            return payloads[:limit]
        return [
            self._payload_for_event(event)
            for event in self.evidence.recent_events(limit=limit, handles=client.handles)
        ]

    def _payload_matches_subscription(self, payload: dict[str, Any], client: ClientSubscription) -> bool:
        has_token_filters = bool(client.cas or client.symbols)
        if client.handles and _event_handle(payload.get("event")) in client.handles:
            return True
        if not has_token_filters:
            return not client.handles
        for entity in payload.get("entities") or []:
            ca_key = (entity.get("chain"), entity.get("normalized_value"))
            if entity.get("entity_type") == "ca" and ca_key in client.cas:
                return True
            symbol = str(entity.get("normalized_value") or "").upper()
            if entity.get("entity_type") == "symbol" and symbol in client.symbols:
                return True
        return False

    def _payload_for_event(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = str(event["event_id"])
        return {
            "type": "event",
            "event": event,
            "entities": self.entities.entities_for_event(event_id),
            "alerts": self.signals.alerts_for_event(event_id),
            "enrichment": self.enrichment.enrichment_for_event(event_id),
        }


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


def _event_handle(event: Any) -> str | None:
    if not isinstance(event, dict):
        return None
    if event.get("author_handle"):
        return str(event["author_handle"]).lower()
    author = event.get("author")
    if isinstance(author, dict) and author.get("handle"):
        return str(author["handle"]).lower()
    return None


async def _close_if_connected(websocket: WebSocket, *, code: int, reason: str) -> None:
    if websocket.client_state != WebSocketState.DISCONNECTED:
        await websocket.close(code=code, reason=reason)
