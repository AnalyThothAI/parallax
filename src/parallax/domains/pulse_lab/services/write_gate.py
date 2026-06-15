from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parallax.domains.pulse_lab.services.claim_evidence_verifier import ClaimEvidenceVerificationResult
from parallax.domains.pulse_lab.services.evidence_completeness_gate import EvidenceCompletenessGateResult
from parallax.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from parallax.domains.pulse_lab.services.pulse_source_quality import PulseSourceQualityDecision
from parallax.domains.pulse_lab.types.agent_decision import FinalDecision
from parallax.domains.pulse_lab.types.pulse_state import (
    display_status_from_decision,
)


@dataclass(frozen=True, slots=True)
class PulseWriteGateDecision:
    write_allowed: bool
    public_write_allowed: bool
    playbook_write_allowed: bool
    decision_status: str
    display_status: str
    reason: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "write_allowed": self.write_allowed,
            "public_write_allowed": self.public_write_allowed,
            "playbook_write_allowed": self.playbook_write_allowed,
            "decision_status": self.decision_status,
            "display_status": self.display_status,
            "reason": self.reason,
        }


class PulseWriteGate:
    def evaluate(
        self,
        *,
        final_decision: FinalDecision,
        eval_result: dict[str, Any],
        gate: PulseGateResult,
        evidence_gate: EvidenceCompletenessGateResult,
        claim_verification: ClaimEvidenceVerificationResult,
        source_quality: PulseSourceQualityDecision,
    ) -> PulseWriteGateDecision:
        if not isinstance(gate, PulseGateResult):
            raise TypeError(
                f"pulse_write_gate_gate_contract_required: expected PulseGateResult, got {type(gate).__name__}"
            )
        if not isinstance(evidence_gate, EvidenceCompletenessGateResult):
            raise TypeError(
                "pulse_write_gate_evidence_gate_contract_required: "
                f"expected EvidenceCompletenessGateResult, got {type(evidence_gate).__name__}"
            )
        if not isinstance(claim_verification, ClaimEvidenceVerificationResult):
            raise TypeError(
                "pulse_write_gate_claim_verification_contract_required: "
                f"expected ClaimEvidenceVerificationResult, got {type(claim_verification).__name__}"
            )
        if not isinstance(source_quality, PulseSourceQualityDecision):
            raise TypeError(
                "pulse_write_gate_source_quality_contract_required: "
                f"expected PulseSourceQualityDecision, got {type(source_quality).__name__}"
            )
        evidence_status = str(evidence_gate.evidence_status or "invalid")
        claim_valid = bool(claim_verification.valid)
        decision_status = str(claim_verification.decision_status or _decision_status(final_decision))
        if not claim_valid:
            return PulseWriteGateDecision(
                write_allowed=True,
                public_write_allowed=False,
                playbook_write_allowed=False,
                decision_status="invalid",
                display_status="hidden_invalid_output",
                reason="claim_verification_failed",
            )
        eval_status = str(eval_result.get("status") or "")
        if eval_status != "pass":
            return PulseWriteGateDecision(
                write_allowed=True,
                public_write_allowed=False,
                playbook_write_allowed=False,
                decision_status="invalid",
                display_status="hidden_invalid_output",
                reason="deterministic_eval_failed",
            )
        if not bool(source_quality.public_allowed):
            return PulseWriteGateDecision(
                write_allowed=True,
                public_write_allowed=False,
                playbook_write_allowed=False,
                decision_status=decision_status,
                display_status="hidden_source_quality",
                reason="source_quality_failed",
            )
        publish_allowed = bool(evidence_gate.public_allowed)
        display_status = display_status_from_decision(
            _normalized_decision_status(decision_status),
            _normalized_evidence_status(evidence_status),
            publish_allowed,
        )
        if final_decision.recommendation == "abstain":
            return PulseWriteGateDecision(
                write_allowed=True,
                public_write_allowed=False,
                playbook_write_allowed=False,
                decision_status="abstain",
                display_status=display_status,
                reason="abstain_no_playbook",
            )
        if final_decision.recommendation == "ignore":
            return PulseWriteGateDecision(
                write_allowed=True,
                public_write_allowed=display_status.startswith("display_"),
                playbook_write_allowed=False,
                decision_status=decision_status,
                display_status=display_status,
                reason="ignore_no_playbook",
            )
        playbook_allowed = bool(
            str(gate.pulse_status or "") in {"trade_candidate", "token_watch"} and final_decision.playbook.has_playbook
        )
        return PulseWriteGateDecision(
            write_allowed=True,
            public_write_allowed=display_status.startswith("display_"),
            playbook_write_allowed=playbook_allowed,
            decision_status=decision_status,
            display_status=display_status,
            reason=None if playbook_allowed else "playbook_not_allowed",
        )


def _decision_status(final_decision: FinalDecision) -> str:
    if final_decision.recommendation in {"high_conviction", "trade_candidate"}:
        return "trade_candidate"
    if final_decision.recommendation == "watchlist":
        return "token_watch"
    if final_decision.recommendation == "ignore":
        return "risk_rejected_high_info"
    if final_decision.recommendation == "abstain":
        return "abstain"
    return "invalid"


def _normalized_decision_status(value: str) -> Any:
    return value if value in {"trade_candidate", "token_watch", "risk_rejected_high_info", "abstain"} else "invalid"


def _normalized_evidence_status(value: str) -> Any:
    return value if value in {"complete", "partial", "insufficient", "stale", "invalid"} else "invalid"


__all__ = ["PulseWriteGate", "PulseWriteGateDecision"]
