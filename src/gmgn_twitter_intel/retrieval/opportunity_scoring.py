from __future__ import annotations

from typing import Any

from .scoring_common import cap, contribution, safe_int, score_payload

WEIGHTS = {
    "heat": 0.26,
    "quality": 0.22,
    "propagation": 0.28,
    "tradeability": 0.18,
    "timing": 0.06,
}


def opportunity_score(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    component_scores = {key: safe_int(components.get(key, {}).get("score")) for key in WEIGHTS}
    weighted_score = sum(component_scores[key] * weight for key, weight in WEIGHTS.items())
    risks: list[str] = []
    reasons: list[str] = []
    hard_risks: list[str] = []
    risk_caps: list[dict[str, Any]] = []
    contributions: list[dict[str, Any]] = []

    for key, component in components.items():
        reasons.extend(str(item) for item in component.get("reasons", []) if item)
        risks.extend(str(item) for item in component.get("risks", []) if item)
        hard_risks.extend(str(item) for item in component.get("hard_risks", []) if item)
        risk_caps.extend(dict(item) for item in component.get("risk_caps", []) if isinstance(item, dict))
        contributions.append(contribution(f"opportunity.{key}", component_scores.get(key, 0), f"{key}_component"))

    if hard_risks:
        risk_caps.append(cap("hard_risk", 40))
    propagation_phase = str((components.get("propagation") or {}).get("phase") or "")
    has_watched_confirmation = any(
        reason in reasons for reason in ("watched_source_present", "watched_author_present", "watched_seed_link")
    )
    if "public_stream_coverage" in risks and not has_watched_confirmation:
        risk_caps.append(cap("public_only_unconfirmed", 68))
    if "chase_risk" in risks:
        risk_caps.append(cap("chase_risk", 50))
    if "repeated_text_cluster" in risks or "duplicate_text_cluster" in risks:
        risk_caps.append(cap("repeated_text_cluster", 50))

    if risks.count("public_stream_coverage") > 1:
        first_coverage_index = risks.index("public_stream_coverage")
        risks = [
            risk
            for index, risk in enumerate(risks)
            if risk != "public_stream_coverage" or index == first_coverage_index
        ]

    score_payload_base = score_payload(
        score_version="social_opportunity_v4",
        score=weighted_score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=risk_caps,
        data_health={key: (components.get(key) or {}).get("data_health", {}) for key in WEIGHTS},
    )
    final_score = score_payload_base["score"]
    if hard_risks or "repeated_text_cluster" in risks or "duplicate_text_cluster" in risks:
        decision = "discard"
    elif (
        final_score >= 72
        and component_scores["heat"] >= 68
        and component_scores["quality"] >= 62
        and component_scores["propagation"] >= 62
        and component_scores["tradeability"] >= 70
        and component_scores["timing"] >= 50
        and propagation_phase in {"expansion", "ignition"}
        and not any(cap_item.get("risk") == "public_only_unconfirmed" for cap_item in risk_caps)
    ):
        decision = "driver"
    elif (
        final_score >= 45
        and component_scores["tradeability"] >= 45
        and (component_scores["propagation"] >= 45 or component_scores["heat"] >= 55 or has_watched_confirmation)
    ):
        decision = "watch"
    else:
        decision = "discard"

    score_payload_base.update(
        {
            "decision": decision,
            "decision_priority": {"driver": 3, "watch": 2, "discard": 1}[decision],
            "components": component_scores,
            "hard_risks": list(dict.fromkeys(hard_risks)),
        }
    )
    return score_payload_base
