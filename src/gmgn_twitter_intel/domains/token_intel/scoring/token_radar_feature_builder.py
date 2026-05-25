from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from gmgn_twitter_intel.domains.token_intel.scoring.baseline_scoring import token_baseline_v2
from gmgn_twitter_intel.domains.token_intel.scoring.diffusion_health import diffusion_health
from gmgn_twitter_intel.domains.token_intel.scoring.post_text_quality import post_quality_score, post_text_features
from gmgn_twitter_intel.domains.token_intel.scoring.social_signal_features import (
    author_entropy,
    public_followup_author_count,
    source_weighted_effective_authors,
    time_to_nth_independent_author_ms,
)
from gmgn_twitter_intel.domains.token_intel.services.atomic_mention import mention_confidence_from_status, tweet_quality

BASELINE_SLOT_COUNT = 6
_SATURATED_AGE_MS = 180 * 24 * 60 * 60_000


@dataclass(frozen=True, slots=True)
class RadarFeatureSet:
    window_rows: list[dict[str, Any]]
    context_rows: list[dict[str, Any]]
    previous_rows: list[dict[str, Any]]
    attention: dict[str, Any]
    heat: dict[str, Any]
    quality: dict[str, Any]
    propagation: dict[str, Any]
    tradeability: dict[str, Any]
    timing: dict[str, Any]


def build_radar_features(
    *,
    window_rows: list[dict[str, Any]],
    context_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    now_ms: int,
    window_ms: int,
    total_window_events: int,
) -> RadarFeatureSet:
    context = list(context_rows or window_rows)
    window = [_with_source_weight(row) for row in window_rows]
    previous = list(previous_rows)
    attention = _attention(window=window, context=context, now_ms=now_ms, total_window_events=total_window_events)
    heat = _heat_features(
        window=window,
        context=context,
        previous=previous,
        attention=attention,
        now_ms=now_ms,
        window_ms=window_ms,
    )
    attention = {
        **attention,
        "previous_mentions": heat["previous_mentions"],
        "mention_delta": heat["mention_delta"],
        "mention_delta_pct": heat["mention_delta_pct"],
        "weighted_mentions": heat["weighted_mentions"],
        "attention_acceleration": heat["attention_acceleration"],
        "z_score": heat["z_score"],
        "z_ewma": heat["z_ewma"],
        "robust_z": heat["robust_z"],
        "new_burst_score": heat["new_burst_score"],
        "baseline_version": heat["baseline_version"],
        "baseline_status": heat["baseline_status"],
        "baseline_sample_count": heat["baseline_sample_count"],
        "baseline_nonzero_sample_count": heat["baseline_nonzero_sample_count"],
        "zero_slot_count": heat["zero_slot_count"],
    }
    diffusion = diffusion_health(
        window,
        watched_author_handles={str(row.get("author_handle") or "") for row in window if row.get("is_watched")},
    )
    quality = _quality_features(window, diffusion=diffusion)
    propagation = _propagation_features(
        window=window,
        previous=previous,
        window_ms=window_ms,
        diffusion=diffusion,
    )
    market = _latest_market_row(window)
    tradeability = _tradeability_features(market)
    timing = {
        "social_signal_start_ms": min((int(row.get("received_at_ms") or 0) for row in window), default=None),
        "price_change_since_social_pct": market.get("price_change_since_social_pct"),
        "price_change_before_social_pct": market.get("price_change_before_social_pct"),
        "market_observation_status": market.get("market_observation_status") or "missing_market",
    }
    return RadarFeatureSet(
        window_rows=window,
        context_rows=context,
        previous_rows=previous,
        attention=attention,
        heat=heat,
        quality=quality,
        propagation=propagation,
        tradeability=tradeability,
        timing=timing,
    )


def _attention(
    *,
    window: list[dict[str, Any]],
    context: list[dict[str, Any]],
    now_ms: int,
    total_window_events: int,
) -> dict[str, Any]:
    def count(interval_ms: int) -> int:
        since_ms = int(now_ms) - interval_ms
        return len({str(row["event_id"]) for row in context if int(row.get("received_at_ms") or 0) >= since_ms})

    event_ids = {str(row["event_id"]) for row in window}
    authors = {str(row.get("author_handle") or "") for row in window if row.get("author_handle")}
    watched = sum(1 for row in window if row.get("is_watched"))
    mentions = len(event_ids)
    return {
        "mentions_5m": count(5 * 60_000),
        "mentions_1h": count(60 * 60_000),
        "mentions_4h": count(4 * 60 * 60_000),
        "mentions_24h": count(24 * 60 * 60_000),
        "mentions_window": mentions,
        "unique_authors": len(authors),
        "watched_mentions": watched,
        "latest_seen_ms": max((int(row.get("received_at_ms") or 0) for row in window), default=0),
        "stream_share": round(mentions / max(1, int(total_window_events)), 6),
    }


