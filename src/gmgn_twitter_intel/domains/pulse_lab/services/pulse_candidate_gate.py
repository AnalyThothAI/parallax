from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import ScoreBand
from gmgn_twitter_intel.domains.token_intel.interfaces import TOKEN_FACTOR_SNAPSHOT_VERSION, clamp_score, safe_float


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


<<<<<<< HEAD
def _component_scores(radar: dict[str, Any]) -> dict[str, int]:
    return {key: _score_at(radar, key) for key in ("heat", "quality", "propagation", "tradeability", "timing")}
=======
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
>>>>>>> origin/main


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


<<<<<<< HEAD
def _hard_risks(radar: dict[str, Any], risk_reasons: list[str]) -> list[str]:
    risks = [
        _normalize_risk(risk)
        for component in _dict_values(radar)
        for risk in (component.get("hard_risks", []) if isinstance(component, dict) else [])
    ]
    risks.extend(_normalize_risk(risk) for risk in risk_reasons if risk in _HARD_RISK_NAMES)
=======
def _factor_risks(snapshot: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for factor in _factor_values(snapshot):
        risks.extend(_stable_strings(factor.get("risk_flags")))
>>>>>>> origin/main
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
<<<<<<< HEAD
        for key in ("hard_risks", "risks", "risk_flags"):
            values = source.get(key) or []
            risks.extend(_normalize_risk(item) for item in values)
    for segment in _list_or_empty(timeline.get("stage_segments")):
        if not isinstance(segment, dict):
            continue
        summary_facts = _dict_or_empty(segment.get("summary_facts"))
        risks.extend(_normalize_risk(item) for item in summary_facts.get("risks", []))
    return risks


def _phase(model: PulseThesisPayload, radar: dict[str, Any], timeline: dict[str, Any]) -> str:
    if model.social_phase != "unknown":
        return model.social_phase
    windows = _dict_or_empty(timeline.get("windows"))
    for window in ("5m", "1h", "4h", "24h"):
        value = windows.get(window)
        if isinstance(value, dict) and value.get("phase"):
            return str(value["phase"])
    propagation = radar.get("propagation")
    return str(propagation.get("phase") if isinstance(propagation, dict) else radar.get("phase") or "unknown")


def _market_status(radar: dict[str, Any], market: dict[str, Any]) -> str | None:
    candidates = (
        market.get("market_status"),
        _nested(radar, "price", "market_status"),
        _nested(radar, "tradeability", "market_status"),
        radar.get("market_status"),
    )
    for value in candidates:
        if value:
            return str(value)
    market_fresh = _nested(radar, "tradeability", "market_fresh")
    if market_fresh is not None:
        return "fresh" if bool(market_fresh) else "stale"
    return None


def _score_at(radar: dict[str, Any], key: str) -> int:
    value = radar.get(key)
    if isinstance(value, dict):
        return clamp_score(safe_int(value.get("score")))
    return clamp_score(safe_int(value))


def _decision(radar: dict[str, Any]) -> str | None:
    return str(_nested(radar, "opportunity", "decision") or radar.get("decision") or "").strip() or None


def _chase_risk(radar: dict[str, Any]) -> bool:
    timing = _dict_or_empty(radar.get("timing"))
    price = _dict_or_empty(radar.get("price"))
    price_lead = max(
        safe_float(timing.get("price_change_before_social_pct")),
        safe_float(price.get("price_change_before_social_pct")),
        safe_float(radar.get("price_change_before_social_pct")),
    )
    return bool(timing.get("chase_risk") or radar.get("chase_risk") or price_lead >= 0.15)


def _strong_information(scores: dict[str, int], confidence: float, thresholds: PulseGateThresholds) -> bool:
    return (
        scores["heat"] >= thresholds.trade_heat_min
        or scores["quality"] >= thresholds.trade_quality_min
        or scores["propagation"] >= thresholds.trade_propagation_min
        or confidence >= thresholds.confidence_min
    )


def _is_low_information(risk_reasons: list[str], timeline: dict[str, Any]) -> bool:
    return bool(set(risk_reasons) & _LOW_INFO_RISKS) or _duplicate_text_share(timeline) >= 0.5


def _public_only_low_confirmed(risks: list[str], timeline: dict[str, Any]) -> bool:
    if "public_only_unconfirmed" not in risks and "public_stream_coverage" not in risks:
        return False
    if not timeline:
        return False
    return _timeline_count(timeline, "authors") <= 2 and _timeline_count(timeline, "mentions") <= 3


def _duplicate_text_share(timeline: dict[str, Any]) -> float:
    windows = _dict_or_empty(timeline.get("windows"))
    shares = [safe_float(window.get("duplicate_text_share")) for window in windows.values() if isinstance(window, dict)]
    post_clusters = _list_or_empty(timeline.get("post_clusters"))
    shares.extend(
        safe_float(cluster.get("duplicate_text_share")) for cluster in post_clusters if isinstance(cluster, dict)
    )
    return max(shares, default=safe_float(timeline.get("duplicate_text_share")))


def _timeline_count(timeline: dict[str, Any], key: str) -> int:
    windows = _dict_or_empty(timeline.get("windows"))
    counts = [safe_int(window.get(key)) for window in windows.values() if isinstance(window, dict)]
    return max(counts, default=safe_int(timeline.get(key)))
=======
        factor_map = family_payload.get("factors")
        if isinstance(factor_map, dict):
            factors.extend(value for value in factor_map.values() if isinstance(value, dict))
    return factors
>>>>>>> origin/main


def _nested(data: dict[str, Any], outer: str, inner: str) -> Any:
    value = data.get(outer)
    if isinstance(value, dict):
        return value.get(inner)
    return None


<<<<<<< HEAD
def _dict_values(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [value for value in data.values() if isinstance(value, dict)]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_risk(value: Any) -> str:
    risk = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "duplicate_text": "duplicate_text_cluster",
        "repeated_text": "repeated_text_cluster",
        "price_chase_risk": "chase_risk",
        "missing_market": "market_missing",
        "stale_market": "market_stale",
        "market_unavailable": "market_missing",
        "market_cap_missing": "missing_market_cap",
        "unresolved_token_identity": "identity_ambiguous",
        "identity_unresolved": "identity_ambiguous",
        "missing_liquidity": "liquidity_missing",
    }
    return aliases.get(risk, risk)
=======
def _stable_strings(values: Any) -> list[str]:
    if not isinstance(values, list | tuple | set):
        return []
    return [str(value).strip() for value in values if str(value or "").strip()]
>>>>>>> origin/main


def _dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
