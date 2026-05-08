from __future__ import annotations

TOKEN_RADAR_PROJECTION_NAME = "token-radar"
TOKEN_RADAR_PROJECTION_VERSION = "token-radar-v5-auditable"
TOKEN_RADAR_SOURCE_TABLE = "token_intent_resolutions+price_observations"
TOKEN_RADAR_SCORE_COMPONENTS = (
    "heat",
    "quality",
    "propagation",
    "tradeability",
    "timing",
    "opportunity",
)
