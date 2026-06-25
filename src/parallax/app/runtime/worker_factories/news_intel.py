from __future__ import annotations

import time
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker, unavailable_worker
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.news_intel.runtime.news_fetch_worker import NewsFetchWorker
from parallax.domains.news_intel.runtime.news_item_brief_worker import NewsItemBriefWorker
from parallax.domains.news_intel.runtime.news_item_process_worker import NewsItemProcessWorker
from parallax.domains.news_intel.runtime.news_page_projection_worker import NewsPageProjectionWorker
from parallax.domains.news_intel.runtime.news_source_quality_projection_worker import (
    NewsSourceQualityProjectionWorker,
)
from parallax.domains.news_intel.runtime.news_story_brief_worker import NewsStoryBriefWorker
from parallax.domains.token_intel.interfaces import TokenIdentityLookupResult
from parallax.domains.token_intel.services.deterministic_token_resolver import (
    DeterministicResolution,
    DeterministicTokenResolver,
    MentionKeys,
)

WORKER_KEYS = manifest_names_for_factory("news_intel.py")
NEWS_ITEM_BRIEF_WAKE_CHANNELS: tuple[str, ...] = ()
NEWS_PAGE_PROJECTION_WAKE_CHANNELS: tuple[str, ...] = (
    "news_item_written",
    "news_item_processed",
    "news_story_brief_updated",
    "news_page_dirty",
)


def construct_news_intel_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    if not ctx.settings.news_intel.enabled:
        return {
            name: disabled_worker(ctx, name)
            for name in (
                "news_fetch",
                "news_item_process",
                "news_item_brief",
                "news_story_brief",
                "news_page_projection",
                "news_source_quality_projection",
            )
            if getattr(workers, name).enabled
        }

    constructed: dict[str, WorkerBase] = {}
    news_providers = ctx.providers.news_intel
    feed_client = news_providers.feed_client
    if workers.news_fetch.enabled:
        if feed_client is not None:
            constructed["news_fetch"] = NewsFetchWorker(
                name="news_fetch",
                settings=workers.news_fetch,
                db=ctx.db,
                telemetry=ctx.telemetry,
                news_settings=ctx.settings.news_intel,
                wake_emitter=ctx.wake_bus,
                feed_client=feed_client,
            )
        else:
            constructed["news_fetch"] = unavailable_worker(ctx, "news_fetch", "missing_news_intel_feed_client")

    if workers.news_item_process.enabled:
        worker_name = "news_item_process"
        constructed["news_item_process"] = NewsItemProcessWorker(
            name=worker_name,
            settings=workers.news_item_process,
            db=ctx.db,
            telemetry=ctx.telemetry,
            identity_lookup=_RuntimeTokenIdentityLookup(
                db=ctx.db,
                statement_timeout_seconds=workers.news_item_process.statement_timeout_seconds,
            ),
            wake_emitter=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.news_item_process.wakes_on),
        )

    brief_provider = news_providers.brief_provider
    if workers.news_item_brief.enabled:
        worker_name = "news_item_brief"
        if not ctx.settings.news_item_brief_configured:
            constructed[worker_name] = disabled_worker(ctx, worker_name)
        elif brief_provider is not None:
            constructed[worker_name] = NewsItemBriefWorker(
                name=worker_name,
                settings=workers.news_item_brief,
                db=ctx.db,
                telemetry=ctx.telemetry,
                provider=brief_provider,
                wake_waiter=ctx.db.wake_listener(worker_name, NEWS_ITEM_BRIEF_WAKE_CHANNELS),
            )
        else:
            constructed[worker_name] = unavailable_worker(ctx, worker_name, "missing_news_item_brief_provider")

    if workers.news_story_brief.enabled:
        worker_name = "news_story_brief"
        if not ctx.settings.news_story_brief_configured:
            constructed[worker_name] = disabled_worker(ctx, worker_name)
        elif brief_provider is not None:
            constructed[worker_name] = NewsStoryBriefWorker(
                name=worker_name,
                settings=workers.news_story_brief,
                db=ctx.db,
                telemetry=ctx.telemetry,
                provider=brief_provider,
                wake_emitter=ctx.wake_bus,
                wake_waiter=ctx.db.wake_listener(worker_name, workers.news_story_brief.wakes_on),
            )
        else:
            constructed[worker_name] = unavailable_worker(ctx, worker_name, "missing_news_story_brief_provider")

    if workers.news_page_projection.enabled:
        worker_name = "news_page_projection"
        constructed["news_page_projection"] = NewsPageProjectionWorker(
            name=worker_name,
            settings=workers.news_page_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_waiter=ctx.db.wake_listener(worker_name, NEWS_PAGE_PROJECTION_WAKE_CHANNELS),
        )

    if workers.news_source_quality_projection.enabled:
        worker_name = "news_source_quality_projection"
        constructed["news_source_quality_projection"] = NewsSourceQualityProjectionWorker(
            name=worker_name,
            settings=workers.news_source_quality_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_emitter=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.news_source_quality_projection.wakes_on),
        )
    return constructed


