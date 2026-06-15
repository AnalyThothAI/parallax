from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker

WORKER_KEYS = manifest_names_for_factory("token_intel.py")


def construct_token_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not workers.token_radar_projection.enabled:
        return {}
    worker_name = "token_radar_projection"
    return {
        worker_name: TokenRadarProjectionWorker(
            name=worker_name,
            settings=workers.token_radar_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_emitter=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.token_radar_projection.wakes_on),
            enqueue_narrative_admission=bool(workers.narrative_admission.enabled),
        )
    }
