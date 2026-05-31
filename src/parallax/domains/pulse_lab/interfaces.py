from __future__ import annotations

from typing import Literal

from parallax.domains.pulse_lab.types.agent_decision import contains_trading_execution_instruction

PULSE_VERSION = "signal-pulse-v3-factor-snapshot"
PULSE_DECISION_SCHEMA_VERSION = "pulse-decision-v2"
PULSE_DECISION_PROMPT_VERSION = "pulse-decision-prompt-v2"
PULSE_GATE_VERSION = "pulse-factor-gate-v2-edge-state"
PULSE_PLAYBOOK_VERSION = "shadow-playbook-v1"
BACKEND = "litellm_sdk"
WORKFLOW_NAME = "parallax.pulse_decision"
AGENT_NAME = "PulseDecisionPipeline"

CANDIDATE_TYPES = {"token_target"}
TARGET_TYPES = {"Asset", "CexToken"}
PULSE_STATUSES = {
    "trade_candidate",
    "token_watch",
    "risk_rejected_high_info",
    "blocked_low_information",
}
DISPLAY_PULSE_STATUSES = {
    "trade_candidate",
    "token_watch",
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

CandidateType = Literal["token_target"]
TargetType = Literal["Asset", "CexToken"]
PulseStatus = Literal[
    "trade_candidate",
    "token_watch",
    "risk_rejected_high_info",
    "blocked_low_information",
]
DisplayPulseStatus = Literal["trade_candidate", "token_watch", "risk_rejected_high_info"]
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
    "DISPLAY_PULSE_STATUSES",
    "NARRATIVE_TYPES",
    "PULSE_DECISION_PROMPT_VERSION",
    "PULSE_DECISION_SCHEMA_VERSION",
    "PULSE_GATE_VERSION",
    "PULSE_PLAYBOOK_VERSION",
    "PULSE_STATUSES",
    "PULSE_VERSION",
    "SCORE_BANDS",
    "SOCIAL_PHASES",
    "TARGET_TYPES",
    "WORKFLOW_NAME",
    "CandidateType",
    "DisplayPulseStatus",
    "NarrativeType",
    "PulseStatus",
    "ScoreBand",
    "SocialPhase",
    "TargetType",
    "contains_trading_execution_instruction",
]
