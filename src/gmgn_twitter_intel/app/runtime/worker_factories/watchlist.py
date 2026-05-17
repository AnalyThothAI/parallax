from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.domains.watchlist_intel.runtime.handle_summary_worker import HandleSummaryWorker

WORKER_KEYS = frozenset({"handle_summary"})


def construct_watchlist_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not (
        workers.handle_summary.enabled
        and ctx.settings.watchlist_handle_summary_configured
        and ctx.providers.watchlist_intel.summary_provider is not None
    ):
        return {}
    return {
        "handle_summary": HandleSummaryWorker(
            name="handle_summary",
            settings=workers.handle_summary,
            db=ctx.db,
            telemetry=ctx.telemetry,
            provider=ctx.providers.watchlist_intel.summary_provider,
            handles=ctx.settings.handles,
        )
    }
