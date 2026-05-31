from __future__ import annotations

from typing import Any, Protocol

from parallax.domains.evidence.interfaces import TwitterEvent
from parallax.domains.ingestion.interfaces import IngestedEvent


class IngestStoreProtocol(Protocol):
    def insert_raw_frame(self, **kwargs: Any) -> bool: ...

    def ingest_event(self, event: TwitterEvent, *, is_watched: bool) -> IngestedEvent: ...

    def event_token_resolutions(self, event_id: str) -> list[dict[str, Any]]: ...


class EventPublisherProtocol(Protocol):
    async def publish(self, payload: dict[str, Any]) -> None: ...


class UpstreamClientProtocol(Protocol):
    async def run(self) -> None: ...


__all__ = [
    "EventPublisherProtocol",
    "IngestStoreProtocol",
    "UpstreamClientProtocol",
]
