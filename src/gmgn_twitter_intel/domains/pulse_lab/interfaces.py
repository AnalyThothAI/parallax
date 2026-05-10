from __future__ import annotations

from typing import Literal

PULSE_VERSION = "signal-pulse-v2-agent-thesis"
PULSE_THESIS_SCHEMA_VERSION = "pulse_thesis_v1"
PULSE_THESIS_PROMPT_VERSION = "pulse-thesis-agents-sdk-v1"
PULSE_GATE_VERSION = "pulse-candidate-gate-v1"
PULSE_PLAYBOOK_VERSION = "shadow-playbook-v1"
BACKEND = "openai_agents_sdk"
WORKFLOW_NAME = "gmgn-twitter-intel.pulse_thesis"
AGENT_NAME = "PulseThesisAgent"

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
    "PULSE_THESIS_PROMPT_VERSION",
    "PULSE_THESIS_SCHEMA_VERSION",
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
