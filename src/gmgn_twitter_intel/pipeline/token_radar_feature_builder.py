from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ..retrieval.baseline_scoring import token_baseline_v2
from ..retrieval.post_text_quality import post_quality_score, post_text_features

BASELINE_SLOT_COUNT = 6


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
    window = list(window_rows)
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
    quality = _quality_features(window)
    propagation = _propagation_features(window=window, previous=previous, window_ms=window_ms)
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
    weighted_mentions = sum(_confidence(row) for row in window)
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
        "mention_delta_pct": mention_delta / max(previous_mentions, 1) if previous_mentions else None,
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


def _quality_features(window: list[dict[str, Any]]) -> dict[str, Any]:
    mentions = max(1, len({str(row["event_id"]) for row in window}))
    post_scores = [_post_score(row) for row in window]
    texts = [str(row.get("text_clean") or row.get("text") or "").strip().lower() for row in window]
    duplicate_share = _duplicate_share(texts)
    text_features = [post_text_features(str(row.get("text") or row.get("text_clean") or "")) for row in window]
    informative_count = sum(1 for item in text_features if item.get("informative"))
    market_context_count = sum(1 for item in text_features if item.get("has_market_context"))
    return {
        "mentions": mentions,
        "direct_mentions": mentions,
        "avg_attribution_confidence": sum(_confidence(row) for row in window) / max(1, len(window)),
        "duplicate_text_share": duplicate_share,
        "informative_post_count": informative_count,
        "watched_source_count": sum(1 for row in window if row.get("is_watched")),
        "market_context_count": market_context_count,
        "avg_post_quality": round(sum(post_scores) / max(1, len(post_scores))),
    }


def _propagation_features(
    *,
    window: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    window_ms: int,
) -> dict[str, Any]:
    authors = [str(row.get("author_handle") or "") for row in window if row.get("author_handle")]
    previous_authors = {str(row.get("author_handle") or "") for row in previous if row.get("author_handle")}
    counts = Counter(authors)
    mentions = len({str(row["event_id"]) for row in window})
    independent = len(counts)
    top_share = max(counts.values(), default=0) / max(1, len(authors))
    duplicate_share = _duplicate_share([str(row.get("text_clean") or row.get("text") or "") for row in window])
    bucket_count = max(1, math.ceil(window_ms / (5 * 60_000)))
    active_buckets = len(
        {
            int(row.get("received_at_ms") or 0) // (5 * 60_000)
            for row in window
            if row.get("received_at_ms") is not None
        }
    )
    return {
        "mentions": mentions,
        "independent_authors": independent,
        "effective_authors": independent * max(0.0, 1.0 - duplicate_share),
        "new_authors": len(set(authors) - previous_authors),
        "top_author_share": top_share,
        "duplicate_text_share": duplicate_share,
        "watched_author_count": len({str(row.get("author_handle")) for row in window if row.get("is_watched")}),
        "seed_lag_ms": None,
        "watch_status": "seed_linked" if any(row.get("is_watched") for row in window) else "public_only",
        "reproduction_rate": active_buckets / bucket_count,
        "phase_hint": None,
        "top_authors": [{"author_handle": author, "mentions": count} for author, count in counts.most_common(3)],
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
    try:
        return float(row.get("intent_confidence") or row.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _duplicate_share(texts: list[str]) -> float:
    normalized = [text for text in (str(item).strip().lower() for item in texts) if text]
    if len(normalized) < 2:
        return 0.0
    counts = Counter(normalized)
    duplicates = sum(count - 1 for count in counts.values() if count > 1)
    return round(duplicates / len(normalized), 6)
