from __future__ import annotations

from typing import Any

from .scoring_common import cap, contribution, log_points, ratio_points, safe_float, safe_int, score_payload


def propagation_score(features: dict[str, Any]) -> dict[str, Any]:
    mentions = safe_int(features.get("mentions"))
    independent_authors = safe_int(features.get("independent_authors"))
    effective_authors = safe_float(features.get("effective_authors"), float(independent_authors))
    new_authors = safe_int(features.get("new_authors"), independent_authors)
    top_share = safe_float(features.get("top_author_share"))
    duplicate_share = safe_float(features.get("duplicate_text_share"))
    watched_author_count = safe_int(features.get("watched_author_count"))
    seed_lag_ms = features.get("seed_lag_ms")

    score = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    risk_caps: list[dict[str, Any]] = []
    contributions: list[dict[str, Any]] = []

    author_points = log_points(independent_authors, scale=12, max_points=25)
    effective_points = log_points(effective_authors, scale=8, max_points=20)
    new_author_points = ratio_points(new_authors, max_ratio=8, max_points=15)
    concentration_points = max(0.0, (1.0 - min(1.0, top_share)) * 15.0)
    watched_points = min(10.0, watched_author_count * 6.0)
    seed_points = 0.0
    if seed_lag_ms is not None:
        seed_points = 10.0 if int(seed_lag_ms) <= 10 * 60_000 else 5.0
    duplicate_points = max(0.0, (1.0 - min(1.0, duplicate_share)) * 5.0)

    for feature, value, reason in [
        ("propagation.independent_authors", author_points, "independent_authors"),
        ("propagation.effective_authors", effective_points, "effective_authors"),
        ("propagation.new_authors", new_author_points, "new_author_growth"),
        ("propagation.concentration", concentration_points, "low_concentration"),
        ("propagation.watched_authors", watched_points, "watched_author_present"),
        ("propagation.seed_lag", seed_points, "fast_seed_to_token_lag"),
        ("propagation.duplicate_text", duplicate_points, "low_duplicate_text"),
    ]:
        score += value
        contributions.append(contribution(feature, value, reason))

    if independent_authors >= 5 and effective_authors >= 4 and top_share < 0.35:
        phase = "expansion"
        reasons.extend(["independent_expansion", "low_concentration"])
    elif top_share >= 0.70:
        phase = "concentration"
        risks.append("author_concentration_high")
        risk_caps.append(cap("author_concentration_high", 65))
    elif independent_authors <= 1 or mentions <= 1:
        phase = "seed"
        risks.append("thin_author_set")
        risk_caps.append(cap("thin_author_set", 55))
    elif independent_authors <= 3:
        phase = "ignition"
        reasons.append("early_ignition")
    else:
        phase = "expansion"
        reasons.append("independent_expansion")

    if duplicate_share >= 0.50 and mentions >= 3:
        phase = "concentration" if phase != "seed" else phase
        risks.append("repeated_text_cluster")
        risk_caps.append(cap("repeated_text_cluster", 55))
    if watched_author_count:
        reasons.append("watched_author_present")

    return score_payload(
        score_version="propagation_v1",
        score=score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=risk_caps,
        extra={
            "independent_authors": independent_authors,
            "effective_authors": round(effective_authors, 4),
            "new_authors": new_authors,
            "top_author_share": top_share,
            "duplicate_text_share": duplicate_share,
            "author_entropy": safe_float(features.get("author_entropy")),
            "reproduction_rate": features.get("reproduction_rate"),
            "phase": phase,
            "top_authors": features.get("top_authors") or [],
        },
    )
