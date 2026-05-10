from __future__ import annotations

from typing import Literal

PULSE_VERSION = "signal-pulse-v3-factor-snapshot"
PULSE_RECOMMENDATION_SCHEMA_VERSION = "pulse_recommendation_v1"
PULSE_RECOMMENDATION_PROMPT_VERSION = "pulse-recommendation-agents-sdk-v1"
PULSE_GATE_VERSION = "pulse-factor-gate-v1"
PULSE_PLAYBOOK_VERSION = "shadow-playbook-v1"
BACKEND = "openai_agents_sdk"
WORKFLOW_NAME = "gmgn-twitter-intel.pulse_recommendation"
AGENT_NAME = "PulseRecommendationAgent"

CANDIDATE_TYPES = {"source_seed", "token_target"}
TARGET_TYPES = {"Asset", "CexToken"}
PULSE_STATUSES = {
    "trade_candidate",
    "token_watch",
    "theme_watch",
    "risk_rejected_high_info",
    "blocked_low_information",
}
DISPLAY_PULSE_STATUSES = {
    "trade_candidate",
    "token_watch",
    "theme_watch",
    "risk_rejected_high_info",
}
SOCIAL_PHASES = {"seed", "ignition", "expansion", "concentration", "chase", "unknown"}
NARRATIVE_TYPES = {
    "direct_token",
    "ecosystem_spillover",
    "listing_or_exchange",
    "product_catalyst",
    "meme_phrase",
    "risk_event",
    "market_structure",
    "unknown",
}
SCORE_BANDS = {"high_conviction", "watch", "speculative", "blocked"}

CandidateType = Literal["source_seed", "token_target"]
TargetType = Literal["Asset", "CexToken"]
PulseStatus = Literal[
    "trade_candidate",
    "token_watch",
    "theme_watch",
    "risk_rejected_high_info",
    "blocked_low_information",
]
DisplayPulseStatus = Literal["trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info"]
SocialPhase = Literal["seed", "ignition", "expansion", "concentration", "chase", "unknown"]
NarrativeType = Literal[
    "direct_token",
    "ecosystem_spillover",
    "listing_or_exchange",
    "product_catalyst",
    "meme_phrase",
    "risk_event",
    "market_structure",
    "unknown",
]
ScoreBand = Literal["high_conviction", "watch", "speculative", "blocked"]

__all__ = [
    "AGENT_NAME",
    "BACKEND",
    "CANDIDATE_TYPES",
    "CandidateType",
    "DISPLAY_PULSE_STATUSES",
    "DisplayPulseStatus",
    "NARRATIVE_TYPES",
    "NarrativeType",
    "PULSE_GATE_VERSION",
    "PULSE_PLAYBOOK_VERSION",
    "PULSE_STATUSES",
    "PULSE_RECOMMENDATION_PROMPT_VERSION",
    "PULSE_RECOMMENDATION_SCHEMA_VERSION",
    "PULSE_VERSION",
    "PulseStatus",
    "SCORE_BANDS",
    "SOCIAL_PHASES",
    "ScoreBand",
    "SocialPhase",
    "TARGET_TYPES",
    "TargetType",
    "WORKFLOW_NAME",
]
