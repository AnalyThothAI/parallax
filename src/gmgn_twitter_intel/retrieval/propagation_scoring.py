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
    watch_status = str(features.get("watch_status") or "")
    reproduction_rate = safe_float(features.get("reproduction_rate"))
    phase_hint = features.get("phase_hint")

    score = 0.0
    reasons: list[str] = []
    risks: list[str] = []
    risk_caps: list[dict[str, Any]] = []
    contributions: list[dict[str, Any]] = []

    author_points = log_points(independent_authors, scale=12, max_points=18)
    effective_points = log_points(effective_authors, scale=8, max_points=18)
    new_author_points = ratio_points(new_authors, max_ratio=8, max_points=16)
    reproduction_points = ratio_points(reproduction_rate, max_ratio=1.0, max_points=16)
    concentration_points = max(0.0, (1.0 - min(1.0, top_share)) * 14.0)
    watched_points = min(10.0, watched_author_count * 6.0)
    seed_points = 0.0
    if seed_lag_ms is not None:
        seed_points = 10.0 if int(seed_lag_ms) <= 10 * 60_000 else 5.0
    duplicate_points = max(0.0, (1.0 - min(1.0, duplicate_share)) * 8.0)

    for feature, value, reason in [
        ("propagation.independent_authors", author_points, "independent_authors"),
        ("propagation.effective_authors", effective_points, "effective_authors"),
        ("propagation.new_authors", new_author_points, "new_author_growth"),
        ("propagation.reproduction", reproduction_points, "bucket_reproduction"),
        ("propagation.concentration", concentration_points, "low_concentration"),
        ("propagation.watched_authors", watched_points, "watched_author_present"),
        ("propagation.seed_lag", seed_points, "fast_seed_to_token_lag"),
        ("propagation.duplicate_text", duplicate_points, "low_duplicate_text"),
    ]:
        score += value
        contributions.append(contribution(feature, value, reason))

    if top_share >= 0.65 and mentions >= 3:
        phase = "concentration"
        risks.append("author_concentration_high")
        risk_caps.append(cap("author_concentration_high", 60))
    elif phase_hint in {"seed", "concentration", "fade", "expansion", "ignition"}:
        phase = str(phase_hint)
    elif independent_authors >= 5 and effective_authors >= 3.5 and top_share < 0.50 and reproduction_rate >= 0.60:
        phase = "expansion"
        reasons.extend(["independent_expansion", "low_concentration"])
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
    if watch_status == "seed_linked":
        reasons.append("watched_seed_link")
    if phase == "seed":
        risk_caps.append(cap("seed_phase", 55))
    if phase == "concentration":
        risk_caps.append(cap("concentration_phase", 60))
    if top_share >= 0.75:
        risk_caps.append(cap("top_author_dominance", 50))
    if new_authors == 0 and mentions >= 3:
        risks.append("no_new_author_growth")
        risk_caps.append(cap("no_new_author_growth", 65))

    return score_payload(
        score_version="propagation_v2",
        score=score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=risk_caps,
        data_health={"timeline_features": "ready"},
        extra={
            "independent_authors": independent_authors,
            "effective_authors": round(effective_authors, 4),
            "new_authors": new_authors,
            "top_author_share": top_share,
            "duplicate_text_share": duplicate_share,
            "author_entropy": safe_float(features.get("author_entropy")),
            "reproduction_rate": reproduction_rate,
            "phase": phase,
            "top_authors": features.get("top_authors") or [],
            "watch_status": watch_status,
        },
    )
