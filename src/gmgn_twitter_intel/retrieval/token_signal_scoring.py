from __future__ import annotations

from typing import Any


def source_quality(
    *,
    identity_status: str,
    mentions: int,
    unique_authors: int,
    watched_authors: int,
    weighted_reach: int,
    top_author_share: float,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if watched_authors >= 1:
        score += 25
        reasons.append("watched_evidence")
    if unique_authors >= 2:
        score += 10
        reasons.append("multi_author")
    if unique_authors >= 3:
        score += 15
        reasons.append("independent_sources")
    if unique_authors >= 8:
        score += 10
        reasons.append("broad_source_spread")
    if weighted_reach > 0:
        score += 5
        reasons.append("known_author_reach")
    if top_author_share >= 0.75 and mentions >= 3:
        score -= 20
        reasons.append("author_concentration_high")
    if identity_status in {"unresolved_symbol", "ambiguous_symbol", "unresolved_chain_ca"}:
        score -= 15
        reasons.append(identity_status)
    return max(0, min(100, score)), reasons


def signal_block(
    row: dict[str, Any],
    *,
    market: dict[str, Any],
    flow: dict[str, Any],
    sources: dict[str, Any],
    evidence_best: dict[str, Any] | None,
) -> dict[str, Any]:
    identity_status = str(row["identity_status"])
    reasons: list[str] = ["coverage_public_stream"]
    risks: list[str] = []
    score = int(sources["source_quality_score"])

    if identity_status == "resolved_ca":
        score += 20
        reasons.append("resolved_ca")
    elif identity_status == "resolved_alias":
        score += 12
        reasons.append("resolved_alias")
        risks.append("symbol_resolved_alias")
    else:
        score -= 25
        risks.append(identity_status)

    if int(flow["watched_mentions"]) > 0:
        score += 10
        reasons.append("watched_evidence")
    else:
        risks.append("no_watched_confirmation")
    if int(flow["mention_delta"]) > 0:
        score += 10
        reasons.append("flow_accelerating")
    if flow["z_score"] is not None and float(flow["z_score"]) >= 2:
        score += 15
        reasons.append("social_burst")

    if market["market_status"] == "missing":
        score -= 25
        risks.append("market_missing")
    elif market["market_status"] == "fresh":
        score += 15
        reasons.append("fresh_market")
    else:
        risks.append("market_stale")
    if market["market_cap"] is None:
        score -= 20
        risks.append("market_cap_missing")
    else:
        score += 10
        reasons.append("market_cap_present")

    if "multi_author" in sources["source_quality_reasons"]:
        reasons.append("multi_author_flow")
    if "author_concentration_high" in sources["source_quality_reasons"]:
        score -= 15
        risks.append("author_concentration_high")

    score = max(0, min(100, score))
    return {
        "decision": _decision(
            identity_status=identity_status,
            market=market,
            flow=flow,
            sources=sources,
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
    sources: dict[str, Any],
    market: dict[str, Any],
    event_age_ms: int | None,
) -> tuple[int, list[str]]:
    score = min(35, int(sources["source_quality_score"]) // 2)
    reasons: list[str] = []
    if event.get("is_watched"):
        score += 20
        reasons.append("watched_source")
    if identity_status == "resolved_ca":
        score += 20
        reasons.append("resolved_ca")
    elif identity_status == "resolved_alias":
        score += 12
        reasons.append("resolved_alias")
    if int(sources["unique_authors"]) >= 2:
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
    if "author_concentration_high" in sources["source_quality_reasons"]:
        score -= 10
        reasons.append("author_concentration_high")
    return max(0, min(100, score)), reasons


def top_author_share(top_authors: list[dict[str, Any]], *, mentions: int) -> float:
    if not top_authors or mentions <= 0:
        return 0.0
    return max(int(author.get("count") or 0) for author in top_authors) / mentions


def _decision(
    *,
    identity_status: str,
    market: dict[str, Any],
    flow: dict[str, Any],
    sources: dict[str, Any],
    score: int,
    risks: list[str],
) -> str:
    if _discard_required(identity_status=identity_status, market=market, sources=sources):
        return "discard"
    if (
        identity_status == "resolved_ca"
        and market["market_status"] == "fresh"
        and market["market_cap"] is not None
        and int(sources["source_quality_score"]) >= 45
        and score >= 75
        and "author_concentration_high" not in risks
        and (int(flow["mention_delta"]) > 0 or int(flow["watched_mentions"]) > 0 or (flow["z_score"] or 0) >= 2)
    ):
        return "driver"
    return "watch"


def _discard_required(*, identity_status: str, market: dict[str, Any], sources: dict[str, Any]) -> bool:
    if identity_status in {"unresolved_symbol", "ambiguous_symbol", "unresolved_chain_ca"}:
        return True
    if market["market_status"] == "missing" or market["market_cap"] is None:
        return True
    return "author_concentration_high" in sources["source_quality_reasons"] and int(sources["unique_authors"]) < 2


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
