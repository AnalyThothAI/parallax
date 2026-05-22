from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_fetch_worker import EquityEventFetchWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_source_reconcile_worker import (
    EquityEventSourceReconcileWorker,
)

WORKER_KEYS = frozenset(
    {
        "equity_event_source_reconcile",
        "equity_event_fetch",
        "equity_event_process",
        "equity_event_story_projection",
        "equity_event_brief",
        "equity_event_page_projection",
    }
)


def construct_equity_event_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not ctx.settings.equity_event_intel.enabled:
        return {}

    constructed: dict[str, WorkerBase] = {}
    if workers.equity_event_source_reconcile.enabled:
        constructed["equity_event_source_reconcile"] = EquityEventSourceReconcileWorker(
            name="equity_event_source_reconcile",
            settings=workers.equity_event_source_reconcile,
            db=ctx.db,
            telemetry=ctx.telemetry,
            equity_settings=ctx.settings.equity_event_intel,
            wake_bus=ctx.wake_bus,
        )

    equity_providers = getattr(ctx.providers, "equity_event_intel", None)
    document_provider = getattr(equity_providers, "document_provider", None)
    if workers.equity_event_fetch.enabled and document_provider is not None:
        worker_name = "equity_event_fetch"
        constructed["equity_event_fetch"] = EquityEventFetchWorker(
            name=worker_name,
            settings=workers.equity_event_fetch,
            db=ctx.db,
            telemetry=ctx.telemetry,
            document_provider=document_provider,
            wake_bus=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.equity_event_fetch.wakes_on),
        )
    return constructed
