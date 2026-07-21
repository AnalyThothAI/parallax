from __future__ import annotations

from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker
from parallax.app.runtime.worker_manifest import require_worker_manifest
from parallax.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker
from parallax.platform.runtime.worker_base import WorkerBase


def construct_token_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
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
            wake_waiter=ctx.db.wake_listener(worker_name, require_worker_manifest(worker_name).wakes_on),
        )
    }
