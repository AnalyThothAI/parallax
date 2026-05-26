from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from gmgn_twitter_intel.domains.pulse_lab.providers import PulseStagePlan
from gmgn_twitter_intel.domains.pulse_lab.services.evidence_completeness_gate import (
    EvidenceCompletenessGateResult,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_source_quality import PulseSourceQualityDecision
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_candidate_context import PulseCandidateContext

PulseCostGuardAction = Literal[
    "no_llm_finalize",
    "reuse_terminal_run",
    "research_only",
    "research_with_public_judge",
    "provider_cooldown",
]


@dataclass(frozen=True, slots=True)
class PulseRunFingerprint:
    candidate_id: str
    trigger_signature: str
    timeline_signature: str
    evidence_packet_hash: str
    runtime_hash: str
    stage_plan_hash: str
    route: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PulseCostGuardDecision:
    action: PulseCostGuardAction
    reason: str
    public_eligible: bool
    research_allowed: bool
    public_judge_allowed: bool
    fingerprint: PulseRunFingerprint
    stage_plan: PulseStagePlan
    cooldown_until_ms: int | None = None
    audit_json: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "public_eligible": bool(self.public_eligible),
            "research_allowed": bool(self.research_allowed),
            "public_judge_allowed": bool(self.public_judge_allowed),
            "fingerprint": self.fingerprint.to_json(),
            "stage_plan": self.stage_plan.to_json(),
            "cooldown_until_ms": self.cooldown_until_ms,
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
    lane_models: Mapping[str, str],
    terminal_fingerprint_found: bool,
    provider_cooldown_until_ms: int | None,
    now_ms: int,
) -> PulseCostGuardDecision:
    route = _route_from_context(context)
    public_eligible = _public_eligible(
        evidence_gate=evidence_gate,
        gate=gate,
        source_quality=source_quality,
    )
    target_plan = _stage_plan(public_judge=public_eligible, lane_models=lane_models)
    if bool(getattr(evidence_gate, "hard_blocked", False)):
        no_llm_plan = _stage_plan(public_judge=False, lane_models=lane_models, no_llm=True)
        return _decision(
            action="no_llm_finalize",
            reason="deterministic_evidence_block",
            public_eligible=False,
            research_allowed=False,
            public_judge_allowed=False,
            context=context,
            route=route,
            evidence_packet_hash=evidence_packet_hash,
            runtime_hash=runtime_hash,
            stage_plan=no_llm_plan,
            evidence_gate=evidence_gate,
            gate=gate,
            source_quality=source_quality,
            now_ms=now_ms,
        )

    if terminal_fingerprint_found:
        return _decision(
            action="reuse_terminal_run",
            reason="duplicate_fingerprint",
            public_eligible=public_eligible,
            research_allowed=False,
            public_judge_allowed=False,
            context=context,
            route=route,
            evidence_packet_hash=evidence_packet_hash,
            runtime_hash=runtime_hash,
            stage_plan=target_plan,
            evidence_gate=evidence_gate,
            gate=gate,
            source_quality=source_quality,
            now_ms=now_ms,
        )

    if provider_cooldown_until_ms is not None and int(provider_cooldown_until_ms) > int(now_ms):
        no_llm_plan = _stage_plan(public_judge=False, lane_models=lane_models, no_llm=True)
        return _decision(
            action="provider_cooldown",
            reason="provider_cooldown_active",
            public_eligible=public_eligible,
            research_allowed=False,
            public_judge_allowed=False,
            context=context,
            route=route,
            evidence_packet_hash=evidence_packet_hash,
            runtime_hash=runtime_hash,
            stage_plan=no_llm_plan,
            evidence_gate=evidence_gate,
            gate=gate,
            source_quality=source_quality,
            now_ms=now_ms,
            cooldown_until_ms=int(provider_cooldown_until_ms),
        )

    if public_eligible:
        return _decision(
            action="research_with_public_judge",
            reason="public_judge",
            public_eligible=True,
            research_allowed=True,
            public_judge_allowed=True,
            context=context,
            route=route,
            evidence_packet_hash=evidence_packet_hash,
            runtime_hash=runtime_hash,
            stage_plan=target_plan,
            evidence_gate=evidence_gate,
            gate=gate,
            source_quality=source_quality,
            now_ms=now_ms,
        )

    research_plan = _stage_plan(public_judge=False, lane_models=lane_models)
    reason = "source_quality_hidden" if not bool(source_quality.public_allowed) else "not_public_eligible"
    return _decision(
        action="research_only",
        reason=reason,
        public_eligible=False,
        research_allowed=True,
        public_judge_allowed=False,
        context=context,
        route=route,
        evidence_packet_hash=evidence_packet_hash,
        runtime_hash=runtime_hash,
        stage_plan=research_plan,
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
    research_allowed: bool,
    public_judge_allowed: bool,
    context: PulseCandidateContext,
    route: str,
    evidence_packet_hash: str,
    runtime_hash: str,
    stage_plan: PulseStagePlan,
    evidence_gate: EvidenceCompletenessGateResult,
    gate: PulseGateResult,
    source_quality: PulseSourceQualityDecision,
    now_ms: int,
    cooldown_until_ms: int | None = None,
) -> PulseCostGuardDecision:
    fingerprint = PulseRunFingerprint(
        candidate_id=str(context.candidate_id),
        trigger_signature=str(context.trigger_signature or ""),
        timeline_signature=str(context.timeline_signature or ""),
        evidence_packet_hash=str(evidence_packet_hash or ""),
        runtime_hash=str(runtime_hash or ""),
        stage_plan_hash=_hash_json(stage_plan.to_json()),
        route=route,
    )
    return PulseCostGuardDecision(
        action=action,
        reason=reason,
        public_eligible=public_eligible,
        research_allowed=research_allowed,
        public_judge_allowed=public_judge_allowed,
        fingerprint=fingerprint,
        stage_plan=stage_plan,
        cooldown_until_ms=cooldown_until_ms,
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


def _stage_plan(
    *,
    public_judge: bool,
    lane_models: Mapping[str, str],
    no_llm: bool = False,
) -> PulseStagePlan:
    signal_model = _lane_model(lane_models, "pulse.signal_analyst", default="")
    bear_model = _lane_model(lane_models, "pulse.bear_case", default="")
    judge_model = _lane_model(lane_models, "pulse.risk_portfolio_judge", default="")
    if no_llm:
        return PulseStagePlan(
            run_signal_analyst=False,
            run_bear_case=False,
            run_risk_portfolio_judge=False,
            signal_model=signal_model,
            bear_model=bear_model,
            judge_model=None,
        )
    return PulseStagePlan(
        run_signal_analyst=True,
        run_bear_case=True,
        run_risk_portfolio_judge=bool(public_judge),
        signal_model=signal_model,
        bear_model=bear_model,
        judge_model=judge_model if public_judge else None,
    )


def _lane_model(lane_models: Mapping[str, str], lane: str, *, default: str) -> str:
    value = str(lane_models.get(lane) or "").strip()
    if value:
        return value
    pipeline = str(lane_models.get("pulse.pipeline") or "").strip()
    return pipeline or default


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


def _hash_json(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "PulseCostGuardAction",
    "PulseCostGuardDecision",
    "PulseRunFingerprint",
    "decide_pulse_agent_cost",
]
