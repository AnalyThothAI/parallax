from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.domains.closed_loop_harness.runtime.harness_ops_worker import HarnessOpsWorker

WORKER_KEYS = frozenset({"harness_ops"})


def construct_harness_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not workers.harness_ops.enabled:
        return {}
    return {
        "harness_ops": HarnessOpsWorker(
            name="harness_ops",
            settings=workers.harness_ops,
            db=ctx.db,
            telemetry=ctx.telemetry,
        )
    }
