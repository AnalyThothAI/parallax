from __future__ import annotations

from typing import Any

from .scoring_common import cap, contribution, log_points, ratio_points, safe_float, safe_int, score_payload


def social_heat_score(features: dict[str, Any]) -> dict[str, Any]:
    mentions = safe_int(features.get("mentions"))
    weighted_mentions = safe_float(features.get("weighted_mentions"), float(mentions))
    previous_mentions = safe_int(features.get("previous_mentions"))
    mention_delta = safe_int(features.get("mention_delta"), mentions - previous_mentions)
    z_score = features.get("z_score")
    z_value = safe_float(z_score) if z_score is not None else None
    new_burst = features.get("new_burst_score")
    new_burst_value = safe_float(new_burst) if new_burst is not None else None
    stream_share = safe_float(features.get("stream_share", features.get("stream_dominance")))
    watched_share = safe_float(features.get("watched_share", features.get("watched_mindshare")))
    is_new = bool(features.get("is_new_local_evidence"))
    is_first_watched = bool(features.get("is_first_seen_by_watched"))

    reasons: list[str] = []
    risks = ["public_stream_coverage"]
    risk_caps: list[dict[str, Any]] = []
    contributions: list[dict[str, Any]] = []
    score = 0.0

    mention_points = log_points(mentions, scale=12, max_points=25)
    score += mention_points
    contributions.append(contribution("heat.mentions", mention_points, "current_mentions"))

    surprise_points = 0.0
    status = "cold"
    if z_value is not None and z_value >= 3:
        surprise_points = 25.0
        status = "burst"
        reasons.append("z_score_above_3")
    elif z_value is not None and z_value >= 2:
        surprise_points = 18.0
        status = "rising"
        reasons.append("z_score_above_2")
    elif new_burst_value is not None and new_burst_value > 0:
        surprise_points = min(18.0, 8.0 + new_burst_value * 4.0)
        status = "new_burst"
        reasons.append("insufficient_baseline_new_burst")
    else:
        risks.append("insufficient_baseline")
        status = "insufficient_history"
    score += surprise_points
    contributions.append(contribution("heat.surprise", surprise_points, "baseline_surprise"))

    if mention_delta > 0:
        delta_points = min(15.0, mention_delta / max(previous_mentions, 1) * 4.0 + min(mention_delta, 6))
        reasons.append("positive_mention_delta")
    else:
        delta_points = 0.0
    score += delta_points
    contributions.append(contribution("heat.delta", delta_points, "positive_mention_delta"))

    stream_points = ratio_points(stream_share, max_ratio=0.20, max_points=10)
    watched_points = ratio_points(watched_share, max_ratio=0.30, max_points=10)
    novelty_points = 10.0 if is_new else 0.0
    first_watched_points = 5.0 if is_first_watched else 0.0
    weighted_points = min(5.0, weighted_mentions / max(mentions, 1) * 5.0) if mentions else 0.0
    if watched_points or first_watched_points:
        reasons.append("watched_source_present")
    if is_new:
        reasons.append("new_local_evidence")
    score += stream_points + watched_points + novelty_points + first_watched_points + weighted_points
    contributions.extend(
        [
            contribution("heat.stream_share", stream_points, "stream_share"),
            contribution("heat.watched_share", watched_points, "watched_share"),
            contribution("heat.new_evidence", novelty_points, "new_local_evidence"),
            contribution("heat.first_watched", first_watched_points, "first_watched_evidence"),
            contribution("heat.weighted_mentions", weighted_points, "attribution_weighted_mentions"),
        ]
    )

    if mentions < 2:
        risks.append("thin_mentions")
        risk_caps.append(cap("thin_mentions", 45))
    if z_value is None and new_burst_value is None:
        risk_caps.append(cap("insufficient_baseline", 70))

    return score_payload(
        score_version="social_heat_v1",
        score=score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=risk_caps,
        extra={
            "mentions_5m": safe_int(features.get("mentions_5m"), mentions),
            "mentions_1h": safe_int(features.get("mentions_1h"), mentions),
            "mentions_4h": safe_int(features.get("mentions_4h")),
            "mentions_24h": safe_int(features.get("mentions_24h")),
            "weighted_mentions": weighted_mentions,
            "stream_share": stream_share,
            "watched_share": watched_share,
            "previous_mentions": previous_mentions,
            "mention_delta": mention_delta,
            "mention_delta_pct": features.get("mention_delta_pct"),
            "z_score": z_value,
            "new_burst_score": new_burst_value,
            "status": status,
        },
    )
