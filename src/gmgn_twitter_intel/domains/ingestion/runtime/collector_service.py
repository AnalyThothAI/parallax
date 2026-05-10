from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Any

from loguru import logger

from gmgn_twitter_intel.domains.ingestion.providers import (
    EventPublisherProtocol,
    IngestStoreProtocol,
    UpstreamClientProtocol,
)
from gmgn_twitter_intel.domains.ingestion.services.normalizer import normalize_gmgn_payload, parse_gmgn_frame
from gmgn_twitter_intel.domains.ingestion.services.subscriptions import event_matches_handles, normalize_handles


@dataclass(slots=True)
class CollectorStatus:
    started_at_ms: int
    last_frame_at_ms: int | None = None
    last_event_at_ms: int | None = None
    last_matched_event_at_ms: int | None = None
    frames_received: int = 0
    twitter_events: int = 0
    matched_twitter_events: int = 0
    events_published: int = 0
    duplicate_twitter_events: int = 0
    duplicate_matched_twitter_events: int = 0
    parse_errors: int = 0

    def to_dict(self) -> dict[str, int | None]:
        return asdict(self)


class CollectorService:
    def __init__(
        self,
        *,
        handles: tuple[str, ...],
        store: IngestStoreProtocol,
        publisher: EventPublisherProtocol,
        upstream_client: UpstreamClientProtocol | None,
        snapshot_timeout: float = 0.5,
    ):
        self.handles = normalize_handles(handles)
        self.store = store
        self.publisher = publisher
        self.upstream_client = upstream_client
        self.snapshot_timeout = snapshot_timeout
        self._pending_snapshots: dict[str, asyncio.Task[None]] = {}
        self.status = CollectorStatus(started_at_ms=_now_ms())

    async def run(self) -> None:
        if self.upstream_client is None:
            raise RuntimeError("upstream_client is required")
        await self.upstream_client.run()

    async def stop(self) -> None:
        tasks = list(self._pending_snapshots.values())
        self._pending_snapshots.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def handle_frame(self, frame_data: Any, *, received_at_ms: int | None = None) -> None:
        received_at_ms = received_at_ms or _now_ms()
        self.status.frames_received += 1
        self.status.last_frame_at_ms = received_at_ms

        try:
            parsed = parse_gmgn_frame(frame_data)
        except Exception as exc:
            self.status.parse_errors += 1
            logger.warning(f"Failed to parse GMGN frame: {exc}")
            return

        if not parsed:
            return

        channel = parsed["channel"]
        await asyncio.to_thread(
            self.store.insert_raw_frame,
            source="gmgn",
            channel=channel,
            received_at_ms=received_at_ms,
            raw_payload_json=frame_data if isinstance(frame_data, str) else str(frame_data),
        )
        for item in parsed["data"]:
            if not isinstance(item, dict):
                continue
            await self._handle_item(channel, item, received_at_ms)

    async def _handle_item(self, channel: str, item: dict[str, Any], received_at_ms: int) -> None:
        if channel == "public_broadcast" or not item.get("tw"):
            await self._process_item(channel, item, received_at_ms)
            return

        internal_id = item.get("i")
        if not internal_id:
            await self._process_item(channel, item, received_at_ms)
            return

        if item.get("cp") == 1:
            pending_task = self._pending_snapshots.pop(str(internal_id), None)
            if pending_task:
                pending_task.cancel()
            await self._process_item(channel, item, received_at_ms)
            return

        if str(internal_id) not in self._pending_snapshots:
            self._pending_snapshots[str(internal_id)] = asyncio.create_task(
                self._dispatch_snapshot_after_timeout(channel, item, received_at_ms, str(internal_id))
            )

    async def _dispatch_snapshot_after_timeout(
        self,
        channel: str,
        item: dict[str, Any],
        received_at_ms: int,
        internal_id: str,
    ) -> None:
        try:
            await asyncio.sleep(self.snapshot_timeout)
            self._pending_snapshots.pop(internal_id, None)
            await self._process_item(channel, item, received_at_ms)
        except asyncio.CancelledError:
            raise

    async def _process_item(self, channel: str, item: dict[str, Any], received_at_ms: int) -> None:
        payload = {"channel": channel, "data": [item]}
        for event in normalize_gmgn_payload(payload, received_at_ms=received_at_ms):
            is_watched = event_matches_handles(event, self.handles)
            ingested = await asyncio.to_thread(self.store.ingest_event, event, is_watched=is_watched)
            if ingested.inserted:
                self.status.twitter_events += 1
                self.status.last_event_at_ms = received_at_ms
            else:
                self.status.duplicate_twitter_events += 1

            if not is_watched:
                continue
            if not ingested.inserted:
                self.status.duplicate_matched_twitter_events += 1
                continue
            self.status.last_matched_event_at_ms = received_at_ms
            self.status.matched_twitter_events += 1
            self.status.events_published += 1
            await self.publisher.publish(
                {
                    "type": "event",
                    "event": event.to_dict(),
                    "entities": ingested.entities,
                    "alerts": ingested.alerts,
                    "token_intents": ingested.token_intents,
                    "token_resolutions": ingested.token_resolutions,
                }
            )


def _now_ms() -> int:
    return int(time.time() * 1000)
