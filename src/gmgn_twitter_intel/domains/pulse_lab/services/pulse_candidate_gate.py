from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import ScoreBand
from gmgn_twitter_intel.domains.token_intel.interfaces import clamp_score, safe_float
from gmgn_twitter_intel.domains.token_intel.scoring.factor_snapshot import TOKEN_FACTOR_SNAPSHOT_VERSION


@dataclass(frozen=True)
class PulseGateResult:
    pulse_status: str
    verdict: str
    candidate_score: float
    score_band: ScoreBand
    gate_reasons: list[str]
    risk_reasons: list[str]
    hard_risks: list[str]
    max_recommendation: str
    eligible_for_high_alert: bool
    blocked_reasons: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "pulse_status": self.pulse_status,
            "verdict": self.verdict,
            "candidate_score": float(self.candidate_score),
            "score_band": self.score_band,
            "gate_reasons": list(self.gate_reasons),
            "risk_reasons": list(self.risk_reasons),
            "hard_risks": list(self.hard_risks),
            "max_recommendation": self.max_recommendation,
            "eligible_for_high_alert": bool(self.eligible_for_high_alert),
            "blocked_reasons": list(self.blocked_reasons),
        }


@dataclass(frozen=True)
class PulseGateThresholds:
    trade_candidate_min: int = 72
    token_watch_min: int = 45
    high_info_rejection_min: int = 30
    high_conviction_min: int = 78


def gate_pulse_candidate_from_factor_snapshot(
    *,
    factor_snapshot: dict[str, Any],
    thresholds: PulseGateThresholds | None = None,
) -> PulseGateResult:
    snapshot = _valid_snapshot(factor_snapshot)
    resolved_thresholds = thresholds or PulseGateThresholds()
    score = float(clamp_score(safe_float(_nested(snapshot, "composite", "rank_score"))))
    hard_gate_reasons = _stable_strings(_nested(snapshot, "hard_gates", "blocked_reasons"))
    blocked_reasons = _blocked_reasons(snapshot, hard_gate_reasons)
    risk_reasons = _dedupe([*blocked_reasons, *_factor_risks(snapshot)])
    hard_risks = _dedupe([*blocked_reasons, *_factor_hard_risks(snapshot)])
    eligible_for_high_alert = bool(_nested(snapshot, "hard_gates", "eligible_for_high_alert")) and not blocked_reasons
    pulse_status = _pulse_status(
        score=score,
        eligible_for_high_alert=eligible_for_high_alert,
        blocked_reasons=blocked_reasons,
        thresholds=resolved_thresholds,
    )
    score_band = _score_band(pulse_status, score, thresholds=resolved_thresholds)
    return PulseGateResult(
        pulse_status=pulse_status,
        verdict=pulse_status,
        candidate_score=score,
        score_band=score_band,
        gate_reasons=list(blocked_reasons) if blocked_reasons else [_positive_reason(pulse_status)],
        risk_reasons=risk_reasons,
        hard_risks=hard_risks,
        max_recommendation=_max_recommendation(pulse_status),
        eligible_for_high_alert=eligible_for_high_alert,
        blocked_reasons=list(blocked_reasons),
    )


def _valid_snapshot(factor_snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(factor_snapshot, dict) or not factor_snapshot:
        raise ValueError("factor_snapshot must be a non-empty dict")
    if factor_snapshot.get("schema_version") != TOKEN_FACTOR_SNAPSHOT_VERSION:
        raise ValueError(f"factor_snapshot.schema_version must be {TOKEN_FACTOR_SNAPSHOT_VERSION}")
    for key in ("subject", "hard_gates", "composite"):
        if not isinstance(factor_snapshot.get(key), dict):
            raise ValueError(f"factor_snapshot.{key} is required")
    return factor_snapshot


def _blocked_reasons(snapshot: dict[str, Any], hard_gate_reasons: list[str]) -> list[str]:
    reasons = list(hard_gate_reasons)
    subject = snapshot.get("subject") if isinstance(snapshot.get("subject"), dict) else {}
    target_type = str(subject.get("target_type") or "").strip()
    target_id = str(subject.get("target_id") or "").strip()
    if not target_type or not target_id or target_type in {"source_seed", "SourceSeed", "unresolved"}:
        reasons.append("missing_token_target")
    return _dedupe(reasons)


def _pulse_status(
    *,
    score: float,
    eligible_for_high_alert: bool,
    blocked_reasons: list[str],
    thresholds: PulseGateThresholds,
) -> str:
    if blocked_reasons:
        if score >= thresholds.high_info_rejection_min:
            return "risk_rejected_high_info"
        return "blocked_low_information"
    if eligible_for_high_alert and score >= thresholds.trade_candidate_min:
        return "trade_candidate"
    if eligible_for_high_alert and score >= thresholds.token_watch_min:
        return "token_watch"
    return "blocked_low_information"


def _score_band(pulse_status: str, score: float, *, thresholds: PulseGateThresholds) -> ScoreBand:
    if pulse_status == "trade_candidate" and score >= thresholds.high_conviction_min:
        return "high_conviction"
    if pulse_status == "trade_candidate":
        return "watch"
    if pulse_status == "token_watch" and score >= 55:
        return "watch"
    if pulse_status == "token_watch":
        return "speculative"
    return "blocked"


def _max_recommendation(pulse_status: str) -> str:
    if pulse_status == "trade_candidate":
        return "trade_candidate"
    if pulse_status == "token_watch":
        return "watch"
    if pulse_status == "risk_rejected_high_info":
        return "research"
    return "ignore"


def _positive_reason(pulse_status: str) -> str:
    if pulse_status == "trade_candidate":
        return "factor_snapshot_trade_gate_passed"
    if pulse_status == "token_watch":
        return "factor_snapshot_watch_gate_passed"
    return "factor_snapshot_low_information"


def _factor_risks(snapshot: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for factor in _factor_values(snapshot):
        risks.extend(_stable_strings(factor.get("risk_flags")))
    return _dedupe(risks)


def _factor_hard_risks(snapshot: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for factor in _factor_values(snapshot):
        hard_gate = str(factor.get("hard_gate") or "").strip()
        if hard_gate:
            risks.extend(_stable_strings(factor.get("risk_flags")))
    return _dedupe(risks)


def _factor_values(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    families = snapshot.get("families") if isinstance(snapshot.get("families"), dict) else {}
    factors: list[dict[str, Any]] = []
    for family_payload in families.values():
        if not isinstance(family_payload, dict):
            continue
        factor_map = family_payload.get("factors")
        if isinstance(factor_map, dict):
            factors.extend(value for value in factor_map.values() if isinstance(value, dict))
    return factors


def _nested(data: dict[str, Any], outer: str, inner: str) -> Any:
    value = data.get(outer)
    if isinstance(value, dict):
        return value.get(inner)
    return None


def _stable_strings(values: Any) -> list[str]:
    if not isinstance(values, list | tuple | set):
        return []
    return [str(value).strip() for value in values if str(value or "").strip()]


def _dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))

