from __future__ import annotations

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.app.runtime.worker_manifest import manifest_names_for_factory
from gmgn_twitter_intel.domains.asset_market.runtime.asset_profile_refresh_worker import AssetProfileRefreshWorker
from gmgn_twitter_intel.domains.asset_market.runtime.event_anchor_backfill_worker import EventAnchorBackfillWorker
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_current_projection_worker import (
    MarketTickCurrentProjectionWorker,
)
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker import ResolutionRefreshWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_capture_tier_worker import TokenCaptureTierWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_image_mirror_worker import TokenImageMirrorWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_profile_current_worker import TokenProfileCurrentWorker
from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION

WORKER_KEYS = manifest_names_for_factory("asset_market.py")


def construct_asset_market_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    asset_market = ctx.providers.asset_market
    cex_market = getattr(asset_market, "cex_market", None)
    dex_quote_market = getattr(asset_market, "dex_quote_market", None)
    dex_profile_sources = tuple(getattr(asset_market, "dex_profile_sources", ()) or ())
    dex_discovery_market = getattr(asset_market, "dex_discovery_market", None)
    stream_dex_market = getattr(asset_market, "stream_dex_market", None)
    constructed: dict[str, WorkerBase] = {}

    if workers.token_profile_current.enabled:
        constructed["token_profile_current"] = TokenProfileCurrentWorker(
            name="token_profile_current",
            settings=workers.token_profile_current,
            db=ctx.db,
            telemetry=ctx.telemetry,
        )
    if workers.token_image_mirror.enabled:
        constructed["token_image_mirror"] = TokenImageMirrorWorker(
            name="token_image_mirror",
            settings=workers.token_image_mirror,
            db=ctx.db,
            telemetry=ctx.telemetry,
            app_home=ctx.settings.app_home,
        )
    if workers.token_capture_tier.enabled:
        constructed["token_capture_tier"] = TokenCaptureTierWorker(
            name="token_capture_tier",
            settings=workers.token_capture_tier,
            pool_bundle=ctx.db,
            telemetry=ctx.telemetry,
            batch_size=workers.token_capture_tier.batch_size,
            ws_limit=workers.token_capture_tier.ws_limit,
            poll_limit=workers.token_capture_tier.poll_limit,
        )
    if workers.market_tick_stream.enabled and stream_dex_market is not None:
        constructed["market_tick_stream"] = MarketTickStreamWorker(
            name="market_tick_stream",
            settings=workers.market_tick_stream,
            pool_bundle=ctx.db,
            telemetry=ctx.telemetry,
            stream_dex_market=stream_dex_market,
            wake_emitter=ctx.wake_bus,
            subscription_limit=workers.market_tick_stream.subscription_limit,
        )
    if workers.market_tick_poll.enabled and (cex_market is not None or dex_quote_market is not None):
        constructed["market_tick_poll"] = MarketTickPollWorker(
            name="market_tick_poll",
            settings=workers.market_tick_poll,
            pool_bundle=ctx.db,
            telemetry=ctx.telemetry,
            providers=asset_market,
            wake_emitter=ctx.wake_bus,
            batch_size=workers.market_tick_poll.batch_size,
        )
    if workers.market_tick_current_projection.enabled:
        worker_name = "market_tick_current_projection"
        constructed[worker_name] = MarketTickCurrentProjectionWorker(
            name=worker_name,
            settings=workers.market_tick_current_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_emitter=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, workers.market_tick_current_projection.wakes_on),
        )
    if workers.event_anchor_backfill.enabled:
        constructed["event_anchor_backfill"] = EventAnchorBackfillWorker(
            name="event_anchor_backfill",
            settings=workers.event_anchor_backfill,
            pool_bundle=ctx.db,
            telemetry=ctx.telemetry,
            providers=asset_market,
            wake_emitter=ctx.wake_bus,
            batch_size=workers.event_anchor_backfill.batch_size,
            concurrency=workers.event_anchor_backfill.concurrency,
            min_age_ms=workers.event_anchor_backfill.min_age_ms,
            active_window_ms=workers.event_anchor_backfill.active_window_ms,
            max_anchor_lag_ms=workers.event_anchor_backfill.max_anchor_lag_ms,
        )
    if workers.asset_profile_refresh.enabled and dex_profile_sources:
        constructed["asset_profile_refresh"] = AssetProfileRefreshWorker(
            name="asset_profile_refresh",
            settings=workers.asset_profile_refresh,
            db=ctx.db,
            telemetry=ctx.telemetry,
            dex_profile_sources=dex_profile_sources,
        )
    if workers.resolution_refresh.enabled and dex_discovery_market is not None:
        constructed["resolution_refresh"] = ResolutionRefreshWorker(
            name="resolution_refresh",
            settings=workers.resolution_refresh,
            db=ctx.db,
            telemetry=ctx.telemetry,
            dex_discovery_market=dex_discovery_market,
            dex_quote_market=dex_quote_market,
            chain_ids=workers.resolution_refresh.chain_ids,
            wake_bus=ctx.wake_bus,
        )
    if workers.live_price_gateway.enabled:
        constructed["live_price_gateway"] = LivePriceGateway(
            name="live_price_gateway",
            pool_bundle=ctx.db,
            telemetry=ctx.telemetry,
            providers=asset_market,
            interval_seconds=workers.live_price_gateway.interval_seconds,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            on_live_market_update=ctx.hub.publish,
        )

    return constructed
