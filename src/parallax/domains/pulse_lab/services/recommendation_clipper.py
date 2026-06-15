from __future__ import annotations

from parallax.domains.pulse_lab.services.evidence_completeness_gate import EvidenceCompletenessGateResult
from parallax.domains.pulse_lab.services.pulse_candidate_gate import PulseGateResult
from parallax.domains.pulse_lab.types.agent_decision import FinalDecision, TradePlaybook

_RECOMMENDATION_RANK = {
    "abstain": 0,
    "ignore": 1,
    "watchlist": 2,
    "trade_candidate": 3,
    "high_conviction": 4,
}


def clip_recommendation(
    decision: FinalDecision,
    *,
    gate: PulseGateResult,
    evidence_gate: EvidenceCompletenessGateResult,
) -> FinalDecision:
    """Apply deterministic gate ceilings before public write/eval."""

    if not isinstance(gate, PulseGateResult):
        raise TypeError(
            f"pulse_recommendation_clipper_gate_contract_required: expected PulseGateResult, got {type(gate).__name__}"
        )
    if not isinstance(evidence_gate, EvidenceCompletenessGateResult):
        raise TypeError(
            "pulse_recommendation_clipper_evidence_gate_contract_required: "
            f"expected EvidenceCompletenessGateResult, got {type(evidence_gate).__name__}"
        )

    decision = _apply_evidence_gate(decision, evidence_gate=evidence_gate)
    if decision.recommendation == "abstain":
        return decision
    pulse_status = str(gate.pulse_status or "")
    max_recommendation = str(gate.max_recommendation or "")
    if pulse_status == "risk_rejected_high_info":
        return _clip_to_ignore(decision, reason="risk_rejected_high_info")
    if max_recommendation and _rank(decision.recommendation) > _rank(max_recommendation):
        if max_recommendation == "ignore":
            return _clip_to_ignore(decision, reason="gate_recommendation_ceiling")
        if max_recommendation in {"watch", "watchlist", "token_watch"}:
            return _replace_recommendation(decision, recommendation="watchlist")
    return decision


def _apply_evidence_gate(
    decision: FinalDecision,
    *,
    evidence_gate: EvidenceCompletenessGateResult,
) -> FinalDecision:
    max_decision_status = str(evidence_gate.max_decision_status or "")
    if max_decision_status == "abstain" or evidence_gate.public_allowed is False:
        return _clip_to_abstain(
            decision,
            reason=str(evidence_gate.blocked_reason or "evidence_gate_blocked"),
            evidence_gate=evidence_gate,
        )
    max_recommendation = _recommendation_from_decision_status(max_decision_status)
    if max_recommendation and _rank(decision.recommendation) > _rank(max_recommendation):
        if max_recommendation == "ignore":
            return _clip_to_ignore(decision, reason="evidence_gate_recommendation_ceiling")
        return _replace_recommendation(
            _append_gate_refs(decision, evidence_gate=evidence_gate, field_name="data_gap_refs"),
            recommendation=max_recommendation,
        )
    return decision


def _clip_to_ignore(decision: FinalDecision, *, reason: str) -> FinalDecision:
    payload = decision.model_dump(mode="json")
    residual_risks = list(payload.get("residual_risks") or [])
    if reason not in residual_risks:
        residual_risks.append(reason)
    payload.update(
        {
            "recommendation": "ignore",
            "confidence": min(float(payload.get("confidence") or 0.0), 0.49),
            "abstain_reason": None,
            "playbook": TradePlaybook(
                has_playbook=False,
                watch_signals=[],
                exit_triggers=[],
                monitoring_horizon=_playbook_monitoring_horizon(payload),
            ).model_dump(mode="json"),
            "residual_risks": residual_risks,
        }
    )
    return FinalDecision.model_validate(payload)


def _clip_to_abstain(
    decision: FinalDecision,
    *,
    reason: str,
    evidence_gate: EvidenceCompletenessGateResult,
) -> FinalDecision:
    payload = _append_gate_refs(decision, evidence_gate=evidence_gate, field_name="data_gap_refs").model_dump(
        mode="json"
    )
    payload.update(
        {
            "recommendation": "abstain",
            "confidence": 0.0,
            "abstain_reason": reason,
            "playbook": TradePlaybook(
                has_playbook=False,
                watch_signals=[],
                exit_triggers=[],
                monitoring_horizon=_playbook_monitoring_horizon(payload),
            ).model_dump(mode="json"),
        }
    )
    return FinalDecision.model_validate(payload)


def _replace_recommendation(decision: FinalDecision, *, recommendation: str) -> FinalDecision:
    payload = decision.model_dump(mode="json")
    payload["recommendation"] = recommendation
    if recommendation in {"ignore", "abstain"}:
        payload["playbook"] = TradePlaybook(
            has_playbook=False,
            watch_signals=[],
            exit_triggers=[],
            monitoring_horizon=_playbook_monitoring_horizon(payload),
        ).model_dump(mode="json")
    return FinalDecision.model_validate(payload)


def _rank(value: str) -> int:
    return _RECOMMENDATION_RANK.get(str(value or ""), -1)


def _recommendation_from_decision_status(value: str) -> str:
    if value == "trade_candidate":
        return "trade_candidate"
    if value in {"token_watch", "watch"}:
        return "watchlist"
    if value == "risk_rejected_high_info":
        return "ignore"
    if value == "abstain":
        return "abstain"
    return ""


def _playbook_monitoring_horizon(payload: dict[str, object]) -> str:
    playbook = payload.get("playbook")
    if not isinstance(playbook, dict):
        raise TypeError("pulse_recommendation_clipper_playbook_horizon_required")
    horizon = str(playbook.get("monitoring_horizon") or "").strip()
    if not horizon:
        raise TypeError("pulse_recommendation_clipper_playbook_horizon_required")
    return horizon


def _append_gate_refs(
    decision: FinalDecision,
    *,
    evidence_gate: EvidenceCompletenessGateResult,
    field_name: str,
) -> FinalDecision:
    refs = tuple(str(ref).strip() for ref in evidence_gate.required_ref_ids if str(ref or "").strip())
    if not refs:
        return decision
    payload = decision.model_dump(mode="json")
    existing = list(payload.get(field_name) or [])
    for ref in refs:
        if ref.startswith("gate:") and ref not in existing:
            existing.append(ref)
    payload[field_name] = existing
    return FinalDecision.model_validate(payload)


__all__ = ["clip_recommendation"]
