"""Per-window cross-sectional rank normalization within an active cohort."""

from __future__ import annotations

NORMALIZER_VERSION = "cross_section_v2_factor_ranks"


def rank_within_cohort(
    *,
    scores: dict[str, float | None],
    cohort: set[str],
) -> dict[str, float | None]:
    rankable = [(token_id, score) for token_id, score in scores.items() if token_id in cohort and score is not None]
    out: dict[str, float | None] = {token_id: None for token_id in scores}
    if not rankable:
        return out
    rankable.sort(key=lambda pair: pair[1])
    n = len(rankable)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and rankable[j + 1][1] == rankable[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        percentile = avg_rank / n
        for k in range(i, j + 1):
            out[rankable[k][0]] = percentile
        i = j + 1
    return out


def rank_factors_within_cohort(
    *,
    factor_scores: dict[str, dict[str, float | None]],
    cohort: set[str],
) -> dict[str, dict[str, float | None]]:
    factor_names = sorted({factor for scores in factor_scores.values() for factor in scores})
    out: dict[str, dict[str, float | None]] = {
        token_id: {factor: None for factor in factor_names} for token_id in factor_scores
    }
    for factor in factor_names:
        ranks = rank_within_cohort(
            scores={token_id: scores.get(factor) for token_id, scores in factor_scores.items()},
            cohort=cohort,
        )
        for token_id, rank in ranks.items():
            out.setdefault(token_id, {name: None for name in factor_names})[factor] = rank
    return out


def weighted_rank_score(
    factor_ranks: dict[str, float | None],
    weights: dict[str, float],
) -> float | None:
    available = [
        (factor, rank)
        for factor, rank in factor_ranks.items()
        if rank is not None and float(weights.get(factor) or 0.0) > 0.0
    ]
    if not available:
        return None
    total_weight = sum(float(weights.get(factor) or 0.0) for factor, _rank in available)
    if total_weight <= 0.0:
        return None
    score = sum(float(rank) * float(weights.get(factor) or 0.0) for factor, rank in available) / total_weight
    return round(score, 6)
