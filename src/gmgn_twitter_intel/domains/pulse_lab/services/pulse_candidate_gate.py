from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import ScoreBand
from gmgn_twitter_intel.domains.pulse_lab.types.pulse_thesis import PulseThesisPayload, validate_pulse_thesis_payload
from gmgn_twitter_intel.domains.token_intel.interfaces import clamp_score, safe_float, safe_int

_TRADE_PHASES = {"ignition", "expansion"}
_HARD_RISK_NAMES = {
    "chase_risk",
    "market_stale",
    "market_missing",
    "missing_market_cap",
    "identity_ambiguous",
    "unresolved_token_identity",
    "liquidity_missing",
    "missing_liquidity",
    "missing_market",
    "stale_market",
    "lookahead_risk",
}
_LOW_INFO_RISKS = {
    "duplicate_text_cluster",
    "repeated_text_cluster",
    "public_only_unconfirmed",
    "thin_mentions",
    "thin_public_only",
    "weak_evidence",
}


@dataclass(frozen=True)
class PulseGateResult:
    pulse_status: str
    verdict: str
    candidate_score: float
    score_band: ScoreBand
    gate_reasons: list[str]
    risk_reasons: list[str]
    hard_risks: list[str]


@dataclass(frozen=True)
class PulseGateThresholds:
    trade_heat_min: int = 75
    trade_quality_min: int = 62
    trade_propagation_min: int = 62
    tradeability_min: int = 70
    timing_min: int = 50
    confidence_min: float = 0.65
    token_watch_signal_min: int = 45
    high_conviction_min: int = 78


def gate_pulse_candidate(
    *,
    thesis: PulseThesisPayload | dict[str, Any],
    radar_score: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    timeline_context: dict[str, Any] | None = None,
    historical_credit: float | None = None,
    thresholds: PulseGateThresholds | None = None,
) -> PulseGateResult:
    model = validate_pulse_thesis_payload(thesis)
    resolved_thresholds = thresholds or PulseGateThresholds()
    radar = radar_score or {}
    market = market_context or {}
    timeline = timeline_context or {}
    component_scores = _component_scores(radar)
    phase = _phase(model, radar, timeline)
    market_status = _market_status(radar, market)
    risk_reasons = _risk_reasons(model, radar, market, timeline, market_status=market_status)
    hard_risks = _hard_risks(radar, risk_reasons)
    low_information = _is_low_information(risk_reasons, timeline)
    gate_reasons = _gate_reasons(
        model,
        component_scores,
        radar,
        phase,
        market_status,
        hard_risks,
        low_information,
        resolved_thresholds,
    )
    candidate_score = _candidate_score(
        component_scores,
        confidence=model.confidence,
        historical_credit=historical_credit,
        market_status=market_status,
        hard_risks=hard_risks,
        low_information=low_information,
    )
    pulse_status = _pulse_status(
        model,
        component_scores,
        radar,
        phase,
        market_status,
        risk_reasons,
        hard_risks,
        gate_reasons,
        low_information,
        resolved_thresholds,
    )
    score_band = _score_band(pulse_status, candidate_score, hard_risks, resolved_thresholds)

    return PulseGateResult(
        pulse_status=pulse_status,
        verdict=pulse_status,
        candidate_score=float(candidate_score),
        score_band=score_band,
        gate_reasons=gate_reasons,
        risk_reasons=risk_reasons,
        hard_risks=hard_risks,
    )


def _component_scores(radar: dict[str, Any]) -> dict[str, int]:
    return {key: _score_at(radar, key) for key in ("heat", "quality", "propagation", "tradeability", "timing")}


