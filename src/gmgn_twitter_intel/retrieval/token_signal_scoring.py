from __future__ import annotations

from typing import Any


def signal_block(
    row: dict[str, Any],
    *,
    market: dict[str, Any],
    flow: dict[str, Any],
    diffusion: dict[str, Any],
    watch: dict[str, Any],
    evidence_highlight_best: dict[str, Any] | None,
) -> dict[str, Any]:
    identity_status = str(row["identity_status"])
    reasons: list[str] = ["coverage_public_stream"]
    risks: list[str] = []
    contributions: list[dict[str, Any]] = []
    score = int(diffusion.get("score") or 0)
    contributions.append(
        {"feature": "diffusion_health", "value": score, "reason": str(diffusion.get("status") or "thin")}
    )

    if identity_status == "resolved_ca":
        score += 20
        contributions.append({"feature": "identity_certainty", "value": 20, "reason": "resolved_ca"})
        reasons.append("resolved_ca")
    else:
        score -= 30
        contributions.append({"feature": "identity_certainty", "value": -30, "reason": identity_status})
        risks.append(identity_status)
        if identity_status in {"unresolved_symbol", "symbol_only"}:
            risks.append("symbol_only_no_market_identity")

    attribution_confidence = float(flow.get("avg_attribution_confidence") or 0.0)
    if int(flow.get("symbol_mentions") or 0) > 0:
        reasons.append("symbol_mentions_attributed")
    if attribution_confidence >= 0.85:
        score += 10
        contributions.append({"feature": "attribution_quality", "value": 10, "reason": "high_attribution_confidence"})
        reasons.append("high_attribution_confidence")
    elif attribution_confidence >= 0.70:
        score += 5
        contributions.append(
            {"feature": "attribution_quality", "value": 5, "reason": "acceptable_attribution_confidence"}
        )
        reasons.append("acceptable_attribution_confidence")
    else:
        score -= 25
        contributions.append({"feature": "attribution_quality", "value": -25, "reason": "attribution_confidence_low"})
        risks.append("attribution_confidence_low")

    watch_status = str(watch.get("status") or "public_only")
    if watch_status == "direct_watch":
        score += 15
        contributions.append({"feature": "watched_confirmation", "value": 15, "reason": "direct_watch"})
        reasons.append("direct_watch")
    elif watch_status == "seed_linked":
        score += 12
        contributions.append({"feature": "watched_confirmation", "value": 12, "reason": "seed_linked"})
        reasons.append("seed_linked")
    else:
        score -= 8
        contributions.append({"feature": "watched_confirmation", "value": -8, "reason": "public_only"})
        risks.append("no_watched_confirmation")

    if int(flow["mention_delta"]) > 0:
        score += 12
        contributions.append({"feature": "flow_acceleration", "value": 12, "reason": "rolling_social_acceleration"})
        reasons.append("rolling_social_acceleration")
    if _ready_social_burst(flow):
        score += 15
        contributions.append({"feature": "flow_acceleration", "value": 15, "reason": "social_burst"})
        reasons.append("social_burst")
    elif _insufficient_baseline_new_burst(flow):
        score += 6
        contributions.append({"feature": "flow_acceleration", "value": 6, "reason": "insufficient_baseline_new_burst"})
        reasons.append("insufficient_baseline_new_burst")

    if market["market_status"] == "missing":
        score -= 35
        contributions.append({"feature": "market_context", "value": -35, "reason": "market_missing"})
        risks.append("market_missing")
    elif market["market_status"] == "fresh":
        score += 15
        contributions.append({"feature": "market_context", "value": 15, "reason": "fresh_market"})
        reasons.append("fresh_market")
    else:
        score -= 10
        contributions.append({"feature": "market_context", "value": -10, "reason": "market_stale"})
        risks.append("market_stale")
    if market["market_cap"] is None:
        score -= 20
        contributions.append({"feature": "market_context", "value": -20, "reason": "market_cap_missing"})
        risks.append("market_cap_missing")
    else:
        score += 10
        contributions.append({"feature": "market_context", "value": 10, "reason": "market_cap_present"})
        reasons.append("market_cap_present")
    if market.get("liquidity") is None:
        score -= 10
        contributions.append({"feature": "market_context", "value": -10, "reason": "liquidity_missing"})
        risks.append("liquidity_missing")
    else:
        score += 8
        contributions.append({"feature": "market_context", "value": 8, "reason": "liquidity_present"})
        reasons.append("liquidity_present")
    if market.get("pool_status") == "ready":
        score += 5
        contributions.append({"feature": "market_context", "value": 5, "reason": "pool_present"})
        reasons.append("pool_present")
    else:
        score -= 5
        contributions.append({"feature": "market_context", "value": -5, "reason": "pool_missing"})
        risks.append("pool_missing")

    diffusion_status = str(diffusion.get("status") or "thin")
    if diffusion_status == "healthy":
        reasons.append("healthy_diffusion")
    if "multi_author" in diffusion.get("reasons", []):
        reasons.append("multi_author_diffusion")
    for risk in diffusion.get("risks", []):
        risks.append(str(risk))
        penalty = {
            "author_concentration_high": 20,
            "repeated_text_cluster": 40,
            "shill_author_pattern": 35,
            "thin_author_set": 10,
        }.get(str(risk), 0)
        score -= penalty
        if penalty:
            contributions.append({"feature": "diffusion_risk", "value": -penalty, "reason": str(risk)})

    risk_caps = _risk_caps(risks)
    score = _apply_risk_caps(max(0, min(100, score)), risks)
    return {
        "score_version": "token_signal_v1",
        "decision": _decision(
            identity_status=identity_status,
            market=market,
            flow=flow,
            diffusion=diffusion,
            score=score,
            risks=risks,
        ),
        "score": score,
        "reasons": _dedupe(reasons),
        "risks": _dedupe(risks),
        "contributions": contributions,
        "risk_caps": risk_caps,
        "evidence_id": evidence_highlight_best.get("event_id") if evidence_highlight_best else None,
    }


