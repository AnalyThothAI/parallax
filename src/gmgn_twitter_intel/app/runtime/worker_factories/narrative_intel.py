from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker import MentionSemanticsWorker
from gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker import (
    TokenDiscussionDigestWorker,
)

WORKER_KEYS = frozenset({"mention_semantics", "token_discussion_digest"})


def construct_narrative_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    provider = getattr(getattr(ctx.providers, "narrative_intel", None), "narrative_provider", None)
    if not ctx.settings.narrative_intel_configured or provider is None:
        return {}

    constructed: dict[str, WorkerBase] = {}
    if workers.mention_semantics.enabled:
        constructed["mention_semantics"] = MentionSemanticsWorker(
            name="mention_semantics",
            settings=workers.mention_semantics,
            db=ctx.db,
            telemetry=ctx.telemetry,
            provider=provider,
            wake_bus=ctx.wake_bus,
        )
    if workers.token_discussion_digest.enabled:
        constructed["token_discussion_digest"] = TokenDiscussionDigestWorker(
            name="token_discussion_digest",
            settings=workers.token_discussion_digest,
            db=ctx.db,
            telemetry=ctx.telemetry,
            provider=provider,
        )
    return constructed


__all__ = ["WORKER_KEYS", "construct_narrative_intel_workers"]
