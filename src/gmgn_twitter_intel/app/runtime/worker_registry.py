from __future__ import annotations

CANONICAL_WORKER_CLASSES = {
    "collector": "gmgn_twitter_intel.domains.ingestion.runtime.collector_service.CollectorService",
    "token_capture_tier": (
        "gmgn_twitter_intel.domains.asset_market.runtime.token_capture_tier_worker.TokenCaptureTierWorker"
    ),
    "market_tick_stream": (
        "gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker.MarketTickStreamWorker"
    ),
    "market_tick_poll": "gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker.MarketTickPollWorker",
    "live_price_gateway": "gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway.LivePriceGateway",
    "resolution_refresh": (
        "gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker.ResolutionRefreshWorker"
    ),
    "asset_profile_refresh": (
        "gmgn_twitter_intel.domains.asset_market.runtime.asset_profile_refresh_worker.AssetProfileRefreshWorker"
    ),
    "token_radar_projection": (
        "gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker.TokenRadarProjectionWorker"
    ),
    "pulse_candidate": "gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker.PulseCandidateWorker",
    "enrichment": "gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker.EnrichmentWorker",
    "handle_summary": "gmgn_twitter_intel.domains.watchlist_intel.runtime.handle_summary_worker.HandleSummaryWorker",
    "harness_ops": "gmgn_twitter_intel.domains.closed_loop_harness.runtime.harness_ops_worker.HarnessOpsWorker",
    "notification_rule": "gmgn_twitter_intel.domains.notifications.runtime.notification_worker.NotificationWorker",
    "notification_delivery": (
        "gmgn_twitter_intel.domains.notifications.runtime.notification_delivery.NotificationDeliveryWorker"
    ),
}

CANONICAL_WORKER_NAMES = tuple(CANONICAL_WORKER_CLASSES)

WORKER_START_PRIORITY = {
    "collector": 10,
    "token_capture_tier": 20,
    "market_tick_stream": 30,
    "market_tick_poll": 40,
    "live_price_gateway": 50,
    "resolution_refresh": 60,
    "asset_profile_refresh": 70,
    "token_radar_projection": 80,
    "pulse_candidate": 90,
    "enrichment": 100,
    "handle_summary": 110,
    "harness_ops": 120,
    "notification_rule": 130,
    "notification_delivery": 140,
}
