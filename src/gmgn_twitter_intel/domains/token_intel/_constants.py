from __future__ import annotations

# Pure constants for the token_intel domain.
# This module intentionally has no intra-domain imports to avoid circular dependencies.

TOKEN_RADAR_PROJECTION_NAME = "token-radar"
TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v9-factor-snapshot"
TOKEN_RADAR_RESOLVER_POLICY_VERSION = "token_radar_v5_identity_resolver"
TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+asset_identity_current+price_observations"
TOKEN_FACTOR_SNAPSHOT_VERSION = "token_factor_snapshot_v1"
TOKEN_RADAR_FACTOR_FAMILIES = (
    "identity",
    "social_attention",
    "social_quality",
    "social_semantics",
    "market_quality",
    "timing",
)
WINDOW_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}
