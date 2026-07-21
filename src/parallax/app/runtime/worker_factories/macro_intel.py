from __future__ import annotations

from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker
from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker
from parallax.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)
from parallax.integrations.macrodata.runner import MacrodataBundleRunner
from parallax.platform.runtime.worker_base import WorkerBase


def construct_macro_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    constructed: dict[str, WorkerBase] = {}
    workers = ctx.settings.workers
    if not workers.macro_sync.enabled:
        constructed["macro_sync"] = disabled_worker(ctx, "macro_sync")
    elif ctx.settings.providers.macrodata.enabled:
        worker_name = "macro_sync"
        constructed[worker_name] = MacroSyncWorker(
            name=worker_name,
            settings=workers.macro_sync,
            db=ctx.db,
            telemetry=ctx.telemetry,
            settings_root=ctx.settings,
            runner=MacrodataBundleRunner(settings=ctx.settings),
        )
    else:
        constructed["macro_sync"] = disabled_worker(ctx, "macro_sync")
    if workers.macro_view_projection.enabled:
        worker_name = "macro_view_projection"
        constructed[worker_name] = MacroViewProjectionWorker(
            name=worker_name,
            settings=workers.macro_view_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
        )
    else:
        constructed["macro_view_projection"] = disabled_worker(ctx, "macro_view_projection")
    return constructed


__all__ = ["construct_macro_intel_workers"]
