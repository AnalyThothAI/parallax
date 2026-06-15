from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.macro_intel.runtime.macro_daily_brief_projection_worker import (
    MacroDailyBriefProjectionWorker,
)
from parallax.domains.macro_intel.runtime.macro_sync_worker import MacroSyncWorker
from parallax.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)
from parallax.integrations.macrodata.runner import MacrodataBundleRunner

WORKER_KEYS = manifest_names_for_factory("macro_intel.py")


def construct_macro_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    constructed: dict[str, WorkerBase] = {}
    workers = ctx.settings.workers
    if workers.macro_sync.enabled and ctx.settings.macrodata_enabled:
        worker_name = "macro_sync"
        constructed[worker_name] = MacroSyncWorker(
            name=worker_name,
            settings=workers.macro_sync,
            db=ctx.db,
            telemetry=ctx.telemetry,
            settings_root=ctx.settings,
            wake_emitter=ctx.wake_bus,
            runner=MacrodataBundleRunner(settings=ctx.settings),
        )
    elif workers.macro_sync.enabled:
        constructed["macro_sync"] = disabled_worker(ctx, "macro_sync")
    if workers.macro_view_projection.enabled:
        worker_name = "macro_view_projection"
        constructed[worker_name] = MacroViewProjectionWorker(
            name=worker_name,
            settings=workers.macro_view_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_emitter=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.macro_view_projection.wakes_on),
        )
    if workers.macro_daily_brief_projection.enabled:
        worker_name = "macro_daily_brief_projection"
        constructed[worker_name] = MacroDailyBriefProjectionWorker(
            name=worker_name,
            settings=workers.macro_daily_brief_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.macro_daily_brief_projection.wakes_on),
        )
    return constructed


__all__ = ["WORKER_KEYS", "construct_macro_intel_workers"]