def _pulse_status(
    model: PulseThesisPayload,
    scores: dict[str, int],
    radar: dict[str, Any],
    phase: str,
    market_status: str | None,
    risk_reasons: list[str],
    hard_risks: list[str],
    gate_reasons: list[str],
    low_information: bool,
    thresholds: PulseGateThresholds,
) -> str:
    strong_info = _strong_information(scores, model.confidence, thresholds)
    identity_risk = bool({"identity_ambiguous", "unresolved_token_identity"} & set(risk_reasons))
    chase_risk = "chase_risk" in risk_reasons

    if chase_risk:
        return "risk_rejected_high_info"
    if hard_risks and strong_info:
        return "risk_rejected_high_info"
    if low_information:
        return "blocked_low_information"
    if identity_risk:
        return "blocked_low_information"
    if _passes_trade_gate(model, scores, radar, phase, market_status, hard_risks, low_information, thresholds):
        return "trade_candidate"
    if model.candidate_type == "source_seed":
        return "theme_watch" if strong_info else "blocked_low_information"
    signal_min = thresholds.token_watch_signal_min
    if (
        scores["heat"] >= signal_min
        or scores["quality"] >= signal_min
        or scores["propagation"] >= signal_min
        or model.confidence >= 0.55
    ):
        gate_reasons.append("trade_gate_incomplete")
        return "token_watch"
    return "blocked_low_information"


def _passes_trade_gate(
    model: PulseThesisPayload,
    scores: dict[str, int],
    radar: dict[str, Any],
    phase: str,
    market_status: str | None,
    hard_risks: list[str],
    low_information: bool,
    thresholds: PulseGateThresholds,
) -> bool:
    return (
        model.candidate_type == "token_target"
        and model.target_type in {"Asset", "CexToken"}
        and bool(model.target_id)
        and _decision(radar) == "driver"
        and scores["heat"] >= thresholds.trade_heat_min
        and scores["quality"] >= thresholds.trade_quality_min
        and scores["propagation"] >= thresholds.trade_propagation_min
        and scores["tradeability"] >= thresholds.tradeability_min
        and scores["timing"] >= thresholds.timing_min
        and phase in _TRADE_PHASES
        and market_status == "fresh"
        and not hard_risks
        and not low_information
        and not _chase_risk(radar)
        and model.confidence >= thresholds.confidence_min
    )


def _candidate_score(
    scores: dict[str, int],
    *,
    confidence: float,
    historical_credit: float | None,
    market_status: str | None,
    hard_risks: list[str],
    low_information: bool,
) -> int:
    weighted = (
        scores["heat"] * 0.22
        + scores["quality"] * 0.18
        + scores["propagation"] * 0.20
        + scores["tradeability"] * 0.18
        + scores["timing"] * 0.10
        + safe_float(confidence) * 100 * 0.12
    )
    if historical_credit is not None:
        weighted = weighted * 0.92 + safe_float(historical_credit) * 100 * 0.08
    if market_status != "fresh":
        weighted -= 12
    if low_information:
        weighted -= 18
    if hard_risks:
        weighted = min(weighted - 20, 48)
    return clamp_score(weighted)


def _score_band(
    pulse_status: str,
    score: int,
    hard_risks: list[str],
    thresholds: PulseGateThresholds,
) -> ScoreBand:
    if pulse_status == "trade_candidate" and score >= thresholds.high_conviction_min:
        return "high_conviction"
    if pulse_status in {"blocked_low_information", "risk_rejected_high_info"}:
        return "blocked" if hard_risks or score < 55 else "speculative"
    if pulse_status in {"trade_candidate", "token_watch"} and score >= 55:
        return "watch"
    return "speculative"


def _gate_reasons(
    model: PulseThesisPayload,
    scores: dict[str, int],
    radar: dict[str, Any],
    phase: str,
    market_status: str | None,
    hard_risks: list[str],
    low_information: bool,
    thresholds: PulseGateThresholds,
) -> list[str]:
    if _passes_trade_gate(model, scores, radar, phase, market_status, hard_risks, low_information, thresholds):
        return ["trade_gate_passed"]
    reasons = ["trade_gate_incomplete"]
    for key, threshold in (
        ("heat", thresholds.trade_heat_min),
        ("quality", thresholds.trade_quality_min),
        ("propagation", thresholds.trade_propagation_min),
        ("tradeability", thresholds.tradeability_min),
        ("timing", thresholds.timing_min),
    ):
        if scores[key] < threshold:
            reasons.append(f"{key}_below_trade_threshold")
    if _decision(radar) != "driver":
        reasons.append("radar_not_driver")
    if phase not in _TRADE_PHASES:
        reasons.append("phase_not_tradeable")
    if market_status != "fresh":
        reasons.append("market_not_fresh")
    if model.confidence < thresholds.confidence_min:
        reasons.append("agent_confidence_below_trade_threshold")
    if model.candidate_type != "token_target":
        reasons.append("source_seed_not_tradeable")
    if hard_risks:
        reasons.append("hard_risk_present")
    if low_information:
        reasons.append("low_information")
    return _dedupe(reasons)


