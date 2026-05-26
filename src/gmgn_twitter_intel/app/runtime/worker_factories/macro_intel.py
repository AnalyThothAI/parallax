from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.app.runtime.worker_manifest import manifest_names_for_factory
from gmgn_twitter_intel.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)

WORKER_KEYS = manifest_names_for_factory("macro_intel.py")


def construct_macro_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    settings = ctx.settings.workers.macro_view_projection
    if not settings.enabled:
        return {}
    return {
        "macro_view_projection": MacroViewProjectionWorker(
            name="macro_view_projection",
            settings=settings,
            db=ctx.db,
            telemetry=ctx.telemetry,
        )
    }


__all__ = ["WORKER_KEYS", "construct_macro_intel_workers"]
