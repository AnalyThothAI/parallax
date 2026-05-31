from __future__ import annotations

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext
from parallax.app.runtime.worker_manifest import manifest_names_for_factory

WORKER_KEYS = manifest_names_for_factory("ingestion.py")


def construct_ingestion_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    if not ctx.collector_enabled:
        return {}
    return {"collector": ctx.collector}