def _risk_reasons(
    model: PulseThesisPayload,
    radar: dict[str, Any],
    market: dict[str, Any],
    timeline: dict[str, Any],
    *,
    market_status: str | None,
) -> list[str]:
    risks = _collected_risks(radar, market, timeline)
    risks.extend(_normalize_risk(risk) for risk in model.top_risks)
    if _chase_risk(radar):
        risks.append("chase_risk")
    if market_status is None:
        risks.append("market_missing")
    elif market_status != "fresh":
        risks.append("market_stale" if market_status == "stale" else "market_missing")
    if model.candidate_type != "token_target" and "unresolved_token_identity" in risks:
        risks.append("identity_ambiguous")
    if _duplicate_text_share(timeline) >= 0.5:
        risks.append("duplicate_text_cluster")
    if _public_only_low_confirmed(risks, timeline):
        risks.append("public_only_unconfirmed")
    return _dedupe(risk for risk in risks if risk)


def _hard_risks(radar: dict[str, Any], risk_reasons: list[str]) -> list[str]:
    risks = [
        _normalize_risk(risk)
        for component in _dict_values(radar)
        for risk in (component.get("hard_risks", []) if isinstance(component, dict) else [])
    ]
    risks.extend(_normalize_risk(risk) for risk in risk_reasons if risk in _HARD_RISK_NAMES)
    return _dedupe(risks)


def _collected_risks(radar: dict[str, Any], market: dict[str, Any], timeline: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for source in [radar, market, timeline, *_dict_values(radar)]:
        if not isinstance(source, dict):
            continue
        for key in ("hard_risks", "risks", "risk_flags"):
            values = source.get(key) or []
            risks.extend(_normalize_risk(item) for item in values)
    for segment in timeline.get("stage_segments", []) if isinstance(timeline.get("stage_segments"), list) else []:
        if not isinstance(segment, dict):
            continue
        summary_facts = segment.get("summary_facts") if isinstance(segment.get("summary_facts"), dict) else {}
        risks.extend(_normalize_risk(item) for item in summary_facts.get("risks", []))
    return risks


def _phase(model: PulseThesisPayload, radar: dict[str, Any], timeline: dict[str, Any]) -> str:
    if model.social_phase != "unknown":
        return model.social_phase
    windows = timeline.get("windows") if isinstance(timeline.get("windows"), dict) else {}
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
    timing = radar.get("timing") if isinstance(radar.get("timing"), dict) else {}
    price = radar.get("price") if isinstance(radar.get("price"), dict) else {}
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
    windows = timeline.get("windows") if isinstance(timeline.get("windows"), dict) else {}
    shares = [safe_float(window.get("duplicate_text_share")) for window in windows.values() if isinstance(window, dict)]
    post_clusters = timeline.get("post_clusters") if isinstance(timeline.get("post_clusters"), list) else []
    shares.extend(
        safe_float(cluster.get("duplicate_text_share")) for cluster in post_clusters if isinstance(cluster, dict)
    )
    return max(shares, default=safe_float(timeline.get("duplicate_text_share")))


def _timeline_count(timeline: dict[str, Any], key: str) -> int:
    windows = timeline.get("windows") if isinstance(timeline.get("windows"), dict) else {}
    counts = [safe_int(window.get(key)) for window in windows.values() if isinstance(window, dict)]
    return max(counts, default=safe_int(timeline.get(key)))


def _nested(data: dict[str, Any], outer: str, inner: str) -> Any:
    value = data.get(outer)
    if isinstance(value, dict):
        return value.get(inner)
    return None


def _dict_values(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [value for value in data.values() if isinstance(value, dict)]


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


def _dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
