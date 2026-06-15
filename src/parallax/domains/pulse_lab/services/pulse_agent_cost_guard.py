from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from parallax.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGateResult,
)
from parallax.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from parallax.domains.pulse_lab.services.pulse_source_quality import PulseSourceQualityDecision
from parallax.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext

PulseCostGuardAction = Literal[
    "deterministic_finalize",
    "skip_decision",
    "run_decision",
]


@dataclass(frozen=True, slots=True)
class PulseRunFingerprint:
    candidate_id: str
    trigger_signature: str
    timeline_signature: str
    evidence_packet_hash: str
    runtime_hash: str
    route: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PulseCostGuardDecision:
    action: PulseCostGuardAction
    reason: str
    public_eligible: bool
    decision_allowed: bool
    fingerprint: PulseRunFingerprint
    audit_json: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "public_eligible": bool(self.public_eligible),
            "decision_allowed": bool(self.decision_allowed),
            "fingerprint": self.fingerprint.to_json(),
            "audit": dict(self.audit_json),
        }


def decide_pulse_agent_cost(
    *,
    context: PulseCandidateContext,
    evidence_gate: EvidenceCompletenessGateResult,
    gate: PulseGateResult,
    source_quality: PulseSourceQualityDecision,
    runtime_hash: str,
    evidence_packet_hash: str,
    now_ms: int,
) -> PulseCostGuardDecision:
    route = _route_from_context(context)
    public_eligible = _public_eligible(
        evidence_gate=evidence_gate,
        gate=gate,
        source_quality=source_quality,
    )
    if evidence_gate.hard_blocked:
        return _decision(
            action="deterministic_finalize",
            reason="deterministic_evidence_block",
            public_eligible=False,
            decision_allowed=False,
            context=context,
            route=route,
            evidence_packet_hash=evidence_packet_hash,
            runtime_hash=runtime_hash,
            evidence_gate=evidence_gate,
            gate=gate,
            source_quality=source_quality,
            now_ms=now_ms,
        )

    if public_eligible:
        return _decision(
            action="run_decision",
            reason="public_decision",
            public_eligible=True,
            decision_allowed=True,
            context=context,
            route=route,
            evidence_packet_hash=evidence_packet_hash,
            runtime_hash=runtime_hash,
            evidence_gate=evidence_gate,
            gate=gate,
            source_quality=source_quality,
            now_ms=now_ms,
        )

    reason = "source_quality_hidden" if not bool(source_quality.public_allowed) else "not_public_eligible"
    return _decision(
        action="skip_decision",
        reason=reason,
        public_eligible=False,
        decision_allowed=False,
        context=context,
        route=route,
        evidence_packet_hash=evidence_packet_hash,
        runtime_hash=runtime_hash,
        evidence_gate=evidence_gate,
        gate=gate,
        source_quality=source_quality,
        now_ms=now_ms,
    )


def _decision(
    *,
    action: PulseCostGuardAction,
    reason: str,
    public_eligible: bool,
    decision_allowed: bool,
    context: PulseCandidateContext,
    route: str,
    evidence_packet_hash: str,
    runtime_hash: str,
    evidence_gate: EvidenceCompletenessGateResult,
    gate: PulseGateResult,
    source_quality: PulseSourceQualityDecision,
    now_ms: int,
) -> PulseCostGuardDecision:
    fingerprint = PulseRunFingerprint(
        candidate_id=str(context.candidate_id),
        trigger_signature=str(context.trigger_signature or ""),
        timeline_signature=str(context.timeline_signature or ""),
        evidence_packet_hash=str(evidence_packet_hash or ""),
        runtime_hash=str(runtime_hash or ""),
        route=route,
    )
    return PulseCostGuardDecision(
        action=action,
        reason=reason,
        public_eligible=public_eligible,
        decision_allowed=decision_allowed,
        fingerprint=fingerprint,
        audit_json={
            "now_ms": int(now_ms),
            "evidence_status": str(evidence_gate.evidence_status),
            "evidence_blocked_reason": evidence_gate.blocked_reason,
            "source_quality_reasons": list(source_quality.reasons),
            "pulse_status": str(gate.pulse_status),
            "max_recommendation": str(gate.max_recommendation),
        },
    )


def _public_eligible(
    *,
    evidence_gate: EvidenceCompletenessGateResult,
    gate: PulseGateResult,
    source_quality: PulseSourceQualityDecision,
) -> bool:
    return (
        bool(evidence_gate.public_allowed)
        and bool(source_quality.public_allowed)
        and str(gate.pulse_status or "") in {"trade_candidate", "token_watch"}
        and str(gate.max_recommendation or "") in {"trade_candidate", "watch"}
    )


def _route_from_context(context: PulseCandidateContext) -> str:
    target_type = str(context.target_type or "").lower()
    subject_key = str(context.subject_key or "").lower()
    if any(token in target_type for token in ("cex", "spot", "perp", "perpetual")):
        return "cex"
    if any(token in target_type for token in ("dex", "meme")):
        return "meme"
    if subject_key.startswith("token:"):
        return "meme"
    return "research_only"


__all__ = [
    "PulseCostGuardAction",
    "PulseCostGuardDecision",
    "PulseRunFingerprint",
    "decide_pulse_agent_cost",
]
