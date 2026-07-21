from __future__ import annotations

from parallax.app.runtime.worker_factories import (
    WorkerFactoryContext,
    disabled_worker,
    intentionally_not_started_worker,
    unavailable_worker,
)
from parallax.platform.runtime.worker_base import WorkerBase


def construct_ingestion_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    if not ctx.settings.workers.collector.enabled:
        return {"collector": disabled_worker(ctx, "collector")}
    if not ctx.collector_start_requested:
        return {"collector": intentionally_not_started_worker(ctx, "collector")}
    if not ctx.collector_enabled:
        return {"collector": unavailable_worker(ctx, "collector", "missing_ingestion_upstream_client_factory")}
    if ctx.collector is None:
        return {"collector": unavailable_worker(ctx, "collector", "missing_collector_service")}
    return {"collector": ctx.collector}