def _heat_features(
    *,
    window: list[dict[str, Any]],
    context: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    attention: dict[str, Any],
    now_ms: int,
    window_ms: int,
) -> dict[str, Any]:
    mentions = len({str(row["event_id"]) for row in window})
    previous_mentions = len({str(row["event_id"]) for row in previous})
    watched_mentions = int(attention.get("watched_mentions") or 0)
    mention_delta = mentions - previous_mentions
    weighted_mentions = sum(_atomic_quality(row) * _confidence(row) for row in window)
    mention_delta_pct = mention_delta / max(previous_mentions, 1) if previous_mentions else None
    attention_acceleration = mention_delta_pct
    baseline = token_baseline_v2(
        slot_counts=_baseline_slot_counts(context=context, now_ms=now_ms, window_ms=window_ms),
        current_mentions=mentions,
        current_weighted_mentions=weighted_mentions,
    )
    z_score = baseline["robust_z"] if baseline["robust_z"] is not None else baseline["z_ewma"]
    return {
        "mentions": mentions,
        "mentions_5m": attention.get("mentions_5m"),
        "mentions_1h": attention.get("mentions_1h"),
        "mentions_4h": attention.get("mentions_4h"),
        "mentions_24h": attention.get("mentions_24h"),
        "weighted_mentions": weighted_mentions,
        "previous_mentions": previous_mentions,
        "mention_delta": mention_delta,
        "mention_delta_pct": mention_delta_pct,
        "attention_acceleration": attention_acceleration,
        "baseline_version": baseline["baseline_version"],
        "baseline_status": baseline["baseline_status"],
        "baseline_sample_count": baseline["sample_count"],
        "baseline_nonzero_sample_count": baseline["nonzero_sample_count"],
        "zero_slot_count": baseline["zero_slot_count"],
        "ewma_mean": baseline["ewma_mean"],
        "ewma_stddev": baseline["ewma_stddev"],
        "median_count": baseline["median_count"],
        "mad": baseline["mad"],
        "robust_z": baseline["robust_z"],
        "z_ewma": baseline["z_ewma"],
        "z_score": z_score,
        "new_burst_score": baseline["new_burst_score"],
        "stream_share": attention.get("stream_share"),
        "watched_share": watched_mentions / max(1, mentions),
        "is_new_local_evidence": previous_mentions == 0 and mentions > 0,
        "is_first_seen_by_watched": watched_mentions > 0 and not any(row.get("is_watched") for row in previous),
    }


def _baseline_slot_counts(*, context: list[dict[str, Any]], now_ms: int, window_ms: int) -> list[int]:
    score_start_ms = int(now_ms) - int(window_ms)
    first_slot_start_ms = score_start_ms - BASELINE_SLOT_COUNT * int(window_ms)
    counts: list[int] = []
    for slot_index in range(BASELINE_SLOT_COUNT):
        slot_start_ms = first_slot_start_ms + slot_index * int(window_ms)
        slot_end_ms = slot_start_ms + int(window_ms)
        counts.append(
            len(
                {
                    str(row["event_id"])
                    for row in context
                    if slot_start_ms <= int(row.get("received_at_ms") or 0) < slot_end_ms
                }
            )
        )
    return counts


def _quality_features(window: list[dict[str, Any]], *, diffusion: dict[str, Any]) -> dict[str, Any]:
    mentions = max(1, len({str(row["event_id"]) for row in window}))
    post_scores = [_post_score(row) for row in window]
    duplicate_share = float(diffusion.get("duplicate_text_share") or 0.0)
    text_features = [post_text_features(str(row.get("text") or row.get("text_clean") or "")) for row in window]
    informative_count = sum(1 for item in text_features if item.get("informative"))
    market_context_count = sum(1 for item in text_features if item.get("has_market_context"))
    llm_utility_values = [v for row in window if (v := _llm_utility(row)) is not None]
    llm_confidence_values = [
        float(row["llm_label_confidence"]) for row in window if row.get("llm_label_confidence") is not None
    ]
    llm_semantic_utility = sum(llm_utility_values) / len(llm_utility_values) if llm_utility_values else None
    llm_label_confidence = sum(llm_confidence_values) / len(llm_confidence_values) if llm_confidence_values else None
    return {
        "mentions": mentions,
        "direct_mentions": mentions,
        "avg_attribution_confidence": sum(_confidence(row) for row in window) / max(1, len(window)),
        "duplicate_text_share": duplicate_share,
        "informative_post_count": informative_count,
        "watched_source_count": sum(1 for row in window if row.get("is_watched")),
        "market_context_count": market_context_count,
        "avg_post_quality": round(sum(post_scores) / max(1, len(post_scores))),
        "llm_semantic_utility": llm_semantic_utility,
        "llm_label_confidence": llm_label_confidence,
        "diffusion_status": diffusion.get("status"),
        "diffusion_score": diffusion.get("score"),
        "diffusion_risks": diffusion.get("risks") or [],
    }


