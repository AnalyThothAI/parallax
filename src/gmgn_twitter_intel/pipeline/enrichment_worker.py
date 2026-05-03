from __future__ import annotations

import asyncio
import time
from threading import RLock

from loguru import logger


class EnrichmentWorker:
    def __init__(
        self,
        *,
        evidence,
        entities,
        enrichment,
        client,
        publisher=None,
        write_lock: RLock | None = None,
        poll_interval: float = 2.0,
    ):
        self.evidence = evidence
        self.entities = entities
        self.enrichment = enrichment
        self.client = client
        self.publisher = publisher
        self.write_lock = write_lock or RLock()
        self.poll_interval = max(0.2, float(poll_interval))
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                processed = await self.process_one()
            except Exception as exc:
                logger.exception(f"enrichment worker loop failed: {exc}")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped.set()

    async def process_one(self, *, now_ms: int | None = None) -> bool:
        with self.write_lock:
            job = self.enrichment.claim_next_job(now_ms=now_ms or _now_ms())
        if job is None:
            return False

        event = self.evidence.events_by_ids([str(job["event_id"])]).get(str(job["event_id"]))
        if event is None:
            with self.write_lock:
                self.enrichment.fail_job(job=job, error="event_not_found")
            return True

        entities = self.entities.entities_for_event(str(job["event_id"]))
        request = {"event_id": job["event_id"], "job_type": job["job_type"]}
        try:
            result = await self.client.enrich_event(event=event, entities=entities)
            with self.write_lock:
                stored = self.enrichment.complete_job(
                    job=job,
                    event=event,
                    result=result,
                    provider=self.client.provider,
                    model=self.client.model,
                    request=request,
                )
        except Exception as exc:
            with self.write_lock:
                self.enrichment.fail_job(job=job, error=str(exc))
            return True

        if self.publisher is not None:
            await self.publisher.publish(
                {
                    "type": "enrichment_update",
                    "event": event,
                    "enrichment": stored,
                    "narratives": stored.get("narratives", []),
                    "alerts": stored.get("alerts", []),
                }
            )
        return True


def _now_ms() -> int:
    return int(time.time() * 1000)
