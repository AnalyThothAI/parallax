from __future__ import annotations

from typing import Any


def signal_block(
    row: dict[str, Any],
    *,
    market: dict[str, Any],
    flow: dict[str, Any],
    diffusion: dict[str, Any],
    watch: dict[str, Any],
    evidence_best: dict[str, Any] | None,
) -> dict[str, Any]:
    identity_status = str(row["identity_status"])
    reasons: list[str] = ["coverage_public_stream"]
    risks: list[str] = []
    score = int(diffusion.get("score") or 0)

    if identity_status == "resolved_ca":
        score += 20
        reasons.append("resolved_ca")
    else:
        score -= 30
        risks.append(identity_status)
        if identity_status in {"unresolved_symbol", "symbol_only"}:
            risks.append("symbol_only_no_market_identity")

    attribution_confidence = float(flow.get("avg_attribution_confidence") or 0.0)
    if int(flow.get("symbol_mentions") or 0) > 0:
        reasons.append("symbol_mentions_attributed")
    if attribution_confidence >= 0.85:
        score += 10
        reasons.append("high_attribution_confidence")
    elif attribution_confidence >= 0.70:
        score += 5
        reasons.append("acceptable_attribution_confidence")
    else:
        score -= 25
        risks.append("attribution_confidence_low")

    watch_status = str(watch.get("status") or "public_only")
    if watch_status == "direct_watch":
        score += 15
        reasons.append("direct_watch")
    elif watch_status == "seed_linked":
        score += 12
        reasons.append("seed_linked")
    else:
        score -= 8
        risks.append("no_watched_confirmation")

    if int(flow["mention_delta"]) > 0:
        score += 12
        reasons.append("rolling_social_acceleration")
    if _ready_social_burst(flow):
        score += 15
        reasons.append("social_burst")
    elif _insufficient_baseline_new_burst(flow):
        score += 6
        reasons.append("insufficient_baseline_new_burst")

    if market["market_status"] == "missing":
        score -= 35
        risks.append("market_missing")
    elif market["market_status"] == "fresh":
        score += 15
        reasons.append("fresh_market")
    else:
        score -= 10
        risks.append("market_stale")
    if market["market_cap"] is None:
        score -= 20
        risks.append("market_cap_missing")
    else:
        score += 10
        reasons.append("market_cap_present")
    if market.get("liquidity") is None:
        score -= 10
        risks.append("liquidity_missing")
    else:
        score += 8
        reasons.append("liquidity_present")
    if market.get("pool_status") == "ready":
        score += 5
        reasons.append("pool_present")
    else:
        score -= 5
        risks.append("pool_missing")

    diffusion_status = str(diffusion.get("status") or "thin")
    if diffusion_status == "healthy":
        reasons.append("healthy_diffusion")
    if "multi_author" in diffusion.get("reasons", []):
        reasons.append("multi_author_diffusion")
    for risk in diffusion.get("risks", []):
        risks.append(str(risk))
        score -= {
            "author_concentration_high": 20,
            "repeated_text_cluster": 40,
            "shill_author_pattern": 35,
            "thin_author_set": 10,
        }.get(str(risk), 0)

    score = _apply_risk_caps(max(0, min(100, score)), risks)
    return {
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
        "evidence_id": evidence_best.get("event_id") if evidence_best else None,
    }


def evidence_score(
    event: dict[str, Any],
    *,
    identity_status: str,
    diffusion: dict[str, Any],
    market: dict[str, Any],
    event_age_ms: int | None,
) -> tuple[int, list[str]]:
    score = min(35, int(diffusion.get("score") or 0) // 2)
    reasons: list[str] = []
    mention_source = str(event.get("mention_source") or event.get("source") or "")
    if mention_source == "gmgn_token_payload":
        score += 18
        reasons.append("structured_token_payload")
    elif mention_source == "cashtag":
        score += 8
        reasons.append("cashtag_match")
    elif mention_source in {"ca", "regex", "contract_address"} or "ca" in mention_source:
        score += 12
        reasons.append("ca_text_match")
    if event.get("is_watched"):
        score += 20
        reasons.append("watched_source")
    if identity_status == "resolved_ca":
        score += 20
        reasons.append("resolved_ca")
    if int(diffusion.get("independent_authors") or 0) >= 2:
        score += 10
        reasons.append("independent_author")
    if event_age_ms is not None and event_age_ms <= 5 * 60_000:
        score += 15
        reasons.append("recent")
    elif event_age_ms is not None and event_age_ms <= 60 * 60_000:
        score += 8
        reasons.append("same_window")
    if market["market_status"] == "fresh":
        score += 10
        reasons.append("fresh_market")
    if market["market_cap"] is not None:
        score += 10
        reasons.append("market_cap_present")
    if "author_concentration_high" in diffusion.get("risks", []):
        score -= 10
        reasons.append("author_concentration_high")
    if event.get("attribution_status") == "selected":
        score += 8
        reasons.append("selected_symbol_candidate")
    return max(0, min(100, score)), reasons


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
    caps = []
    if "repeated_text_cluster" in risks or "shill_author_pattern" in risks:
        caps.append(45)
    if "author_concentration_high" in risks:
        caps.append(65)
    if "attribution_confidence_low" in risks:
        caps.append(60)
    if "market_stale" in risks:
        caps.append(70)
    if "no_watched_confirmation" in risks:
        caps.append(85)
    return min([score, *caps]) if caps else score
