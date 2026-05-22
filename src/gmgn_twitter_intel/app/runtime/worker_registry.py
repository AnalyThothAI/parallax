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
    "event_anchor_backfill": (
        "gmgn_twitter_intel.domains.asset_market.runtime.event_anchor_backfill_worker.EventAnchorBackfillWorker"
    ),
    "live_price_gateway": "gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway.LivePriceGateway",
    "resolution_refresh": (
        "gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker.ResolutionRefreshWorker"
    ),
    "asset_profile_refresh": (
        "gmgn_twitter_intel.domains.asset_market.runtime.asset_profile_refresh_worker.AssetProfileRefreshWorker"
    ),
    "token_image_mirror": (
        "gmgn_twitter_intel.domains.asset_market.runtime.token_image_mirror_worker.TokenImageMirrorWorker"
    ),
    "token_profile_current": (
        "gmgn_twitter_intel.domains.asset_market.runtime.token_profile_current_worker.TokenProfileCurrentWorker"
    ),
    "token_radar_projection": (
        "gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker.TokenRadarProjectionWorker"
    ),
    "narrative_admission": (
        "gmgn_twitter_intel.domains.narrative_intel.runtime.narrative_admission_worker.NarrativeAdmissionWorker"
    ),
    "mention_semantics": (
        "gmgn_twitter_intel.domains.narrative_intel.runtime.mention_semantics_worker.MentionSemanticsWorker"
    ),
    "token_discussion_digest": (
        "gmgn_twitter_intel.domains.narrative_intel.runtime.token_discussion_digest_worker.TokenDiscussionDigestWorker"
    ),
    "news_fetch": "gmgn_twitter_intel.domains.news_intel.runtime.news_fetch_worker.NewsFetchWorker",
    "news_item_process": "gmgn_twitter_intel.domains.news_intel.runtime.news_item_process_worker.NewsItemProcessWorker",
    "news_story_projection": (
        "gmgn_twitter_intel.domains.news_intel.runtime.news_story_projection_worker.NewsStoryProjectionWorker"
    ),
    "news_item_brief": ("gmgn_twitter_intel.domains.news_intel.runtime.news_item_brief_worker.NewsItemBriefWorker"),
    "news_page_projection": (
        "gmgn_twitter_intel.domains.news_intel.runtime.news_page_projection_worker.NewsPageProjectionWorker"
    ),
    "news_source_quality_projection": (
        "gmgn_twitter_intel.domains.news_intel.runtime.news_source_quality_projection_worker."
        "NewsSourceQualityProjectionWorker"
    ),
    "cex_oi_radar_board": (
        "gmgn_twitter_intel.domains.cex_market_intel.runtime.cex_oi_radar_board_worker.CexOiRadarBoardWorker"
    ),
    "macro_view_projection": (
        "gmgn_twitter_intel.domains.macro_intel.runtime.macro_view_projection_worker.MacroViewProjectionWorker"
    ),
    "pulse_candidate": "gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker.PulseCandidateWorker",
    "enrichment": "gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker.EnrichmentWorker",
    "handle_summary": "gmgn_twitter_intel.domains.watchlist_intel.runtime.handle_summary_worker.HandleSummaryWorker",
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
    "event_anchor_backfill": 45,
    "live_price_gateway": 50,
    "resolution_refresh": 60,
    "asset_profile_refresh": 70,
    "token_radar_projection": 80,
    "token_image_mirror": 82,
    "token_profile_current": 85,
    "narrative_admission": 87,
    "mention_semantics": 88,
    "token_discussion_digest": 89,
    "news_fetch": 90,
    "news_item_process": 91,
    "news_story_projection": 92,
    "news_item_brief": 94,
    "news_page_projection": 95,
    "news_source_quality_projection": 95,
    "cex_oi_radar_board": 95,
    "macro_view_projection": 95,
    "pulse_candidate": 96,
    "enrichment": 100,
    "handle_summary": 110,
    "notification_rule": 120,
    "notification_delivery": 130,
}
