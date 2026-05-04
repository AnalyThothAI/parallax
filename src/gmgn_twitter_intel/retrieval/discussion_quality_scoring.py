from __future__ import annotations

from typing import Any

from .post_text_quality import post_quality_score as _post_quality_score
from .scoring_common import cap, contribution, ratio_points, safe_float, safe_int, score_payload


def post_quality_score(features: dict[str, Any]) -> dict[str, Any]:
    return _post_quality_score(features)


def discussion_quality_score(features: dict[str, Any]) -> dict[str, Any]:
    mentions = max(1, safe_int(features.get("mentions")))
    direct_mentions = safe_int(features.get("direct_mentions"))
    confidence = safe_float(features.get("avg_attribution_confidence"))
    raw_duplicate_share = safe_float(features.get("duplicate_text_share"))
    duplicate_share = raw_duplicate_share if mentions >= 3 else 0.0
    informative_count = safe_int(features.get("informative_post_count"))
    watched_count = safe_int(features.get("watched_source_count"))
    market_context_count = safe_int(features.get("market_context_count"))

    score = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    risk_caps: list[dict[str, Any]] = []
    contributions: list[dict[str, Any]] = []

    direct_points = ratio_points(direct_mentions / mentions, max_ratio=0.8, max_points=20)
    if direct_points >= 14:
        reasons.append("resolved_direct_evidence")
    score += direct_points
    contributions.append(contribution("quality.direct_mentions", direct_points, "resolved_direct_evidence"))

    confidence_points = min(20.0, confidence * 20.0)
    score += confidence_points
    contributions.append(contribution("quality.attribution_confidence", confidence_points, "attribution_confidence"))
    if confidence < 0.55:
        risks.append("attribution_confidence_low")
        risk_caps.append(cap("attribution_confidence_low", 60))

    informative_ratio = informative_count / mentions
    informative_points = ratio_points(informative_ratio, max_ratio=0.75, max_points=15)
    if informative_ratio >= 0.5:
        reasons.append("informative_discussion")
    else:
        risks.append("low_information_posts")
    score += informative_points
    contributions.append(contribution("quality.informative_ratio", informative_points, "informative_discussion"))

    watched_points = ratio_points(watched_count, max_ratio=2, max_points=15)
    if watched_points:
        reasons.append("watched_source_present")
    score += watched_points
    contributions.append(contribution("quality.watched_sources", watched_points, "watched_source_present"))

    originality_points = max(0.0, (1.0 - duplicate_share) * 15.0)
    if duplicate_share >= 0.5:
        risks.append("duplicate_text_cluster")
        risk_caps.append(cap("duplicate_text_cluster", 45))
    score += originality_points
    contributions.append(contribution("quality.originality", originality_points, "non_duplicate_text"))

    market_points = ratio_points(market_context_count / mentions, max_ratio=0.5, max_points=15)
    if market_points:
        reasons.append("market_context_present")
    score += market_points
    contributions.append(contribution("quality.market_context", market_points, "market_context_present"))

    return score_payload(
        score_version="discussion_quality_v1",
        score=score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=risk_caps,
        extra={
            "evidence_specificity": round(direct_mentions / mentions, 4),
            "avg_post_quality": safe_int(features.get("avg_post_quality")),
            "avg_attribution_confidence": confidence,
            "duplicate_text_share": raw_duplicate_share,
            "informative_post_count": informative_count,
            "watched_source_count": watched_count,
        },
    )
