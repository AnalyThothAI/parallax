from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.pulse_lab.runtime.pulse_candidate_worker import PulseCandidateWorker

WORKER_KEYS = manifest_names_for_factory("pulse.py")


def construct_pulse_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not (workers.pulse_candidate.enabled and ctx.settings.pulse_agent_configured):
        return {}
    worker_name = "pulse_candidate"
    return {
        worker_name: PulseCandidateWorker(
            name=worker_name,
            settings=workers.pulse_candidate,
            db=ctx.db,
            telemetry=ctx.telemetry,
            decision_client=ctx.providers.pulse_lab.decision_provider,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.pulse_candidate.wakes_on),
        )
    }
