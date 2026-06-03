from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker, unavailable_worker
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.pulse_lab.runtime.pulse_candidate_worker import PulseCandidateWorker

WORKER_KEYS = manifest_names_for_factory("pulse.py")


def construct_pulse_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not workers.pulse_candidate.enabled:
        return {}
    worker_name = "pulse_candidate"
    if not ctx.settings.pulse_agent_configured:
        return {worker_name: disabled_worker(ctx, worker_name)}
    if ctx.providers.pulse_lab.decision_provider is None:
        return {worker_name: unavailable_worker(ctx, worker_name, "missing_pulse_decision_provider")}
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
