from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker import EnrichmentWorker
from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_service import HandleSummaryTriggerConfig

WORKER_KEYS = frozenset({"enrichment"})


def construct_enrichment_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not (workers.enrichment.enabled and ctx.settings.llm_configured):
        return {}
    return {
        "enrichment": EnrichmentWorker(
            name="enrichment",
            settings=workers.enrichment,
            db=ctx.db,
            telemetry=ctx.telemetry,
            client=ctx.providers.social_enrichment.event_enrichment,
            publisher=ctx.hub,
            watchlist_summary_config=HandleSummaryTriggerConfig(
                signal_threshold=workers.handle_summary.signal_threshold,
                time_threshold_ms=workers.handle_summary.time_threshold_ms,
                min_interval_ms=workers.handle_summary.min_interval_ms,
                input_limit=workers.handle_summary.input_limit,
                window_days=workers.handle_summary.window_days,
                max_attempts=workers.handle_summary.max_attempts,
            )
            if workers.handle_summary.enabled
            else None,
        )
    }
