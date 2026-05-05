from __future__ import annotations

import asyncio
import time
from threading import RLock

from loguru import logger

from .notification_models import NotificationCandidate

SEVERITY_RANK = {"info": 0, "warning": 1, "high": 2, "critical": 3}


class NotificationWorker:
    def __init__(
        self,
        *,
        repository,
        rule_engine,
        publisher=None,
        delivery_channels: dict | None = None,
        write_lock: RLock | None = None,
        poll_interval: float = 5.0,
    ):
        self.repository = repository
        self.rule_engine = rule_engine
        self.publisher = publisher
        self.delivery_channels = delivery_channels or {}
        self.write_lock = write_lock or RLock()
        self.poll_interval = max(0.5, float(poll_interval))
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                created = await self.process_once()
            except Exception as exc:
                logger.exception(f"notification worker loop failed: {exc}")
                created = []
            if not created:
                await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped.set()

    async def process_once(self, *, now_ms: int | None = None) -> list[dict]:
        now = int(now_ms if now_ms is not None else _now_ms())
        with self.write_lock:
            candidates = self.rule_engine.evaluate(now_ms=now)
            created: list[dict] = []
            for candidate in candidates:
                row = self._insert_candidate(candidate)
                if row is None:
                    continue
                self._enqueue_external_deliveries(row, candidate)
                created.append(row)

        if self.publisher is not None:
            for row in created:
                await self.publisher.publish({"type": "notification", "notification": row})
        return created

    def _insert_candidate(self, candidate: NotificationCandidate) -> dict | None:
        return self.repository.insert_notification(
            dedup_key=candidate.dedup_key,
            rule_id=candidate.rule_id,
            severity=candidate.severity,
            title=candidate.title,
            body=candidate.body,
            entity_type=candidate.entity_type,
            entity_key=candidate.entity_key,
            author_handle=candidate.author_handle,
            symbol=candidate.symbol,
            chain=candidate.chain,
            address=candidate.address,
            event_id=candidate.event_id,
            source_table=candidate.source_table,
            source_id=candidate.source_id,
            occurrence_at_ms=candidate.occurrence_at_ms,
            payload=candidate.payload,
            channels=candidate.channels,
        )

    def _enqueue_external_deliveries(self, row: dict, candidate: NotificationCandidate) -> None:
        for channel_id in candidate.channels:
            if channel_id == "in_app":
                continue
            channel = self.delivery_channels.get(channel_id)
            if channel is None or not channel.enabled:
                continue
            if channel.provider in {"apprise", "pushdeer"} and not channel.url:
                continue
            if SEVERITY_RANK.get(candidate.severity, 0) < SEVERITY_RANK.get(channel.min_severity, 1):
                continue
            self.repository.enqueue_delivery(
                notification_id=str(row["notification_id"]),
                channel_id=channel_id,
                provider=channel.provider,
                max_attempts=channel.max_attempts,
                commit=False,
            )
        self.repository.conn.commit()


def _now_ms() -> int:
    return int(time.time() * 1000)
