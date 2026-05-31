from __future__ import annotations

from parallax.app.runtime.narrative_bulk_analysis_gate import narrative_bulk_analysis_enabled
from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.narrative_intel.runtime.mention_semantics_worker import MentionSemanticsWorker
from parallax.domains.narrative_intel.runtime.narrative_admission_worker import NarrativeAdmissionWorker
from parallax.domains.narrative_intel.runtime.token_discussion_digest_worker import (
    TokenDiscussionDigestWorker,
)

WORKER_KEYS = manifest_names_for_factory("narrative_intel.py")


def construct_narrative_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    provider = getattr(getattr(ctx.providers, "narrative_intel", None), "narrative_provider", None)
    if not narrative_bulk_analysis_enabled(ctx.settings) or provider is None:
        return {}

    constructed: dict[str, WorkerBase] = {}
    constructed["narrative_admission"] = NarrativeAdmissionWorker(
        name="narrative_admission",
        settings=workers.narrative_admission,
        db=ctx.db,
        telemetry=ctx.telemetry,
        wake_bus=ctx.wake_bus,
    )

    worker_name = "mention_semantics"
    constructed["mention_semantics"] = MentionSemanticsWorker(
        name=worker_name,
        settings=workers.mention_semantics,
        db=ctx.db,
        telemetry=ctx.telemetry,
        provider=provider,
        wake_bus=ctx.wake_bus,
        wake_waiter=ctx.db.wake_listener(worker_name, workers.mention_semantics.wakes_on),
    )
    worker_name = "token_discussion_digest"
    constructed["token_discussion_digest"] = TokenDiscussionDigestWorker(
        name=worker_name,
        settings=workers.token_discussion_digest,
        db=ctx.db,
        telemetry=ctx.telemetry,
        provider=provider,
        wake_waiter=ctx.db.wake_listener(worker_name, workers.token_discussion_digest.wakes_on),
    )
    return constructed


__all__ = ["WORKER_KEYS", "construct_narrative_intel_workers"]
