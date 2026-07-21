from __future__ import annotations

from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker, unavailable_worker
from parallax.app.runtime.worker_manifest import require_worker_manifest
from parallax.domains.asset_market.runtime.asset_profile_refresh_worker import AssetProfileRefreshWorker
from parallax.domains.asset_market.runtime.event_anchor_backfill_worker import EventAnchorBackfillWorker
from parallax.domains.asset_market.runtime.live_price_gateway import LivePriceGateway
from parallax.domains.asset_market.runtime.market_tick_current_projection_worker import (
    MarketTickCurrentProjectionWorker,
)
from parallax.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from parallax.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from parallax.domains.asset_market.runtime.resolution_refresh_worker import ResolutionRefreshWorker
from parallax.domains.asset_market.runtime.token_capture_tier_worker import TokenCaptureTierWorker
from parallax.domains.asset_market.runtime.token_image_mirror_worker import TokenImageMirrorWorker
from parallax.domains.asset_market.runtime.token_profile_current_worker import TokenProfileCurrentWorker
from parallax.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION
from parallax.platform.runtime.worker_base import WorkerBase


def construct_asset_market_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    asset_market = ctx.asset_market
    cex_market = asset_market.cex_market if asset_market is not None else None
    dex_quote_market = asset_market.dex_quote_market if asset_market is not None else None
    dex_profile_sources = tuple(asset_market.dex_profile_sources or ()) if asset_market is not None else ()
    dex_discovery_market = asset_market.dex_discovery_market if asset_market is not None else None
    stream_dex_market = asset_market.stream_dex_market if asset_market is not None else None
    constructed: dict[str, WorkerBase] = {}

    if workers.token_profile_current.enabled:
        constructed["token_profile_current"] = TokenProfileCurrentWorker(
            name="token_profile_current",
            settings=workers.token_profile_current,
            db=ctx.db,
            telemetry=ctx.telemetry,
        )
    else:
        constructed["token_profile_current"] = disabled_worker(ctx, "token_profile_current")
    if workers.token_image_mirror.enabled:
        constructed["token_image_mirror"] = TokenImageMirrorWorker(
            name="token_image_mirror",
            settings=workers.token_image_mirror,
            db=ctx.db,
            telemetry=ctx.telemetry,
            app_home=ctx.settings.app_home,
        )
    else:
        constructed["token_image_mirror"] = disabled_worker(ctx, "token_image_mirror")
    if workers.token_capture_tier.enabled:
        constructed["token_capture_tier"] = TokenCaptureTierWorker(
            name="token_capture_tier",
            settings=workers.token_capture_tier,
            pool_bundle=ctx.db,
            telemetry=ctx.telemetry,
        )
    else:
        constructed["token_capture_tier"] = disabled_worker(ctx, "token_capture_tier")
    if workers.market_tick_stream.enabled:
        if stream_dex_market is not None:
            constructed["market_tick_stream"] = MarketTickStreamWorker(
                name="market_tick_stream",
                settings=workers.market_tick_stream,
                pool_bundle=ctx.db,
                telemetry=ctx.telemetry,
                stream_dex_market=stream_dex_market,
                wake_emitter=ctx.wake_bus,
            )
        else:
            constructed["market_tick_stream"] = unavailable_worker(
                ctx, "market_tick_stream", "missing_asset_market_stream_provider"
            )
    else:
        constructed["market_tick_stream"] = disabled_worker(ctx, "market_tick_stream")
    if workers.market_tick_poll.enabled:
        if asset_market is not None and (cex_market is not None or dex_quote_market is not None):
            constructed["market_tick_poll"] = MarketTickPollWorker(
                name="market_tick_poll",
                settings=workers.market_tick_poll,
                pool_bundle=ctx.db,
                telemetry=ctx.telemetry,
                providers=asset_market,
                wake_emitter=ctx.wake_bus,
            )
        else:
            constructed["market_tick_poll"] = unavailable_worker(
                ctx, "market_tick_poll", "missing_asset_market_quote_provider"
            )
    else:
        constructed["market_tick_poll"] = disabled_worker(ctx, "market_tick_poll")
    if workers.market_tick_current_projection.enabled:
        worker_name = "market_tick_current_projection"
        constructed[worker_name] = MarketTickCurrentProjectionWorker(
            name=worker_name,
            settings=workers.market_tick_current_projection,
            db=ctx.db,
            telemetry=ctx.telemetry,
            wake_emitter=ctx.wake_bus,
            wake_waiter=ctx.db.wake_listener(worker_name, require_worker_manifest(worker_name).wakes_on),
        )
    else:
        constructed["market_tick_current_projection"] = disabled_worker(ctx, "market_tick_current_projection")
    if workers.event_anchor_backfill.enabled:
        if asset_market is not None:
            constructed["event_anchor_backfill"] = EventAnchorBackfillWorker(
                name="event_anchor_backfill",
                settings=workers.event_anchor_backfill,
                pool_bundle=ctx.db,
                telemetry=ctx.telemetry,
                providers=asset_market,
                wake_emitter=ctx.wake_bus,
            )
        else:
            constructed["event_anchor_backfill"] = unavailable_worker(
                ctx, "event_anchor_backfill", "missing_asset_market_provider"
            )
    else:
        constructed["event_anchor_backfill"] = disabled_worker(ctx, "event_anchor_backfill")
    if workers.asset_profile_refresh.enabled:
        if dex_profile_sources:
            constructed["asset_profile_refresh"] = AssetProfileRefreshWorker(
                name="asset_profile_refresh",
                settings=workers.asset_profile_refresh,
                db=ctx.db,
                telemetry=ctx.telemetry,
                dex_profile_sources=dex_profile_sources,
            )
        else:
            constructed["asset_profile_refresh"] = unavailable_worker(
                ctx, "asset_profile_refresh", "missing_asset_profile_provider"
            )
    else:
        constructed["asset_profile_refresh"] = disabled_worker(ctx, "asset_profile_refresh")
    if workers.resolution_refresh.enabled:
        if dex_discovery_market is not None:
            constructed["resolution_refresh"] = ResolutionRefreshWorker(
                name="resolution_refresh",
                settings=workers.resolution_refresh,
                db=ctx.db,
                telemetry=ctx.telemetry,
                dex_discovery_market=dex_discovery_market,
                wake_emitter=ctx.wake_bus,
            )
        else:
            constructed["resolution_refresh"] = unavailable_worker(
                ctx, "resolution_refresh", "missing_asset_discovery_provider"
            )
    else:
        constructed["resolution_refresh"] = disabled_worker(ctx, "resolution_refresh")
    if workers.live_price_gateway.enabled and ctx.hub is not None:
        constructed["live_price_gateway"] = LivePriceGateway(
            name="live_price_gateway",
            settings=workers.live_price_gateway,
            pool_bundle=ctx.db,
            telemetry=ctx.telemetry,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            on_live_market_update=ctx.hub.publish,
        )
    elif workers.live_price_gateway.enabled:
        constructed["live_price_gateway"] = unavailable_worker(ctx, "live_price_gateway", "missing_event_publisher")
    else:
        constructed["live_price_gateway"] = disabled_worker(ctx, "live_price_gateway")

    return constructed
