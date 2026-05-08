from __future__ import annotations

from typing import Any

from .scoring_common import cap, contribution, log_points, ratio_points, safe_float, safe_int, score_payload


def social_heat_score(features: dict[str, Any]) -> dict[str, Any]:
    mentions = safe_int(features.get("mentions"))
    weighted_mentions = safe_float(features.get("weighted_mentions"), float(mentions))
    previous_mentions = safe_int(features.get("previous_mentions"))
    mention_delta = safe_int(features.get("mention_delta"), mentions - previous_mentions)
    robust_z = safe_float(features.get("robust_z")) if features.get("robust_z") is not None else None
    z_ewma = safe_float(features.get("z_ewma")) if features.get("z_ewma") is not None else None
    z_raw = robust_z if robust_z is not None else z_ewma
    z_value = safe_float(z_raw) if z_raw is not None else None
    new_burst = features.get("new_burst_score")
    new_burst_value = safe_float(new_burst) if new_burst is not None else None
    baseline_status = str(features["baseline_status"])
    baseline_version = str(features["baseline_version"])
    baseline_sample_count = safe_int(features["baseline_sample_count"])
    baseline_nonzero_sample_count = safe_int(features["baseline_nonzero_sample_count"])
    zero_slot_count = safe_int(features["zero_slot_count"])
    stream_share = safe_float(features.get("stream_share", features.get("stream_dominance")))
    watched_share = safe_float(features.get("watched_share", features.get("watched_mindshare")))
    is_new = bool(features.get("is_new_local_evidence"))
    is_first_watched = bool(features.get("is_first_seen_by_watched"))

    reasons: list[str] = []
    risks = ["public_stream_coverage"]
    risk_caps: list[dict[str, Any]] = []
    contributions: list[dict[str, Any]] = []
    score = 0.0

    mention_points = log_points(mentions, scale=18, max_points=18)
    score += mention_points
    contributions.append(contribution("heat.mentions", mention_points, "current_mentions"))

    surprise_points = 0.0
    status = "cold"
    if baseline_status != "ready":
        risks.append("sparse_baseline")
        risk_caps.append(cap("sparse_baseline", 70))

    if robust_z is not None and robust_z >= 3:
        surprise_points = 24.0
        status = "burst"
        reasons.append("robust_z_above_3")
    elif z_ewma is not None and z_ewma >= 3:
        surprise_points = 22.0
        status = "burst"
        reasons.append("z_ewma_above_3")
    elif z_value is not None and z_value >= 2:
        surprise_points = 17.0
        status = "rising"
        reasons.append("baseline_z_above_2")
    elif new_burst_value is not None and new_burst_value > 0:
        surprise_points = min(18.0, 8.0 + new_burst_value * 4.0)
        status = "new_burst"
        reasons.append("sparse_baseline_new_burst")
    else:
        risks.append("baseline_not_discriminative")
        status = "insufficient_history" if baseline_status != "ready" else "cold"
    score += surprise_points
    contributions.append(contribution("heat.surprise", surprise_points, "baseline_surprise"))

    if mention_delta > 0:
        delta_points = min(14.0, mention_delta / max(previous_mentions, 1) * 3.0 + min(mention_delta, 5))
        reasons.append("positive_mention_delta")
    else:
        delta_points = 0.0
    score += delta_points
    contributions.append(contribution("heat.delta", delta_points, "positive_mention_delta"))

    stream_points = ratio_points(stream_share, max_ratio=0.20, max_points=8)
    watched_points = ratio_points(watched_share, max_ratio=0.30, max_points=12)
    novelty_points = 8.0 if is_new else 0.0
    first_watched_points = 8.0 if is_first_watched else 0.0
    weighted_points = min(8.0, weighted_mentions / max(mentions, 1) * 8.0) if mentions else 0.0
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
    if mentions < 3 and watched_share == 0:
        risks.append("thin_public_only")
        risk_caps.append(cap("thin_public_only", 55))
    if stream_share > 0.50:
        risks.append("market_wide_noise_or_query_bias")
        risk_caps.append(cap("market_wide_noise_or_query_bias", 75))

    return score_payload(
        score_version="social_heat_v2",
        score=score,
        reasons=reasons,
        risks=risks,
        contributions=contributions,
        risk_caps=risk_caps,
        data_health={
            "baseline_ready": baseline_status == "ready",
            "baseline_status": baseline_status,
            "sample_count": baseline_sample_count,
            "nonzero_sample_count": baseline_nonzero_sample_count,
            "zero_slot_count": zero_slot_count,
            "baseline_version": baseline_version,
            "public_stream_coverage": True,
        },
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
            "z_ewma": z_ewma,
            "robust_z": robust_z,
            "new_burst_score": new_burst_value,
            "status": status,
        },
    )
