from __future__ import annotations

CANONICAL_WORKER_CLASSES = {
    "collector": "gmgn_twitter_intel.domains.ingestion.runtime.collector_service.CollectorService",
    "anchor_price": "gmgn_twitter_intel.domains.asset_market.runtime.anchor_price_worker.AnchorPriceWorker",
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
    "token_radar_projection": 10,
    "pulse_candidate": 10,
    "anchor_price": 20,
    "resolution_refresh": 20,
    "asset_profile_refresh": 20,
    "harness_ops": 20,
    "enrichment": 30,
    "handle_summary": 30,
    "notification_rule": 40,
    "notification_delivery": 40,
    "live_price_gateway": 50,
    "collector": 60,
}
