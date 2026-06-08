from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from threading import Lock
from typing import Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.cex_market_intel.providers import CexOiMarketProvider, CoinglassDerivativesProvider
from parallax.domains.cex_market_intel.services.binance_oi_radar_builder import (
    build_binance_oi_radar_rows,
)
from parallax.domains.cex_market_intel.services.cex_detail_snapshot_builder import (
    build_cex_detail_snapshot,
)
from parallax.domains.cex_market_intel.services.coinglass_detail_enricher import (
    enrich_rows_with_coinglass,
)


class CexOiRadarBoardWorker(WorkerBase):
    def __init__(
        self,
        *,
        oi_market: CexOiMarketProvider | None,
        coinglass_derivatives: CoinglassDerivativesProvider | None = None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.oi_market = oi_market
        self.coinglass_derivatives = coinglass_derivatives
        self.clock_ms = clock_ms or _now_ms
        self._local_run_lock = Lock()

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        if not self._local_run_lock.acquire(blocking=False):
            return WorkerResult(
                skipped=1,
                notes={
                    "reason": "previous_run_still_finishing",
                    "claimed": 0,
                    "queue_depth": 0,
                    "source_rows_scanned": 0,
                    "targets_loaded": 0,
                    "rows_written": 0,
                },
            )
        try:
            return self._run_once_sync_locked(now_ms=now_ms)
        finally:
            self._local_run_lock.release()

    def _run_once_sync_locked(self, *, now_ms: int | None = None) -> WorkerResult:
        if self.oi_market is None:
            return WorkerResult(
                skipped=1,
                notes={
                    "reason": "cex_market_unavailable",
                    "claimed": 0,
                    "queue_depth": 0,
                    "source_rows_scanned": 0,
                    "targets_loaded": 0,
                    "rows_written": 0,
                },
            )

        now = int(now_ms if now_ms is not None else self.clock_ms())
        period = str(getattr(self.settings, "period", "5m"))
        limit = max(1, min(int(getattr(self.settings, "universe_limit", self._batch_size())), self._batch_size()))
        with self._repository_session() as repos:
            universe = repos.cex_oi_radar.binance_usdt_perp_universe(limit=limit)

        if not universe:
            with self._repository_session() as repos:
                repos.cex_oi_radar.publish_board(
                    rows=[],
                    computed_at_ms=now,
                    period=period,
                    status="skipped",
                    notes={"reason": "empty_binance_universe"},
                )
            return WorkerResult(
                skipped=1,
                notes={
                    "reason": "empty_binance_universe",
                    "claimed": 0,
                    "queue_depth": 0,
                    "source_rows_scanned": 0,
                    "targets_loaded": 0,
                    "rows_written": 0,
                },
            )

        try:
            built = build_binance_oi_radar_rows(
                universe=universe,
                client=self.oi_market,
                now_ms=now,
                period=period,
                limit=limit,
            )
            rows = enrich_rows_with_coinglass(
                list(built["rows"]),
                client=self.coinglass_derivatives,
                now_ms=now,
                limit=int(getattr(self.settings, "coinglass_enrichment_limit", 0)),
                level_limit=int(getattr(self.settings, "coinglass_level_limit", 6)),
            )
            if not rows and int(built["failed"]) > 0:
                with self._repository_session() as repos:
                    repos.cex_oi_radar.record_attempt_failure(
                        computed_at_ms=now,
                        period=period,
                        notes={"reason": "all_symbols_failed", "failed_symbols": built["failed_symbols"][:20]},
                    )
                return WorkerResult(
                    failed=int(built["failed"]),
                    notes={
                        "universe_count": len(universe),
                        "status": "failed",
                        "claimed": len(universe),
                        "queue_depth": 0,
                        "source_rows_scanned": len(universe),
                        "targets_loaded": len(universe),
                        "rows_written": 0,
                        "failed_symbols": built["failed_symbols"][:20],
                    },
                )
            status = "success" if int(built["failed"]) == 0 else "partial"
            snapshots = [
                build_cex_detail_snapshot(row=row, computed_at_ms=now, period=period)
                for row in rows
                if row.get("native_market_id")
            ]
            with self._repository_session() as repos:
                publication = self._publish_board_and_detail(
                    repos,
                    rows=rows,
                    snapshots=snapshots,
                    computed_at_ms=now,
                    period=period,
                    status=status,
                    notes={"failed_symbols": built["failed_symbols"][:20], "detail_snapshot_count": len(snapshots)},
                )
            return WorkerResult(
                processed=len(rows),
                failed=int(built["failed"]),
                notes={
                    "universe_count": len(universe),
                    "status": status,
                    "claimed": len(universe),
                    "queue_depth": 0,
                    "source_rows_scanned": len(universe),
                    "targets_loaded": len(universe),
                    **publication,
                    "rows_written": int(publication["board_rows_written"]) + int(publication["detail_rows_written"]),
                },
            )
        except Exception as exc:
            with self._repository_session() as repos:
                repos.cex_oi_radar.record_attempt_failure(
                    computed_at_ms=now,
                    period=period,
                    notes={"reason": type(exc).__name__},
                )
            raise

    def _repository_session(self) -> AbstractContextManager[Any]:
        return cast(
            AbstractContextManager[Any],
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
            ),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 100)))

    def _publish_board_and_detail(
        self,
        repos: Any,
        *,
        rows: list[dict[str, Any]],
        snapshots: list[dict[str, Any]],
        computed_at_ms: int,
        period: str,
        status: str,
        notes: dict[str, Any],
    ) -> dict[str, Any]:
        with repos.transaction():
            board_result = repos.cex_oi_radar.publish_board_with_result(
                rows=rows,
                computed_at_ms=computed_at_ms,
                period=period,
                status=status,
                notes=notes,
                commit=False,
            )
            board_changed = bool(board_result.board_changed)
            board_rows_written = int(board_result.board_rows_written)
            detail_rows_written = (
                int(repos.cex_detail_snapshots.upsert_many(snapshots, commit=False)) if snapshots else 0
            )
        return {
            "board_changed": board_changed,
            "board_rows_written": board_rows_written,
            "detail_changed_count": detail_rows_written,
            "detail_rows_written": detail_rows_written,
        }


def _now_ms() -> int:
    return int(time.time() * 1000)
