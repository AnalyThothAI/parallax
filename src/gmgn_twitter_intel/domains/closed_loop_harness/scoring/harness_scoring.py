from __future__ import annotations


def base_event_score(*, direction: int, impact: float, confidence: float, novelty: float, pricedness: float) -> float:
    sign = 1 if direction > 0 else -1 if direction < 0 else 0
    return sign * _clamp(impact) * _clamp(confidence) * _clamp(novelty) * (1 - _clamp(pricedness))


def price_move_penalty(*, pre_move: float, recent_vol: float) -> float:
    threshold = max(abs(recent_vol) * 1.5, 1e-9)
    if abs(pre_move) <= threshold:
        return 1.0
    return max(0.2, 1 - abs(pre_move) / max(abs(recent_vol) * 4, 1e-9))


def event_score(
    base_score: float,
    *,
    source_weight: float,
    event_type_weight: float,
    horizon_weight: float,
    time_decay: float,
    price_penalty: float,
) -> float:
    return base_score * source_weight * event_type_weight * horizon_weight * time_decay * price_penalty


def combined_score(event_scores: list[float]) -> float:
    return round(sum(event_scores), 12)


def policy_signal(score: float, *, long_threshold: float, short_threshold: float) -> str:
    if score >= long_threshold:
        return "LONG"
    if score <= short_threshold:
        return "SHORT_OR_AVOID"
    return "NO_TRADE"


def shadow_signal(score: float, *, long_threshold: float, short_threshold: float) -> str:
    if score >= long_threshold:
        return "LONG_SMALL"
    if score <= short_threshold:
        return "SHORT_SMALL"
    return "NO_TRADE"


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))
