from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import (
    WorkerFactoryContext,
    intentionally_not_started_worker,
    unavailable_worker,
)
from parallax.app.runtime.worker_manifest import manifest_names_for_factory

WORKER_KEYS = manifest_names_for_factory("ingestion.py")


def construct_ingestion_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    if not ctx.collector_start_requested:
        return {"collector": intentionally_not_started_worker(ctx, "collector")}
    if not ctx.collector_enabled and ctx.settings.workers.collector.enabled:
        return {"collector": unavailable_worker(ctx, "collector", "missing_ingestion_upstream_client_factory")}
    if not ctx.collector_enabled:
        return {}
    return {"collector": ctx.collector}
