from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from ..market.gmgn_openapi_client import GmgnOpenApiError
from ..storage.postgres_client import transaction


class MarketObservationWorker:
    def __init__(
        self,
        *,
        client,
        repository_session: Callable[[], AbstractContextManager[Any]],
        poll_interval: float = 1.0,
    ):
        self.repository_session = repository_session
        self.client = client
        self.poll_interval = max(0.2, float(poll_interval))
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                processed = await self.process_one()
            except Exception as exc:
                logger.exception(f"market observation worker loop failed: {exc}")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped.set()

    async def process_one(self, *, now_ms: int | None = None) -> bool:
        now = now_ms if now_ms is not None else _now_ms()
        with self.repository_session() as repos:
            observation = repos.market_observations.claim_next(now_ms=now)
        if observation is None:
            return False

        if self.client is None:
            with self.repository_session() as repos:
                repos.market_observations.complete(
                    observation,
                    snapshot_id=None,
                    status="provider_not_configured",
                    provider=None,
                    now_ms=now,
                )
            return True

        try:
            lookup = self.client.lookup_token_info(
                chain=str(observation["chain"]),
                address=str(observation["address"]),
            )
        except GmgnOpenApiError as exc:
            with self.repository_session() as repos:
                repos.market_observations.fail(
                    observation,
                    error=str(exc),
                    status="rate_limited" if _is_rate_limited(exc) else "provider_error",
                    now_ms=now,
                )
            return True
        except Exception as exc:
            with self.repository_session() as repos:
                repos.market_observations.fail(observation, error=str(exc), status="provider_error", now_ms=now)
            return True

        if lookup.info is None:
            with self.repository_session() as repos:
                repos.market_observations.complete(
                    observation,
                    snapshot_id=None,
                    status="provider_not_found",
                    provider=_provider_name(self.client),
                    now_ms=now,
                )
            return True

        status = "cached" if lookup.cache_status == "hit" else "ready"
        with self.repository_session() as repos, transaction(repos.conn):
            identity = repos.tokens.upsert_openapi_token_info(
                event_id=str(observation["event_id"]),
                info=lookup.info,
                received_at_ms=int(observation["target_received_at_ms"]),
                source_channel=str(observation["source_channel"]),
                commit=False,
            )
            snapshot = repos.tokens.market_snapshot_for_event(
                token_id=identity.token_id,
                event_id=str(observation["event_id"]),
            )
            repos.market_observations.complete(
                observation,
                snapshot_id=str(snapshot["snapshot_id"]) if snapshot else None,
                status=status,
                provider=_provider_name(self.client),
                now_ms=now,
                commit=False,
            )
        return True


def _is_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate" in text


def _provider_name(client: Any) -> str:
    return str(getattr(client, "provider", "gmgn_openapi"))


def _now_ms() -> int:
    return int(time.time() * 1000)
