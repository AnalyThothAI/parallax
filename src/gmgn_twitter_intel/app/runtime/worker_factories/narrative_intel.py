from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.app.runtime.worker_manifest import manifest_names_for_factory
from gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker import MentionSemanticsWorker
from gmgn_twitter_intel.domains.narrative_intel.runtime.narrative_admission_worker import NarrativeAdmissionWorker
from gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker import (
    TokenDiscussionDigestWorker,
)

WORKER_KEYS = manifest_names_for_factory("narrative_intel.py")


def construct_narrative_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    provider = getattr(getattr(ctx.providers, "narrative_intel", None), "narrative_provider", None)
    constructed: dict[str, WorkerBase] = {}
    if workers.narrative_admission.enabled:
        constructed["narrative_admission"] = NarrativeAdmissionWorker(
            name="narrative_admission",
            settings=workers.narrative_admission,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_bus=ctx.wake_bus,
        )
    if not ctx.settings.narrative_intel_configured or provider is None:
        return constructed

    if workers.mention_semantics.enabled:
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
    if workers.token_discussion_digest.enabled:
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
