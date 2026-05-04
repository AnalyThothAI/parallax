from __future__ import annotations

import asyncio
import time
from threading import RLock

from loguru import logger

from ..storage.sqlite_client import transaction
from .narrative_seed_builder import NarrativeSeedBuilder
from .narrative_token_linker import NarrativeTokenLinker


class EnrichmentWorker:
    def __init__(
        self,
        *,
        evidence,
        entities,
        signals,
        enrichment,
        tokens,
        client,
        publisher=None,
        write_lock: RLock | None = None,
        poll_interval: float = 2.0,
    ):
        self.evidence = evidence
        self.entities = entities
        self.signals = signals
        self.enrichment = enrichment
        self.tokens = tokens
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

        with self.write_lock:
            event = self.evidence.events_by_ids([str(job["event_id"])]).get(str(job["event_id"]))
        if event is None:
            with self.write_lock:
                self.enrichment.fail_job(job=job, error="event_not_found")
            return True

        with self.write_lock:
            entities = self.entities.entities_for_event(str(job["event_id"]))
        request = {"event_id": job["event_id"], "job_type": job["job_type"]}
        try:
            result = await self.client.enrich_event(event=event, entities=entities)
        except Exception as exc:
            with self.write_lock:
                self.enrichment.fail_job(job=job, error=str(exc))
            return True

        with self.write_lock:
            stored = self.enrichment.complete_job(
                job=job,
                event=event,
                result=result,
                provider=self.client.provider,
                model=self.client.model,
                request=request,
            )

        seeds: list[dict] = []
        links: list[dict] = []
        try:
            with self.write_lock:
                seeds, links = self._materialize_narrative_links(event=event, result=result)
        except Exception as exc:
            logger.exception(f"narrative link materialization failed event_id={event.get('event_id')}: {exc}")

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
            if links:
                await self.publisher.publish(
                    {
                        "type": "narrative_link_update",
                        "event": event,
                        "seeds": seeds,
                        "links": links,
                    }
                )
        return True

    def _materialize_narrative_links(self, *, event: dict, result) -> tuple[list[dict], list[dict]]:
        if not event.get("is_watched"):
            return [], []
        seed_builder = NarrativeSeedBuilder(self.enrichment)
        linker = NarrativeTokenLinker(
            evidence=self.evidence,
            signals=self.signals,
            enrichment=self.enrichment,
            tokens=self.tokens,
        )
        links: list[dict] = []
        with transaction(self.enrichment.conn):
            seeds = seed_builder.build_for_event(event=event, result=result)
            for seed in seeds:
                for window in ("5m", "1h", "24h"):
                    links.extend(linker.link_seed(seed=seed, window=window, commit=False))
        return seeds, links


def _now_ms() -> int:
    return int(time.time() * 1000)
