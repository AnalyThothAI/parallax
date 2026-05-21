from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.domains.cex_market_intel.runtime.cex_oi_radar_board_worker import (
    CexOiRadarBoardWorker,
)

WORKER_KEYS = frozenset({"cex_oi_radar_board"})


def construct_cex_market_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    settings = ctx.settings.workers.cex_oi_radar_board
    if not settings.enabled:
        return {}
    return {
        "cex_oi_radar_board": CexOiRadarBoardWorker(
            name="cex_oi_radar_board",
            settings=settings,
            db=ctx.db,
            telemetry=ctx.telemetry,
            cex_market=getattr(ctx.providers.asset_market, "cex_market", None),
        )
    }