def post_score(
    event: dict[str, Any],
    *,
    identity_status: str,
    diffusion: dict[str, Any] | None = None,
    market: dict[str, Any] | None = None,
    event_age_ms: int | None,
) -> dict[str, Any]:
    diffusion = diffusion or {}
    score = 0
    reasons: list[str] = []
    risks: list[str] = []
    contributions: list[dict[str, Any]] = []

    def add(feature: str, value: int, reason: str) -> None:
        nonlocal score
        score += value
        contributions.append({"feature": feature, "value": value, "reason": reason})
        if value >= 0:
            reasons.append(reason)
        else:
            risks.append(reason)

    mention_source = str(event.get("mention_source") or event.get("source") or "")
    if identity_status == "resolved_ca":
        add("identity_certainty", 18, "resolved_ca")
    else:
        add("identity_certainty", -20, identity_status)
        if identity_status in {"unresolved_symbol", "symbol_only"}:
            risks.append("symbol_only_no_market_identity")

    if mention_source == "gmgn_token_payload":
        add("source_specificity", 18, "structured_token_payload")
    elif mention_source == "cashtag":
        add("source_specificity", 8, "cashtag_match")
    elif mention_source in {"ca", "regex", "contract_address"} or "ca" in mention_source:
        add("source_specificity", 14, "ca_text_match")
    else:
        add("source_specificity", 4, "token_attribution")

    attribution_confidence = float(event.get("attribution_confidence") or 0.0)
    if attribution_confidence >= 0.90:
        add("attribution_quality", 15, "high_attribution_confidence")
    elif attribution_confidence >= 0.75:
        add("attribution_quality", 10, "acceptable_attribution_confidence")
    else:
        add("attribution_quality", -10, "attribution_confidence_low")
    if float(event.get("attribution_weight") or 0.0) >= 1.0:
        add("attribution_quality", 5, "full_attribution_weight")
    if event.get("attribution_status") == "direct":
        add("attribution_quality", 6, "direct_attribution")
    elif event.get("attribution_status") == "selected":
        add("attribution_quality", 2, "selected_symbol_candidate")

    if event.get("is_watched"):
        add("source_trust", 16, "watched_source")

    independent_authors = int(diffusion.get("independent_authors") or 0)
    if independent_authors >= 3:
        add("diffusion_context", 12, "multi_author_diffusion")
    elif independent_authors >= 2:
        add("diffusion_context", 8, "independent_author")

    if event_age_ms is not None and event_age_ms <= 5 * 60_000:
        add("freshness", 12, "recent")
    elif event_age_ms is not None and event_age_ms <= 60 * 60_000:
        add("freshness", 6, "same_window")

    if market is not None:
        if market.get("market_status") == "fresh":
            add("market_context", 8, "fresh_market")
        elif market.get("market_status") == "stale":
            add("market_context", -6, "market_stale")
        if market.get("market_cap") is not None:
            add("market_context", 6, "market_cap_present")
        if market.get("liquidity") is not None:
            add("market_context", 5, "liquidity_present")
        if market.get("pool_status") == "ready":
            add("market_context", 4, "pool_present")

    risks.extend(str(risk) for risk in diffusion.get("risks", []))
    risk_caps = _risk_caps(risks)
    capped_score = _apply_risk_caps(max(0, min(100, score)), risks)
    return {
        "score": capped_score,
        "score_version": "post_score_v1",
        "reasons": _dedupe(reasons),
        "risks": _dedupe(risks),
        "contributions": contributions,
        "risk_caps": risk_caps,
    }