class _RuntimeTokenIdentityLookup:
    def __init__(self, *, db: Any, statement_timeout_seconds: float | None) -> None:
        self.db = db
        self.statement_timeout_seconds = statement_timeout_seconds

    def resolve_address(self, *, chain_id: str | None, address: str) -> TokenIdentityLookupResult:
        normalized_chain = _resolver_chain_id(chain_id)
        return self._resolve(
            intent_id=f"news-address:{normalized_chain or 'any'}:{address.lower()}",
            keys=MentionKeys(chain_id=normalized_chain, address=address),
            observed_symbol=None,
        )

    def resolve_symbol(self, *, symbol: str) -> TokenIdentityLookupResult:
        normalized_symbol = str(symbol or "").strip().lstrip("$").upper()
        return self._resolve(
            intent_id=f"news-symbol:{normalized_symbol}",
            keys=MentionKeys(symbol=normalized_symbol),
            observed_symbol=normalized_symbol or None,
        )

    def _resolve(
        self,
        *,
        intent_id: str,
        keys: MentionKeys,
        observed_symbol: str | None,
    ) -> TokenIdentityLookupResult:
        decision_time_ms = int(time.time() * 1000)
        with self.db.worker_session(
            "news_item_process",
            statement_timeout_seconds=self.statement_timeout_seconds,
        ) as repos:
            resolution = DeterministicTokenResolver(registry=repos.registry).resolve(
                intent_id=intent_id,
                event_id="news-intel",
                keys=keys,
                decision_time_ms=decision_time_ms,
            )
        return _lookup_result(resolution, observed_symbol=observed_symbol)


def _lookup_result(
    resolution: DeterministicResolution,
    *,
    observed_symbol: str | None,
) -> TokenIdentityLookupResult:
    return TokenIdentityLookupResult(
        resolution_status=resolution.resolution_status,
        target_type=resolution.target_type,
        target_id=resolution.target_id,
        display_symbol=observed_symbol,
        display_name=None,
        reason_codes=list(resolution.reason_codes),
        candidate_targets=_candidate_targets(resolution),
    )


def _candidate_targets(resolution: DeterministicResolution) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    for candidate_id in resolution.candidate_ids:
        target_type = resolution.target_type if candidate_id == resolution.target_id else None
        targets.append({"target_type": target_type, "target_id": candidate_id})
    return targets


def _resolver_chain_id(chain_id: str | None) -> str | None:
    normalized = str(chain_id or "").strip().lower()
    if normalized in {"", "evm", "evm_unknown", "unknown"}:
        return None
    if normalized in {"eth", "ethereum", "eip155:1"}:
        return "eip155:1"
    if normalized in {"base", "eip155:8453"}:
        return "eip155:8453"
    if normalized in {"bsc", "bnb", "bnb chain", "eip155:56"}:
        return "eip155:56"
    if normalized in {"sol", "solana"}:
        return "solana"
    if normalized in {"ton", "toncoin"}:
        return "ton"
    return normalized


__all__ = ["WORKER_KEYS", "construct_news_intel_workers"]
