from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.narrative_intel.runtime.narrative_admission_worker import NarrativeAdmissionWorker

WORKER_KEYS = manifest_names_for_factory("narrative_intel.py")


def construct_narrative_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not workers.narrative_admission.enabled:
        return {}

    return {
        "narrative_admission": NarrativeAdmissionWorker(
            name="narrative_admission",
            settings=workers.narrative_admission,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_waiter=ctx.db.wake_listener("narrative_admission", workers.narrative_admission.wakes_on),
        )
    }


__all__ = ["WORKER_KEYS", "construct_narrative_intel_workers"]
