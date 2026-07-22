from __future__ import annotations

from typing import Any, Protocol

from parallax.domains.evidence.interfaces import TwitterEvent
from parallax.domains.ingestion.interfaces import IngestedEvent


class IngestStoreProtocol(Protocol):
    def insert_raw_frame(self, **kwargs: Any) -> bool: ...

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent: ...


class EventPublisherProtocol(Protocol):
    async def publish(self, payload: dict[str, Any]) -> None: ...


class UpstreamClientProtocol(Protocol):
    async def run(self) -> None: ...

    async def aclose(self) -> None: ...

    def connection_state_payload(self) -> dict[str, Any]: ...


__all__ = [
    "EventPublisherProtocol",
    "IngestStoreProtocol",
    "UpstreamClientProtocol",
]
