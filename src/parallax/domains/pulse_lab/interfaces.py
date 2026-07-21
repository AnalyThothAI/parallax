from __future__ import annotations

from typing import Literal

from parallax.domains.pulse_lab.types.agent_decision import contains_trading_execution_instruction

PULSE_VERSION = "signal-pulse-v3-factor-snapshot"
PULSE_DECISION_SCHEMA_VERSION = "pulse-decision-v2"
PULSE_DECISION_PROMPT_VERSION = "pulse-decision-prompt-v2"
PULSE_GATE_VERSION = "pulse-factor-gate-v2-edge-state"
PULSE_PLAYBOOK_VERSION = "shadow-playbook-v1"
BACKEND = "litellm_sdk"
ScoreBand = Literal["high_conviction", "watch", "speculative", "blocked"]

__all__ = [
    "BACKEND",
    "PULSE_DECISION_PROMPT_VERSION",
    "PULSE_DECISION_SCHEMA_VERSION",
    "PULSE_GATE_VERSION",
    "PULSE_PLAYBOOK_VERSION",
    "PULSE_VERSION",
    "ScoreBand",
    "contains_trading_execution_instruction",
]
