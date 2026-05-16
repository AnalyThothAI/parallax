"""Async backfill worker for inline-pending event anchors.

The collector hot path persists ``enriched_events`` rows with
``capture_method = 'unavailable'`` and ``capture_reason = 'pending_backfill'``
whenever no fresh ``market_ticks`` row is available for the event's
target. This worker catches up by:

1. Listing pending rows older than ``min_age_ms`` (the wait gives the
   tier-1 stream / tier-2 poll a chance to land a fresher tick first).
2. Calling
   :meth:`EventMarketCaptureService.capture_backfill_quote` for each row
   inside ``asyncio.to_thread`` with a bounded
   ``asyncio.Semaphore(concurrency)``.
3. Persisting successful ticks to ``market_ticks`` and flipping the
   enriched row to ``capture_method = 'tier3_inline'`` /
   ``capture_reason = 'async_backfill'`` with the new ``tick_id``.

It is wake-driven only indirectly: the partial index on
``(capture_method, capture_reason, tick_id IS NULL, created_at_ms ASC)``
gives ``list_pending_backfill`` a cheap seek, so the worker can simply
poll on ``interval_seconds``.

The worker writes to ``market_ticks`` (append-only fact, multi-writer
safe) and ``enriched_events`` (PK uniqueness + dedicated trigger
allowance). It does *not* hold an advisory lock for that reason — same
pattern as ``market_tick_stream`` / ``market_tick_poll``.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.services.event_market_capture import (
    CaptureResult,
    EventMarketCaptureService,
)
from gmgn_twitter_intel.domains.asset_market.types import EnrichedEventCapture, MarketTick

DEFAULT_BATCH_SIZE = 50
DEFAULT_CONCURRENCY = 8
DEFAULT_MIN_AGE_MS = 250
DEFAULT_INTERVAL_SECONDS = 1.0


class EventAnchorBackfillWorker(WorkerBase):
    """Catch up unavailable/pending_backfill enriched events asynchronously."""

    worker_name = "event_anchor_backfill"

    def __init__(
        self,
        *,
        pool_bundle: Any | None = None,
        capture_service: EventMarketCaptureService | None = None,
        providers: Any | None = None,
        dex_quote_market: Any | None = None,
        message_cex_market: Any | None = None,
        wake_emitter: Any | None = None,
        wake_bus: Any | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        concurrency: int = DEFAULT_CONCURRENCY,
        min_age_ms: int = DEFAULT_MIN_AGE_MS,
        interval_seconds: float | None = None,
        clock: Any | None = None,
        name: str = "event_anchor_backfill",
        settings: Any | None = None,
        db: Any | None = None,
        telemetry: Any | None = None,
    ) -> None:
        resolved_settings = _settings(
            settings,
            interval_seconds=interval_seconds,
            batch_size=batch_size,
            concurrency=concurrency,
            min_age_ms=min_age_ms,
        )
        super().__init__(
            name=name,
            settings=resolved_settings,
            db=pool_bundle or db,
            telemetry=telemetry or object(),
        )
        self.clock = clock or _now_ms
        if capture_service is None:
            resolved_providers = providers or SimpleNamespace(
                dex_quote_market=dex_quote_market,
                message_cex_market=message_cex_market,
            )
            capture_service = EventMarketCaptureService(
                providers=resolved_providers,
                now_ms=lambda: int(self.clock()),
            )
        self._capture_service = capture_service
        self.wake_emitter = wake_emitter or wake_bus
        self.batch_size = max(1, int(getattr(resolved_settings, "batch_size", batch_size)))
        self.concurrency = max(1, int(getattr(resolved_settings, "concurrency", concurrency)))
        self.min_age_ms = max(0, int(getattr(resolved_settings, "min_age_ms", min_age_ms)))

    async def run_once(self) -> WorkerResult:
        now_ms = int(self.clock())
        rows = await asyncio.to_thread(self._list_pending, now_ms=now_ms)
        if not rows:
            return WorkerResult(
                processed=0,
                skipped=0,
                notes={"pending_selected": 0, "ticks_inserted": 0, "captures_attached": 0},
            )

        semaphore = asyncio.Semaphore(self.concurrency)
        results = await asyncio.gather(*(self._capture_one(row, semaphore) for row in rows))

        ticks: list[MarketTick] = []
        captures: list[EnrichedEventCapture] = []
        skipped_reasons: Counter[str] = Counter()
        for row, result in zip(rows, results, strict=True):
            if result.tick is None:
                skipped_reasons[result.capture.capture_reason or "unknown"] += 1
                continue
            ticks.append(result.tick)
            captures.append(
                replace(
                    result.capture,
                    capture_method="tier3_inline",
                    capture_reason="async_backfill",
                    event_id=str(row["event_id"]),
                    intent_id=str(row["intent_id"]),
                    resolution_id=str(row["resolution_id"]),
                )
            )

        inserted, attached_ticks = await asyncio.to_thread(self._persist, ticks=ticks, captures=captures)
        for tick in attached_ticks:
            _emit_wake(self.wake_emitter, target_type=tick.target_type, target_id=tick.target_id)
        attached = len(attached_ticks)
        return WorkerResult(
            processed=attached,
            skipped=len(rows) - attached,
            notes={
                "pending_selected": len(rows),
                "ticks_inserted": inserted,
                "captures_attached": attached,
                "skipped_reasons": dict(sorted(skipped_reasons.items())),
            },
        )

    async def _capture_one(
        self,
        row: Mapping[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> CaptureResult:
        resolution = _resolution_from_row(row)
        async with semaphore:
            return await asyncio.to_thread(
                self._capture_service.capture_backfill_quote,
                event_id=str(row["event_id"]),
                intent_id=str(row["intent_id"]),
                resolution_id=str(row["resolution_id"]),
                resolution=resolution,
                event_ms=int(row["t_event_ms"]),
            )

    def _list_pending(self, *, now_ms: int) -> list[dict[str, Any]]:
        with self.db.worker_session(self.name) as repos:
            rows = repos.enriched_events.list_pending_backfill(
                limit=self.batch_size,
                now_ms=now_ms,
                min_age_ms=self.min_age_ms,
            )
        return [dict(row) for row in rows]

    def _persist(
        self,
        *,
        ticks: Sequence[MarketTick],
        captures: Sequence[EnrichedEventCapture],
    ) -> tuple[int, list[MarketTick]]:
        if not ticks:
            return 0, []
        with self.db.worker_session(self.name) as repos:
            inserted = int(repos.market_ticks.insert_ticks(ticks))
            attached_ticks: list[MarketTick] = []
            for tick, capture in zip(ticks, captures, strict=True):
                if repos.enriched_events.attach_backfill_capture(capture):
                    attached_ticks.append(tick)
            _commit_if_supported(repos)
        return inserted, attached_ticks


def _resolution_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    target_type = str(row["target_type"])
    target_id = str(row["target_id"])
    resolution: dict[str, Any] = {"target_type": target_type, "target_id": target_id}
    if target_type == "chain_token":
        chain_id, _, token_address = target_id.rpartition(":")
        if chain_id:
            resolution["chain_id"] = chain_id.strip()
            resolution["token_address"] = token_address.strip()
    elif target_type == "cex_symbol":
        exchange, _, instrument = target_id.partition(":")
        if exchange:
            resolution["exchange"] = exchange.strip()
            resolution["instrument"] = instrument.strip()
    return resolution


def _emit_wake(wake_emitter: Any, *, target_type: str, target_id: str) -> None:
    if wake_emitter is None:
        return
    notify = getattr(wake_emitter, "notify_market_tick_written", None)
    if notify is None:
        return
    notify(target_type=target_type, target_id=target_id)


def _commit_if_supported(repos: Any) -> None:
    conn = getattr(repos, "conn", None)
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()
        return
    commit = getattr(repos, "commit", None)
    if callable(commit):
        commit()


def _settings(
    settings: Any | None,
    *,
    interval_seconds: float | None,
    batch_size: int,
    concurrency: int,
    min_age_ms: int,
) -> Any:
    if settings is None:
        return SimpleNamespace(
            enabled=True,
            interval_seconds=interval_seconds if interval_seconds is not None else DEFAULT_INTERVAL_SECONDS,
            timeout_seconds=120.0,
            batch_size=batch_size,
            concurrency=concurrency,
            min_age_ms=min_age_ms,
        )
    if interval_seconds is None:
        return settings
    try:
        settings.interval_seconds = interval_seconds
        return settings
    except Exception:
        values = dict(getattr(settings, "__dict__", {}))
        values["interval_seconds"] = interval_seconds
        return SimpleNamespace(**values)


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["EventAnchorBackfillWorker"]
