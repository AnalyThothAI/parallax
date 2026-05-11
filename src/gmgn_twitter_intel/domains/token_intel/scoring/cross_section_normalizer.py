"""Per-window cross-sectional rank normalization within an active cohort."""

from __future__ import annotations

NORMALIZER_VERSION = "cross_section_v1"


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
