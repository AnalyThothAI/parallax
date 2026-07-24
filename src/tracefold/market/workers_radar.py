from __future__ import annotations

from tracefold.market.radar.projection_worker import TokenRadarProjectionWorker
from tracefold.platform.workers.factory import WorkerFactoryContext, disabled_worker
from tracefold.platform.workers.worker_base import WorkerBase


def construct_radar_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not workers.token_radar_projection.enabled:
        return {"token_radar_projection": disabled_worker(ctx, "token_radar_projection")}
    worker_name = "token_radar_projection"
    return {
        worker_name: TokenRadarProjectionWorker(
            name=worker_name,
            settings=workers.token_radar_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
        )
    }
