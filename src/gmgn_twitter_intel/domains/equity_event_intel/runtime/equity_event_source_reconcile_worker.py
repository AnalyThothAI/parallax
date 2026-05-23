from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.equity_event_intel.services.source_reconcile import (
    build_source_reconcile_payloads,
)


class EquityEventSourceReconcileWorker(WorkerBase):
    def __init__(
        self,
        *,
        equity_settings: Any,
        wake_bus: Any | None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.equity_settings = equity_settings
        self.wake_bus = wake_bus
        self.clock_ms = clock_ms or _now_ms

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        with self._repository_session() as repos:
            payloads = build_source_reconcile_payloads(
                settings=self.equity_settings,
                registry_lookup=repos.registry.find_us_equity_symbol,
                now_ms=now,
            )
            sources = repos.equity_events.reconcile_sources(
                sources=payloads.sources,
                universe_members=payloads.universe_members,
                now_ms=now,
                commit=False,
            )
            expected_events = repos.equity_events.reconcile_expected_events(
                expected_events=payloads.expected_events,
                scoped_source_ids=payloads.expected_event_source_ids,
                now_ms=now,
                commit=False,
            )
            repos.conn.commit()

        count = len(sources)
        if self.wake_bus is not None:
            self.wake_bus.notify_equity_event_sources_reconciled(count=count)
        return WorkerResult(
            processed=count,
            notes={
                "sources": count,
                "universe_members": len(payloads.universe_members),
                "expected_events": len(expected_events),
            },
        )

    def _repository_session(self):
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )


def _now_ms() -> int:
    return int(time.time() * 1000)
