from __future__ import annotations

import math
from typing import Any

from gmgn_twitter_intel.domains.token_intel.scoring.scoring_common import (
    clamp_score,
    log_points,
    ratio_points,
    safe_float,
)

TOKEN_FACTOR_SNAPSHOT_VERSION = "token_factor_snapshot_v1"
FACTOR_FAMILIES = (
    "identity",
    "social_attention",
    "social_quality",
    "social_semantics",
    "market_quality",
    "timing",
)

DEX_HIGH_ALERT_FLOORS = {
    "holders": 100,
    "liquidity_usd": 25_000.0,
    "market_cap_usd": 50_000.0,
    "unique_authors": 3,
    "duplicate_text_share": 0.50,
}

_DEX_FLOOR_REASONS = {
    "holders": "holders_below_high_alert_floor",
    "liquidity_usd": "liquidity_below_high_alert_floor",
    "market_cap_usd": "market_cap_below_high_alert_floor",
}


def build_token_factor_snapshot(
    *,
    target: dict[str, Any],
    attention: dict[str, Any],
    social_quality: dict[str, Any],
    social_semantics: dict[str, Any],
    market: dict[str, Any],
    timing: dict[str, Any],
    source_event_ids: list[str],
    computed_at_ms: int,
) -> dict[str, Any]:
    families = {
        "identity": _identity_family(target=target),
        "social_attention": _social_attention_family(attention=attention),
        "social_quality": _social_quality_family(social_quality=social_quality),
        "social_semantics": _social_semantics_family(social_semantics=social_semantics),
        "market_quality": _market_quality_family(target=target, market=market),
        "timing": _timing_family(timing=timing),
    }
    hard_gates = _hard_gates(families=families)
    composite = _composite(families=families, hard_gates=hard_gates)
    return {
        "schema_version": TOKEN_FACTOR_SNAPSHOT_VERSION,
        "subject": _subject(target),
        "families": families,
        "hard_gates": hard_gates,
        "composite": composite,
        "provenance": {
            "source_event_ids": _dedupe_strings(source_event_ids),
            "computed_at_ms": _computed_at_ms(computed_at_ms),
        },
    }


def _identity_family(*, target: dict[str, Any]) -> dict[str, Any]:
    facts = {
        "target_type": _optional_str(target.get("target_type")),
        "target_id": _optional_str(target.get("target_id")),
        "symbol": _optional_str(target.get("symbol")),
        "chain": _optional_str(target.get("chain") or target.get("asset_chain_id")),
        "address": _optional_str(target.get("address") or target.get("asset_address")),
    }
    return _family(
        "identity",
        facts=facts,
        factors=[
            _presence_factor("identity", "target_id", facts["target_id"]),
            _presence_factor("identity", "target_type", facts["target_type"]),
            _presence_factor("identity", "symbol", facts["symbol"]),
        ],
    )


def _social_attention_family(*, attention: dict[str, Any]) -> dict[str, Any]:
    facts = {
        "mentions_5m": _optional_int(attention.get("mentions_5m")),
        "mentions_1h": _count_int(attention.get("mentions_1h")),
        "mentions_4h": _count_int(attention.get("mentions_4h")),
        "mentions_24h": _count_int(attention.get("mentions_24h")),
        "unique_authors": _count_int(attention.get("unique_authors")),
        "watched_mentions": _count_int(attention.get("watched_mentions")),
        "latest_seen_ms": _optional_int(attention.get("latest_seen_ms")),
    }
    return _family(
        "social_attention",
        facts=facts,
        factors=[
            _count_factor("social_attention", "mentions_1h", facts["mentions_1h"], scale=10),
            _count_factor("social_attention", "mentions_4h", facts["mentions_4h"], scale=20),
            _count_factor("social_attention", "mentions_24h", facts["mentions_24h"], scale=40),
            _count_factor("social_attention", "unique_authors", facts["unique_authors"], scale=10),
            _count_factor("social_attention", "watched_mentions", facts["watched_mentions"], scale=3),
        ],
    )


