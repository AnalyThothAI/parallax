from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext, unavailable_worker
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.cex_market_intel.runtime.cex_oi_radar_board_worker import (
    CexOiRadarBoardWorker,
)

WORKER_KEYS = manifest_names_for_factory("cex_market_intel.py")


def construct_cex_market_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    settings = ctx.settings.workers.cex_oi_radar_board
    if not settings.enabled:
        return {}
    cex_providers = ctx.providers.cex_market_intel
    oi_market = cex_providers.oi_market
    coinglass_derivatives = cex_providers.coinglass_derivatives
    if oi_market is None:
        return {
            "cex_oi_radar_board": unavailable_worker(
                ctx,
                "cex_oi_radar_board",
                "missing_cex_oi_market_provider",
            )
        }
    return {
        "cex_oi_radar_board": CexOiRadarBoardWorker(
            name="cex_oi_radar_board",
            settings=settings,
            db=ctx.db,
            telemetry=ctx.telemetry,
            oi_market=oi_market,
            coinglass_derivatives=coinglass_derivatives,
        )
    }
