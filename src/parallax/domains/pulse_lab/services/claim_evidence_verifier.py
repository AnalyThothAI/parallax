from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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
        packet: PulseEvidencePacket | Any,
        final_decision: FinalDecision | Any,
    ) -> ClaimEvidenceVerificationResult:
        allowed = _allowed_ref_ids(packet)
        unknown: list[str] = []
        unsupported: list[str] = []
        missing: list[str] = []

        recommendation = str(getattr(final_decision, "recommendation", "") or "")
        supporting_refs = _string_tuple(getattr(final_decision, "supporting_evidence_refs", ()))
        risk_refs = _string_tuple(getattr(final_decision, "risk_evidence_refs", ()))
        data_gap_refs = _string_tuple(getattr(final_decision, "data_gap_refs", ()))
        unknown.extend(ref_id for ref_id in (*supporting_refs, *risk_refs) if ref_id not in allowed)
        unknown.extend(
            ref_id for ref_id in data_gap_refs if ref_id not in allowed and not ref_id.startswith("missing:")
        )

        evidence_event_ids = _string_tuple(getattr(final_decision, "evidence_event_ids", ()))
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
    packet: PulseEvidencePacket | Any,
    final_decision: FinalDecision | Any,
) -> ClaimEvidenceVerificationResult:
    return ClaimEvidenceVerifier().verify(packet, final_decision)


def _allowed_ref_ids(packet: Any) -> set[str]:
    refs = _sequence(getattr(packet, "allowed_evidence_refs", ()))
    allowed: set[str] = set()
    for ref in refs:
        ref_id = ref.get("ref_id") if isinstance(ref, dict) else getattr(ref, "ref_id", None)
        if ref_id:
            allowed.add(str(ref_id))
    return allowed


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


def _sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, list | tuple | set):
        return tuple(value)
    return tuple()


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in _sequence(value) if str(item or "").strip())


__all__ = ["ClaimEvidenceVerificationResult", "ClaimEvidenceVerifier", "verify_claim_evidence"]
