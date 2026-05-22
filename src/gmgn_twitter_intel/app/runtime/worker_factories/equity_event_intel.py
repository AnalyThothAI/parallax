from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext

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
    del ctx
    return {}