def _propagation_features(
    *,
    window: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    window_ms: int,
    diffusion: dict[str, Any],
) -> dict[str, Any]:
    authors = [str(row.get("author_handle") or "") for row in window if row.get("author_handle")]
    previous_authors = {str(row.get("author_handle") or "") for row in previous if row.get("author_handle")}
    counts = Counter(authors)
    mentions = len({str(row["event_id"]) for row in window})
    independent = len(counts)
    bucket_count = max(1, math.ceil(window_ms / (5 * 60_000)))
    active_buckets = len(
        {int(row.get("received_at_ms") or 0) // (5 * 60_000) for row in window if row.get("received_at_ms") is not None}
    )
    return {
        "mentions": mentions,
        "independent_authors": independent,
        "effective_authors": diffusion.get("effective_authors"),
        "source_weighted_effective_authors": source_weighted_effective_authors(window),
        "time_to_second_author_ms": time_to_nth_independent_author_ms(window, 2),
        "time_to_third_author_ms": time_to_nth_independent_author_ms(window, 3),
        "public_followup_author_count": public_followup_author_count(window),
        "author_entropy": author_entropy(window),
        "new_authors": len(set(authors) - previous_authors),
        "top_author_share": diffusion.get("top_author_share"),
        "duplicate_text_share": diffusion.get("duplicate_text_share"),
        "watched_author_count": len({str(row.get("author_handle")) for row in window if row.get("is_watched")}),
        "seed_lag_ms": None,
        "watch_status": "seed_linked" if any(row.get("is_watched") for row in window) else "public_only",
        "reproduction_rate": active_buckets / bucket_count,
        "phase_hint": None,
        "top_authors": diffusion.get("top_authors") or [],
    }


def _tradeability_features(row: dict[str, Any]) -> dict[str, Any]:
    target_type = str(row.get("target_type") or "")
    market_status = str(row.get("market_status") or row.get("market_observation_status") or "missing")
    if target_type == "CexToken":
        return {
            "target_type": "CexToken",
            "identity_status": "resolved_cex" if row.get("target_id") else "unresolved",
            "token_id": row.get("target_id"),
            "pricefeed_id": row.get("pricefeed_id"),
            "native_market_id": row.get("native_market_id"),
            "market_status": market_status,
            "volume_24h": row.get("market_volume_24h_usd"),
            "open_interest": row.get("market_open_interest_usd"),
        }
    return {
        "target_type": "Asset",
        "identity_status": "resolved_ca" if row.get("target_id") else "unresolved",
        "token_id": row.get("target_id"),
        "chain": row.get("asset_chain_id"),
        "address": row.get("asset_address"),
        "market_status": market_status,
        "market_cap": row.get("market_market_cap_usd"),
        "liquidity": row.get("market_liquidity_usd"),
        "pool_status": "ready" if row.get("pricefeed_id") or row.get("asset_address") else "missing",
    }


def _latest_market_row(window: list[dict[str, Any]]) -> dict[str, Any]:
    if not window:
        return {}
    return max(window, key=lambda row: int(row.get("received_at_ms") or 0))


def _with_source_weight(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "_source_weight": _atomic_quality(row) * _confidence(row)}


def _post_score(row: dict[str, Any]) -> int:
    score = post_quality_score(
        {
            "text": row.get("text") or row.get("text_clean"),
            "mention_source": row.get("primary_evidence_source") or row.get("mention_source") or "token_intent",
            "attribution_status": "direct",
            "attribution_confidence": _confidence(row),
            "attribution_weight": _confidence(row),
            "is_watched": bool(row.get("is_watched")),
        }
    )
    return int(score.get("score") or 0)


def _confidence(row: dict[str, Any]) -> float:
    return mention_confidence_from_status(row.get("resolution_status"))


def _atomic_quality(row: dict[str, Any]) -> float:
    return tweet_quality(
        gmgn_platform_followers=_int_or_none(row.get("gmgn_platform_followers")),
        ws_author_followers=_int_or_none(row.get("ws_author_followers")) or _int_or_none(row.get("author_followers")),
        user_tags=row.get("gmgn_user_tags") or (),
        first_seen_age_ms=_age_ms(
            row.get("account_profile_first_seen_ms"),
            row.get("received_at_ms"),
        ),
    )


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _age_ms(first_seen_ms: Any, received_at_ms: Any) -> int:
    received = _int_or_none(received_at_ms)
    if received is None:
        return 0
    first = _int_or_none(first_seen_ms)
    if first is None:
        # No profile data → treat as mature; tag/follower floors still apply
        return _SATURATED_AGE_MS
    return max(0, received - first)


def _llm_utility(row: dict[str, Any]) -> float | None:
    novelty = row.get("llm_semantic_novelty_hint")
    impact = row.get("llm_impact_hint")
    if novelty is None or impact is None:
        return None
    try:
        return max(0.0, min(1.0, 0.5 * float(novelty) + 0.5 * float(impact)))
    except (TypeError, ValueError):
        return None