def evidence_score(
    event: dict[str, Any],
    *,
    identity_status: str,
    diffusion: dict[str, Any],
    market: dict[str, Any],
    event_age_ms: int | None,
) -> dict[str, Any]:
    return post_score(
        event,
        identity_status=identity_status,
        diffusion=diffusion,
        market=market,
        event_age_ms=event_age_ms,
    )


def _decision(
    *,
    identity_status: str,
    market: dict[str, Any],
    flow: dict[str, Any],
    diffusion: dict[str, Any],
    score: int,
    risks: list[str],
) -> str:
    if _discard_required(identity_status=identity_status, market=market, diffusion=diffusion):
        return "discard"
    if (
        identity_status == "resolved_ca"
        and market["market_status"] == "fresh"
        and market["market_cap"] is not None
        and market.get("liquidity") is not None
        and market.get("pool_status") == "ready"
        and int(flow["mentions"]) >= 2
        and float(flow.get("avg_attribution_confidence") or 0.0) >= 0.70
        and _rolling_acceleration(flow)
        and str(diffusion.get("status") or "") == "healthy"
        and "author_concentration_high" not in risks
        and score >= 70
    ):
        return "driver"
    return "watch"


def _discard_required(*, identity_status: str, market: dict[str, Any], diffusion: dict[str, Any]) -> bool:
    if identity_status in {"unresolved_symbol", "ambiguous_symbol", "unresolved_chain_ca", "symbol_only"}:
        return True
    if market["market_status"] == "missing" or market["market_cap"] is None:
        return True
    return str(diffusion.get("status") or "") in {"repeated", "shill_risk"}


def _rolling_acceleration(flow: dict[str, Any]) -> bool:
    return int(flow.get("mention_delta") or 0) > 0 or _ready_social_burst(flow)


def _ready_social_burst(flow: dict[str, Any]) -> bool:
    if flow.get("baseline_status") != "ready" or flow.get("z_score") is None:
        return False
    return float(flow["z_score"]) >= 2


def _insufficient_baseline_new_burst(flow: dict[str, Any]) -> bool:
    if flow.get("z_score") is not None or flow.get("baseline_status") != "insufficient_history":
        return False
    new_burst_score = flow.get("new_burst_score")
    return new_burst_score is not None and float(new_burst_score) > 0


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _apply_risk_caps(score: int, risks: list[str]) -> int:
    caps = [item["cap"] for item in _risk_caps(risks)]
    return min([score, *caps]) if caps else score


def _risk_caps(risks: list[str]) -> list[dict[str, Any]]:
    caps = []
    if "repeated_text_cluster" in risks or "shill_author_pattern" in risks:
        caps.append(
            {
                "risk": "repeated_text_cluster" if "repeated_text_cluster" in risks else "shill_author_pattern",
                "cap": 45,
            }
        )
    if "author_concentration_high" in risks:
        caps.append({"risk": "author_concentration_high", "cap": 65})
    if "attribution_confidence_low" in risks:
        caps.append({"risk": "attribution_confidence_low", "cap": 60})
    if "market_stale" in risks:
        caps.append({"risk": "market_stale", "cap": 70})
    if "no_watched_confirmation" in risks:
        caps.append({"risk": "no_watched_confirmation", "cap": 85})
    return caps