def _social_quality_family(*, social_quality: dict[str, Any]) -> dict[str, Any]:
    duplicate_text_share = _optional_float(social_quality.get("duplicate_text_share"))
    duplicate_risk = (
        ["duplicate_text_share_high"]
        if _is_at_or_above(duplicate_text_share, "duplicate_text_share")
        else []
    )
    facts = {
        "duplicate_text_share": duplicate_text_share,
        "informative_post_count": _count_int(social_quality.get("informative_post_count")),
        "mentions": _count_int(social_quality.get("mentions")),
        "independent_authors": _count_int(social_quality.get("independent_authors")),
    }
    return _family(
        "social_quality",
        facts=facts,
        factors=[
            _factor_point(
                "social_quality",
                "duplicate_text_share",
                raw_value=duplicate_text_share,
                score=0.0 if duplicate_text_share is None else 100.0 - duplicate_text_share * 100.0,
                risk_flags=duplicate_risk,
                hard_gate="block_high_alert" if duplicate_risk else None,
            ),
            _count_factor("social_quality", "informative_post_count", facts["informative_post_count"], scale=8),
            _count_factor("social_quality", "independent_authors", facts["independent_authors"], scale=10),
            _count_factor("social_quality", "mentions", facts["mentions"], scale=20),
        ],
    )


def _social_semantics_family(*, social_semantics: dict[str, Any]) -> dict[str, Any]:
    direction_counts = _count_map(social_semantics.get("direction_counts"))
    impact_mean = _optional_float(social_semantics.get("impact_mean"))
    novelty_mean = _optional_float(social_semantics.get("novelty_mean"))
    confidence_mean = _optional_float(social_semantics.get("confidence_mean"))
    facts = {
        "direction_counts": direction_counts,
        "impact_mean": impact_mean,
        "novelty_mean": novelty_mean,
        "confidence_mean": confidence_mean,
    }
    return _family(
        "social_semantics",
        facts=facts,
        factors=[
            _ratio_factor("social_semantics", "impact_mean", impact_mean),
            _ratio_factor("social_semantics", "novelty_mean", novelty_mean),
            _ratio_factor("social_semantics", "confidence_mean", confidence_mean),
            _direction_factor(facts["direction_counts"]),
        ],
    )


