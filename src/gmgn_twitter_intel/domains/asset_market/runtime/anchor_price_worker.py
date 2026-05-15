from __future__ import annotations

import asyncio
import time
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult

from ..services.anchor_price_observation import (
    anchor_price_empty_result,
    fetch_anchor_price_quotes,
    select_pending_anchor_price_rows,
    write_anchor_price_observations,
)


class AnchorPriceWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        cex_market: Any = None,
        dex_quote_market: Any = None,
        wake_bus: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.cex_market = cex_market
        self.dex_quote_market = dex_quote_market
        self.wake_bus = wake_bus

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        observed_at_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        result = await asyncio.to_thread(self._observe_once, observed_at_ms)
        if int(result.get("anchor_observations_written") or 0) > 0 and self.wake_bus is not None:
            for target in result.get("written_targets") or ():
                self.wake_bus.notify_market_observation_written(
                    target_type=str(target.get("target_type") or ""),
                    target_id=str(target.get("target_id") or ""),
                )
        return WorkerResult(
            processed=int(result.get("anchor_observations_written") or 0),
            failed=int(result.get("provider_errors") or 0),
            skipped=_anchor_skipped_count(result),
            notes={"result": result},
        )

    def _observe_once(self, now_ms: int) -> dict[str, Any]:
        with self.db.worker_session(self.name) as repos:
            rows = select_pending_anchor_price_rows(
                repos=repos,
                now_ms=now_ms,
                limit=max(1, int(getattr(self.settings, "batch_size", 100))),
            )
        result = anchor_price_empty_result(rows_selected=len(rows))
        cex_quotes, dex_quotes = fetch_anchor_price_quotes(
            rows=rows,
            cex_market=self.cex_market,
            dex_quote_market=self.dex_quote_market,
            result=result,
        )
        with self.db.worker_session(self.name) as repos:
            return write_anchor_price_observations(
                repos=repos,
                rows=rows,
                cex_quotes=cex_quotes,
                dex_quotes=dex_quotes,
                now_ms=now_ms,
                result=result,
            )


def _anchor_skipped_count(result: dict[str, Any]) -> int:
    return sum(
        int(result.get(key) or 0)
        for key in ("skipped_missing_pricefeed", "skipped_missing_provider", "skipped_missing_market")
    )
