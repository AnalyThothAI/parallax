from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from parallax.domains.pulse_lab.types.agent_decision import FinalDecision
from parallax.domains.pulse_lab.types.evidence_packet import PulseEvidencePacket


@dataclass(frozen=True, slots=True)
class ClaimEvidenceVerificationResult:
    valid: bool
    unknown_ref_ids: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    missing_required_ref_claims: tuple[str, ...]
    decision_status: str
    display_status_if_failed: str | None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


class ClaimEvidenceVerifier:
    def verify(
        self,
        packet: PulseEvidencePacket,
        final_decision: FinalDecision,
    ) -> ClaimEvidenceVerificationResult:
        if not isinstance(packet, PulseEvidencePacket):
            raise TypeError(
                "pulse_claim_verifier_packet_contract_required: "
                f"expected PulseEvidencePacket, got {type(packet).__name__}"
            )
        if not isinstance(final_decision, FinalDecision):
            raise TypeError(
                "pulse_claim_verifier_final_decision_contract_required: "
                f"expected FinalDecision, got {type(final_decision).__name__}"
            )
        allowed = _allowed_ref_ids(packet)
        unknown: list[str] = []
        unsupported: list[str] = []
        missing: list[str] = []

        recommendation = str(final_decision.recommendation)
        supporting_refs = _string_tuple(final_decision.supporting_evidence_refs)
        risk_refs = _string_tuple(final_decision.risk_evidence_refs)
        data_gap_refs = _string_tuple(final_decision.data_gap_refs)
        unknown.extend(ref_id for ref_id in (*supporting_refs, *risk_refs) if ref_id not in allowed)
        unknown.extend(
            ref_id for ref_id in data_gap_refs if ref_id not in allowed and not ref_id.startswith("missing:")
        )

        evidence_event_ids = _string_tuple(final_decision.evidence_event_ids)
        if recommendation != "abstain" and not supporting_refs:
            missing.append("final_decision.supporting_evidence_refs")
            if evidence_event_ids:
                unsupported.append("event_id_only_final_decision")
        if recommendation != "abstain" and evidence_event_ids and not supporting_refs:
            unsupported.append("evidence_event_ids_cannot_substitute_for_refs")

        unknown_tuple = tuple(dict.fromkeys(unknown))
        unsupported_tuple = tuple(dict.fromkeys(unsupported))
        missing_tuple = tuple(dict.fromkeys(missing))
        valid = not unknown_tuple and not unsupported_tuple and not missing_tuple
        return ClaimEvidenceVerificationResult(
            valid=valid,
            unknown_ref_ids=unknown_tuple,
            unsupported_claims=unsupported_tuple,
            missing_required_ref_claims=missing_tuple,
            decision_status=_decision_status(recommendation, valid=valid),
            display_status_if_failed=None if valid else "hidden_invalid_output",
        )


def verify_claim_evidence(
    *,
    packet: PulseEvidencePacket,
    final_decision: FinalDecision,
) -> ClaimEvidenceVerificationResult:
    return ClaimEvidenceVerifier().verify(packet, final_decision)


def _allowed_ref_ids(packet: PulseEvidencePacket) -> set[str]:
    return {ref.ref_id for ref in packet.allowed_evidence_refs if ref.ref_id.strip()}


def _decision_status(recommendation: str, *, valid: bool) -> str:
    if not valid:
        return "invalid"
    if recommendation in {"high_conviction", "trade_candidate"}:
        return "trade_candidate"
    if recommendation in {"watchlist", "token_watch", "watch"}:
        return "token_watch"
    if recommendation == "ignore":
        return "risk_rejected_high_info"
    return "abstain"


def _string_tuple(value: Iterable[str]) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in value if str(item or "").strip())


__all__ = ["ClaimEvidenceVerificationResult", "ClaimEvidenceVerifier", "verify_claim_evidence"]
