from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.app.runtime.worker_manifest import manifest_names_for_factory
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_brief_worker import EquityEventBriefWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_evidence_hydration_worker import (
    EquityEventEvidenceHydrationWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_fetch_worker import EquityEventFetchWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_page_projection_worker import (
    EquityEventPageProjectionWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_process_worker import EquityEventProcessWorker
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_source_reconcile_worker import (
    EquityEventSourceReconcileWorker,
)
from gmgn_twitter_intel.domains.equity_event_intel.runtime.equity_event_story_projection_worker import (
    EquityEventStoryProjectionWorker,
)

WORKER_KEYS = manifest_names_for_factory("equity_event_intel.py")


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
    if workers.equity_event_evidence_hydration.enabled and document_provider is not None:
        worker_name = "equity_event_evidence_hydration"
        constructed[worker_name] = EquityEventEvidenceHydrationWorker(
            name=worker_name,
            settings=workers.equity_event_evidence_hydration,
            db=ctx.db,
            telemetry=ctx.telemetry,
            document_provider=document_provider,
            wake_bus=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.equity_event_evidence_hydration.wakes_on),
        )
    if workers.equity_event_process.enabled:
        worker_name = "equity_event_process"
        constructed[worker_name] = EquityEventProcessWorker(
            name=worker_name,
            settings=workers.equity_event_process,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_bus=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.equity_event_process.wakes_on),
        )
    if workers.equity_event_story_projection.enabled:
        worker_name = "equity_event_story_projection"
        constructed[worker_name] = EquityEventStoryProjectionWorker(
            name=worker_name,
            settings=workers.equity_event_story_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_bus=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.equity_event_story_projection.wakes_on),
        )
    brief_provider = getattr(equity_providers, "brief_provider", None)
    if workers.equity_event_brief.enabled and ctx.settings.equity_event_brief_configured and brief_provider is not None:
        worker_name = "equity_event_brief"
        constructed[worker_name] = EquityEventBriefWorker(
            name=worker_name,
            settings=workers.equity_event_brief,
            db=ctx.db,
            telemetry=ctx.telemetry,
            provider=brief_provider,
            wake_bus=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.equity_event_brief.wakes_on),
        )
    if workers.equity_event_page_projection.enabled:
        worker_name = "equity_event_page_projection"
        constructed[worker_name] = EquityEventPageProjectionWorker(
            name=worker_name,
            settings=workers.equity_event_page_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_bus=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.equity_event_page_projection.wakes_on),
        )
    return constructed
