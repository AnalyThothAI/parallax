from __future__ import annotations

from typing import Any

from .scoring_common import cap, contribution, score_payload


def tradeability_score(features: dict[str, Any]) -> dict[str, Any]:
    identity_tradeable = (
        features.get("identity_status") == "resolved_ca"
        and bool(features.get("token_id"))
        and bool(features.get("chain"))
        and bool(features.get("address"))
    )
    market_fresh = features.get("market_status") == "fresh"
    market_cap_present = features.get("market_cap") is not None
    liquidity_present = features.get("liquidity") is not None
    pool_present = features.get("pool_status") == "ready"
    lookahead_risk = bool(features.get("lookahead_risk"))

    score = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    hard_risks: list[str] = []
    risk_caps: list[dict[str, Any]] = []
    contributions: list[dict[str, Any]] = []

    if identity_tradeable:
        score += 30.0
        reasons.append("resolved_ca")
        contributions.append(contribution("tradeability.identity", 30.0, "resolved_ca"))
    else:
        risks.append("unresolved_token_identity")
        hard_risks.append("unresolved_token_identity")
        risk_caps.append(cap("unresolved_token_identity", 20))

    if market_fresh:
        score += 25.0
        reasons.append("fresh_market")
        contributions.append(contribution("tradeability.market_fresh", 25.0, "fresh_market"))
    else:
        risk = "missing_market" if features.get("market_status") == "missing" else "stale_market"
        risks.append(risk)
        if risk == "missing_market":
            hard_risks.append(risk)
            risk_caps.append(cap(risk, 35))
        else:
            risk_caps.append(cap(risk, 70))

    if market_cap_present:
        score += 20.0
        reasons.append("market_cap_present")
        contributions.append(contribution("tradeability.market_cap", 20.0, "market_cap_present"))
    else:
        risks.append("missing_market_cap")
        hard_risks.append("missing_market_cap")
        risk_caps.append(cap("missing_market_cap", 40))

    if liquidity_present:
        score += 15.0
        reasons.append("liquidity_present")
        contributions.append(contribution("tradeability.liquidity", 15.0, "liquidity_present"))
    else:
        risks.append("missing_liquidity")

    if pool_present:
        score += 10.0
        reasons.append("pool_present")
        contributions.append(contribution("tradeability.pool", 10.0, "pool_present"))
    else:
        risks.append("missing_pool")
    if lookahead_risk:
        risks.append("lookahead_risk")
        hard_risks.append("lookahead_risk")
        risk_caps.append(cap("lookahead_risk", 40))

    return score_payload(
        score_version="tradeability_v2",
        score=score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=risk_caps,
        data_health={
            "identity": "resolved" if identity_tradeable else "unresolved",
            "market": features.get("market_status") or "missing",
        },
        extra={
            "identity_tradeable": identity_tradeable,
            "market_fresh": market_fresh,
            "market_cap_present": market_cap_present,
            "liquidity_present": liquidity_present,
            "pool_present": pool_present,
            "hard_risks": hard_risks,
        },
    )
