from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.cex_market_intel.runtime.cex_oi_radar_board_worker import (
    CexOiRadarBoardWorker,
)

WORKER_KEYS = manifest_names_for_factory("cex_market_intel.py")


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
            coinglass=_coinglass_client(settings),
        )
    }


def _coinglass_client(settings):
    if int(getattr(settings, "coinglass_enrichment_limit", 0)) <= 0:
        return None
    try:
        from coinglass_cli.client import CoinglassClient
    except Exception:
        return None
    return CoinglassClient()
