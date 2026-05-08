from __future__ import annotations

TOKEN_RADAR_PROJECTION_NAME = "token-radar"
TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v6-auditable"
TOKEN_RADAR_RESOLVER_POLICY_VERSION = "token_radar_v5_identity_resolver"
TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+price_observations"
TOKEN_RADAR_SCORE_COMPONENTS = (
    "heat",
    "quality",
    "propagation",
    "tradeability",
    "timing",
    "opportunity",
)
TOKEN_RADAR_REQUIRED_ATTENTION_FIELDS = (
    "mentions_5m",
    "mentions_1h",
    "mentions_4h",
    "mentions_24h",
    "mentions_window",
    "unique_authors",
    "watched_mentions",
    "latest_seen_ms",
    "previous_mentions",
    "mention_delta",
    "mention_delta_pct",
    "z_score",
    "z_ewma",
    "robust_z",
    "new_burst_score",
    "stream_share",
    "baseline_version",
    "baseline_status",
    "baseline_sample_count",
    "baseline_nonzero_sample_count",
    "zero_slot_count",
)
TOKEN_RADAR_REQUIRED_HEAT_HEALTH_FIELDS = (
    "baseline_ready",
    "baseline_status",
    "sample_count",
    "nonzero_sample_count",
    "zero_slot_count",
    "baseline_version",
    "public_stream_coverage",
)