def _market_quality_family(*, target: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    target_market_type = _target_market_type(target)
    facts = {
        "target_market_type": target_market_type,
        "market_status": _optional_str(market.get("market_status") or market.get("market_observation_status")),
        "holders": _optional_int(market.get("holders")),
        "liquidity_usd": _optional_float(market.get("liquidity_usd")),
        "market_cap_usd": _optional_float(market.get("market_cap_usd")),
        "volume_24h_usd": _optional_float(market.get("volume_24h_usd")),
        "open_interest_usd": _optional_float(market.get("open_interest_usd")),
        "native_market_id": _optional_str(market.get("native_market_id")),
    }
    if target_market_type == "cex":
        factors = [
            _market_status_factor(facts["market_status"]),
            _count_factor("market_quality", "volume_24h_usd", facts["volume_24h_usd"], scale=5_000_000),
            _count_factor("market_quality", "open_interest_usd", facts["open_interest_usd"], scale=2_000_000),
            _presence_factor("market_quality", "native_market_id", facts["native_market_id"]),
        ]
    else:
        factors = [
            _market_status_factor(facts["market_status"]),
            _dex_market_factor("holders", facts["holders"]),
            _dex_market_factor("liquidity_usd", facts["liquidity_usd"]),
            _dex_market_factor("market_cap_usd", facts["market_cap_usd"]),
        ]
    return _family(
        "market_quality",
        facts=facts,
        factors=factors,
        target_market_type=target_market_type,
    )


def _timing_family(*, timing: dict[str, Any]) -> dict[str, Any]:
    facts = {
        "price_change_before_social_pct": _optional_float(timing.get("price_change_before_social_pct")),
        "price_change_since_social_pct": _optional_float(timing.get("price_change_since_social_pct")),
        "social_signal_start_ms": _optional_int(timing.get("social_signal_start_ms")),
    }
    return _family(
        "timing",
        facts=facts,
        factors=[
            _timing_change_factor("price_change_before_social_pct", facts["price_change_before_social_pct"]),
            _timing_change_factor("price_change_since_social_pct", facts["price_change_since_social_pct"]),
            _presence_factor("timing", "social_signal_start_ms", facts["social_signal_start_ms"], confidence=0.8),
        ],
    )


def _hard_gates(*, families: dict[str, dict[str, Any]]) -> dict[str, Any]:
    identity_facts = families["identity"]["facts"]
    market_facts = families["market_quality"]["facts"]
    attention_facts = families["social_attention"]["facts"]
    quality_facts = families["social_quality"]["facts"]
    reasons: list[str] = []
    if _identity_unresolved(identity_facts):
        reasons.append("identity_unresolved")
    if freshness_reason := _market_freshness_block_reason(market_facts.get("market_status")):
        reasons.append(freshness_reason)
    if families["market_quality"]["target_market_type"] == "dex":
        for key, reason in _DEX_FLOOR_REASONS.items():
            if _is_below(market_facts.get(key), key):
                reasons.append(reason)
    independent_sources = max(
        _count_int(attention_facts.get("unique_authors")),
        _count_int(quality_facts.get("independent_authors")),
    )
    watched_mentions = _count_int(attention_facts.get("watched_mentions"))
    if independent_sources < DEX_HIGH_ALERT_FLOORS["unique_authors"] and watched_mentions <= 0:
        reasons.append("insufficient_independent_social_sources")
    if _is_at_or_above(quality_facts.get("duplicate_text_share"), "duplicate_text_share"):
        reasons.append("duplicate_text_share_high")
    blocked_reasons = _dedupe_strings(reasons)
    return {
        "eligible_for_high_alert": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
        "gates": [
            {"reason": reason, "action": "block_high_alert"}
            for reason in blocked_reasons
        ],
    }


def _identity_unresolved(identity_facts: dict[str, Any]) -> bool:
    target_type = str(identity_facts.get("target_type") or "").lower()
    target_id = str(identity_facts.get("target_id") or "")
    return not target_type or not target_id or target_type in {"source_seed", "sourceseed", "unresolved"}


def _market_freshness_block_reason(market_status: Any) -> str | None:
    status = str(market_status or "").lower()
    if status in {"fresh", "ready"}:
        return None
    if status in {"", "missing", "missing_market", "none", "null"}:
        return "market_freshness_missing"
    return "market_freshness_stale"


def _composite(*, families: dict[str, dict[str, Any]], hard_gates: dict[str, Any]) -> dict[str, Any]:
    family_scores = {family: _count_int(families[family]["score"]) for family in FACTOR_FAMILIES}
    rank_score = round(sum(family_scores.values()) / len(FACTOR_FAMILIES))
    if hard_gates["blocked_reasons"]:
        return {
            "family_scores": family_scores,
            "rank_score": min(rank_score, 20),
            "recommended_decision": "discard",
        }
    if rank_score >= 70:
        decision = "high_alert"
    elif rank_score >= 40:
        decision = "watch"
    else:
        decision = "discard"
    return {
        "family_scores": family_scores,
        "rank_score": rank_score,
        "recommended_decision": decision,
    }


def _family(
    family: str,
    *,
    facts: dict[str, Any],
    factors: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    factor_map = {str(factor["key"]): factor for factor in factors}
    payload = {
        "family": family,
        "score": _average_score([_count_int(factor["score"]) for factor in factors]),
        "data_health": _family_data_health(factors),
        "facts": facts,
        "factors": factor_map,
    }
    payload.update(extra)
    return payload


def _factor_point(
    family: str,
    key: str,
    *,
    raw_value: Any,
    score: float,
    confidence: float = 0.95,
    data_health: str | None = None,
    freshness_ms: int | None = None,
    source_refs: list[str] | None = None,
    risk_flags: list[str] | None = None,
    hard_gate: str | None = None,
) -> dict[str, Any]:
    health = data_health or ("missing" if raw_value is None else "ready")
    return {
        "family": family,
        "key": key,
        "raw_value": raw_value,
        "score": clamp_score(_finite_score(score)),
        "confidence": round(max(0.0, min(1.0, float(confidence))), 4),
        "data_health": health,
        "freshness_ms": freshness_ms,
        "source_refs": _dedupe_strings(source_refs or []),
        "risk_flags": _dedupe_strings(risk_flags or []),
        "hard_gate": hard_gate,
    }


def _family_data_health(factors: list[dict[str, Any]]) -> str:
    health_values = {str(factor.get("data_health") or "missing") for factor in factors}
    if not health_values or health_values == {"missing"}:
        return "missing"
    if health_values == {"ready"}:
        return "ready"
    return "partial"


def _finite_score(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(parsed):
        return 0.0
    return parsed


def _presence_factor(family: str, key: str, value: Any, *, confidence: float = 0.95) -> dict[str, Any]:
    return _factor_point(
        family,
        key,
        raw_value=value,
        score=100 if value not in (None, "") else 0,
        confidence=confidence,
    )


def _count_factor(family: str, key: str, value: Any, *, scale: float) -> dict[str, Any]:
    return _factor_point(
        family,
        key,
        raw_value=value,
        score=log_points(safe_float(value), scale=scale, max_points=100.0),
        confidence=0.95 if value is not None else 0.0,
    )


def _ratio_factor(family: str, key: str, value: float | None) -> dict[str, Any]:
    return _factor_point(
        family,
        key,
        raw_value=value,
        score=ratio_points(safe_float(value), max_ratio=1.0, max_points=100.0),
        confidence=0.9 if value is not None else 0.0,
    )


def _direction_factor(direction_counts: dict[str, Any]) -> dict[str, Any]:
    total = sum(_count_int(value) for value in direction_counts.values())
    bullish = _count_int(direction_counts.get("bullish"))
    neutral = _count_int(direction_counts.get("neutral"))
    score = 0.0
    if total > 0:
        score = (bullish + neutral * 0.5) / total * 100.0
    return _factor_point(
        "social_semantics",
        "direction_counts",
        raw_value=direction_counts,
        score=score,
        confidence=0.85 if total > 0 else 0.0,
    )


def _market_status_factor(market_status: str | None) -> dict[str, Any]:
    score_by_status = {
        "fresh": 100,
        "ready": 100,
        "stale": 45,
        "missing": 0,
        "missing_market": 0,
    }
    status = (market_status or "missing").lower()
    return _factor_point(
        "market_quality",
        "market_status",
        raw_value=market_status,
        score=score_by_status.get(status, 50),
        confidence=0.95 if market_status else 0.0,
    )


def _dex_market_factor(key: str, value: Any) -> dict[str, Any]:
    risk_flags = [_DEX_FLOOR_REASONS[key]] if _is_below(value, key) else []
    floor = safe_float(DEX_HIGH_ALERT_FLOORS[key])
    return _factor_point(
        "market_quality",
        key,
        raw_value=value,
        score=ratio_points(safe_float(value), max_ratio=floor * 4.0, max_points=100.0),
        confidence=0.95 if value is not None else 0.0,
        risk_flags=risk_flags,
        hard_gate="block_high_alert" if risk_flags else None,
    )


def _timing_change_factor(key: str, value: float | None) -> dict[str, Any]:
    score = 0.0 if value is None else 100.0 - min(100.0, abs(value) * 500.0)
    return _factor_point(
        "timing",
        key,
        raw_value=value,
        score=score,
        confidence=0.8 if value is not None else 0.0,
    )


def _subject(target: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_type": _optional_str(target.get("target_type")),
        "target_id": _optional_str(target.get("target_id")),
        "symbol": _optional_str(target.get("symbol")),
        "chain": _optional_str(target.get("chain") or target.get("asset_chain_id")),
        "address": _optional_str(target.get("address") or target.get("asset_address")),
        "target_market_type": _target_market_type(target),
    }


def _target_market_type(target: dict[str, Any]) -> str:
    target_type = str(target.get("target_type") or "").lower()
    target_id = str(target.get("target_id") or "").lower()
    if target_type in {"cextoken", "cex_token"} or target_id.startswith("cex_token:"):
        return "cex"
    return "dex"


def _is_below(value: Any, floor_key: str) -> bool:
    if value is None:
        return True
    return safe_float(value) < safe_float(DEX_HIGH_ALERT_FLOORS[floor_key])


def _is_at_or_above(value: Any, floor_key: str) -> bool:
    if value is None:
        return False
    return safe_float(value) >= safe_float(DEX_HIGH_ALERT_FLOORS[floor_key])


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _optional_int(value: Any) -> int | None:
    parsed = _finite_number(value)
    if parsed is None:
        return None
    return int(parsed)


def _count_int(value: Any, default: int = 0) -> int:
    parsed = _finite_number(value)
    if parsed is None:
        return default
    return int(parsed)


def _count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _count_int(item) for key, item in value.items()}


def _computed_at_ms(value: Any) -> int:
    parsed = _finite_number(value)
    if parsed is None:
        return 0
    return int(parsed)


def _finite_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _average_score(scores: list[int]) -> int:
    if not scores:
        return 0
    return clamp_score(sum(scores) / len(scores))


def _dedupe_strings(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value is not None and str(value)))
