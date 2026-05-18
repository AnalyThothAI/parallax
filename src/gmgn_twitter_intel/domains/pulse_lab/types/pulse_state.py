from __future__ import annotations

from typing import Literal

EvidenceStatus = Literal["complete", "partial", "insufficient", "stale", "invalid"]
DecisionStatus = Literal["trade_candidate", "token_watch", "risk_rejected_high_info", "abstain", "invalid"]
DisplayStatus = Literal[
    "display_trade_candidate",
    "display_token_watch",
    "display_risk_rejected_high_info",
    "hidden_abstain",
    "hidden_insufficient_evidence",
    "hidden_blocked_low_information",
    "hidden_invalid_output",
    "hidden_hold_publish",
]
AgentRunOutcome = Literal[
    "running",
    "completed",
    "abstain_insufficient_evidence",
    "blocked_market_contract",
    "blocked_social_contract",
    "blocked_identity_contract",
    "invalid_schema",
    "invalid_unknown_evidence_ref",
    "invalid_unsupported_claim",
    "timeout",
    "provider_rate_limited",
    "provider_unavailable",
    "unexpected_exception",
]

PUBLIC_DISPLAY_STATUSES: tuple[DisplayStatus, ...] = (
    "display_trade_candidate",
    "display_token_watch",
    "display_risk_rejected_high_info",
)


def display_status_from_decision(
    decision_status: DecisionStatus,
    evidence_status: EvidenceStatus,
    publish_allowed: bool,
) -> DisplayStatus:
    if decision_status == "invalid" or evidence_status == "invalid":
        return "hidden_invalid_output"
    if evidence_status == "insufficient":
        return "hidden_insufficient_evidence"
    if evidence_status == "stale":
        return "hidden_hold_publish"
    if decision_status == "abstain":
        return "hidden_abstain"
    if not publish_allowed:
        return "hidden_hold_publish"
    if decision_status == "trade_candidate" and evidence_status == "complete":
        return "display_trade_candidate"
    if decision_status == "token_watch" and evidence_status in {"complete", "partial"}:
        return "display_token_watch"
    if decision_status == "risk_rejected_high_info" and evidence_status in {"complete", "partial"}:
        return "display_risk_rejected_high_info"
    return "hidden_insufficient_evidence"


def run_outcome_from_failure(reason: str | None) -> AgentRunOutcome:
    normalized = str(reason or "").strip().lower()
    mapping: dict[str, AgentRunOutcome] = {
        "insufficient_evidence": "abstain_insufficient_evidence",
        "data_completeness_below_hard_gate": "abstain_insufficient_evidence",
        "blocked_market_contract": "blocked_market_contract",
        "blocked_social_contract": "blocked_social_contract",
        "blocked_identity_contract": "blocked_identity_contract",
        "schema_validation_failed": "invalid_schema",
        "invalid_schema": "invalid_schema",
        "unknown_evidence_id": "invalid_unknown_evidence_ref",
        "invalid_unknown_evidence_ref": "invalid_unknown_evidence_ref",
        "unsupported_claim": "invalid_unsupported_claim",
        "invalid_unsupported_claim": "invalid_unsupported_claim",
        "timeout": "timeout",
        "provider_rate_limited": "provider_rate_limited",
        "rate_limited": "provider_rate_limited",
        "provider_unavailable": "provider_unavailable",
        "provider_error": "provider_unavailable",
    }
    return mapping.get(normalized, "unexpected_exception")


def is_public_display_status(display_status: str) -> bool:
    return display_status in PUBLIC_DISPLAY_STATUSES
